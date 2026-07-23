"""Stateless runtime boundary for one persisted direct order schedule."""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import Awaitable, Callable, Coroutine
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, Protocol
from uuid import NAMESPACE_URL, uuid5

from halpha.capital.checks import effective_leverage
from halpha.capital.models import ActionCheckInput, AuthorityClass, EnvironmentKind
from halpha.domain_values import canonical_decimal
from halpha.executor.product_entry import (
    DirectScheduleFacts,
    ProductAccountFacts,
)
from halpha.executor.responsibilities import ProductRiskReductionFacts
from halpha.planning.models import PlanActivation, PlanLifecycle, RunState
from halpha.planning.order_policies import (
    CancelOnShockRule,
    ConditionResult,
    ExpireRemainingRule,
    PriceMoveBpsCondition,
    evaluate_condition_group,
)
from halpha.planning.order_schedule import (
    BINANCE_GTD_MIN_LEAD_SECONDS,
    ScheduleSubmissionMode,
)
from halpha.planning.order_schedule_actions import (
    MaterializedOrderLeg,
    materialize_direct_schedule,
)
from halpha.planning.registry import DIRECT_EXECUTION_REF, Direction
from halpha.venue_integration.facts import (
    order_is_working,
    terminal_fills_complete,
    terminal_order_status,
)
from halpha.venue_integration.models import (
    ExecutionAction,
    ExecutionActionKind,
    ExecutionActionState,
    VenueFact,
    VenueFactKind,
)


class DirectScheduleCoordinator(Protocol):
    def get_activation_snapshot(self, activation_id: str) -> PlanActivation: ...

    def expire_empty_entry_window(
        self,
        *,
        activation_id: str,
        observed_at: datetime,
    ) -> tuple[PlanActivation, Any]: ...

    def list_execution_actions(
        self,
        activation_id: str,
    ) -> tuple[ExecutionAction, ...]: ...

    def list_venue_facts_for_action(
        self,
        execution_action_id: str,
    ) -> tuple[VenueFact, ...]: ...

    def consume_order_schedule_atomic(self, **kwargs: Any) -> tuple[Any, ...]: ...

    def process_execution_action(
        self,
        execution_action_id: str,
        **kwargs: Any,
    ) -> Any: ...

    def reconcile_execution_action(
        self,
        execution_action_id: str,
        **kwargs: Any,
    ) -> ExecutionAction: ...

    def reject_execution_action_before_submission(
        self,
        execution_action_id: str,
        **kwargs: Any,
    ) -> ExecutionAction: ...

    def create_cancel_for_action(self, **kwargs: Any) -> Any: ...


DirectFactProvider = Callable[
    [
        PlanActivation,
        MaterializedOrderLeg,
        frozenset[str],
        frozenset[str],
        str,
        str,
        str,
        dict[int, str],
    ],
    Awaitable[DirectScheduleFacts],
]
RiskReductionFactProvider = Callable[
    [PlanActivation], Awaitable[ProductRiskReductionFacts]
]
FailureSink = Callable[[str, BaseException], None]


MAX_PRICE_MOVE_LATEST_AGE_NS = 3_000_000_000


class DirectPriceMoveTracker:
    """Keep only a bounded in-memory mark window; restart begins UNKNOWN."""

    def __init__(self) -> None:
        self._marks: deque[tuple[int, Decimal]] = deque()

    def record_mark(self, update: object) -> None:
        try:
            timestamp = int(getattr(update, "ts_event"))
            value = Decimal(str(getattr(update, "value")))
        except (AttributeError, TypeError, ValueError):
            return
        if timestamp <= 0 or value <= 0:
            return
        if self._marks and timestamp <= self._marks[-1][0]:
            return
        self._marks.append((timestamp, value))
        cutoff = timestamp - 310_000_000_000
        while self._marks and self._marks[0][0] < cutoff:
            self._marks.popleft()

    def moves(
        self,
        windows: frozenset[int],
        *,
        cutoff_ns: int,
    ) -> dict[int, str]:
        if not self._marks:
            return {}
        latest_ts, latest = self._marks[-1]
        latest_age = cutoff_ns - latest_ts
        if latest_age < 0 or latest_age > MAX_PRICE_MOVE_LATEST_AGE_NS:
            return {}
        results: dict[int, str] = {}
        samples = tuple(self._marks)
        for window in windows:
            target = latest_ts - window * 1_000_000_000
            candidates = tuple(item for item in samples if item[0] <= target)
            if not candidates:
                continue
            start_ts, start = candidates[-1]
            relevant = tuple(item for item in samples if item[0] >= start_ts)
            maximum_gap = max(
                (
                    right[0] - left[0]
                    for left, right in zip(relevant, relevant[1:])
                ),
                default=0,
            )
            allowed_gap = max(3, min(window, 15)) * 1_000_000_000
            if target - start_ts > allowed_gap or maximum_gap > allowed_gap:
                continue
            results[window] = canonical_decimal(
                (latest - start) / start * Decimal(10_000)
            )
        return results

    def latest_source_time_ns(self, *, cutoff_ns: int) -> int | None:
        if not self._marks:
            return None
        latest_ts = self._marks[-1][0]
        age = cutoff_ns - latest_ts
        if age < 0 or age > MAX_PRICE_MOVE_LATEST_AGE_NS:
            return None
        return latest_ts


class DirectScheduleBoundary:
    """Reconstruct progress from snapshot, actions, and facts without a second FSM."""

    def __init__(
        self,
        *,
        loop: asyncio.AbstractEventLoop,
        coordinator: DirectScheduleCoordinator,
        fact_provider: DirectFactProvider,
        risk_reduction_fact_provider: RiskReductionFactProvider,
        environment_id: str,
        environment_kind: EnvironmentKind,
        authority_class: AuthorityClass,
        account_ref: str,
        submission_enabled: Callable[[], bool] | None = None,
        current_time_provider: Callable[[], datetime] | None = None,
        failure_sink: FailureSink | None = None,
    ) -> None:
        self._loop = loop
        self._coordinator = coordinator
        self._fact_provider = fact_provider
        self._risk_reduction_fact_provider = risk_reduction_fact_provider
        self._environment_id = environment_id
        self._environment_kind = environment_kind
        self._authority_class = authority_class
        self._account_ref = account_ref
        self._submission_enabled = submission_enabled or (lambda: True)
        self._current_time_provider = current_time_provider or (lambda: datetime.now(UTC))
        self._failure_sink = failure_sink
        self._tracker = DirectPriceMoveTracker()
        self._tasks: dict[str, asyncio.Task[None]] = {}

    def resume(self, activation_id: str) -> None:
        if not self._submission_enabled():
            return
        self._schedule(activation_id, self._advance(activation_id))

    def record_mark(self, activation_id: str, update: object) -> None:
        self._tracker.record_mark(update)
        if not self._submission_enabled():
            return
        self._schedule(activation_id, self._advance(activation_id))

    def _schedule(self, key: str, coroutine: Coroutine[Any, Any, None]) -> None:
        existing = self._tasks.get(key)
        if existing is not None and not existing.done():
            coroutine.close()
            return
        task = self._loop.create_task(coroutine)
        self._tasks[key] = task
        task.add_done_callback(
            lambda completed, activation_id=key: self._report_failure(
                activation_id,
                completed,
            )
        )

    def _report_failure(
        self,
        activation_id: str,
        task: asyncio.Task[None],
    ) -> None:
        if task.cancelled():
            return
        exception = task.exception()
        if exception is not None:
            if self._failure_sink is not None:
                self._failure_sink(activation_id, exception)
            self._loop.call_exception_handler(
                {
                    "message": "HALPHA_DIRECT_SCHEDULE_FAILED",
                    "exception": exception,
                    "task": task,
                }
            )

    async def _advance(self, activation_id: str) -> None:
        if not self._submission_enabled():
            return
        activation = self._coordinator.get_activation_snapshot(activation_id)
        if (
            activation.decision_basis_ref != DIRECT_EXECUTION_REF
            or activation.lifecycle is not PlanLifecycle.RUNNING
            or activation.run_state is not RunState.ACTIVE
        ):
            return
        entry_valid_until = _entry_valid_until(activation)
        legs = materialize_direct_schedule(
            activation,
            entry_valid_until=entry_valid_until,
        )
        snapshot = activation.order_schedule_snapshot
        if snapshot is None:
            raise ValueError("ORDER_SCHEDULE_SNAPSHOT_REQUIRED")
        if (
            snapshot.schedule_spec.submission_mode
            is ScheduleSubmissionMode.PREPROTECTED_PARALLEL
        ):
            # A persisted capability bit is not venue evidence. This runtime
            # path remains closed until a Demo-qualified pre-protection
            # implementation exists.
            raise ValueError("PREPROTECTED_PARALLEL_RUNTIME_NOT_QUALIFIED")
        actions = self._coordinator.list_execution_actions(activation_id)
        schedule_actions = _schedule_actions(actions, activation, legs)
        windows = _price_move_windows(activation)
        now = self._current_time_provider()
        if now.utcoffset() is None:
            raise ValueError("DIRECT_SCHEDULE_TIMEZONE_REQUIRED")
        now = now.astimezone(UTC)
        cutoff_ns = int(now.timestamp() * 1_000_000_000)
        if now >= entry_valid_until and not schedule_actions:
            self._coordinator.expire_empty_entry_window(
                activation_id=activation_id,
                observed_at=now,
            )
            return
        if not schedule_actions:
            facts = await self._facts_for_leg(
                activation,
                legs[0],
                actions,
                windows,
                cutoff_ns=cutoff_ns,
            )
            evaluation = evaluate_condition_group(
                snapshot.schedule_spec.entry_conditions,
                facts.conditions,
            )
            if evaluation.result is not ConditionResult.TRUE:
                return
            checks = tuple(
                _action_check_for_leg(
                    facts.account,
                    activation,
                    item,
                    economic_action_prior_notional=(
                        item.economic_action_prior_notional
                    ),
                    include_economic_prior_margin=True,
                    environment_id=self._environment_id,
                    environment_kind=self._environment_kind,
                    authority_class=self._authority_class,
                    account_ref=self._account_ref,
                )
                for item in legs
            )
            self._coordinator.consume_order_schedule_atomic(
                activation_id=activation_id,
                legs=legs,
                action_checks=checks,
                observed_at=facts.account.checked_at,
                condition_evidence={
                    "condition_group": snapshot.schedule_spec.entry_conditions.model_dump(
                        mode="json"
                    ),
                    "facts": facts.conditions.model_dump(mode="json"),
                    "evaluation": evaluation.model_dump(mode="json"),
                    "price_move_source_time_ns": self._tracker.latest_source_time_ns(
                        cutoff_ns=cutoff_ns
                    ),
                },
            )
            actions = self._coordinator.list_execution_actions(activation_id)
            schedule_actions = _schedule_actions(actions, activation, legs)

        risk_facts: ProductRiskReductionFacts | None = None
        if _has_terminal_open_entry(self._coordinator, actions):
            risk_facts = await self._risk_reduction_fact_provider(activation)
            _close_proven_entry_actions(
                self._coordinator,
                actions,
                risk_facts=risk_facts,
                risk_summary=_risk_summary(self._coordinator, activation, actions),
                observed_at=risk_facts.checked_at,
            )
        actions = self._coordinator.list_execution_actions(activation_id)
        schedule_actions = _schedule_actions(actions, activation, legs)
        cycle_closed = False
        cycle_status_unknown = False
        risk_reduction_seen = activation.has_entry_fill and _has_risk_reduction_fill(
            self._coordinator,
            actions,
        )
        if risk_reduction_seen:
            if risk_facts is None:
                risk_facts = await self._risk_reduction_fact_provider(activation)
            cycle_status_unknown = risk_facts.position_fact is None
            cycle_closed = not cycle_status_unknown and Decimal(
                risk_facts.current_abs_position
            ) == 0
        protection_unproven = _has_unprotected_open_entry_fill(
            self._coordinator,
            actions,
        )
        management = _entry_management_decision(
            activation,
            actions,
            schedule_actions,
            moves=self._tracker.moves(windows, cutoff_ns=cutoff_ns),
            observed_at=now,
            entry_valid_until=_remaining_valid_until(
                legs,
                schedule_actions,
                default=entry_valid_until,
            ),
            expire_anchor=_schedule_submission_started_at(schedule_actions),
            cycle_closed=cycle_closed,
            cycle_status_unknown=cycle_status_unknown,
            protection_unproven=protection_unproven,
        )
        handled, risk_facts = await self._apply_entry_management(
            activation,
            schedule_actions,
            management,
            observed_at=now,
            risk_facts=risk_facts,
        )
        if handled:
            return
        if any(
            action.state
            in {
                ExecutionActionState.SUBMITTING,
                ExecutionActionState.UNKNOWN,
                ExecutionActionState.OPEN,
            }
            for action in schedule_actions
        ):
            return
        by_id = {action.execution_action_id: action for action in schedule_actions}
        target: MaterializedOrderLeg | None = None
        for item in legs:
            action = by_id[item.execution_action_id]
            if action.state is ExecutionActionState.READY:
                target = item
                break
            if action.state not in {
                ExecutionActionState.CLOSED,
                ExecutionActionState.NOT_SUBMITTED,
            }:
                return
        if target is None:
            return
        facts = await self._facts_for_leg(
            activation,
            target,
            actions,
            windows,
            cutoff_ns=cutoff_ns,
        )
        refreshed_now = self._current_time_provider()
        if (
            refreshed_now.utcoffset() is None
            or facts.account.checked_at.utcoffset() is None
        ):
            raise ValueError("DIRECT_SCHEDULE_TIMEZONE_REQUIRED")
        refreshed_now = max(
            refreshed_now.astimezone(UTC),
            facts.account.checked_at.astimezone(UTC),
        )
        refreshed_cutoff_ns = int(refreshed_now.timestamp() * 1_000_000_000)
        actions = self._coordinator.list_execution_actions(activation_id)
        schedule_actions = _schedule_actions(actions, activation, legs)
        refreshed_by_id = {
            action.execution_action_id: action for action in schedule_actions
        }
        refreshed_target = refreshed_by_id.get(target.execution_action_id)
        if (
            refreshed_target is None
            or refreshed_target.state is not ExecutionActionState.READY
            or any(
                action.state
                in {
                    ExecutionActionState.SUBMITTING,
                    ExecutionActionState.UNKNOWN,
                    ExecutionActionState.OPEN,
                }
                for action in schedule_actions
            )
        ):
            return
        if not risk_reduction_seen and _has_risk_reduction_fill(
            self._coordinator,
            actions,
        ):
            # A new reduction fill arrived while account/condition facts were
            # awaited.  Its current position must be re-queried next cycle.
            return
        refreshed_moves = self._tracker.moves(
            windows,
            cutoff_ns=refreshed_cutoff_ns,
        )
        refreshed_management = _entry_management_decision(
            activation,
            actions,
            schedule_actions,
            moves=refreshed_moves,
            observed_at=refreshed_now,
            entry_valid_until=_remaining_valid_until(
                legs,
                schedule_actions,
                default=entry_valid_until,
            ),
            expire_anchor=_schedule_submission_started_at(schedule_actions),
            cycle_closed=cycle_closed,
            cycle_status_unknown=cycle_status_unknown,
            protection_unproven=_has_unprotected_open_entry_fill(
                self._coordinator,
                actions,
            ),
        )
        handled, risk_facts = await self._apply_entry_management(
            activation,
            schedule_actions,
            refreshed_management,
            observed_at=refreshed_now,
            risk_facts=risk_facts,
        )
        if handled:
            return
        current_evaluation = evaluate_condition_group(
            snapshot.schedule_spec.entry_conditions,
            facts.conditions.model_copy(
                update={"price_move_bps_by_window": refreshed_moves}
            ),
        )
        if current_evaluation.result is not ConditionResult.TRUE:
            # Materializing all local legs records the original entry
            # opportunity.  Each later external risk request still needs the
            # current direct-execution conditions to be true; stale or unknown
            # market facts keep the READY responsibility dormant.
            return
        policy = target.proposed_action.execution_context["venue_policy"]
        if _gtd_expiry_too_soon(policy, observed_at=refreshed_now):
            for action in schedule_actions:
                if action.state is ExecutionActionState.READY:
                    self._coordinator.reject_execution_action_before_submission(
                        action.execution_action_id,
                        reason_code="DIRECT_GTD_EXPIRY_TOO_SOON",
                        observed_at=refreshed_now,
                    )
            return
        check = _action_check_for_leg(
            facts.account,
            activation,
            target,
            economic_action_prior_notional=target.economic_action_prior_notional,
            environment_id=self._environment_id,
            environment_kind=self._environment_kind,
            authority_class=self._authority_class,
            account_ref=self._account_ref,
        )
        self._coordinator.process_execution_action(
            target.execution_action_id,
            action_check=check,
            request_payload={
                "profile": target.proposed_action.action_profile,
                "quantity": target.proposed_action.quantity,
                "venue_policy": policy,
                "pre_submit_cutoff": facts.account.checked_at.isoformat(),
            },
            observed_at=facts.account.checked_at,
        )

    async def _apply_entry_management(
        self,
        activation: PlanActivation,
        schedule_actions: tuple[ExecutionAction, ...],
        management: _EntryManagementDecision,
        *,
        observed_at: datetime,
        risk_facts: ProductRiskReductionFacts | None,
    ) -> tuple[bool, ProductRiskReductionFacts | None]:
        if management.reason_code is None:
            return False, risk_facts
        if management.expire_ready:
            for action in schedule_actions:
                if action.state is ExecutionActionState.READY:
                    self._coordinator.reject_execution_action_before_submission(
                        action.execution_action_id,
                        reason_code=management.reason_code,
                        observed_at=observed_at,
                    )
        if management.cancel_target is not None:
            target = management.cancel_target
            if risk_facts is None:
                risk_facts = await self._risk_reduction_fact_provider(activation)
            reason_ref = (
                f"{activation.activation_id}:DIRECT_DYNAMIC:"
                f"{management.reason_code}:{target.execution_action_id}:"
                f"v{target.state_version}"
            )
            check = risk_facts.cancel_check(activation)
            result = self._coordinator.create_cancel_for_action(
                target_action_id=target.execution_action_id,
                target_endpoint="ORDINARY",
                plan_event_id=_management_uuid(
                    self._environment_id,
                    "plan-event",
                    reason_ref,
                ),
                execution_action_id=_management_uuid(
                    self._environment_id,
                    "execution-action",
                    reason_ref,
                ),
                action_check=check,
                reason_ref=reason_ref,
                observed_at=risk_facts.checked_at,
                client_order_id=None,
            )
            cancel = result.execution_action
            if cancel is not None and cancel.state is ExecutionActionState.READY:
                self._coordinator.process_execution_action(
                    cancel.execution_action_id,
                    action_check=check,
                    request_payload={"profile": "CANCEL_ORDER"},
                    observed_at=risk_facts.checked_at,
                )
        return True, risk_facts

    async def _facts_for_leg(
        self,
        activation: PlanActivation,
        leg: MaterializedOrderLeg,
        actions: tuple[ExecutionAction, ...],
        windows: frozenset[int],
        *,
        cutoff_ns: int,
    ) -> DirectScheduleFacts:
        summary = _risk_summary(
            self._coordinator,
            activation,
            actions,
        )
        return await self._fact_provider(
            activation,
            leg,
            summary.ordinary_client_ids,
            summary.algo_client_ids,
            summary.expected_signed_position,
            summary.outstanding_entry_quantity,
            summary.outstanding_entry_notional,
            self._tracker.moves(windows, cutoff_ns=cutoff_ns),
        )

    async def wait_idle(self) -> None:
        pending = tuple(task for task in self._tasks.values() if not task.done())
        if pending:
            await asyncio.gather(*pending)

    def close(self) -> None:
        for task in self._tasks.values():
            if not task.done():
                task.cancel()
        self._tasks.clear()


@dataclass(frozen=True, slots=True)
class _RiskSummary:
    expected_signed_position: str
    outstanding_entry_quantity: str
    outstanding_entry_notional: str
    ordinary_client_ids: frozenset[str]
    algo_client_ids: frozenset[str]


def _entry_valid_until(activation: PlanActivation) -> datetime:
    deadlines = activation.rule_state.get("deadlines")
    value = deadlines.get("entry_valid_until") if isinstance(deadlines, dict) else None
    if not isinstance(value, str):
        raise ValueError("ENTRY_DEADLINE_INVALID")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise ValueError("ENTRY_DEADLINE_INVALID") from None
    if parsed.utcoffset() is None:
        raise ValueError("ENTRY_DEADLINE_INVALID")
    return parsed


def _remaining_valid_until(
    legs: tuple[MaterializedOrderLeg, ...],
    schedule_actions: tuple[ExecutionAction, ...],
    *,
    default: datetime,
) -> datetime:
    """Use the earliest immutable venue/plan deadline of any unfinished leg."""

    states = {action.execution_action_id: action.state for action in schedule_actions}
    deadlines = tuple(
        item.proposed_action.valid_until
        for item in legs
        if states.get(item.execution_action_id)
        not in {ExecutionActionState.CLOSED, ExecutionActionState.NOT_SUBMITTED}
        and item.proposed_action.valid_until is not None
    )
    return min((default, *deadlines))


def _price_move_windows(activation: PlanActivation) -> frozenset[int]:
    snapshot = activation.order_schedule_snapshot
    if snapshot is None:
        return frozenset()
    condition_windows = {
        item.window_seconds
        for item in snapshot.schedule_spec.entry_conditions.items
        if isinstance(item, PriceMoveBpsCondition)
    }
    dynamic_windows = {
        item.window_seconds
        for item in snapshot.schedule_spec.dynamic_rules
        if isinstance(item, CancelOnShockRule)
    }
    return frozenset(condition_windows | dynamic_windows)


@dataclass(frozen=True, slots=True)
class _EntryManagementDecision:
    reason_code: str | None = None
    expire_ready: bool = False
    cancel_target: ExecutionAction | None = None


def _entry_management_decision(
    activation: PlanActivation,
    all_actions: tuple[ExecutionAction, ...],
    schedule_actions: tuple[ExecutionAction, ...],
    *,
    moves: dict[int, str],
    observed_at: datetime,
    entry_valid_until: datetime,
    expire_anchor: datetime | None,
    cycle_closed: bool,
    cycle_status_unknown: bool,
    protection_unproven: bool,
) -> _EntryManagementDecision:
    snapshot = activation.order_schedule_snapshot
    if snapshot is None:
        raise ValueError("ORDER_SCHEDULE_SNAPSHOT_REQUIRED")
    expire_rule = next(
        (
            item
            for item in snapshot.schedule_spec.dynamic_rules
            if isinstance(item, ExpireRemainingRule)
        ),
        None,
    )
    direct_time_exit = _direct_time_exit_at(activation)
    expired = observed_at >= entry_valid_until or (
        expire_rule is not None
        and expire_anchor is not None
        and observed_at
        >= expire_anchor + timedelta(seconds=expire_rule.after_seconds)
    ) or (direct_time_exit is not None and observed_at >= direct_time_exit)
    active = next(
        (
            action
            for action in schedule_actions
            if action.state
            in {
                ExecutionActionState.SUBMITTING,
                ExecutionActionState.UNKNOWN,
                ExecutionActionState.OPEN,
            }
        ),
        None,
    )
    cancel_already_recorded = (
        active is not None
        and active.client_order_id is not None
        and any(
            action.action_kind is ExecutionActionKind.CANCEL
            and isinstance(action.cancel_target, dict)
            and action.cancel_target.get("client_order_id")
            == active.client_order_id
            for action in all_actions
        )
    )
    if cycle_closed:
        return _EntryManagementDecision(
            reason_code="DIRECT_ENTRY_CYCLE_CLOSED",
            expire_ready=True,
            cancel_target=(
                active
                if active is not None
                and active.state is ExecutionActionState.OPEN
                and not cancel_already_recorded
                else None
            ),
        )
    if expired:
        return _EntryManagementDecision(
            reason_code="DIRECT_ENTRY_REMAINING_EXPIRED",
            expire_ready=True,
            cancel_target=(
                active
                if active is not None
                and active.state is ExecutionActionState.OPEN
                and not cancel_already_recorded
                else None
            ),
        )
    if cycle_status_unknown:
        return _EntryManagementDecision(
            reason_code="DIRECT_ENTRY_CYCLE_STATUS_UNKNOWN",
            cancel_target=(
                active
                if active is not None
                and active.state is ExecutionActionState.OPEN
                and not cancel_already_recorded
                else None
            ),
        )
    if protection_unproven:
        return _EntryManagementDecision(
            reason_code="DIRECT_ENTRY_PROTECTION_UNPROVEN",
            cancel_target=(
                active
                if active is not None
                and active.state is ExecutionActionState.OPEN
                and not cancel_already_recorded
                else None
            ),
        )
    shock = next(
        (
            item
            for item in snapshot.schedule_spec.dynamic_rules
            if isinstance(item, CancelOnShockRule)
        ),
        None,
    )
    if shock is None:
        return _EntryManagementDecision()
    trigger_count = sum(
        1
        for action in all_actions
        if action.action_kind is ExecutionActionKind.CANCEL
        and ":DIRECT_DYNAMIC:DIRECT_ENTRY_SHOCK:" in action.source_identity
    )
    if trigger_count:
        return _EntryManagementDecision(
            reason_code="DIRECT_ENTRY_SHOCK_TRIGGERED",
            expire_ready=True,
            cancel_target=(
                active
                if active is not None
                and active.state is ExecutionActionState.OPEN
                and not cancel_already_recorded
                else None
            ),
        )
    move_value = moves.get(shock.window_seconds)
    if move_value is None:
        return _EntryManagementDecision(
            reason_code="DIRECT_ENTRY_SHOCK_STATUS_UNKNOWN",
            cancel_target=(
                active
                if active is not None
                and active.state is ExecutionActionState.OPEN
                and not cancel_already_recorded
                else None
            ),
        )
    move = Decimal(move_value)
    adverse = (
        move <= -Decimal(shock.adverse_move_bps)
        if activation.direction is Direction.LONG
        else move >= Decimal(shock.adverse_move_bps)
    )
    if not adverse:
        return _EntryManagementDecision()
    return _EntryManagementDecision(
        reason_code="DIRECT_ENTRY_SHOCK",
        cancel_target=(
            active
            if active is not None
            and active.state is ExecutionActionState.OPEN
            and not cancel_already_recorded
            else None
        ),
    )


def _gtd_expiry_too_soon(policy: object, *, observed_at: datetime) -> bool:
    if not isinstance(policy, dict) or policy.get("time_in_force") != "GTD":
        return False
    raw_expire_at = policy.get("expire_at")
    if not isinstance(raw_expire_at, str):
        raise ValueError("DIRECT_GTD_EXPIRY_REQUIRED")
    try:
        expire_at = datetime.fromisoformat(raw_expire_at.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("DIRECT_GTD_EXPIRY_INVALID") from None
    if expire_at.utcoffset() is None or observed_at.utcoffset() is None:
        raise ValueError("DIRECT_GTD_TIMEZONE_REQUIRED")
    return expire_at <= observed_at + timedelta(seconds=BINANCE_GTD_MIN_LEAD_SECONDS)


def _schedule_submission_started_at(
    schedule_actions: tuple[ExecutionAction, ...],
) -> datetime | None:
    started = tuple(
        value
        for action in schedule_actions
        if (value := getattr(action, "call_started_at", None)) is not None
    )
    if not started:
        return None
    if any(value.utcoffset() is None for value in started):
        raise ValueError("DIRECT_SCHEDULE_TIMEZONE_REQUIRED")
    return min(value.astimezone(UTC) for value in started)


def _management_uuid(environment_id: str, kind: str, identity: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"urn:halpha:{environment_id}:{kind}:{identity}"))


def _direct_time_exit_at(activation: PlanActivation) -> datetime | None:
    state = activation.rule_state.get("direct_protection")
    if not isinstance(state, dict):
        return None
    anchor_ref = state.get("anchor_fill_ref")
    fills = state.get("fills")
    if not isinstance(anchor_ref, str) or not isinstance(fills, dict):
        return None
    anchor = fills.get(anchor_ref)
    if not isinstance(anchor, dict):
        return None
    policy = anchor.get("protection_policy")
    fill_time_value = anchor.get("fill_time")
    if not isinstance(policy, dict) or not isinstance(fill_time_value, str):
        return None
    seconds = policy.get("time_exit_seconds")
    if seconds is None:
        return None
    if not isinstance(seconds, int) or seconds <= 0:
        raise ValueError("DIRECT_TIME_EXIT_INVALID")
    try:
        fill_time = datetime.fromisoformat(fill_time_value)
    except ValueError:
        raise ValueError("DIRECT_TIME_EXIT_INVALID") from None
    if fill_time.utcoffset() is None:
        raise ValueError("DIRECT_TIME_EXIT_INVALID")
    return fill_time.astimezone(UTC) + timedelta(seconds=seconds)


def _schedule_actions(
    actions: tuple[ExecutionAction, ...],
    activation: PlanActivation,
    legs: tuple[MaterializedOrderLeg, ...],
) -> tuple[ExecutionAction, ...]:
    snapshot = activation.order_schedule_snapshot
    if snapshot is None:
        raise ValueError("ORDER_SCHEDULE_SNAPSHOT_REQUIRED")
    expected = {item.execution_action_id: item for item in legs}
    selected = tuple(
        action
        for action in actions
        if isinstance(action.action_terms.get("execution_context"), dict)
        and action.action_terms["execution_context"]
        .get("order_schedule", {})
        .get("schedule_digest")
        == snapshot.schedule_digest
    )
    if not selected:
        return ()
    if {action.execution_action_id for action in selected} != set(expected):
        raise ValueError("ORDER_SCHEDULE_LOCAL_RESPONSIBILITY_CONFLICT")
    for action in selected:
        item = expected[action.execution_action_id]
        context = action.action_terms.get("execution_context", {})
        schedule = context.get("order_schedule", {})
        if (
            action.source_identity != item.source_identity
            or action.client_order_id != item.client_order_id
            or schedule.get("leg_index") != item.leg.leg_index
            or schedule.get("submission_index") != item.submission_index
            or action.action_terms.get("causation_ref")
            != item.proposed_action.causation_ref
        ):
            raise ValueError("ORDER_SCHEDULE_ACTION_CONFLICT")
    return tuple(
        sorted(
            selected,
            key=lambda action: int(
                action.action_terms["execution_context"]["order_schedule"][
                    "submission_index"
                ]
            ),
        )
    )


def _risk_summary(
    coordinator: DirectScheduleCoordinator,
    activation: PlanActivation,
    actions: tuple[ExecutionAction, ...],
) -> _RiskSummary:
    sign = Decimal(1) if activation.direction is Direction.LONG else Decimal(-1)
    position = Decimal(0)
    outstanding_quantity = Decimal(0)
    outstanding_notional = Decimal(0)
    ordinary: set[str] = set()
    algo: set[str] = set()
    for action in actions:
        if action.client_order_id is not None:
            if action.action_kind in {
                ExecutionActionKind.PROTECTION,
                ExecutionActionKind.TAKE_PROFIT,
            }:
                algo.add(action.client_order_id)
            else:
                ordinary.add(action.client_order_id)
        facts = coordinator.list_venue_facts_for_action(action.execution_action_id)
        filled = sum(
            (
                Decimal(str(fact.payload["last_quantity"]))
                for fact in facts
                if fact.kind is VenueFactKind.FILL
                and fact.payload.get("last_quantity") is not None
            ),
            Decimal(0),
        )
        if action.action_kind is ExecutionActionKind.ENTRY:
            position += sign * filled
            if action.state in {
                ExecutionActionState.SUBMITTING,
                ExecutionActionState.UNKNOWN,
                ExecutionActionState.OPEN,
            }:
                quantity = Decimal(str(action.action_terms.get("quantity", "0")))
                remaining = max(Decimal(0), quantity - filled)
                outstanding_quantity += remaining
                price = action.action_terms.get("price")
                if price is None:
                    schedule = action.action_terms.get("execution_context", {}).get(
                        "order_schedule",
                        {},
                    )
                    price = schedule.get("sizing_price")
                if price is not None:
                    outstanding_notional += remaining * Decimal(str(price))
        elif action.action_kind in {
            ExecutionActionKind.PROTECTION,
            ExecutionActionKind.TAKE_PROFIT,
            ExecutionActionKind.RISK_REDUCTION,
            ExecutionActionKind.EXIT,
        }:
            position -= sign * filled
    return _RiskSummary(
        canonical_decimal(position),
        canonical_decimal(outstanding_quantity),
        canonical_decimal(outstanding_notional),
        frozenset(ordinary),
        frozenset(algo),
    )


def _fills_have_commissions(facts: tuple[VenueFact, ...]) -> bool:
    fill_trade_ids = {
        str(fact.payload.get("trade_id"))
        for fact in facts
        if fact.kind is VenueFactKind.FILL
        and fact.payload.get("trade_id") is not None
    }
    commission_trade_ids = {
        str(fact.payload.get("trade_id"))
        for fact in facts
        if fact.kind is VenueFactKind.COMMISSION
        and fact.payload.get("trade_id") is not None
    }
    return bool(fill_trade_ids) and fill_trade_ids.issubset(commission_trade_ids)


def _has_terminal_open_entry(
    coordinator: DirectScheduleCoordinator,
    actions: tuple[ExecutionAction, ...],
) -> bool:
    return any(
        action.action_kind is ExecutionActionKind.ENTRY
        and action.state is ExecutionActionState.OPEN
        and terminal_order_status(
            coordinator.list_venue_facts_for_action(action.execution_action_id)
        )
        is not None
        for action in actions
    )


def _has_risk_reduction_fill(
    coordinator: DirectScheduleCoordinator,
    actions: tuple[ExecutionAction, ...],
) -> bool:
    return any(
        action.action_kind
        in {
            ExecutionActionKind.PROTECTION,
            ExecutionActionKind.TAKE_PROFIT,
            ExecutionActionKind.RISK_REDUCTION,
            ExecutionActionKind.EXIT,
        }
        and any(
            fact.kind is VenueFactKind.FILL
            for fact in coordinator.list_venue_facts_for_action(
                action.execution_action_id
            )
        )
        for action in actions
    )


def _has_unprotected_open_entry_fill(
    coordinator: DirectScheduleCoordinator,
    actions: tuple[ExecutionAction, ...],
) -> bool:
    protections = tuple(
        action
        for action in actions
        if action.action_kind is ExecutionActionKind.PROTECTION
    )
    for entry in actions:
        if entry.action_kind is not ExecutionActionKind.ENTRY:
            continue
        fills = tuple(
            fact
            for fact in coordinator.list_venue_facts_for_action(
                entry.execution_action_id
            )
            if fact.kind is VenueFactKind.FILL
        )
        for fill in fills:
            matching: list[ExecutionAction] = []
            for protection in protections:
                protection_facts = coordinator.list_venue_facts_for_action(
                    protection.execution_action_id
                )
                protective = order_is_working(protection_facts) or (
                    terminal_order_status(protection_facts) == "FILLED"
                    and terminal_fills_complete(protection, protection_facts)
                    and _fills_have_commissions(protection_facts)
                )
                if (
                    protection.action_terms.get("execution_context", {}).get(
                        "fill_fact_ref"
                    )
                    == fill.venue_fact_id
                    and protection.action_terms.get("quantity")
                    == fill.payload.get("last_quantity")
                    and protective
                ):
                    matching.append(protection)
            if len(matching) != 1:
                return True
    return False


def _close_proven_entry_actions(
    coordinator: DirectScheduleCoordinator,
    actions: tuple[ExecutionAction, ...],
    *,
    risk_facts: ProductRiskReductionFacts,
    risk_summary: _RiskSummary,
    observed_at: datetime,
) -> None:
    position_fact = risk_facts.position_fact
    if position_fact is None or Decimal(risk_facts.current_abs_position) != abs(
        Decimal(risk_summary.expected_signed_position)
    ):
        return
    protections = tuple(
        action
        for action in actions
        if action.action_kind is ExecutionActionKind.PROTECTION
    )
    for entry in actions:
        if (
            entry.action_kind is not ExecutionActionKind.ENTRY
            or entry.state is not ExecutionActionState.OPEN
        ):
            continue
        facts = coordinator.list_venue_facts_for_action(entry.execution_action_id)
        terminal = terminal_order_status(facts)
        if terminal is None:
            continue
        if not terminal_fills_complete(entry, facts):
            continue
        fills = tuple(fact for fact in facts if fact.kind is VenueFactKind.FILL)
        if fills and not _fills_have_commissions(facts):
            continue
        covering_refs: list[str] = []
        protection_fact_refs: list[str] = []
        protected = True
        for fill in fills:
            matching: list[tuple[ExecutionAction, tuple[VenueFact, ...]]] = []
            for protection in protections:
                protection_facts = coordinator.list_venue_facts_for_action(
                    protection.execution_action_id
                )
                terminal_protection = terminal_order_status(protection_facts)
                is_protective = order_is_working(protection_facts) or (
                    terminal_protection == "FILLED"
                    and terminal_fills_complete(protection, protection_facts)
                    and _fills_have_commissions(protection_facts)
                )
                if (
                    protection.action_terms.get("execution_context", {}).get(
                        "fill_fact_ref"
                    )
                    == fill.venue_fact_id
                    and protection.action_terms.get("quantity")
                    == fill.payload.get("last_quantity")
                    and is_protective
                ):
                    matching.append((protection, protection_facts))
            if len(matching) != 1:
                protected = False
                break
            protection, matched_facts = matching[0]
            covering_refs.append(protection.execution_action_id)
            protection_fact_refs.extend(fact.venue_fact_id for fact in matched_facts)
        if not protected:
            continue
        fact_refs = tuple(
            dict.fromkeys(
                (
                    *(fact.venue_fact_id for fact in facts),
                    *protection_fact_refs,
                    position_fact.venue_fact_id,
                )
            )
        )
        coordinator.reconcile_execution_action(
            entry.execution_action_id,
            closure_evidence={
                "order_terminal": True,
                "terminal_order_status": terminal,
                "fills_complete": True,
                "fees_complete": not fills or _fills_have_commissions(facts),
                "position_effect_known": True,
                "position_fact_ref": position_fact.venue_fact_id,
                "protection_action_refs": tuple(covering_refs),
            },
            venue_fact_refs=fact_refs,
            observed_at=observed_at,
        )


def _action_check_for_leg(
    account: ProductAccountFacts,
    activation: PlanActivation,
    leg: MaterializedOrderLeg,
    *,
    economic_action_prior_notional: str,
    include_economic_prior_margin: bool = False,
    environment_id: str,
    environment_kind: EnvironmentKind,
    authority_class: AuthorityClass,
    account_ref: str,
) -> ActionCheckInput:
    action_price = canonical_decimal(
        max(
            Decimal(account.conservative_price),
            Decimal(leg.leg.sizing_price),
        )
    )
    prior_margin = Decimal(0)
    if include_economic_prior_margin:
        prior_margin = Decimal(economic_action_prior_notional) / effective_leverage(
            account.actual_margin_mode,
            account.actual_leverage,
        )
    adjusted = replace(
        account,
        conservative_price=action_price,
        activation_current_margin=canonical_decimal(
            Decimal(account.activation_current_margin) + prior_margin
        ),
        post_action_abs_position=canonical_decimal(
            Decimal(account.current_abs_position) + Decimal(leg.leg.quantity)
        ),
    )
    return adjusted.direct_action_check(
        leg.proposed_action,
        activation_id=activation.activation_id,
        economic_action_prior_notional=economic_action_prior_notional,
        environment_id=environment_id,
        environment_kind=environment_kind,
        authority_class=authority_class,
        account_ref=account_ref,
    )
