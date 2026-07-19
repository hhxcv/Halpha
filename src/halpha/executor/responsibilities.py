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
from halpha.planning.models import PlanActivation
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


RiskReductionFactProvider = Callable[
    [PlanActivation], Awaitable[ProductRiskReductionFacts]
]


class ProductResponsibilityBoundary:
    """Create protection and take-profit actions from persisted venue facts."""

    def __init__(
        self,
        *,
        loop: asyncio.AbstractEventLoop,
        coordinator: ProductResponsibilityCoordinator,
        fact_provider: RiskReductionFactProvider,
        environment_id: str,
    ) -> None:
        self._loop = loop
        self._coordinator = coordinator
        self._fact_provider = fact_provider
        self._environment_id = environment_id
        self._tasks: dict[str, asyncio.Task[None]] = {}

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

    def resume(self, activation_id: str) -> None:
        self._schedule(f"RESUME:{activation_id}", self._resume(activation_id))

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
            "quantity": action.action_terms["quantity"],
        }
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
