"""Run the concrete post-entry responsibilities for the one-shot strategy."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Coroutine
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol
from uuid import NAMESPACE_URL, uuid5

from halpha.capital.models import ActionCheckInput, RiskClass, StopCategory
from halpha.domain_values import canonical_decimal
from halpha.planning.models import PlanActivation, PlanLifecycle
from halpha.planning.transitions import (
    proposed_take_profits_from_fill,
    venue_source_identity,
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

    def process_execution_action(self, execution_action_id: str, **kwargs: Any) -> Any: ...

    def apply_venue_fact(self, fact: VenueFact, **kwargs: Any) -> ExecutionAction | None: ...

    def create_position_exit(self, **kwargs: Any) -> Any: ...

    def create_cancel_for_action(self, **kwargs: Any) -> Any: ...

    def reconcile_execution_action(self, execution_action_id: str, **kwargs: Any) -> ExecutionAction: ...

    def query_unknown_action_if_due(self, execution_action_id: str, **kwargs: Any) -> bool: ...

    def record_unknown_action_not_submitted(
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
    ) -> None:
        self._loop = loop
        self._coordinator = coordinator
        self._fact_provider = fact_provider
        self._entry_order_absence_provider = entry_order_absence_provider
        self._environment_id = environment_id
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._last_fallback_sync: dict[str, float] = {}

    def submit_event(self, event: NormalizedNautilusEvent) -> None:
        action = event.action
        if action is None:
            return
        if action.action_kind is ExecutionActionKind.ENTRY:
            for fact in event.facts:
                if fact.kind is VenueFactKind.FILL:
                    self._schedule(
                        f"PROTECTION:{fact.content_digest}",
                        self._protect_fill(fact),
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
        self._schedule(f"RESUME:{activation_id}", self._resume(activation_id))

    async def sync(self, activation_id: str, *, force: bool = False) -> None:
        """Advance only venue-backed responsibilities already persisted for one activation."""

        activation = self._coordinator.get_activation_snapshot(activation_id)
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
        for action in actions:
            if action.state is ExecutionActionState.SUBMITTED_UNKNOWN:
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
        if activation.lifecycle is PlanLifecycle.EXITING or (
            activation.lifecycle is PlanLifecycle.RUNNING
            and Decimal(facts.current_abs_position) == 0
            and self._risk_reduction_fill_seen(actions)
        ):
            await self._ensure_exit(activation, facts)
        await self._try_close_activation(activation, facts)

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
                and action.state is ExecutionActionState.WORKING
            ):
                await self._create_take_profits(action.execution_action_id)

    async def _protect_fill(self, fill: VenueFact) -> None:
        if fill.action_ref is None or fill.activation_ref is None:
            return
        activation = self._coordinator.get_activation_snapshot(fill.activation_ref)
        facts = await self._fact_provider(activation)
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
        result = self._coordinator.create_protection_for_fill(
            fill_fact=fill,
            plan_event_id=_stable_id(self._environment_id, "plan-event", source_identity),
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
        if action is not None:
            self._submit_ready(action, check, observed_at=facts.checked_at)

    async def _create_take_profits(self, protection_action_id: str) -> None:
        protection = self._coordinator.get_execution_action(protection_action_id)
        if protection.state is not ExecutionActionState.WORKING:
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

    async def _ensure_exit(
        self,
        activation: PlanActivation,
        facts: ProductRiskReductionFacts,
    ) -> None:
        actions = self._coordinator.list_execution_actions(activation.activation_id)
        exit_actions = tuple(
            action
            for action in actions
            if action.action_kind is ExecutionActionKind.EXIT
        )
        if Decimal(facts.current_abs_position) > 0 and not exit_actions:
            position_fact = facts.position_fact
            if position_fact is None:
                raise ValueError("POSITION_FACT_REQUIRED")
            self._coordinator.apply_venue_fact(
                position_fact,
                observed_at=position_fact.received_at,
            )
            reason_ref = f"{activation.activation_id}:EXIT_STRATEGY"
            source_identity = (
                f"{activation.activation_id}:EXIT:"
                f"{position_fact.venue_fact_id}:{reason_ref}"
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
                action_check=facts.action_check(
                    activation,
                    action_profile="REDUCE_OR_CLOSE_MARKET",
                    control_category=StopCategory.RISK_REDUCTION_OR_ORDER_MANAGEMENT,
                    quantity=facts.current_abs_position,
                ),
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
                    facts.action_check(
                        activation,
                        action_profile="REDUCE_OR_CLOSE_MARKET",
                        control_category=(
                            StopCategory.RISK_REDUCTION_OR_ORDER_MANAGEMENT
                        ),
                        quantity=facts.current_abs_position,
                    ),
                    observed_at=facts.checked_at,
                )
            return
        if Decimal(facts.current_abs_position) != 0:
            return
        for target in actions:
            if (
                target.action_kind
                not in {ExecutionActionKind.PROTECTION, ExecutionActionKind.TAKE_PROFIT}
                or target.state
                not in {
                    ExecutionActionState.ACKNOWLEDGED,
                    ExecutionActionState.WORKING,
                    ExecutionActionState.PARTIALLY_FILLED,
                }
                or target.client_order_id is None
            ):
                continue
            reason_ref = (
                f"{activation.activation_id}:EXIT_CANCEL:"
                f"{target.execution_action_id}:v{target.state_version}"
            )
            result = self._coordinator.create_cancel_for_action(
                target_action_id=target.execution_action_id,
                target_endpoint="ALGO",
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
                ExecutionActionState.RECONCILED,
                ExecutionActionState.NOT_SUBMITTED,
                ExecutionActionState.HANDED_OVER,
            }:
                continue
            if action.state not in {
                ExecutionActionState.FILLED,
                ExecutionActionState.CANCELLED,
                ExecutionActionState.REJECTED,
                ExecutionActionState.EXPIRED,
            }:
                return
            action_facts = self._coordinator.list_venue_facts_for_action(
                action.execution_action_id
            )
            fact_refs = tuple(fact.venue_fact_id for fact in action_facts)
            kinds = {fact.kind for fact in action_facts}
            if VenueFactKind.ORDER_STATE not in kinds:
                return
            if action.state is ExecutionActionState.FILLED and not {
                VenueFactKind.FILL,
                VenueFactKind.COMMISSION,
            }.issubset(kinds):
                return
            closure_fact_refs.update(fact_refs)
            self._coordinator.reconcile_execution_action(
                action.execution_action_id,
                closure_evidence={
                    "order_terminal": True,
                    "fills_complete": (
                        action.state is not ExecutionActionState.FILLED
                        or VenueFactKind.FILL in kinds
                    ),
                    "fees_complete": (
                        action.state is not ExecutionActionState.FILLED
                        or VenueFactKind.COMMISSION in kinds
                    ),
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
                ExecutionActionState.RECONCILED,
                ExecutionActionState.NOT_SUBMITTED,
                ExecutionActionState.HANDED_OVER,
            }
            for action in refreshed
        ):
            return
        self._coordinator.close_activation(
            activation_id=activation.activation_id,
            cutoff=facts.checked_at,
            position_zero=True,
            open_order_refs=(),
            external_activity_conflict=False,
            user_takeover=False,
            handover_command_ref=None,
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
