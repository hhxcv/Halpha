"""Run the concrete post-entry responsibilities for the one-shot strategy."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Coroutine
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol
from uuid import NAMESPACE_URL, uuid5

from halpha.capital.models import ActionCheckInput, RiskClass, StopCategory
from halpha.domain_values import canonical_decimal
from halpha.planning.models import PlanActivation, PlanLifecycle
from halpha.planning.registry import Direction
from halpha.planning.transitions import (
    proposed_direct_take_profits_from_fill,
    proposed_take_profits_from_fill,
    venue_source_identity,
)
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
from halpha.venue_integration.nautilus_events import NormalizedNautilusEvent


class ProductResponsibilityCoordinator(Protocol):
    def get_activation_snapshot(self, activation_id: str) -> PlanActivation: ...

    def get_execution_action(self, execution_action_id: str) -> ExecutionAction: ...

    def list_execution_actions(self, activation_id: str) -> tuple[ExecutionAction, ...]: ...

    def list_venue_facts_for_action(self, execution_action_id: str) -> tuple[VenueFact, ...]: ...

    def create_protection_for_fill(self, **kwargs: Any) -> Any: ...

    def create_take_profits_for_protected_fill(self, **kwargs: Any) -> Any: ...

    def create_direct_take_profits_for_protected_fill(self, **kwargs: Any) -> Any: ...

    def process_execution_action(self, execution_action_id: str, **kwargs: Any) -> Any: ...

    def apply_venue_fact(self, fact: VenueFact, **kwargs: Any) -> ExecutionAction | None: ...

    def create_position_exit(self, **kwargs: Any) -> Any: ...

    def create_cancel_for_action(self, **kwargs: Any) -> Any: ...

    def reconcile_execution_action(self, execution_action_id: str, **kwargs: Any) -> ExecutionAction: ...

    def query_unknown_action_if_due(self, execution_action_id: str, **kwargs: Any) -> bool: ...

    def query_called_action_identity(self, execution_action_id: str) -> bool: ...

    def apply_persisted_user_takeover(
        self, *, activation_id: str, observed_at: datetime
    ) -> tuple[ExecutionAction, ...]: ...

    def record_unknown_action_not_submitted(
        self, execution_action_id: str, **kwargs: Any
    ) -> ExecutionAction: ...

    def reject_execution_action_before_submission(
        self, execution_action_id: str, **kwargs: Any
    ) -> ExecutionAction: ...

    def close_activation(self, **kwargs: Any) -> str: ...


@dataclass(frozen=True, slots=True)
class ProductRiskReductionFacts:
    checked_at: datetime
    conservative_price: str
    available_margin: str
    actual_margin_mode: str
    actual_leverage: str
    activation_current_notional: str
    account_current_notional: str
    activation_current_margin: str
    current_abs_position: str
    position_fact: VenueFact | None = None
    open_order_client_ids: tuple[str, ...] = ()
    open_algo_client_ids: tuple[str, ...] = ()

    def action_check(
        self,
        activation: PlanActivation,
        *,
        action_profile: str,
        control_category: StopCategory,
        quantity: str,
    ) -> ActionCheckInput:
        current = Decimal(self.current_abs_position)
        requested = Decimal(quantity)
        would_reverse = requested > current
        post_action = max(current - requested, Decimal("0"))
        return ActionCheckInput(
            environment_id=activation.environment_id,
            environment_kind=activation.environment_kind,
            authority_class=activation.authority_class,
            activation_id=activation.activation_id,
            account_ref=activation.account_ref,
            instrument_ref=activation.instrument_ref,
            action_profile=action_profile,
            control_category=control_category,
            risk_class=RiskClass.RISK_REDUCING,
            checked_at=self.checked_at,
            quantized_quantity=quantity,
            conservative_price=self.conservative_price,
            activation_current_notional=self.activation_current_notional,
            account_current_notional=self.account_current_notional,
            activation_current_margin=self.activation_current_margin,
            account_dynamic_available_margin=self.available_margin,
            actual_margin_mode=self.actual_margin_mode,
            actual_leverage=self.actual_leverage,
            post_action_abs_position=canonical_decimal(post_action),
            current_abs_position=self.current_abs_position,
            would_reverse_position=would_reverse,
        )

    def cancel_check(self, activation: PlanActivation) -> ActionCheckInput:
        """Build the risk-neutral check for cancelling an existing order identity."""

        return ActionCheckInput(
            environment_id=activation.environment_id,
            environment_kind=activation.environment_kind,
            authority_class=activation.authority_class,
            activation_id=activation.activation_id,
            account_ref=activation.account_ref,
            instrument_ref=activation.instrument_ref,
            action_profile="CANCEL_ORDER",
            control_category=StopCategory.RISK_REDUCTION_OR_ORDER_MANAGEMENT,
            risk_class=RiskClass.RISK_NEUTRAL,
            checked_at=self.checked_at,
            quantized_quantity="0",
            conservative_price=self.conservative_price,
            activation_current_notional=self.activation_current_notional,
            account_current_notional=self.account_current_notional,
            activation_current_margin=self.activation_current_margin,
            account_dynamic_available_margin=self.available_margin,
            actual_margin_mode=self.actual_margin_mode,
            actual_leverage=self.actual_leverage,
            post_action_abs_position=self.current_abs_position,
            current_abs_position=self.current_abs_position,
            would_reverse_position=False,
        )


RiskReductionFactProvider = Callable[
    [PlanActivation], Awaitable[ProductRiskReductionFacts]
]
EntryOrderAbsenceProvider = Callable[[ExecutionAction], Awaitable[bool]]


class ProductResponsibilityBoundary:
    """Create protection and take-profit actions from persisted venue facts."""

    def __init__(
        self,
        *,
        loop: asyncio.AbstractEventLoop,
        coordinator: ProductResponsibilityCoordinator,
        fact_provider: RiskReductionFactProvider,
        entry_order_absence_provider: EntryOrderAbsenceProvider | None = None,
        environment_id: str,
        submission_enabled: Callable[[], bool] | None = None,
    ) -> None:
        self._loop = loop
        self._coordinator = coordinator
        self._fact_provider = fact_provider
        self._entry_order_absence_provider = entry_order_absence_provider
        self._environment_id = environment_id
        self._submission_enabled = submission_enabled or (lambda: True)
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._last_fallback_sync: dict[str, float] = {}

    def submit_event(self, event: NormalizedNautilusEvent) -> None:
        if not self._submission_enabled():
            return
        action = event.action
        if action is None:
            return
        activation = self._coordinator.get_activation_snapshot(action.activation_id)
        if activation.lifecycle is PlanLifecycle.COMPLETED:
            return
        if activation.lifecycle is PlanLifecycle.USER_TAKEOVER:
            source = ":".join(fact.content_digest for fact in event.facts)
            self._schedule(
                f"TAKEOVER_SYNC:{action.activation_id}:{source}",
                self.sync(action.activation_id, force=True),
            )
            return
        if action.action_kind is ExecutionActionKind.ENTRY:
            for fact in event.facts:
                if fact.kind is VenueFactKind.FILL:
                    self._schedule(
                        f"PROTECTION:{fact.content_digest}",
                        self._protect_fill_and_sync(fact),
                    )
        if action.action_kind is ExecutionActionKind.PROTECTION and any(
            fact.kind is VenueFactKind.ORDER_STATE
            and fact.payload.get("status") == "WORKING"
            for fact in event.facts
        ):
            self._schedule(
                f"TAKE_PROFIT:{action.execution_action_id}",
                self._create_take_profits(action.execution_action_id),
            )
        if (
            action.action_kind is ExecutionActionKind.PROTECTION
            and event.definitely_not_submitted
        ):
            # OrderDenied has no venue fact by definition, but the coordinator
            # has already persisted NOT_SUBMITTED.  Reconcile immediately so a
            # confirmed position does not wait for the periodic fallback.
            self._schedule(
                f"SYNC:{action.activation_id}:PROTECTION_DENIED:{action.execution_action_id}",
                self.sync(action.activation_id, force=True),
            )
        if action.action_kind is not ExecutionActionKind.ENTRY and any(
            fact.kind is VenueFactKind.FILL
            or (
                fact.kind is VenueFactKind.ORDER_STATE
                and fact.payload.get("status")
                in {"FILLED", "CANCELLED", "REJECTED", "EXPIRED"}
            )
            for fact in event.facts
        ):
            # Nautilus owns the live order stream and reconciliation. React to
            # its decisive events immediately; the periodic path remains only
            # a bounded fallback for a missed or delayed callback.
            source = ":".join(fact.content_digest for fact in event.facts)
            self._schedule(
                f"SYNC:{action.activation_id}:{source}",
                self.sync(action.activation_id, force=True),
            )

    def resume(self, activation_id: str) -> None:
        if not self._submission_enabled():
            return
        activation = self._coordinator.get_activation_snapshot(activation_id)
        if activation.lifecycle is PlanLifecycle.COMPLETED:
            return
        if activation.lifecycle is PlanLifecycle.USER_TAKEOVER:
            self._schedule(
                f"TAKEOVER_RESUME:{activation_id}",
                self.sync(activation_id, force=True),
            )
            return
        self._schedule(f"RESUME:{activation_id}", self._resume(activation_id))

    async def sync(self, activation_id: str, *, force: bool = False) -> None:
        """Advance only venue-backed responsibilities already persisted for one activation."""

        if not self._submission_enabled():
            return
        activation = self._coordinator.get_activation_snapshot(activation_id)
        if activation.lifecycle is PlanLifecycle.COMPLETED:
            return
        if activation.lifecycle is PlanLifecycle.USER_TAKEOVER:
            await self._sync_user_takeover(activation, force=force)
            return
        actions = self._coordinator.list_execution_actions(activation_id)
        # While a plan is only waiting for entry, Nautilus owns market streaming,
        # strategy evaluation and account cache updates. There is no persisted
        # execution responsibility for this fallback loop to reconcile yet.
        if activation.lifecycle is PlanLifecycle.RUNNING and not actions:
            return
        now = self._loop.time()
        last_sync = self._last_fallback_sync.get(activation_id)
        if (
            not force
            and activation.lifecycle is PlanLifecycle.RUNNING
            and last_sync is not None
            and now - last_sync < 10.0
        ):
            return
        self._last_fallback_sync[activation_id] = now
        facts = await self._fact_provider(activation)
        protection_gap = await self._replay_entry_fill_protections(
            activation,
            actions,
            facts,
        )
        activation = self._coordinator.get_activation_snapshot(activation_id)
        if activation.lifecycle in {
            PlanLifecycle.USER_TAKEOVER,
            PlanLifecycle.COMPLETED,
        }:
            return
        actions = self._coordinator.list_execution_actions(activation_id)
        protection_gap = protection_gap or self._failed_protection_seen(actions)
        for action in actions:
            if action.state is ExecutionActionState.UNKNOWN:
                if action.action_kind is ExecutionActionKind.CANCEL:
                    target_client_order_id = (action.cancel_target or {}).get(
                        "client_order_id"
                    )
                    target = next(
                        (
                            candidate
                            for candidate in actions
                            if candidate.client_order_id == target_client_order_id
                        ),
                        None,
                    )
                    target_fact = (
                        _latest_terminal_order_fact(
                            self._coordinator.list_venue_facts_for_action(
                                target.execution_action_id
                            )
                        )
                        if target is not None
                        else None
                    )
                    if target_fact is not None:
                        self._coordinator.reconcile_cancel_from_target_fact(
                            action.execution_action_id,
                            target_fact=target_fact,
                            observed_at=facts.checked_at,
                        )
                        continue
                definitely_absent = False
                if (
                    action.action_kind is ExecutionActionKind.ENTRY
                    and self._entry_order_absence_provider is not None
                ):
                    definitely_absent = await self._entry_order_absence_provider(action)
                if definitely_absent:
                    self._coordinator.record_unknown_action_not_submitted(
                        action.execution_action_id,
                        reason_code="VENUE_QUERY_PROVED_ABSENT",
                        observed_at=facts.checked_at,
                    )
                else:
                    self._coordinator.query_unknown_action_if_due(
                        action.execution_action_id,
                        observed_at=facts.checked_at,
                    )
        actions = self._coordinator.list_execution_actions(activation_id)
        for action in actions:
            context = action.action_terms.get("execution_context")
            if (
                activation.lifecycle is PlanLifecycle.RUNNING
                and action.action_kind is ExecutionActionKind.PROTECTION
                and isinstance(action.action_terms.get("quantity"), str)
                and isinstance(context, dict)
                and all(
                    isinstance(context.get(key), str)
                    for key in (
                        "entry_action_ref",
                        "fill_fact_ref",
                        "fill_source_identity",
                    )
                )
                and order_is_working(
                    self._coordinator.list_venue_facts_for_action(
                        action.execution_action_id
                    )
                )
            ):
                # The streaming WORKING callback is only a latency path.  A
                # persisted working protection must be able to recover its TP
                # responsibility in the same process after a dropped task.
                await self._create_take_profits(action.execution_action_id)
        actions = self._coordinator.list_execution_actions(activation_id)
        self._resume_ready_non_entry_actions(activation, facts, actions)
        direct_time_exit_due = _direct_time_exit_due(
            activation,
            observed_at=facts.checked_at,
        )
        entry_cycle_closed = (
            activation.lifecycle is PlanLifecycle.RUNNING
            and Decimal(facts.current_abs_position) == 0
            and self._risk_reduction_fill_seen(actions)
        )
        if protection_gap:
            await self._ensure_exit(
                activation,
                facts,
                reason_code="PROTECTION_GAP",
            )
        elif activation.lifecycle is PlanLifecycle.EXITING:
            await self._ensure_exit(activation, facts, reason_code="PLAN_EXIT")
        elif direct_time_exit_due:
            await self._ensure_exit(
                activation,
                facts,
                reason_code="DIRECT_TIME_EXIT",
            )
        elif entry_cycle_closed:
            await self._ensure_exit(
                activation,
                facts,
                reason_code="ENTRY_CYCLE_CLOSED",
            )
        await self._try_close_activation(activation, facts)

    async def _sync_user_takeover(
        self,
        activation: PlanActivation,
        *,
        force: bool,
    ) -> None:
        """Hand over never-called actions and retain only read-only reconciliation."""

        now = self._loop.time()
        last_sync = self._last_fallback_sync.get(activation.activation_id)
        if not force and last_sync is not None and now - last_sync < 10.0:
            return
        self._last_fallback_sync[activation.activation_id] = now
        observed_at = datetime.now(UTC)
        self._coordinator.apply_persisted_user_takeover(
            activation_id=activation.activation_id,
            observed_at=observed_at,
        )
        actions = self._coordinator.list_execution_actions(activation.activation_id)
        for action in actions:
            if (
                action.action_kind is ExecutionActionKind.CANCEL
                and action.state is ExecutionActionState.UNKNOWN
            ):
                target_client_order_id = (action.cancel_target or {}).get(
                    "client_order_id"
                )
                target = next(
                    (
                        candidate
                        for candidate in actions
                        if candidate.client_order_id == target_client_order_id
                    ),
                    None,
                )
                target_fact = (
                    _latest_terminal_order_fact(
                        self._coordinator.list_venue_facts_for_action(
                            target.execution_action_id
                        )
                    )
                    if target is not None
                    else None
                )
                if target_fact is not None:
                    self._coordinator.reconcile_cancel_from_target_fact(
                        action.execution_action_id,
                        target_fact=target_fact,
                        observed_at=observed_at,
                    )
                    continue
            self._coordinator.query_called_action_identity(
                action.execution_action_id
            )
        refreshed = self._coordinator.get_activation_snapshot(
            activation.activation_id
        )
        if refreshed.lifecycle is not PlanLifecycle.USER_TAKEOVER:
            return
        facts = await self._fact_provider(refreshed)
        await self._try_close_activation(refreshed, facts)

    async def _replay_entry_fill_protections(
        self,
        activation: PlanActivation,
        actions: tuple[ExecutionAction, ...],
        facts: ProductRiskReductionFacts,
    ) -> bool:
        """Idempotently derive protection from every durable entry fill.

        The stream callback is only a latency optimization.  A callback task or
        transaction failure must be recoverable on the next ordinary sync,
        without requiring a process restart.
        """

        confirmed_gap = False
        for action in actions:
            if action.action_kind is not ExecutionActionKind.ENTRY:
                continue
            for fill in self._coordinator.list_venue_facts_for_action(
                action.execution_action_id
            ):
                if fill.kind is not VenueFactKind.FILL:
                    continue
                if (
                    getattr(fill, "action_ref", None)
                    != action.execution_action_id
                    or getattr(fill, "activation_ref", None)
                    != activation.activation_id
                ):
                    continue
                protection = await self._protect_fill(fill, risk_facts=facts)
                confirmed_gap = confirmed_gap or protection is None
        return confirmed_gap

    def _schedule(self, key: str, coroutine: Coroutine[Any, Any, None]) -> None:
        existing = self._tasks.get(key)
        if existing is not None and (
            not existing.done()
            or (not existing.cancelled() and existing.exception() is None)
        ):
            coroutine.close()
            return
        task = self._loop.create_task(coroutine)
        self._tasks[key] = task
        task.add_done_callback(self._report_failure)

    def _report_failure(self, task: asyncio.Task[None]) -> None:
        if task.cancelled():
            return
        exception = task.exception()
        if exception is not None:
            self._loop.call_exception_handler(
                {
                    "message": "HALPHA_PRODUCT_RESPONSIBILITY_FAILED",
                    "exception": exception,
                    "task": task,
                }
            )

    async def _resume(self, activation_id: str) -> None:
        for action in self._coordinator.list_execution_actions(activation_id):
            if action.action_kind is ExecutionActionKind.ENTRY:
                for fact in self._coordinator.list_venue_facts_for_action(
                    action.execution_action_id
                ):
                    if fact.kind is VenueFactKind.FILL:
                        await self._protect_fill(fact)
            elif (
                action.action_kind is ExecutionActionKind.PROTECTION
                and order_is_working(
                    self._coordinator.list_venue_facts_for_action(
                        action.execution_action_id
                    )
                )
            ):
                await self._create_take_profits(action.execution_action_id)
        # Resume is also the fail-closed reconciliation boundary.  In
        # particular, a persisted fill whose protection could not be compiled
        # must immediately form an exit instead of waiting for a periodic tick.
        await self.sync(activation_id, force=True)

    async def _protect_fill_and_sync(self, fill: VenueFact) -> None:
        """Protect one callback fill, then reconcile its aggregate risk state."""

        await self._protect_fill(fill)
        activation_ref = getattr(fill, "activation_ref", None)
        if isinstance(activation_ref, str):
            await self.sync(activation_ref, force=True)

    async def _protect_fill(
        self,
        fill: VenueFact,
        *,
        risk_facts: ProductRiskReductionFacts | None = None,
    ) -> ExecutionAction | None:
        action_ref = getattr(fill, "action_ref", None)
        activation_ref = getattr(fill, "activation_ref", None)
        if action_ref is None or activation_ref is None:
            return None
        activation = self._coordinator.get_activation_snapshot(activation_ref)
        if activation.lifecycle not in {
            PlanLifecycle.RUNNING,
            PlanLifecycle.EXITING,
        }:
            return None
        existing = next(
            (
                action
                for action in self._coordinator.list_execution_actions(
                    activation.activation_id
                )
                if action.action_kind is ExecutionActionKind.PROTECTION
                and action.action_terms.get("execution_context", {}).get(
                    "fill_fact_ref"
                )
                == fill.venue_fact_id
            ),
            None,
        )
        if existing is not None and existing.state is not ExecutionActionState.READY:
            return existing
        facts = risk_facts or await self._fact_provider(activation)
        quantity = str(fill.payload["last_quantity"])
        check = facts.action_check(
            activation,
            action_profile="PROTECTIVE_STOP_REDUCE_ONLY",
            control_category=StopCategory.PROTECTION,
            quantity=quantity,
        )
        source_identity = venue_source_identity(
            activation_id=activation.activation_id,
            rule_id="PROTECTION_AFTER_FILL",
            source_class=fill.source_class.value,
            source_object_id=fill.source_object_id,
            source_sequence_or_version=fill.source_sequence,
        )
        if existing is None:
            result = self._coordinator.create_protection_for_fill(
                fill_fact=fill,
                plan_event_id=_stable_id(
                    self._environment_id,
                    "plan-event",
                    source_identity,
                ),
                execution_action_id=_stable_id(
                    self._environment_id, "execution-action", source_identity
                ),
                action_check=check,
                observed_at=facts.checked_at,
                client_order_id=_stable_client_order_id(
                    self._environment_id, source_identity
                ),
            )
            action = result.execution_action
        else:
            action = existing
        if action is not None:
            self._submit_ready(action, check, observed_at=facts.checked_at)
        return action

    async def _create_take_profits(self, protection_action_id: str) -> None:
        protection = self._coordinator.get_execution_action(protection_action_id)
        if not order_is_working(
            self._coordinator.list_venue_facts_for_action(protection_action_id)
        ):
            return
        context = protection.action_terms.get("execution_context")
        quantity = protection.action_terms.get("quantity")
        if not isinstance(context, dict) or not isinstance(quantity, str):
            raise ValueError("PROTECTION_UNKNOWN")
        required = ("entry_action_ref", "fill_fact_ref", "fill_source_identity")
        if any(not isinstance(context.get(key), str) for key in required):
            raise ValueError("PROTECTION_UNKNOWN")
        activation = self._coordinator.get_activation_snapshot(protection.activation_id)
        if activation.lifecycle is not PlanLifecycle.RUNNING:
            return
        if isinstance(context.get("direct_fill"), dict):
            await self._create_direct_take_profits(
                activation,
                protection,
                context,
            )
            return
        proposed = proposed_take_profits_from_fill(
            activation,
            entry_action_ref=str(context["entry_action_ref"]),
            protection_action_ref=protection.execution_action_id,
            fill_fact_ref=str(context["fill_fact_ref"]),
            fill_source_identity=str(context["fill_source_identity"]),
            fill_quantity=quantity,
        )
        facts = await self._fact_provider(activation)
        checks = tuple(
            facts.action_check(
                activation,
                action_profile=item.action_profile,
                control_category=StopCategory.RISK_REDUCTION_OR_ORDER_MANAGEMENT,
                quantity=str(item.quantity),
            )
            for item in proposed
        )
        source = f"{protection.execution_action_id}:TAKE_PROFITS"
        action_ids = tuple(
            _stable_id(self._environment_id, f"execution-action-{index}", source)
            for index in (1, 2)
        )
        results = self._coordinator.create_take_profits_for_protected_fill(
            protection_action_id=protection.execution_action_id,
            fill_fact_ref=str(context["fill_fact_ref"]),
            fill_source_identity=str(context["fill_source_identity"]),
            fill_quantity=quantity,
            plan_event_ids=tuple(
                _stable_id(self._environment_id, f"plan-event-{index}", source)
                for index in (1, 2)
            ),
            execution_action_ids=action_ids,
            action_checks=checks,
            observed_at=facts.checked_at,
            client_order_ids=tuple(
                _stable_client_order_id(self._environment_id, f"{source}:{index}")
                for index in (1, 2)
            ),
        )
        for result, check in zip(results, checks, strict=True):
            action = result.execution_action
            if action is not None:
                self._submit_ready(action, check, observed_at=facts.checked_at)

    async def _create_direct_take_profits(
        self,
        activation: PlanActivation,
        protection: ExecutionAction,
        context: dict[str, object],
    ) -> None:
        entry_action_ref = context.get("entry_action_ref")
        fill_fact_ref = context.get("fill_fact_ref")
        fill_source_identity = context.get("fill_source_identity")
        if not all(
            isinstance(value, str)
            for value in (entry_action_ref, fill_fact_ref, fill_source_identity)
        ):
            raise ValueError("PROTECTION_UNKNOWN")
        proposed = proposed_direct_take_profits_from_fill(
            activation,
            entry_action_ref=str(entry_action_ref),
            protection_action_ref=protection.execution_action_id,
            fill_fact_ref=str(fill_fact_ref),
            fill_source_identity=str(fill_source_identity),
        )
        if not proposed:
            return
        facts = await self._fact_provider(activation)
        checks = tuple(
            facts.action_check(
                activation,
                action_profile=item.action_profile,
                control_category=StopCategory.RISK_REDUCTION_OR_ORDER_MANAGEMENT,
                quantity=str(item.quantity),
            )
            for item in proposed
        )
        source = f"{protection.execution_action_id}:DIRECT_TAKE_PROFITS"
        ordinals = tuple(range(1, len(proposed) + 1))
        results = self._coordinator.create_direct_take_profits_for_protected_fill(
            protection_action_id=protection.execution_action_id,
            fill_fact_ref=str(fill_fact_ref),
            fill_source_identity=str(fill_source_identity),
            plan_event_ids=tuple(
                _stable_id(self._environment_id, f"plan-event-{index}", source)
                for index in ordinals
            ),
            execution_action_ids=tuple(
                _stable_id(self._environment_id, f"execution-action-{index}", source)
                for index in ordinals
            ),
            action_checks=checks,
            observed_at=facts.checked_at,
            client_order_ids=tuple(
                _stable_client_order_id(self._environment_id, f"{source}:{index}")
                for index in ordinals
            ),
        )
        for result, check in zip(results, checks, strict=True):
            action = result.execution_action
            if action is not None:
                self._submit_ready(action, check, observed_at=facts.checked_at)

    async def _ensure_exit(
        self,
        activation: PlanActivation,
        facts: ProductRiskReductionFacts,
        *,
        reason_code: str,
    ) -> None:
        actions = self._coordinator.list_execution_actions(activation.activation_id)
        unresolved_entry = False
        for target in actions:
            if target.action_kind is not ExecutionActionKind.ENTRY:
                continue
            if target.state is ExecutionActionState.READY:
                self._coordinator.reject_execution_action_before_submission(
                    target.execution_action_id,
                    reason_code=f"{reason_code}_ENTRY_NOT_SUBMITTED",
                    observed_at=facts.checked_at,
                )
                continue
            if target.state in {
                ExecutionActionState.SUBMITTING,
                ExecutionActionState.UNKNOWN,
            }:
                unresolved_entry = True
                continue
            if target.state is not ExecutionActionState.OPEN:
                continue
            target_facts = self._coordinator.list_venue_facts_for_action(
                target.execution_action_id
            )
            if terminal_order_status(target_facts) is not None:
                if terminal_fills_complete(target, target_facts):
                    continue
                unresolved_entry = True
                continue
            unresolved_entry = True
            if not order_is_working(target_facts) or target.client_order_id is None:
                continue
            self._ensure_cancel(
                activation,
                facts,
                target,
                target_endpoint="ORDINARY",
                reason_code=reason_code,
            )

        # A market exit must not race an entry that may still fill.  Reconcile
        # the original entry identity (and any cancel/fill competition) first,
        # then size the exit from a refreshed authoritative position fact.
        if unresolved_entry:
            return

        actions = self._coordinator.list_execution_actions(activation.activation_id)
        exit_actions = tuple(
            action
            for action in actions
            if action.action_kind is ExecutionActionKind.EXIT
        )
        if Decimal(facts.current_abs_position) > 0:
            position_fact = facts.position_fact
            if position_fact is None:
                raise ValueError("POSITION_FACT_REQUIRED")
            if not _position_attribution_proven(
                activation,
                facts,
                actions,
                self._coordinator,
            ):
                raise ValueError("POSITION_ATTRIBUTION_UNKNOWN")
            predecessor: ExecutionAction | None = None
            if exit_actions:
                if any(
                    not _exit_action_resolved(action, self._coordinator)
                    for action in exit_actions
                ):
                    return
                predecessor = exit_actions[-1]
                if (
                    ":EXIT_SUCCESSOR:"
                    in str(getattr(predecessor, "source_identity", ""))
                    and not _action_has_fill(predecessor, self._coordinator)
                ):
                    # One deterministic retry is allowed after a no-progress
                    # pre-submit or terminal failure.  Repeated blind market
                    # retries require new evidence or owner intervention.
                    return
            self._coordinator.apply_venue_fact(
                position_fact,
                observed_at=position_fact.received_at,
            )
            reason_ref = (
                f"{activation.activation_id}:EXIT:{reason_code}"
                if predecessor is None
                else (
                    f"{activation.activation_id}:EXIT:{reason_code}:"
                    f"EXIT_SUCCESSOR:{predecessor.execution_action_id}"
                )
            )
            source_identity = (
                f"{activation.activation_id}:EXIT:"
                f"{position_fact.venue_fact_id}:{reason_ref}"
            )
            check = facts.action_check(
                activation,
                action_profile="REDUCE_OR_CLOSE_MARKET",
                control_category=StopCategory.RISK_REDUCTION_OR_ORDER_MANAGEMENT,
                quantity=facts.current_abs_position,
            )
            result = self._coordinator.create_position_exit(
                activation_id=activation.activation_id,
                position_quantity=facts.current_abs_position,
                position_fact_ref=position_fact.venue_fact_id,
                reason_ref=reason_ref,
                plan_event_id=_stable_id(
                    self._environment_id,
                    "plan-event-exit",
                    source_identity,
                ),
                execution_action_id=_stable_id(
                    self._environment_id,
                    "execution-action-exit",
                    reason_ref,
                ),
                action_check=check,
                observed_at=facts.checked_at,
                client_order_id=_stable_client_order_id(
                    self._environment_id,
                    reason_ref,
                ),
            )
            action = result.execution_action
            if action is not None:
                self._submit_ready(
                    action,
                    check,
                    observed_at=facts.checked_at,
                )
            return
        for target in actions:
            if (
                target.action_kind
                not in {
                    ExecutionActionKind.ENTRY,
                    ExecutionActionKind.PROTECTION,
                    ExecutionActionKind.TAKE_PROFIT,
                }
            ):
                continue
            if target.state is ExecutionActionState.READY:
                self._coordinator.reject_execution_action_before_submission(
                    target.execution_action_id,
                    reason_code=f"{reason_code}_NO_POSITION",
                    observed_at=facts.checked_at,
                )
                continue
            if (
                target.state is not ExecutionActionState.OPEN
                or not order_is_working(
                    self._coordinator.list_venue_facts_for_action(
                        target.execution_action_id
                    )
                )
                or target.client_order_id is None
            ):
                continue
            self._ensure_cancel(
                activation,
                facts,
                target,
                target_endpoint=(
                    "ORDINARY"
                    if target.action_kind is ExecutionActionKind.ENTRY
                    else "ALGO"
                ),
                reason_code=reason_code,
            )

    def _ensure_cancel(
        self,
        activation: PlanActivation,
        facts: ProductRiskReductionFacts,
        target: ExecutionAction,
        *,
        target_endpoint: str,
        reason_code: str,
    ) -> None:
        existing = next(
            (
                action
                for action in self._coordinator.list_execution_actions(
                    activation.activation_id
                )
                if action.action_kind is ExecutionActionKind.CANCEL
                and (action.cancel_target or {}).get("client_order_id")
                == target.client_order_id
                and action.state
                in {
                    ExecutionActionState.READY,
                    ExecutionActionState.SUBMITTING,
                    ExecutionActionState.UNKNOWN,
                    ExecutionActionState.OPEN,
                }
            ),
            None,
        )
        if existing is not None:
            if existing.state is ExecutionActionState.READY:
                self._submit_ready(
                    existing,
                    facts.cancel_check(activation),
                    observed_at=facts.checked_at,
                )
            return
        reason_ref = (
            f"{activation.activation_id}:EXIT_CANCEL:{reason_code}:"
            f"{target.execution_action_id}:v{target.state_version}"
        )
        result = self._coordinator.create_cancel_for_action(
            target_action_id=target.execution_action_id,
            target_endpoint=target_endpoint,
            plan_event_id=_stable_id(
                self._environment_id,
                "plan-event-cancel",
                reason_ref,
            ),
            execution_action_id=_stable_id(
                self._environment_id,
                "execution-action-cancel",
                reason_ref,
            ),
            action_check=facts.cancel_check(activation),
            reason_ref=reason_ref,
            observed_at=facts.checked_at,
            client_order_id=None,
        )
        action = result.execution_action
        if action is not None:
            self._submit_ready(
                action,
                facts.cancel_check(activation),
                observed_at=facts.checked_at,
            )

    def _resume_ready_non_entry_actions(
        self,
        activation: PlanActivation,
        facts: ProductRiskReductionFacts,
        actions: tuple[ExecutionAction, ...],
    ) -> None:
        """Retry only local responsibilities proven never to have been called."""

        if activation.lifecycle is PlanLifecycle.USER_TAKEOVER:
            return
        for action in actions:
            if (
                action.state is not ExecutionActionState.READY
                or action.action_kind is ExecutionActionKind.ENTRY
            ):
                continue
            if action.action_kind is ExecutionActionKind.CANCEL:
                check = facts.cancel_check(activation)
            else:
                quantity = action.action_terms.get("quantity")
                profile = action.action_terms.get("action_profile")
                if not isinstance(quantity, str) or not isinstance(profile, str):
                    continue
                if action.action_kind is ExecutionActionKind.EXIT:
                    if not _position_attribution_proven(
                        activation,
                        facts,
                        actions,
                        self._coordinator,
                    ):
                        raise ValueError("POSITION_ATTRIBUTION_UNKNOWN")
                    if Decimal(quantity) != Decimal(facts.current_abs_position):
                        self._coordinator.reject_execution_action_before_submission(
                            action.execution_action_id,
                            reason_code="EXIT_POSITION_CHANGED_BEFORE_SUBMISSION",
                            observed_at=facts.checked_at,
                        )
                        continue
                check = facts.action_check(
                    activation,
                    action_profile=profile,
                    control_category=(
                        StopCategory.PROTECTION
                        if action.action_kind is ExecutionActionKind.PROTECTION
                        else StopCategory.RISK_REDUCTION_OR_ORDER_MANAGEMENT
                    ),
                    quantity=quantity,
                )
            self._submit_ready(action, check, observed_at=facts.checked_at)

    async def _try_close_activation(
        self,
        activation: PlanActivation,
        facts: ProductRiskReductionFacts,
    ) -> None:
        if Decimal(facts.current_abs_position) != 0:
            return
        if facts.open_order_client_ids or facts.open_algo_client_ids:
            return
        position_fact = facts.position_fact
        if position_fact is None:
            return
        self._coordinator.apply_venue_fact(
            position_fact,
            observed_at=position_fact.received_at,
        )
        actions = self._coordinator.list_execution_actions(activation.activation_id)
        if not actions:
            return
        action_has_fill = {
            action.execution_action_id: any(
                fact.kind is VenueFactKind.FILL
                for fact in self._coordinator.list_venue_facts_for_action(
                    action.execution_action_id
                )
            )
            for action in actions
        }
        entry_fill_seen = activation.has_entry_fill or any(
            action.action_kind is ExecutionActionKind.ENTRY
            and action_has_fill[action.execution_action_id]
            for action in actions
        )
        risk_reduction_fill_seen = self._risk_reduction_fill_seen(actions)
        if (
            activation.lifecycle is PlanLifecycle.RUNNING
            and entry_fill_seen
            and not risk_reduction_fill_seen
        ):
            # A zero position snapshot can briefly lag an entry fill at Binance.
            # Do not let that transient fact close the activation before its
            # protection task can persist and submit the first reduce-only order.
            return

        closure_fact_refs = {position_fact.venue_fact_id}
        for action in actions:
            if action.state in {
                ExecutionActionState.CLOSED,
                ExecutionActionState.NOT_SUBMITTED,
                ExecutionActionState.HANDED_OVER,
            }:
                continue
            if action.state is not ExecutionActionState.OPEN:
                return
            action_facts = self._coordinator.list_venue_facts_for_action(
                action.execution_action_id
            )
            fact_refs = tuple(fact.venue_fact_id for fact in action_facts)
            terminal_status = terminal_order_status(action_facts)
            if terminal_status is None:
                return
            fills_complete = terminal_fills_complete(action, action_facts)
            fees_complete = _fills_have_commissions(action_facts)
            if not fills_complete or not fees_complete:
                return
            closure_fact_refs.update(fact_refs)
            self._coordinator.reconcile_execution_action(
                action.execution_action_id,
                closure_evidence={
                    "order_terminal": True,
                    "terminal_order_status": terminal_status,
                    "fills_complete": fills_complete,
                    "fees_complete": fees_complete,
                    "position_effect_known": True,
                    "position_fact_ref": position_fact.venue_fact_id,
                },
                venue_fact_refs=fact_refs,
                observed_at=facts.checked_at,
            )

        refreshed = self._coordinator.list_execution_actions(
            activation.activation_id
        )
        if any(
            action.state
            not in {
                ExecutionActionState.CLOSED,
                ExecutionActionState.NOT_SUBMITTED,
                ExecutionActionState.HANDED_OVER,
            }
            for action in refreshed
        ):
            return
        user_takeover = activation.lifecycle is PlanLifecycle.USER_TAKEOVER
        takeover_scope = activation.takeover_scope or {}
        handover_command_ref = takeover_scope.get("command_ref")
        if user_takeover and not isinstance(handover_command_ref, str):
            raise ValueError("HANDOVER_COMMAND_REF_REQUIRED")
        self._coordinator.close_activation(
            activation_id=activation.activation_id,
            cutoff=facts.checked_at,
            position_zero=True,
            open_order_refs=(),
            external_activity_conflict=False,
            user_takeover=user_takeover,
            handover_command_ref=(
                handover_command_ref if user_takeover else None
            ),
            fact_refs=tuple(sorted(closure_fact_refs)),
            observed_at=facts.checked_at,
        )

    def _risk_reduction_fill_seen(
        self,
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
                for fact in self._coordinator.list_venue_facts_for_action(
                    action.execution_action_id
                )
            )
            for action in actions
        )

    def _failed_protection_seen(
        self,
        actions: tuple[ExecutionAction, ...],
    ) -> bool:
        for action in actions:
            if action.action_kind is not ExecutionActionKind.PROTECTION:
                continue
            context = action.action_terms.get("execution_context")
            if not isinstance(context, dict) or not isinstance(
                context.get("fill_fact_ref"),
                str,
            ):
                continue
            if action.state is ExecutionActionState.NOT_SUBMITTED:
                return True
            terminal = terminal_order_status(
                self._coordinator.list_venue_facts_for_action(
                    action.execution_action_id
                )
            )
            if terminal in {"CANCELLED", "REJECTED", "EXPIRED"}:
                return True
        return False

    def _submit_ready(
        self,
        action: ExecutionAction,
        check: ActionCheckInput,
        *,
        observed_at: datetime,
    ) -> None:
        if action.state is not ExecutionActionState.READY:
            return
        request = {
            "profile": action.action_terms["action_profile"],
        }
        if action.action_terms.get("quantity") is not None:
            request["quantity"] = action.action_terms["quantity"]
        if action.action_terms.get("trigger_price") is not None:
            request["trigger_price"] = action.action_terms["trigger_price"]
        self._coordinator.process_execution_action(
            action.execution_action_id,
            action_check=check,
            request_payload=request,
            observed_at=observed_at,
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


def _direct_time_exit_due(
    activation: PlanActivation,
    *,
    observed_at: datetime,
) -> bool:
    state = activation.rule_state.get("direct_protection")
    if not isinstance(state, dict):
        return False
    anchor_ref = state.get("anchor_fill_ref")
    fills = state.get("fills")
    if not isinstance(anchor_ref, str) or not isinstance(fills, dict):
        return False
    anchor = fills.get(anchor_ref)
    if not isinstance(anchor, dict):
        return False
    policy = anchor.get("protection_policy")
    fill_time_value = anchor.get("fill_time")
    if not isinstance(policy, dict) or not isinstance(fill_time_value, str):
        return False
    seconds = policy.get("time_exit_seconds")
    if seconds is None:
        return False
    if not isinstance(seconds, int) or seconds <= 0:
        raise ValueError("DIRECT_TIME_EXIT_INVALID")
    try:
        fill_time = datetime.fromisoformat(fill_time_value)
    except ValueError:
        raise ValueError("DIRECT_TIME_EXIT_INVALID") from None
    if fill_time.utcoffset() is None or observed_at.utcoffset() is None:
        raise ValueError("DIRECT_TIME_EXIT_INVALID")
    return observed_at >= fill_time + timedelta(seconds=seconds)


def _fills_have_commissions(facts: tuple[VenueFact, ...]) -> bool:
    fills = tuple(fact for fact in facts if fact.kind is VenueFactKind.FILL)
    if any(fact.payload.get("trade_id") is None for fact in fills):
        return False
    fill_trade_ids = {
        str(fact.payload.get("trade_id"))
        for fact in fills
    }
    commission_trade_ids = {
        str(fact.payload.get("trade_id"))
        for fact in facts
        if fact.kind is VenueFactKind.COMMISSION
        and fact.payload.get("trade_id") is not None
    }
    return fill_trade_ids.issubset(commission_trade_ids)


def _action_has_fill(
    action: ExecutionAction,
    coordinator: ProductResponsibilityCoordinator,
) -> bool:
    return any(
        fact.kind is VenueFactKind.FILL
        for fact in coordinator.list_venue_facts_for_action(
            action.execution_action_id
        )
    )


def _exit_action_resolved(
    action: ExecutionAction,
    coordinator: ProductResponsibilityCoordinator,
) -> bool:
    if action.state in {
        ExecutionActionState.NOT_SUBMITTED,
        ExecutionActionState.CLOSED,
    }:
        return True
    if action.state is not ExecutionActionState.OPEN:
        return False
    action_facts = coordinator.list_venue_facts_for_action(
        action.execution_action_id
    )
    return (
        terminal_order_status(action_facts) is not None
        and terminal_fills_complete(action, action_facts)
        and _fills_have_commissions(action_facts)
    )


def _position_attribution_proven(
    activation: PlanActivation,
    facts: ProductRiskReductionFacts,
    actions: tuple[ExecutionAction, ...],
    coordinator: ProductResponsibilityCoordinator,
) -> bool:
    position_fact = facts.position_fact
    payload = getattr(position_fact, "payload", None)
    if not isinstance(payload, dict):
        return False
    try:
        signed_position = Decimal(str(payload["position_quantity"]))
        reported_abs = Decimal(facts.current_abs_position)
    except (InvalidOperation, KeyError, TypeError, ValueError):
        return False
    if abs(signed_position) != reported_abs:
        return False

    direction_sign = (
        Decimal(1) if activation.direction is Direction.LONG else Decimal(-1)
    )
    expected_quantity = Decimal(0)
    seen_fill_ids: set[str] = set()
    ordinary_client_ids: set[str] = set()
    algo_client_ids: set[str] = set()
    reduction_kinds = {
        ExecutionActionKind.PROTECTION,
        ExecutionActionKind.TAKE_PROFIT,
        ExecutionActionKind.RISK_REDUCTION,
        ExecutionActionKind.EXIT,
    }
    for action in actions:
        if action.client_order_id is not None:
            if action.action_kind in {
                ExecutionActionKind.PROTECTION,
                ExecutionActionKind.TAKE_PROFIT,
            }:
                algo_client_ids.add(action.client_order_id)
            elif action.action_kind is not ExecutionActionKind.CANCEL:
                ordinary_client_ids.add(action.client_order_id)
        if action.action_kind not in {
            ExecutionActionKind.ENTRY,
            *reduction_kinds,
        }:
            continue
        for fact in coordinator.list_venue_facts_for_action(
            action.execution_action_id
        ):
            if fact.kind is not VenueFactKind.FILL:
                continue
            if fact.venue_fact_id in seen_fill_ids:
                return False
            seen_fill_ids.add(fact.venue_fact_id)
            try:
                quantity = Decimal(str(fact.payload["last_quantity"]))
            except (InvalidOperation, KeyError, TypeError, ValueError):
                return False
            if quantity <= 0:
                return False
            expected_quantity += (
                quantity
                if action.action_kind is ExecutionActionKind.ENTRY
                else -quantity
            )
    expected_signed_position = direction_sign * expected_quantity
    if expected_quantity < 0 or signed_position != expected_signed_position:
        return False
    if not set(facts.open_order_client_ids).issubset(ordinary_client_ids):
        return False
    return set(facts.open_algo_client_ids).issubset(algo_client_ids)


def _latest_terminal_order_fact(
    facts: tuple[VenueFact, ...],
) -> VenueFact | None:
    terminal_facts = tuple(
        fact for fact in facts if terminal_order_status((fact,)) is not None
    )
    if not terminal_facts:
        return None
    return max(
        terminal_facts,
        key=lambda fact: (
            fact.source_time or fact.cutoff,
            fact.cutoff,
            fact.received_at,
            fact.venue_fact_id,
        ),
    )


def _stable_id(environment_id: str, kind: str, source_identity: str) -> str:
    return str(
        uuid5(
            NAMESPACE_URL,
            f"urn:halpha:{environment_id}:{kind}:{source_identity}",
        )
    )


def _stable_client_order_id(environment_id: str, source_identity: str) -> str:
    return uuid5(
        NAMESPACE_URL,
        f"urn:halpha:{environment_id}:client-order:{source_identity}",
    ).hex
