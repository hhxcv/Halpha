from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from halpha.capital.models import AuthorityClass, EnvironmentKind, StopCategory
from halpha.planning.models import PlanActivation, PlanLifecycle, ProtectionState
from halpha.planning.transitions import enter_exit, record_direct_fill, record_first_fill
from halpha.executor.responsibilities import (
    ProductResponsibilityBoundary,
    ProductRiskReductionFacts,
)
from halpha.venue_integration.models import (
    ExecutionActionKind,
    ExecutionActionState,
    VenueFactKind,
    VenueFactSourceClass,
)
from halpha.venue_integration.nautilus_events import NormalizedNautilusEvent


NOW = datetime(2026, 7, 19, 8, tzinfo=UTC)


def _activation(*, first_fill: bool = False) -> PlanActivation:
    activation = PlanActivation(
        activation_id="activation-1",
        environment_id="demo-1",
        environment_kind=EnvironmentKind.DEMO,
        authority_class=AuthorityClass.DEMO_VALIDATION,
        plan_version_ref="plan-version-1",
        account_ref="account-1",
        instrument_ref="BTCUSDT-PERP",
        direction="LONG",
        decision_basis_ref="ONE_SHOT_DONCHIAN_ATR_BREAKOUT@1.0.1",
        framework_strategy_id="HALPHA-TEST",
        target_exposure="0.01",
        rule_state={"deadlines": {}, "condition_judgements": {}, "last_bar_cursors": {}},
        created_at=NOW,
        updated_at=NOW,
    )
    if not first_fill:
        return activation
    return record_first_fill(
        activation,
        entry_action_ref="entry-action",
        fill_fact_ref="fill-fact",
        fill_price="100",
        fill_time=NOW,
        entry_risk_context={
            "trigger_atr": "2",
            "initial_stop_atr_multiple": "1.5",
            "take_profit_1_r": "1.5",
            "take_profit_1_fraction": "0.5",
            "take_profit_2_r": "3",
            "max_hold_bars_15m": 96,
            "indicator_source_digest": "a" * 64,
            "indicator_source_cutoff_ns": 1_773_910_800_000_000_000,
            "quantity_step": "0.001",
            "price_tick_size": "0.1",
            "entry_extension_boundary": "110",
            "sizing_taker_fee_rate": "0.0006",
            "sizing_effective_leverage": "5",
            "instrument_rules_digest": "b" * 64,
        },
        observed_at=NOW,
    )


def _direct_activation_with_time_exit() -> PlanActivation:
    activation = _activation().model_copy(
        update={"decision_basis_ref": "DIRECT_EXECUTION@1"}
    )
    return record_direct_fill(
        activation,
        entry_action_ref="entry-action",
        fill_fact_ref="fill-fact",
        fill_price="100",
        fill_quantity="0.01",
        fill_time=NOW - timedelta(seconds=61),
        protection_policy={
            "initial_stop": {
                "distance_bps": "100",
                "trigger_source": "MARK_PRICE",
                "coverage": "EACH_CONFIRMED_FILL",
            },
            "take_profit_ladder": None,
            "time_exit_seconds": 60,
        },
        price_tick_size="0.1",
        quantity_step="0.001",
        observed_at=NOW - timedelta(seconds=61),
    )


def _facts(
    *,
    current_abs_position: str = "0.01",
    position_fact: object | None = None,
    open_algo_client_ids: tuple[str, ...] = (),
) -> ProductRiskReductionFacts:
    return ProductRiskReductionFacts(
        checked_at=NOW,
        conservative_price="100",
        available_margin="1000",
        actual_margin_mode="ISOLATED",
        actual_leverage="5",
        activation_current_notional="1",
        account_current_notional="1",
        activation_current_margin="0.2",
        current_abs_position=current_abs_position,
        position_fact=position_fact,
        open_algo_client_ids=open_algo_client_ids,
    )


def _action(
    action_id: str,
    kind: ExecutionActionKind,
    *,
    state: ExecutionActionState,
    terms: dict[str, object],
    client_order_id: str | None = None,
    cancel_target: dict[str, object] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        execution_action_id=action_id,
        activation_id="activation-1",
        action_kind=kind,
        state=state,
        state_version=1,
        action_terms=terms,
        client_order_id=client_order_id,
        cancel_target=cancel_target,
    )


def _venue_fact(
    fact_id: str,
    kind: VenueFactKind,
    *,
    status: str | None = None,
    trade_id: str | None = None,
    leaves_quantity: str = "0",
    last_quantity: str | None = None,
    cumulative_filled_quantity: str | None = None,
    position_quantity: str | None = None,
    action_ref: str | None = None,
    activation_ref: str | None = None,
    source_sequence: str = "1",
) -> SimpleNamespace:
    payload: dict[str, object] = {}
    if status is not None:
        payload["status"] = status
    if trade_id is not None:
        payload["trade_id"] = trade_id
    if kind is VenueFactKind.FILL:
        payload["leaves_quantity"] = leaves_quantity
        if last_quantity is not None:
            payload["last_quantity"] = last_quantity
    if cumulative_filled_quantity is not None:
        payload["cumulative_filled_quantity"] = cumulative_filled_quantity
    if position_quantity is not None:
        payload["position_quantity"] = position_quantity
    return SimpleNamespace(
        venue_fact_id=fact_id,
        kind=kind,
        payload=payload,
        source_time=NOW,
        cutoff=NOW,
        received_at=NOW,
        action_ref=action_ref,
        activation_ref=activation_ref,
        source_class=VenueFactSourceClass.VENUE_STREAM,
        source_object_id=fact_id,
        source_sequence=source_sequence,
        content_digest=f"digest-{fact_id}",
    )


class _Coordinator:
    def __init__(self, activation: PlanActivation) -> None:
        self.activation = activation
        self.actions: dict[str, SimpleNamespace] = {}
        self.facts: dict[str, tuple[SimpleNamespace, ...]] = {}
        self.protection_checks = []
        self.take_profit_checks = []
        self.exit_checks = []
        self.exit_requests: list[dict[str, object]] = []
        self.cancel_checks = []
        self.cancel_requests: list[dict[str, object]] = []
        self.applied_facts = []
        self.submissions: list[tuple[str, dict[str, object]]] = []
        self.reconciliations: list[dict[str, object]] = []
        self.closures: list[dict[str, object]] = []
        self.unknown_queries: list[tuple[str, datetime]] = []
        self.absent_actions: list[tuple[str, str, datetime]] = []
        self.rejections: list[tuple[str, str]] = []
        self.called_queries: list[str] = []
        self.takeover_calls: list[tuple[str, datetime]] = []

    def get_activation_snapshot(self, _activation_id: str) -> PlanActivation:
        return self.activation

    def get_execution_action(self, action_id: str) -> SimpleNamespace:
        return self.actions[action_id]

    def list_execution_actions(self, _activation_id: str) -> tuple[SimpleNamespace, ...]:
        return tuple(self.actions.values())

    def list_venue_facts_for_action(self, action_id: str) -> tuple[SimpleNamespace, ...]:
        return self.facts.get(action_id, ())

    def query_unknown_action_if_due(
        self,
        action_id: str,
        *,
        observed_at: datetime,
    ) -> bool:
        self.unknown_queries.append((action_id, observed_at))
        return True

    def query_called_action_identity(self, action_id: str) -> bool:
        action = self.actions[action_id]
        if action.state not in {
            ExecutionActionState.SUBMITTING,
            ExecutionActionState.UNKNOWN,
            ExecutionActionState.OPEN,
        }:
            return False
        self.called_queries.append(action_id)
        return True

    def apply_persisted_user_takeover(
        self,
        *,
        activation_id: str,
        observed_at: datetime,
    ) -> tuple[SimpleNamespace, ...]:
        self.takeover_calls.append((activation_id, observed_at))
        for action in self.actions.values():
            if action.state is ExecutionActionState.READY:
                action.state = ExecutionActionState.HANDED_OVER
        return tuple(self.actions.values())

    def record_unknown_action_not_submitted(
        self,
        action_id: str,
        *,
        reason_code: str,
        observed_at: datetime,
    ) -> SimpleNamespace:
        self.absent_actions.append((action_id, reason_code, observed_at))
        action = self.actions[action_id]
        action.state = ExecutionActionState.NOT_SUBMITTED
        return action

    def create_protection_for_fill(self, **kwargs: object) -> SimpleNamespace:
        self.protection_checks.append(kwargs["action_check"])
        action = _action(
            "protection-action",
            ExecutionActionKind.PROTECTION,
            state=ExecutionActionState.READY,
            terms={
                "action_profile": "PROTECTIVE_STOP_REDUCE_ONLY",
                "quantity": "0.01",
                "trigger_price": "97",
            },
        )
        return SimpleNamespace(execution_action=action)

    def create_take_profits_for_protected_fill(self, **kwargs: object) -> tuple[SimpleNamespace, SimpleNamespace]:
        self.take_profit_checks.extend(kwargs["action_checks"])
        return tuple(
            SimpleNamespace(
                execution_action=_action(
                    f"take-profit-{index}",
                    ExecutionActionKind.TAKE_PROFIT,
                    state=ExecutionActionState.READY,
                    terms={
                        "action_profile": f"TAKE_PROFIT_{index}",
                        "quantity": "0.005",
                        "trigger_price": trigger,
                    },
                )
            )
            for index, trigger in ((1, "104.5"), (2, "109"))
        )

    def process_execution_action(self, action_id: str, **kwargs: object) -> None:
        self.submissions.append((action_id, kwargs["request_payload"]))
        if action_id in self.actions:
            self.actions[action_id].state = ExecutionActionState.SUBMITTING

    def reject_execution_action_before_submission(
        self,
        action_id: str,
        *,
        reason_code: str,
        **_kwargs: object,
    ) -> SimpleNamespace:
        self.rejections.append((action_id, reason_code))
        action = self.actions[action_id]
        action.state = ExecutionActionState.NOT_SUBMITTED
        return action

    def apply_venue_fact(self, fact: object, **_kwargs: object) -> SimpleNamespace | None:
        self.applied_facts.append(fact)
        action_ref = getattr(fact, "action_ref", None)
        if action_ref is None:
            return None
        action = self.actions[action_ref]
        self.facts[action_ref] = (*self.facts.get(action_ref, ()), fact)
        if getattr(fact, "kind", None) in {
            VenueFactKind.ORDER_STATE,
            VenueFactKind.FILL,
        }:
            action.state = ExecutionActionState.OPEN
        return action

    def create_position_exit(self, **kwargs: object) -> SimpleNamespace:
        self.exit_checks.append(kwargs["action_check"])
        self.exit_requests.append(dict(kwargs))
        action = _action(
            "exit-action",
            ExecutionActionKind.EXIT,
            state=ExecutionActionState.READY,
            terms={
                "action_profile": "REDUCE_OR_CLOSE_MARKET",
                "quantity": kwargs["position_quantity"],
            },
            client_order_id="e" * 32,
        )
        self.actions[action.execution_action_id] = action
        return SimpleNamespace(execution_action=action)

    def create_cancel_for_action(self, **kwargs: object) -> SimpleNamespace:
        cancel_index = len(self.cancel_checks)
        self.cancel_checks.append(kwargs["action_check"])
        self.cancel_requests.append(dict(kwargs))
        action = _action(
            "cancel-action" if cancel_index == 0 else f"cancel-action-{cancel_index + 1}",
            ExecutionActionKind.CANCEL,
            state=ExecutionActionState.READY,
            terms={"action_profile": "CANCEL_ORDER", "quantity": None},
        )
        self.actions[action.execution_action_id] = action
        return SimpleNamespace(execution_action=action)

    def reconcile_execution_action(
        self,
        action_id: str,
        **kwargs: object,
    ) -> SimpleNamespace:
        self.reconciliations.append({"action_id": action_id, **kwargs})
        action = self.actions[action_id]
        action.state = ExecutionActionState.CLOSED
        return action

    def reconcile_cancel_from_target_fact(
        self,
        action_id: str,
        **kwargs: object,
    ) -> SimpleNamespace:
        self.reconciliations.append({"action_id": action_id, **kwargs})
        action = self.actions[action_id]
        action.state = ExecutionActionState.CLOSED
        return action

    def close_activation(self, **kwargs: object) -> str:
        self.closures.append(kwargs)
        return "c" * 64


class _SuccessorCoordinator(_Coordinator):
    def create_position_exit(self, **kwargs: object) -> SimpleNamespace:
        self.exit_checks.append(kwargs["action_check"])
        self.exit_requests.append(dict(kwargs))
        action = _action(
            str(kwargs["execution_action_id"]),
            ExecutionActionKind.EXIT,
            state=ExecutionActionState.READY,
            terms={
                "action_profile": "REDUCE_OR_CLOSE_MARKET",
                "quantity": kwargs["position_quantity"],
            },
            client_order_id=str(kwargs["client_order_id"]),
        )
        action.source_identity = (
            f"activation-1:EXIT:{kwargs['position_fact_ref']}:"
            f"{kwargs['reason_ref']}"
        )
        self.actions[action.execution_action_id] = action
        return SimpleNamespace(execution_action=action)


def test_user_takeover_hands_over_ready_actions_and_only_queries_called_identity() -> None:
    async def scenario() -> _Coordinator:
        activation = _activation().model_copy(
            update={
                "lifecycle": PlanLifecycle.USER_TAKEOVER,
                "takeover_scope": {"command_ref": "command-takeover-1"},
            }
        )
        coordinator = _Coordinator(activation)
        coordinator.actions["entry-ready"] = _action(
            "entry-ready",
            ExecutionActionKind.ENTRY,
            state=ExecutionActionState.READY,
            terms={},
            client_order_id="a" * 32,
        )
        coordinator.actions["entry-open"] = _action(
            "entry-open",
            ExecutionActionKind.ENTRY,
            state=ExecutionActionState.OPEN,
            terms={},
            client_order_id="b" * 32,
        )
        boundary = ProductResponsibilityBoundary(
            loop=asyncio.get_running_loop(),
            coordinator=coordinator,
            fact_provider=lambda _activation: asyncio.sleep(0, result=_facts()),
            environment_id="demo-1",
        )

        await boundary.sync("activation-1", force=True)
        return coordinator

    coordinator = asyncio.run(scenario())

    assert coordinator.actions["entry-ready"].state is ExecutionActionState.HANDED_OVER
    assert coordinator.called_queries == ["entry-open"]
    assert coordinator.submissions == []
    assert len(coordinator.takeover_calls) == 1


def test_user_takeover_closure_preserves_handover_command_identity() -> None:
    async def scenario() -> _Coordinator:
        activation = _activation().model_copy(
            update={
                "lifecycle": PlanLifecycle.USER_TAKEOVER,
                "takeover_scope": {"command_ref": "command-takeover-1"},
            }
        )
        coordinator = _Coordinator(activation)
        coordinator.actions["entry-ready"] = _action(
            "entry-ready",
            ExecutionActionKind.ENTRY,
            state=ExecutionActionState.READY,
            terms={},
            client_order_id="a" * 32,
        )
        position = _venue_fact(
            "position-zero",
            VenueFactKind.POSITION_STATE,
            position_quantity="0",
        )
        boundary = ProductResponsibilityBoundary(
            loop=asyncio.get_running_loop(),
            coordinator=coordinator,
            fact_provider=lambda _activation: asyncio.sleep(
                0,
                result=_facts(current_abs_position="0", position_fact=position),
            ),
            environment_id="demo-1",
        )

        await boundary.sync("activation-1", force=True)
        return coordinator

    coordinator = asyncio.run(scenario())

    assert len(coordinator.closures) == 1
    assert coordinator.closures[0]["user_takeover"] is True
    assert coordinator.closures[0]["handover_command_ref"] == "command-takeover-1"
    assert coordinator.closures[0]["fact_refs"] == ("position-zero",)


def test_late_fill_event_during_user_takeover_never_creates_protection() -> None:
    async def scenario() -> _Coordinator:
        activation = _activation().model_copy(
            update={
                "lifecycle": PlanLifecycle.USER_TAKEOVER,
                "takeover_scope": {"command_ref": "command-takeover-1"},
            }
        )
        coordinator = _Coordinator(activation)
        entry = _action(
            "entry-open",
            ExecutionActionKind.ENTRY,
            state=ExecutionActionState.OPEN,
            terms={},
            client_order_id="a" * 32,
        )
        coordinator.actions[entry.execution_action_id] = entry
        boundary = ProductResponsibilityBoundary(
            loop=asyncio.get_running_loop(),
            coordinator=coordinator,
            fact_provider=lambda _activation: asyncio.sleep(0, result=_facts()),
            environment_id="demo-1",
        )
        fill = _venue_fact(
            "late-fill",
            VenueFactKind.FILL,
            trade_id="trade-late",
            last_quantity="0.01",
            action_ref=entry.execution_action_id,
            activation_ref=activation.activation_id,
        )

        boundary.submit_event(NormalizedNautilusEvent(action=entry, facts=(fill,)))
        await boundary.wait_idle()
        return coordinator

    coordinator = asyncio.run(scenario())

    assert coordinator.protection_checks == []
    assert coordinator.submissions == []
    assert coordinator.called_queries == ["entry-open"]


def test_waiting_activation_without_actions_reuses_framework_stream_without_account_poll() -> None:
    async def scenario() -> int:
        fact_reads = 0

        async def read_facts(_activation: PlanActivation) -> ProductRiskReductionFacts:
            nonlocal fact_reads
            fact_reads += 1
            return _facts()

        boundary = ProductResponsibilityBoundary(
            loop=asyncio.get_running_loop(),
            coordinator=_Coordinator(_activation()),
            fact_provider=read_facts,
            environment_id="demo-1",
        )

        await boundary.sync("activation-1")
        return fact_reads

    assert asyncio.run(scenario()) == 0


def test_running_responsibility_uses_framework_events_between_bounded_fallback_polls() -> None:
    async def scenario() -> int:
        fact_reads = 0

        async def read_facts(_activation: PlanActivation) -> ProductRiskReductionFacts:
            nonlocal fact_reads
            fact_reads += 1
            return _facts()

        coordinator = _Coordinator(_activation(first_fill=True))
        coordinator.actions["working-protection"] = _action(
            "working-protection",
            ExecutionActionKind.PROTECTION,
            state=ExecutionActionState.OPEN,
            terms={"quantity": "0.01"},
            client_order_id="a" * 32,
        )
        boundary = ProductResponsibilityBoundary(
            loop=asyncio.get_running_loop(),
            coordinator=coordinator,
            fact_provider=read_facts,
            environment_id="demo-1",
        )

        await boundary.sync("activation-1")
        await boundary.sync("activation-1")
        return fact_reads

    assert asyncio.run(scenario()) == 1


def test_risk_reduction_fill_triggers_immediate_framework_event_sync() -> None:
    async def scenario() -> int:
        fact_reads = 0

        async def read_facts(_activation: PlanActivation) -> ProductRiskReductionFacts:
            nonlocal fact_reads
            fact_reads += 1
            return _facts()

        coordinator = _Coordinator(_activation(first_fill=True))
        take_profit = _action(
            "take-profit-action",
            ExecutionActionKind.TAKE_PROFIT,
            state=ExecutionActionState.OPEN,
            terms={"quantity": "0.005"},
            client_order_id="b" * 32,
        )
        coordinator.actions[take_profit.execution_action_id] = take_profit
        boundary = ProductResponsibilityBoundary(
            loop=asyncio.get_running_loop(),
            coordinator=coordinator,
            fact_provider=read_facts,
            environment_id="demo-1",
        )
        fill = SimpleNamespace(
            kind=VenueFactKind.FILL,
            content_digest="f" * 64,
            payload={},
        )

        await boundary.sync("activation-1")
        boundary.submit_event(
            NormalizedNautilusEvent(action=take_profit, facts=(fill,))
        )
        await boundary.wait_idle()
        return fact_reads

    assert asyncio.run(scenario()) == 2


def test_entry_fill_creates_and_submits_one_reduce_only_protection() -> None:
    async def scenario() -> _Coordinator:
        coordinator = _Coordinator(_activation())
        boundary = ProductResponsibilityBoundary(
            loop=asyncio.get_running_loop(),
            coordinator=coordinator,
            fact_provider=lambda _activation: asyncio.sleep(0, result=_facts()),
            environment_id="demo-1",
        )
        fill = SimpleNamespace(
            kind=VenueFactKind.FILL,
            content_digest="c" * 64,
            action_ref="entry-action",
            activation_ref="activation-1",
            payload={"last_quantity": "0.01"},
            source_class=VenueFactSourceClass.VENUE_STREAM,
            source_object_id="trade-1",
            source_sequence="1",
            venue_fact_id="fill-fact",
            cutoff=NOW,
        )
        entry = _action(
            "entry-action",
            ExecutionActionKind.ENTRY,
            state=ExecutionActionState.OPEN,
            terms={},
        )

        boundary.submit_event(NormalizedNautilusEvent(action=entry, facts=(fill,)))
        await boundary.wait_idle()
        return coordinator

    coordinator = asyncio.run(scenario())

    assert len(coordinator.protection_checks) == 1
    check = coordinator.protection_checks[0]
    assert check.control_category is StopCategory.PROTECTION
    assert check.would_reverse_position is False
    assert coordinator.submissions == [
        (
            "protection-action",
            {
                "profile": "PROTECTIVE_STOP_REDUCE_ONLY",
                "quantity": "0.01",
                "trigger_price": "97",
            },
        )
    ]


def test_sync_retries_persisted_entry_fill_after_transient_protection_failure() -> None:
    class TransientProtectionCoordinator(_Coordinator):
        def __init__(self, activation: PlanActivation) -> None:
            super().__init__(activation)
            self.protection_attempts = 0

        def create_protection_for_fill(self, **kwargs: object) -> SimpleNamespace:
            self.protection_attempts += 1
            if self.protection_attempts == 1:
                raise RuntimeError("TRANSIENT_PROTECTION_TRANSACTION_FAILURE")
            fill = kwargs["fill_fact"]
            action = _action(
                "protection-replayed",
                ExecutionActionKind.PROTECTION,
                state=ExecutionActionState.READY,
                terms={
                    "action_profile": "PROTECTIVE_STOP_REDUCE_ONLY",
                    "quantity": "0.01",
                    "trigger_price": "97",
                    "execution_context": {
                        "fill_fact_ref": fill.venue_fact_id,
                    },
                },
                client_order_id="a" * 32,
            )
            self.actions[action.execution_action_id] = action
            return SimpleNamespace(execution_action=action)

    async def scenario() -> TransientProtectionCoordinator:
        coordinator = TransientProtectionCoordinator(_activation(first_fill=True))
        entry = _action(
            "entry-action",
            ExecutionActionKind.ENTRY,
            state=ExecutionActionState.OPEN,
            terms={"quantity": "0.01"},
        )
        coordinator.actions[entry.execution_action_id] = entry
        coordinator.facts[entry.execution_action_id] = (
            _venue_fact(
                "fill-fact",
                VenueFactKind.FILL,
                trade_id="entry-trade",
                last_quantity="0.01",
                action_ref=entry.execution_action_id,
                activation_ref="activation-1",
            ),
        )
        boundary = ProductResponsibilityBoundary(
            loop=asyncio.get_running_loop(),
            coordinator=coordinator,
            fact_provider=lambda _activation: asyncio.sleep(0, result=_facts()),
            environment_id="demo-1",
        )

        with pytest.raises(
            RuntimeError,
            match="TRANSIENT_PROTECTION_TRANSACTION_FAILURE",
        ):
            await boundary.sync("activation-1", force=True)
        await boundary.sync("activation-1", force=True)
        return coordinator

    coordinator = asyncio.run(scenario())
    assert coordinator.protection_attempts == 2
    assert coordinator.submissions == [
        (
            "protection-replayed",
            {
                "profile": "PROTECTIVE_STOP_REDUCE_ONLY",
                "quantity": "0.01",
                "trigger_price": "97",
            },
        )
    ]


@pytest.mark.parametrize(
    ("protection_state", "terminal_status"),
    (
        (ExecutionActionState.NOT_SUBMITTED, None),
        (ExecutionActionState.OPEN, "REJECTED"),
        (ExecutionActionState.OPEN, "EXPIRED"),
    ),
)
def test_failed_protection_forms_attributed_market_exit(
    protection_state: ExecutionActionState,
    terminal_status: str | None,
) -> None:
    async def scenario() -> _Coordinator:
        coordinator = _Coordinator(_activation(first_fill=True))
        entry = _action(
            "entry-action",
            ExecutionActionKind.ENTRY,
            state=ExecutionActionState.CLOSED,
            terms={"quantity": "0.01"},
        )
        coordinator.actions[entry.execution_action_id] = entry
        fill = _venue_fact(
            "fill-fact",
            VenueFactKind.FILL,
            trade_id="entry-trade",
            last_quantity="0.01",
            action_ref=entry.execution_action_id,
            activation_ref="activation-1",
        )
        coordinator.facts[entry.execution_action_id] = (fill,)
        protection = _action(
            "failed-protection",
            ExecutionActionKind.PROTECTION,
            state=protection_state,
            terms={
                "action_profile": "PROTECTIVE_STOP_REDUCE_ONLY",
                "quantity": "0.01",
                "execution_context": {"fill_fact_ref": fill.venue_fact_id},
            },
            client_order_id="a" * 32,
        )
        coordinator.actions[protection.execution_action_id] = protection
        if terminal_status is not None:
            coordinator.facts[protection.execution_action_id] = (
                _venue_fact(
                    "protection-terminal",
                    VenueFactKind.ORDER_STATE,
                    status=terminal_status,
                    cumulative_filled_quantity="0",
                ),
            )
        position_fact = _venue_fact(
            "position-current",
            VenueFactKind.POSITION_STATE,
            position_quantity="0.01",
        )
        boundary = ProductResponsibilityBoundary(
            loop=asyncio.get_running_loop(),
            coordinator=coordinator,
            fact_provider=lambda _activation: asyncio.sleep(
                0,
                result=_facts(position_fact=position_fact),
            ),
            environment_id="demo-1",
        )

        await boundary.sync("activation-1", force=True)
        return coordinator

    coordinator = asyncio.run(scenario())
    assert coordinator.exit_requests[0]["reason_ref"].endswith("PROTECTION_GAP")
    assert coordinator.submissions[-1] == (
        "exit-action",
        {"profile": "REDUCE_OR_CLOSE_MARKET", "quantity": "0.01"},
    )


def test_unprotectable_fill_callback_immediately_forms_attributed_market_exit() -> None:
    class UnprotectableFillCoordinator(_Coordinator):
        def create_protection_for_fill(self, **kwargs: object) -> SimpleNamespace:
            self.protection_checks.append(kwargs["action_check"])
            self.activation = self.activation.model_copy(
                update={
                    "has_entry_fill": True,
                    "entry_opportunity_consumed": True,
                    "protection_state": ProtectionState.GAP,
                    "state_version": self.activation.state_version + 1,
                }
            )
            return SimpleNamespace(execution_action=None)

    async def scenario() -> UnprotectableFillCoordinator:
        coordinator = UnprotectableFillCoordinator(_activation())
        entry = _action(
            "entry-action",
            ExecutionActionKind.ENTRY,
            state=ExecutionActionState.CLOSED,
            terms={"quantity": "0.01"},
        )
        fill = _venue_fact(
            "fill-invalid-protection-price",
            VenueFactKind.FILL,
            trade_id="entry-trade",
            last_quantity="0.01",
            action_ref=entry.execution_action_id,
            activation_ref="activation-1",
        )
        coordinator.actions[entry.execution_action_id] = entry
        coordinator.facts[entry.execution_action_id] = (fill,)
        position_fact = _venue_fact(
            "position-current",
            VenueFactKind.POSITION_STATE,
            position_quantity="0.01",
        )
        boundary = ProductResponsibilityBoundary(
            loop=asyncio.get_running_loop(),
            coordinator=coordinator,
            fact_provider=lambda _activation: asyncio.sleep(
                0,
                result=_facts(position_fact=position_fact),
            ),
            environment_id="demo-1",
        )

        boundary.submit_event(NormalizedNautilusEvent(action=entry, facts=(fill,)))
        await boundary.wait_idle()
        return coordinator

    coordinator = asyncio.run(scenario())
    assert len(coordinator.protection_checks) == 2
    assert coordinator.exit_requests[0]["reason_ref"].endswith("PROTECTION_GAP")
    assert coordinator.submissions == [
        ("exit-action", {"profile": "REDUCE_OR_CLOSE_MARKET", "quantity": "0.01"})
    ]


def test_protection_gap_exit_does_not_wait_for_entry_commission() -> None:
    async def scenario() -> _Coordinator:
        coordinator = _Coordinator(_activation(first_fill=True))
        entry = _action(
            "entry-action",
            ExecutionActionKind.ENTRY,
            state=ExecutionActionState.OPEN,
            terms={"quantity": "0.01"},
        )
        fill = _venue_fact(
            "fill-fact",
            VenueFactKind.FILL,
            trade_id="entry-trade",
            last_quantity="0.01",
            action_ref=entry.execution_action_id,
            activation_ref="activation-1",
        )
        coordinator.actions[entry.execution_action_id] = entry
        coordinator.facts[entry.execution_action_id] = (
            fill,
            _venue_fact(
                "entry-filled",
                VenueFactKind.ORDER_STATE,
                status="FILLED",
                cumulative_filled_quantity="0.01",
            ),
        )
        protection = _action(
            "protection-denied",
            ExecutionActionKind.PROTECTION,
            state=ExecutionActionState.NOT_SUBMITTED,
            terms={
                "quantity": "0.01",
                "execution_context": {"fill_fact_ref": fill.venue_fact_id},
            },
        )
        coordinator.actions[protection.execution_action_id] = protection
        position_fact = _venue_fact(
            "position-current",
            VenueFactKind.POSITION_STATE,
            position_quantity="0.01",
        )
        boundary = ProductResponsibilityBoundary(
            loop=asyncio.get_running_loop(),
            coordinator=coordinator,
            fact_provider=lambda _activation: asyncio.sleep(
                0,
                result=_facts(position_fact=position_fact),
            ),
            environment_id="demo-1",
        )

        await boundary.sync("activation-1", force=True)
        return coordinator

    coordinator = asyncio.run(scenario())
    assert coordinator.exit_requests[0]["reason_ref"].endswith("PROTECTION_GAP")
    assert coordinator.closures == []
    assert coordinator.submissions[-1] == (
        "exit-action",
        {"profile": "REDUCE_OR_CLOSE_MARKET", "quantity": "0.01"},
    )


def test_protection_denied_callback_immediately_forms_exit_without_venue_fact() -> None:
    async def scenario() -> _Coordinator:
        coordinator = _Coordinator(_activation(first_fill=True))
        entry = _action(
            "entry-action",
            ExecutionActionKind.ENTRY,
            state=ExecutionActionState.CLOSED,
            terms={"quantity": "0.01"},
        )
        fill = _venue_fact(
            "fill-fact",
            VenueFactKind.FILL,
            trade_id="entry-trade",
            last_quantity="0.01",
            action_ref=entry.execution_action_id,
            activation_ref="activation-1",
        )
        protection = _action(
            "protection-denied",
            ExecutionActionKind.PROTECTION,
            state=ExecutionActionState.NOT_SUBMITTED,
            terms={
                "quantity": "0.01",
                "execution_context": {"fill_fact_ref": fill.venue_fact_id},
            },
        )
        coordinator.actions.update(
            {
                entry.execution_action_id: entry,
                protection.execution_action_id: protection,
            }
        )
        coordinator.facts[entry.execution_action_id] = (fill,)
        position_fact = _venue_fact(
            "position-current",
            VenueFactKind.POSITION_STATE,
            position_quantity="0.01",
        )
        boundary = ProductResponsibilityBoundary(
            loop=asyncio.get_running_loop(),
            coordinator=coordinator,
            fact_provider=lambda _activation: asyncio.sleep(
                0,
                result=_facts(position_fact=position_fact),
            ),
            environment_id="demo-1",
        )

        boundary.submit_event(
            NormalizedNautilusEvent(
                action=protection,
                facts=(),
                definitely_not_submitted=True,
            )
        )
        await boundary.wait_idle()
        return coordinator

    coordinator = asyncio.run(scenario())
    assert coordinator.exit_requests[0]["reason_ref"].endswith("PROTECTION_GAP")
    assert coordinator.submissions == [
        ("exit-action", {"profile": "REDUCE_OR_CLOSE_MARKET", "quantity": "0.01"})
    ]


def test_existing_gap_still_persists_late_fill_responsibility_before_exit() -> None:
    class ExistingGapCoordinator(_Coordinator):
        def __init__(self, activation: PlanActivation) -> None:
            super().__init__(activation)
            self.gap_fill_refs: list[str] = []

        def create_protection_for_fill(self, **kwargs: object) -> SimpleNamespace:
            fill = kwargs["fill_fact"]
            self.gap_fill_refs.append(fill.venue_fact_id)
            return SimpleNamespace(execution_action=None)

    async def scenario() -> ExistingGapCoordinator:
        activation = _activation().model_copy(
            update={"protection_state": ProtectionState.GAP}
        )
        coordinator = ExistingGapCoordinator(activation)
        entry = _action(
            "entry-late-fill",
            ExecutionActionKind.ENTRY,
            state=ExecutionActionState.CLOSED,
            terms={"quantity": "0.01"},
        )
        late_fill = _venue_fact(
            "late-fill-after-gap",
            VenueFactKind.FILL,
            trade_id="late-entry-trade",
            last_quantity="0.01",
            action_ref=entry.execution_action_id,
            activation_ref="activation-1",
        )
        coordinator.actions[entry.execution_action_id] = entry
        coordinator.facts[entry.execution_action_id] = (late_fill,)
        position_fact = _venue_fact(
            "position-current",
            VenueFactKind.POSITION_STATE,
            position_quantity="0.01",
        )
        boundary = ProductResponsibilityBoundary(
            loop=asyncio.get_running_loop(),
            coordinator=coordinator,
            fact_provider=lambda _activation: asyncio.sleep(
                0,
                result=_facts(position_fact=position_fact),
            ),
            environment_id="demo-1",
        )

        await boundary.sync("activation-1", force=True)
        return coordinator

    coordinator = asyncio.run(scenario())
    assert coordinator.gap_fill_refs == ["late-fill-after-gap"]
    assert coordinator.exit_requests[0]["reason_ref"].endswith("PROTECTION_GAP")


def test_sync_recovers_take_profit_from_persisted_working_protection() -> None:
    class PersistingTakeProfitCoordinator(_Coordinator):
        def create_take_profits_for_protected_fill(
            self,
            **kwargs: object,
        ) -> tuple[SimpleNamespace, SimpleNamespace]:
            existing = tuple(
                action
                for action in self.actions.values()
                if action.action_kind is ExecutionActionKind.TAKE_PROFIT
            )
            if existing:
                return tuple(
                    SimpleNamespace(execution_action=action) for action in existing
                )  # type: ignore[return-value]
            results = super().create_take_profits_for_protected_fill(**kwargs)
            for result in results:
                action = result.execution_action
                self.actions[action.execution_action_id] = action
            return results

    async def scenario() -> PersistingTakeProfitCoordinator:
        coordinator = PersistingTakeProfitCoordinator(_activation(first_fill=True))
        entry = _action(
            "entry-action",
            ExecutionActionKind.ENTRY,
            state=ExecutionActionState.CLOSED,
            terms={"quantity": "0.01"},
        )
        fill = _venue_fact(
            "fill-fact",
            VenueFactKind.FILL,
            trade_id="entry-trade",
            last_quantity="0.01",
            action_ref=entry.execution_action_id,
            activation_ref="activation-1",
        )
        protection = _action(
            "protection-working",
            ExecutionActionKind.PROTECTION,
            state=ExecutionActionState.OPEN,
            terms={
                "quantity": "0.01",
                "execution_context": {
                    "entry_action_ref": entry.execution_action_id,
                    "fill_fact_ref": fill.venue_fact_id,
                    "fill_source_identity": "entry-trade:1",
                },
            },
        )
        coordinator.actions.update(
            {
                entry.execution_action_id: entry,
                protection.execution_action_id: protection,
            }
        )
        coordinator.facts[entry.execution_action_id] = (fill,)
        coordinator.facts[protection.execution_action_id] = (
            _venue_fact(
                "protection-working-fact",
                VenueFactKind.ORDER_STATE,
                status="WORKING",
            ),
        )
        boundary = ProductResponsibilityBoundary(
            loop=asyncio.get_running_loop(),
            coordinator=coordinator,
            fact_provider=lambda _activation: asyncio.sleep(0, result=_facts()),
            environment_id="demo-1",
        )

        await boundary.sync("activation-1", force=True)
        await boundary.sync("activation-1", force=True)
        return coordinator

    coordinator = asyncio.run(scenario())
    assert [action_id for action_id, _payload in coordinator.submissions] == [
        "take-profit-1",
        "take-profit-2",
    ]


def test_direct_time_exit_creates_one_reduce_only_position_exit() -> None:
    async def scenario() -> _Coordinator:
        coordinator = _Coordinator(_direct_activation_with_time_exit())
        coordinator.actions["entry-action"] = _action(
            "entry-action",
            ExecutionActionKind.ENTRY,
            state=ExecutionActionState.CLOSED,
            terms={"quantity": "0.01"},
        )
        coordinator.facts["entry-action"] = (
            _venue_fact(
                "entry-fill",
                VenueFactKind.FILL,
                trade_id="entry-trade",
                last_quantity="0.01",
            ),
        )
        position_fact = _venue_fact(
            "position-current",
            VenueFactKind.POSITION_STATE,
            position_quantity="0.01",
        )
        boundary = ProductResponsibilityBoundary(
            loop=asyncio.get_running_loop(),
            coordinator=coordinator,
            fact_provider=lambda _activation: asyncio.sleep(
                0,
                result=_facts(position_fact=position_fact),
            ),
            environment_id="demo-1",
        )

        await boundary.sync("activation-1", force=True)
        return coordinator

    coordinator = asyncio.run(scenario())
    assert len(coordinator.exit_requests) == 1
    assert coordinator.exit_requests[0]["position_quantity"] == "0.01"
    assert coordinator.submissions == [
        ("exit-action", {"profile": "REDUCE_OR_CLOSE_MARKET", "quantity": "0.01"})
    ]


def test_direct_time_exit_cancels_open_entry_before_sizing_position_exit() -> None:
    async def scenario() -> tuple[_Coordinator, int]:
        coordinator = _Coordinator(_direct_activation_with_time_exit())
        entry = _action(
            "entry-action",
            ExecutionActionKind.ENTRY,
            state=ExecutionActionState.OPEN,
            terms={"quantity": "0.02"},
            client_order_id="b" * 32,
        )
        coordinator.actions[entry.execution_action_id] = entry
        coordinator.facts[entry.execution_action_id] = (
            _venue_fact("entry-working", VenueFactKind.ORDER_STATE, status="WORKING"),
            _venue_fact(
                "entry-fill",
                VenueFactKind.FILL,
                trade_id="entry-trade",
                leaves_quantity="0.01",
                last_quantity="0.01",
            ),
            _venue_fact(
                "entry-commission",
                VenueFactKind.COMMISSION,
                trade_id="entry-trade",
            ),
        )
        position_fact = _venue_fact(
            "position-current",
            VenueFactKind.POSITION_STATE,
            position_quantity="0.01",
        )
        boundary = ProductResponsibilityBoundary(
            loop=asyncio.get_running_loop(),
            coordinator=coordinator,
            fact_provider=lambda _activation: asyncio.sleep(
                0,
                result=_facts(position_fact=position_fact),
            ),
            environment_id="demo-1",
        )

        await boundary.sync("activation-1", force=True)
        submissions_after_cancel = len(coordinator.submissions)
        assert coordinator.exit_requests == []
        coordinator.facts[entry.execution_action_id] = (
            _venue_fact(
                "entry-fill",
                VenueFactKind.FILL,
                trade_id="entry-trade",
                leaves_quantity="0.01",
                last_quantity="0.01",
            ),
            _venue_fact(
                "entry-commission",
                VenueFactKind.COMMISSION,
                trade_id="entry-trade",
            ),
            _venue_fact(
                "entry-cancelled",
                VenueFactKind.ORDER_STATE,
                status="CANCELLED",
                cumulative_filled_quantity="0.01",
            ),
        )
        await boundary.sync("activation-1", force=True)
        return coordinator, submissions_after_cancel

    coordinator, submissions_after_cancel = asyncio.run(scenario())
    assert submissions_after_cancel == 1
    assert coordinator.cancel_requests[0]["target_endpoint"] == "ORDINARY"
    assert coordinator.exit_requests[0]["position_quantity"] == "0.01"
    assert coordinator.submissions[-1] == (
        "exit-action",
        {"profile": "REDUCE_OR_CLOSE_MARKET", "quantity": "0.01"},
    )


def test_direct_time_exit_reuses_unknown_cancel_for_same_entry_identity() -> None:
    async def scenario() -> _Coordinator:
        coordinator = _Coordinator(_direct_activation_with_time_exit())
        entry = _action(
            "entry-action",
            ExecutionActionKind.ENTRY,
            state=ExecutionActionState.OPEN,
            terms={"quantity": "0.02"},
            client_order_id="b" * 32,
        )
        entry.state_version = 7
        coordinator.actions[entry.execution_action_id] = entry
        coordinator.facts[entry.execution_action_id] = (
            _venue_fact("entry-working", VenueFactKind.ORDER_STATE, status="WORKING"),
        )
        existing_cancel = _action(
            "entry-cancel-unknown",
            ExecutionActionKind.CANCEL,
            state=ExecutionActionState.UNKNOWN,
            terms={"action_profile": "CANCEL_ORDER"},
            cancel_target={
                "client_order_id": entry.client_order_id,
                "endpoint": "ORDINARY",
            },
        )
        coordinator.actions[existing_cancel.execution_action_id] = existing_cancel
        boundary = ProductResponsibilityBoundary(
            loop=asyncio.get_running_loop(),
            coordinator=coordinator,
            fact_provider=lambda _activation: asyncio.sleep(
                0,
                result=_facts(
                    position_fact=_venue_fact(
                        "position-current",
                        VenueFactKind.POSITION_STATE,
                    )
                ),
            ),
            environment_id="demo-1",
        )

        await boundary.sync("activation-1", force=True)
        return coordinator

    coordinator = asyncio.run(scenario())
    assert coordinator.cancel_requests == []
    assert coordinator.unknown_queries == [("entry-cancel-unknown", NOW)]
    assert coordinator.exit_requests == []


def test_recovery_barrier_defers_responsibility_mutations_until_resume() -> None:
    async def scenario() -> tuple[_Coordinator, int]:
        coordinator = _Coordinator(_activation(first_fill=True))
        protection = _action(
            "protection-ready",
            ExecutionActionKind.PROTECTION,
            state=ExecutionActionState.READY,
            terms={
                "action_profile": "PROTECTIVE_STOP_REDUCE_ONLY",
                "quantity": "0.01",
                "trigger_price": "97",
            },
        )
        coordinator.actions[protection.execution_action_id] = protection
        enabled = False
        fact_reads = 0

        async def read_facts(_activation: PlanActivation) -> ProductRiskReductionFacts:
            nonlocal fact_reads
            fact_reads += 1
            return _facts()

        boundary = ProductResponsibilityBoundary(
            loop=asyncio.get_running_loop(),
            coordinator=coordinator,
            fact_provider=read_facts,
            environment_id="demo-1",
            submission_enabled=lambda: enabled,
        )

        await boundary.sync("activation-1", force=True)
        boundary.resume("activation-1")
        await asyncio.sleep(0)
        assert coordinator.submissions == []
        assert fact_reads == 0

        enabled = True
        await boundary.sync("activation-1", force=True)
        return coordinator, fact_reads

    coordinator, fact_reads = asyncio.run(scenario())
    assert fact_reads == 1
    assert coordinator.submissions == [
        (
            "protection-ready",
            {
                "profile": "PROTECTIVE_STOP_REDUCE_ONLY",
                "quantity": "0.01",
                "trigger_price": "97",
            },
        )
    ]


def test_restart_resubmits_ready_protection_that_was_proven_never_called() -> None:
    async def scenario() -> _Coordinator:
        coordinator = _Coordinator(_activation(first_fill=True))
        protection = _action(
            "protection-ready",
            ExecutionActionKind.PROTECTION,
            state=ExecutionActionState.READY,
            terms={
                "action_profile": "PROTECTIVE_STOP_REDUCE_ONLY",
                "quantity": "0.01",
                "trigger_price": "97",
            },
            client_order_id="a" * 32,
        )
        coordinator.actions[protection.execution_action_id] = protection
        boundary = ProductResponsibilityBoundary(
            loop=asyncio.get_running_loop(),
            coordinator=coordinator,
            fact_provider=lambda _activation: asyncio.sleep(0, result=_facts()),
            environment_id="demo-1",
        )

        await boundary.sync("activation-1", force=True)
        return coordinator

    coordinator = asyncio.run(scenario())
    assert coordinator.submissions == [
        (
            "protection-ready",
            {
                "profile": "PROTECTIVE_STOP_REDUCE_ONLY",
                "quantity": "0.01",
                "trigger_price": "97",
            },
        )
    ]
    assert coordinator.actions["protection-ready"].state is ExecutionActionState.SUBMITTING


def test_sync_queries_unknown_action_by_original_identity() -> None:
    async def scenario() -> _Coordinator:
        coordinator = _Coordinator(_activation())
        unknown = _action(
            "entry-action-unknown",
            ExecutionActionKind.ENTRY,
            state=ExecutionActionState.UNKNOWN,
            terms={},
            client_order_id="0123456789abcdef0123456789abcdef",
        )
        coordinator.actions[unknown.execution_action_id] = unknown
        boundary = ProductResponsibilityBoundary(
            loop=asyncio.get_running_loop(),
            coordinator=coordinator,
            fact_provider=lambda _activation: asyncio.sleep(0, result=_facts()),
            environment_id="demo-1",
        )

        await boundary.sync("activation-1")
        return coordinator

    coordinator = asyncio.run(scenario())

    assert coordinator.unknown_queries == [("entry-action-unknown", NOW)]


def test_unknown_cancel_uses_framework_original_identity_query() -> None:
    async def scenario() -> _Coordinator:
        coordinator = _Coordinator(_activation(first_fill=True))
        target = _action(
            "protection-action",
            ExecutionActionKind.PROTECTION,
            state=ExecutionActionState.OPEN,
            terms={"quantity": "0.01"},
            client_order_id="a" * 32,
        )
        cancel = _action(
            "cancel-action-unknown",
            ExecutionActionKind.CANCEL,
            state=ExecutionActionState.UNKNOWN,
            terms={"action_profile": "CANCEL_ORDER"},
            cancel_target={"client_order_id": "a" * 32, "endpoint": "ALGO"},
        )
        coordinator.actions[target.execution_action_id] = target
        coordinator.facts[target.execution_action_id] = (
            _venue_fact("protection-working", VenueFactKind.ORDER_STATE, status="WORKING"),
        )
        coordinator.actions[cancel.execution_action_id] = cancel
        boundary = ProductResponsibilityBoundary(
            loop=asyncio.get_running_loop(),
            coordinator=coordinator,
            fact_provider=lambda _activation: asyncio.sleep(0, result=_facts()),
            environment_id="demo-1",
        )

        await boundary.sync("activation-1")
        return coordinator

    coordinator = asyncio.run(scenario())

    assert coordinator.unknown_queries == [("cancel-action-unknown", NOW)]
    assert coordinator.applied_facts == []
    assert coordinator.actions["protection-action"].state is ExecutionActionState.OPEN


def test_sync_closes_unknown_entry_only_after_exact_uuid_is_proved_absent() -> None:
    async def scenario() -> _Coordinator:
        coordinator = _Coordinator(_activation())
        unknown = _action(
            "entry-action-absent",
            ExecutionActionKind.ENTRY,
            state=ExecutionActionState.UNKNOWN,
            terms={},
            client_order_id="0123456789abcdef0123456789abcdef",
        )
        coordinator.actions[unknown.execution_action_id] = unknown
        boundary = ProductResponsibilityBoundary(
            loop=asyncio.get_running_loop(),
            coordinator=coordinator,
            fact_provider=lambda _activation: asyncio.sleep(0, result=_facts()),
            entry_order_absence_provider=lambda _action: asyncio.sleep(
                0, result=True
            ),
            environment_id="demo-1",
        )

        await boundary.sync("activation-1")
        return coordinator

    coordinator = asyncio.run(scenario())

    assert coordinator.absent_actions == [
        ("entry-action-absent", "VENUE_QUERY_PROVED_ABSENT", NOW)
    ]
    assert coordinator.unknown_queries == []


def test_working_protection_creates_and_submits_two_fixed_take_profits() -> None:
    async def scenario() -> _Coordinator:
        coordinator = _Coordinator(_activation(first_fill=True))
        protection = _action(
            "protection-action",
            ExecutionActionKind.PROTECTION,
            state=ExecutionActionState.OPEN,
            terms={
                "quantity": "0.01",
                "execution_context": {
                    "entry_action_ref": "entry-action",
                    "fill_fact_ref": "fill-fact",
                    "fill_source_identity": "trade-1:1",
                },
            },
        )
        coordinator.actions[protection.execution_action_id] = protection
        coordinator.facts[protection.execution_action_id] = (
            _venue_fact("protection-working", VenueFactKind.ORDER_STATE, status="WORKING"),
        )
        boundary = ProductResponsibilityBoundary(
            loop=asyncio.get_running_loop(),
            coordinator=coordinator,
            fact_provider=lambda _activation: asyncio.sleep(0, result=_facts()),
            environment_id="demo-1",
        )
        working = SimpleNamespace(
            kind=VenueFactKind.ORDER_STATE,
            payload={"status": "WORKING"},
        )

        boundary.submit_event(
            NormalizedNautilusEvent(action=protection, facts=(working,))
        )
        await boundary.wait_idle()
        return coordinator

    coordinator = asyncio.run(scenario())

    assert [check.quantized_quantity for check in coordinator.take_profit_checks] == [
        "0.005",
        "0.005",
    ]
    assert [item[0] for item in coordinator.submissions] == [
        "take-profit-1",
        "take-profit-2",
    ]
    assert [item[1]["trigger_price"] for item in coordinator.submissions] == [
        "104.5",
        "109",
    ]


def test_exiting_activation_creates_and_submits_one_reduce_only_market_exit() -> None:
    async def scenario() -> _Coordinator:
        activation = enter_exit(_activation(first_fill=True), observed_at=NOW)
        coordinator = _Coordinator(activation)
        coordinator.actions["entry-action"] = _action(
            "entry-action",
            ExecutionActionKind.ENTRY,
            state=ExecutionActionState.CLOSED,
            terms={"quantity": "0.01"},
        )
        coordinator.facts["entry-action"] = (
            _venue_fact(
                "entry-fill",
                VenueFactKind.FILL,
                trade_id="entry-trade",
                last_quantity="0.01",
            ),
        )
        position_fact = SimpleNamespace(
            action_ref=None,
            received_at=NOW,
            venue_fact_id="position-fact",
            payload={"position_quantity": "0.01"},
        )
        boundary = ProductResponsibilityBoundary(
            loop=asyncio.get_running_loop(),
            coordinator=coordinator,
            fact_provider=lambda _activation: asyncio.sleep(
                0,
                result=_facts(position_fact=position_fact),
            ),
            environment_id="demo-1",
        )

        await boundary.sync("activation-1")
        return coordinator

    coordinator = asyncio.run(scenario())

    assert len(coordinator.exit_checks) == 1
    assert coordinator.exit_checks[0].risk_class.value == "RISK_REDUCING"
    assert coordinator.submissions == [
        (
            "exit-action",
            {"profile": "REDUCE_OR_CLOSE_MARKET", "quantity": "0.01"},
        )
    ]


def test_rejected_exit_recheck_uses_new_event_identity_but_one_action_identity() -> None:
    class RejectingExitCoordinator(_Coordinator):
        def create_position_exit(self, **kwargs: object) -> SimpleNamespace:
            self.exit_checks.append(kwargs["action_check"])
            self.exit_requests.append(dict(kwargs))
            return SimpleNamespace(execution_action=None)

    async def scenario() -> RejectingExitCoordinator:
        activation = enter_exit(_activation(first_fill=True), observed_at=NOW)
        coordinator = RejectingExitCoordinator(activation)
        coordinator.actions["entry-action"] = _action(
            "entry-action",
            ExecutionActionKind.ENTRY,
            state=ExecutionActionState.CLOSED,
            terms={"quantity": "0.01"},
        )
        coordinator.facts["entry-action"] = (
            _venue_fact(
                "entry-fill",
                VenueFactKind.FILL,
                trade_id="entry-trade",
                last_quantity="0.01",
            ),
        )
        facts = iter(
            _facts(
                position_fact=SimpleNamespace(
                        action_ref=None,
                        received_at=NOW,
                        venue_fact_id=f"position-fact-{index}",
                        payload={"position_quantity": "0.01"},
                )
            )
            for index in (1, 2)
        )
        boundary = ProductResponsibilityBoundary(
            loop=asyncio.get_running_loop(),
            coordinator=coordinator,
            fact_provider=lambda _activation: asyncio.sleep(0, result=next(facts)),
            environment_id="demo-1",
        )

        await boundary.sync("activation-1")
        await boundary.sync("activation-1")
        return coordinator

    coordinator = asyncio.run(scenario())

    first, second = coordinator.exit_requests
    assert first["plan_event_id"] != second["plan_event_id"]
    assert first["execution_action_id"] == second["execution_action_id"]
    assert first["client_order_id"] == second["client_order_id"]


@pytest.mark.parametrize(
    "predecessor_state",
    (ExecutionActionState.NOT_SUBMITTED, ExecutionActionState.CLOSED),
)
def test_residual_position_forms_one_successor_after_resolved_exit(
    predecessor_state: ExecutionActionState,
) -> None:
    async def scenario() -> _SuccessorCoordinator:
        activation = enter_exit(_activation(first_fill=True), observed_at=NOW)
        coordinator = _SuccessorCoordinator(activation)
        entry = _action(
            "entry-action",
            ExecutionActionKind.ENTRY,
            state=ExecutionActionState.CLOSED,
            terms={"quantity": "0.01"},
        )
        predecessor = _action(
            "exit-predecessor",
            ExecutionActionKind.EXIT,
            state=predecessor_state,
            terms={
                "action_profile": "REDUCE_OR_CLOSE_MARKET",
                "quantity": "0.01",
            },
            client_order_id="d" * 32,
        )
        predecessor.source_identity = "activation-1:EXIT:PLAN_EXIT"
        coordinator.actions.update(
            {
                entry.execution_action_id: entry,
                predecessor.execution_action_id: predecessor,
            }
        )
        coordinator.facts[entry.execution_action_id] = (
            _venue_fact(
                "entry-fill",
                VenueFactKind.FILL,
                trade_id="entry-trade",
                last_quantity="0.01",
            ),
        )
        position_fact = _venue_fact(
            "position-current",
            VenueFactKind.POSITION_STATE,
            position_quantity="0.01",
        )
        boundary = ProductResponsibilityBoundary(
            loop=asyncio.get_running_loop(),
            coordinator=coordinator,
            fact_provider=lambda _activation: asyncio.sleep(
                0,
                result=_facts(position_fact=position_fact),
            ),
            environment_id="demo-1",
        )

        await boundary.sync("activation-1", force=True)
        await boundary.sync("activation-1", force=True)
        return coordinator

    coordinator = asyncio.run(scenario())
    assert len(coordinator.exit_requests) == 1
    request = coordinator.exit_requests[0]
    assert "EXIT_SUCCESSOR:exit-predecessor" in request["reason_ref"]
    assert request["position_quantity"] == "0.01"
    assert request["execution_action_id"] != "exit-predecessor"


def test_terminal_partial_exit_forms_successor_for_exact_residual() -> None:
    async def scenario() -> _SuccessorCoordinator:
        activation = enter_exit(_activation(first_fill=True), observed_at=NOW)
        coordinator = _SuccessorCoordinator(activation)
        entry = _action(
            "entry-action",
            ExecutionActionKind.ENTRY,
            state=ExecutionActionState.CLOSED,
            terms={"quantity": "0.02"},
        )
        predecessor = _action(
            "exit-partial",
            ExecutionActionKind.EXIT,
            state=ExecutionActionState.OPEN,
            terms={
                "action_profile": "REDUCE_OR_CLOSE_MARKET",
                "quantity": "0.02",
            },
            client_order_id="d" * 32,
        )
        predecessor.source_identity = "activation-1:EXIT:PLAN_EXIT"
        coordinator.actions.update(
            {
                entry.execution_action_id: entry,
                predecessor.execution_action_id: predecessor,
            }
        )
        coordinator.facts[entry.execution_action_id] = (
            _venue_fact(
                "entry-fill",
                VenueFactKind.FILL,
                trade_id="entry-trade",
                last_quantity="0.02",
            ),
        )
        coordinator.facts[predecessor.execution_action_id] = (
            _venue_fact(
                "exit-fill",
                VenueFactKind.FILL,
                trade_id="exit-trade",
                last_quantity="0.01",
                leaves_quantity="0.01",
            ),
            _venue_fact(
                "exit-commission",
                VenueFactKind.COMMISSION,
                trade_id="exit-trade",
            ),
            _venue_fact(
                "exit-cancelled",
                VenueFactKind.ORDER_STATE,
                status="CANCELLED",
                cumulative_filled_quantity="0.01",
            ),
        )
        position_fact = _venue_fact(
            "position-current",
            VenueFactKind.POSITION_STATE,
            position_quantity="0.01",
        )
        boundary = ProductResponsibilityBoundary(
            loop=asyncio.get_running_loop(),
            coordinator=coordinator,
            fact_provider=lambda _activation: asyncio.sleep(
                0,
                result=_facts(position_fact=position_fact),
            ),
            environment_id="demo-1",
        )

        await boundary.sync("activation-1", force=True)
        return coordinator

    coordinator = asyncio.run(scenario())
    assert len(coordinator.exit_requests) == 1
    assert coordinator.exit_requests[0]["position_quantity"] == "0.01"
    assert "EXIT_SUCCESSOR:exit-partial" in coordinator.exit_requests[0][
        "reason_ref"
    ]


def test_same_direction_manual_position_is_not_auto_closed() -> None:
    async def scenario() -> _SuccessorCoordinator:
        activation = enter_exit(_activation(first_fill=True), observed_at=NOW)
        coordinator = _SuccessorCoordinator(activation)
        entry = _action(
            "entry-action",
            ExecutionActionKind.ENTRY,
            state=ExecutionActionState.CLOSED,
            terms={"quantity": "0.01"},
        )
        coordinator.actions[entry.execution_action_id] = entry
        coordinator.facts[entry.execution_action_id] = (
            _venue_fact(
                "entry-fill",
                VenueFactKind.FILL,
                trade_id="entry-trade",
                last_quantity="0.01",
            ),
        )
        position_fact = _venue_fact(
            "position-with-manual-addition",
            VenueFactKind.POSITION_STATE,
            position_quantity="0.02",
        )
        boundary = ProductResponsibilityBoundary(
            loop=asyncio.get_running_loop(),
            coordinator=coordinator,
            fact_provider=lambda _activation: asyncio.sleep(
                0,
                result=_facts(
                    current_abs_position="0.02",
                    position_fact=position_fact,
                ),
            ),
            environment_id="demo-1",
        )

        with pytest.raises(ValueError, match="POSITION_ATTRIBUTION_UNKNOWN"):
            await boundary.sync("activation-1", force=True)
        return coordinator

    coordinator = asyncio.run(scenario())
    assert coordinator.exit_requests == []


def test_ready_exit_is_not_recovered_against_a_manual_same_direction_position() -> None:
    async def scenario() -> _Coordinator:
        activation = enter_exit(_activation(first_fill=True), observed_at=NOW)
        coordinator = _Coordinator(activation)
        entry = _action(
            "entry-action",
            ExecutionActionKind.ENTRY,
            state=ExecutionActionState.CLOSED,
            terms={"quantity": "0.01"},
        )
        coordinator.actions[entry.execution_action_id] = entry
        coordinator.facts[entry.execution_action_id] = (
            _venue_fact(
                "entry-fill",
                VenueFactKind.FILL,
                trade_id="entry-trade",
                last_quantity="0.01",
            ),
        )
        ready_exit = _action(
            "exit-ready",
            ExecutionActionKind.EXIT,
            state=ExecutionActionState.READY,
            terms={
                "action_profile": "REDUCE_OR_CLOSE_MARKET",
                "quantity": "0.01",
            },
            client_order_id="e" * 32,
        )
        coordinator.actions[ready_exit.execution_action_id] = ready_exit
        position_fact = _venue_fact(
            "position-with-manual-addition",
            VenueFactKind.POSITION_STATE,
            position_quantity="0.02",
        )
        boundary = ProductResponsibilityBoundary(
            loop=asyncio.get_running_loop(),
            coordinator=coordinator,
            fact_provider=lambda _activation: asyncio.sleep(
                0,
                result=_facts(
                    current_abs_position="0.02",
                    position_fact=position_fact,
                ),
            ),
            environment_id="demo-1",
        )

        with pytest.raises(ValueError, match="POSITION_ATTRIBUTION_UNKNOWN"):
            await boundary.sync("activation-1", force=True)
        return coordinator

    coordinator = asyncio.run(scenario())
    assert coordinator.submissions == []
    assert coordinator.actions["exit-ready"].state is ExecutionActionState.READY


def test_ready_exit_with_stale_quantity_is_replaced_from_current_attributed_position() -> None:
    async def scenario() -> _SuccessorCoordinator:
        activation = enter_exit(_activation(first_fill=True), observed_at=NOW)
        coordinator = _SuccessorCoordinator(activation)
        entry = _action(
            "entry-action",
            ExecutionActionKind.ENTRY,
            state=ExecutionActionState.CLOSED,
            terms={"quantity": "0.01"},
        )
        coordinator.actions[entry.execution_action_id] = entry
        coordinator.facts[entry.execution_action_id] = (
            _venue_fact(
                "entry-fill",
                VenueFactKind.FILL,
                trade_id="entry-trade",
                last_quantity="0.01",
            ),
        )
        reduction = _action(
            "protection-filled",
            ExecutionActionKind.PROTECTION,
            state=ExecutionActionState.CLOSED,
            terms={"quantity": "0.005"},
        )
        coordinator.actions[reduction.execution_action_id] = reduction
        coordinator.facts[reduction.execution_action_id] = (
            _venue_fact(
                "protection-fill",
                VenueFactKind.FILL,
                trade_id="protection-trade",
                last_quantity="0.005",
            ),
        )
        stale_exit = _action(
            "exit-ready",
            ExecutionActionKind.EXIT,
            state=ExecutionActionState.READY,
            terms={
                "action_profile": "REDUCE_OR_CLOSE_MARKET",
                "quantity": "0.01",
            },
            client_order_id="e" * 32,
        )
        coordinator.actions[stale_exit.execution_action_id] = stale_exit
        position_fact = _venue_fact(
            "position-current",
            VenueFactKind.POSITION_STATE,
            position_quantity="0.005",
        )
        boundary = ProductResponsibilityBoundary(
            loop=asyncio.get_running_loop(),
            coordinator=coordinator,
            fact_provider=lambda _activation: asyncio.sleep(
                0,
                result=_facts(
                    current_abs_position="0.005",
                    position_fact=position_fact,
                ),
            ),
            environment_id="demo-1",
        )

        await boundary.sync("activation-1", force=True)
        return coordinator

    coordinator = asyncio.run(scenario())
    assert coordinator.rejections == [
        ("exit-ready", "EXIT_POSITION_CHANGED_BEFORE_SUBMISSION")
    ]
    assert len(coordinator.exit_requests) == 1
    assert coordinator.exit_requests[0]["position_quantity"] == "0.005"
    assert [item[1]["quantity"] for item in coordinator.submissions] == ["0.005"]


def test_late_halpha_fill_unblocks_attributed_exit_on_next_sync() -> None:
    async def scenario() -> _SuccessorCoordinator:
        activation = enter_exit(_activation(first_fill=True), observed_at=NOW)
        coordinator = _SuccessorCoordinator(activation)
        entry = _action(
            "entry-action",
            ExecutionActionKind.ENTRY,
            state=ExecutionActionState.CLOSED,
            terms={"quantity": "0.02"},
        )
        coordinator.actions[entry.execution_action_id] = entry
        first_fill = _venue_fact(
            "entry-fill-1",
            VenueFactKind.FILL,
            trade_id="entry-trade-1",
            last_quantity="0.01",
        )
        coordinator.facts[entry.execution_action_id] = (first_fill,)
        position_fact = _venue_fact(
            "position-current",
            VenueFactKind.POSITION_STATE,
            position_quantity="0.02",
        )
        boundary = ProductResponsibilityBoundary(
            loop=asyncio.get_running_loop(),
            coordinator=coordinator,
            fact_provider=lambda _activation: asyncio.sleep(
                0,
                result=_facts(
                    current_abs_position="0.02",
                    position_fact=position_fact,
                ),
            ),
            environment_id="demo-1",
        )

        with pytest.raises(ValueError, match="POSITION_ATTRIBUTION_UNKNOWN"):
            await boundary.sync("activation-1", force=True)
        coordinator.facts[entry.execution_action_id] = (
            first_fill,
            _venue_fact(
                "entry-fill-2",
                VenueFactKind.FILL,
                trade_id="entry-trade-2",
                last_quantity="0.01",
            ),
        )
        await boundary.sync("activation-1", force=True)
        return coordinator

    coordinator = asyncio.run(scenario())
    assert len(coordinator.exit_requests) == 1
    assert coordinator.exit_requests[0]["position_quantity"] == "0.02"


def test_external_open_order_identity_blocks_auto_exit() -> None:
    async def scenario() -> _SuccessorCoordinator:
        activation = enter_exit(_activation(first_fill=True), observed_at=NOW)
        coordinator = _SuccessorCoordinator(activation)
        entry = _action(
            "entry-action",
            ExecutionActionKind.ENTRY,
            state=ExecutionActionState.CLOSED,
            terms={"quantity": "0.01"},
            client_order_id="b" * 32,
        )
        coordinator.actions[entry.execution_action_id] = entry
        coordinator.facts[entry.execution_action_id] = (
            _venue_fact(
                "entry-fill",
                VenueFactKind.FILL,
                trade_id="entry-trade",
                last_quantity="0.01",
            ),
        )
        position_fact = _venue_fact(
            "position-current",
            VenueFactKind.POSITION_STATE,
            position_quantity="0.01",
        )
        boundary = ProductResponsibilityBoundary(
            loop=asyncio.get_running_loop(),
            coordinator=coordinator,
            fact_provider=lambda _activation: asyncio.sleep(
                0,
                result=replace(
                    _facts(position_fact=position_fact),
                    open_order_client_ids=("external-order",),
                ),
            ),
            environment_id="demo-1",
        )

        with pytest.raises(ValueError, match="POSITION_ATTRIBUTION_UNKNOWN"):
            await boundary.sync("activation-1", force=True)
        return coordinator

    coordinator = asyncio.run(scenario())
    assert coordinator.exit_requests == []


def test_flat_exiting_activation_cancels_remaining_algo_protection() -> None:
    async def scenario() -> _Coordinator:
        activation = enter_exit(_activation(first_fill=True), observed_at=NOW)
        coordinator = _Coordinator(activation)
        protection = _action(
            "protection-action",
            ExecutionActionKind.PROTECTION,
            state=ExecutionActionState.OPEN,
            terms={"quantity": "0.01"},
            client_order_id="a" * 32,
        )
        coordinator.actions[protection.execution_action_id] = protection
        coordinator.facts[protection.execution_action_id] = (
            _venue_fact("protection-working", VenueFactKind.ORDER_STATE, status="WORKING"),
        )
        boundary = ProductResponsibilityBoundary(
            loop=asyncio.get_running_loop(),
            coordinator=coordinator,
            fact_provider=lambda _activation: asyncio.sleep(
                0,
                result=_facts(
                    current_abs_position="0",
                ),
            ),
            environment_id="demo-1",
        )

        await boundary.sync("activation-1")
        return coordinator

    coordinator = asyncio.run(scenario())

    assert len(coordinator.cancel_checks) == 1
    assert coordinator.cancel_checks[0].risk_class.value == "RISK_NEUTRAL"
    assert coordinator.cancel_requests[0]["target_endpoint"] == "ALGO"
    assert coordinator.submissions == [
        ("cancel-action", {"profile": "CANCEL_ORDER"})
    ]


def test_flat_exiting_activation_cancels_working_entry_at_ordinary_endpoint() -> None:
    async def scenario() -> _Coordinator:
        activation = enter_exit(_activation(), observed_at=NOW)
        coordinator = _Coordinator(activation)
        entry = _action(
            "entry-action",
            ExecutionActionKind.ENTRY,
            state=ExecutionActionState.OPEN,
            terms={"quantity": "0.01"},
            client_order_id="b" * 32,
        )
        coordinator.actions[entry.execution_action_id] = entry
        coordinator.facts[entry.execution_action_id] = (
            _venue_fact("entry-working", VenueFactKind.ORDER_STATE, status="WORKING"),
        )
        boundary = ProductResponsibilityBoundary(
            loop=asyncio.get_running_loop(),
            coordinator=coordinator,
            fact_provider=lambda _activation: asyncio.sleep(
                0,
                result=_facts(current_abs_position="0"),
            ),
            environment_id="demo-1",
        )

        await boundary.sync("activation-1")
        return coordinator

    coordinator = asyncio.run(scenario())

    assert len(coordinator.cancel_requests) == 1
    assert coordinator.cancel_requests[0]["target_action_id"] == "entry-action"
    assert coordinator.cancel_requests[0]["target_endpoint"] == "ORDINARY"
    assert coordinator.submissions == [
        ("cancel-action", {"profile": "CANCEL_ORDER"})
    ]


def test_running_activation_cancels_sibling_orders_after_stop_flattens_position() -> None:
    async def scenario() -> _Coordinator:
        coordinator = _Coordinator(_activation(first_fill=True))
        stop = _action(
            "protection-action",
            ExecutionActionKind.PROTECTION,
            state=ExecutionActionState.OPEN,
            terms={"quantity": "0.01"},
            client_order_id="a" * 32,
        )
        coordinator.actions[stop.execution_action_id] = stop
        coordinator.facts[stop.execution_action_id] = (
            _venue_fact(
                "stop-fill",
                VenueFactKind.FILL,
                trade_id="stop-trade",
            ),
        )
        for index in (1, 2):
            take_profit = _action(
                f"take-profit-{index}",
                ExecutionActionKind.TAKE_PROFIT,
                state=ExecutionActionState.OPEN,
                terms={"quantity": "0.005"},
                client_order_id=str(index) * 32,
            )
            coordinator.actions[take_profit.execution_action_id] = take_profit
            coordinator.facts[take_profit.execution_action_id] = (
                _venue_fact(
                    f"take-profit-{index}-working",
                    VenueFactKind.ORDER_STATE,
                    status="WORKING",
                ),
            )
        boundary = ProductResponsibilityBoundary(
            loop=asyncio.get_running_loop(),
            coordinator=coordinator,
            fact_provider=lambda _activation: asyncio.sleep(
                0,
                result=_facts(
                    current_abs_position="0",
                    open_algo_client_ids=("1" * 32, "2" * 32),
                ),
            ),
            environment_id="demo-1",
        )

        await boundary.sync("activation-1")
        return coordinator

    coordinator = asyncio.run(scenario())

    assert coordinator.exit_requests == []
    assert len(coordinator.cancel_checks) == 2
    assert coordinator.submissions == [
        ("cancel-action", {"profile": "CANCEL_ORDER"}),
        ("cancel-action-2", {"profile": "CANCEL_ORDER"}),
    ]


def test_partial_take_profit_keeps_remaining_protection_while_position_exists() -> None:
    async def scenario() -> _Coordinator:
        coordinator = _Coordinator(_activation(first_fill=True))
        take_profit = _action(
            "take-profit-filled",
            ExecutionActionKind.TAKE_PROFIT,
            state=ExecutionActionState.OPEN,
            terms={"quantity": "0.005"},
            client_order_id="1" * 32,
        )
        coordinator.actions[take_profit.execution_action_id] = take_profit
        coordinator.facts[take_profit.execution_action_id] = (
            _venue_fact(
                "take-profit-fill",
                VenueFactKind.FILL,
                trade_id="take-profit-trade",
            ),
        )
        protection = _action(
            "protection-action",
            ExecutionActionKind.PROTECTION,
            state=ExecutionActionState.OPEN,
            terms={"quantity": "0.01"},
            client_order_id="a" * 32,
        )
        coordinator.actions[protection.execution_action_id] = protection
        coordinator.facts[protection.execution_action_id] = (
            _venue_fact("protection-working", VenueFactKind.ORDER_STATE, status="WORKING"),
        )
        boundary = ProductResponsibilityBoundary(
            loop=asyncio.get_running_loop(),
            coordinator=coordinator,
            fact_provider=lambda _activation: asyncio.sleep(
                0,
                result=_facts(
                    current_abs_position="0.005",
                    open_algo_client_ids=("a" * 32,),
                ),
            ),
            environment_id="demo-1",
        )

        await boundary.sync("activation-1")
        return coordinator

    coordinator = asyncio.run(scenario())

    assert coordinator.cancel_checks == []
    assert coordinator.exit_requests == []
    assert coordinator.closures == []


def test_flat_terminal_actions_are_reconciled_and_activation_closes() -> None:
    async def scenario() -> _Coordinator:
        coordinator = _Coordinator(_activation(first_fill=True))
        for action_id, kind in (
            ("entry-action", ExecutionActionKind.ENTRY),
            ("protection-action", ExecutionActionKind.PROTECTION),
        ):
            coordinator.actions[action_id] = _action(
                action_id,
                kind,
                state=ExecutionActionState.OPEN,
                terms={"quantity": "0.01"},
                client_order_id=(
                    "a" * 32 if kind is ExecutionActionKind.PROTECTION else None
                ),
            )
            trade_id = f"{action_id}-trade"
            coordinator.facts[action_id] = (
                _venue_fact(
                    f"{action_id}-ORDER_STATE",
                    VenueFactKind.ORDER_STATE,
                    status="FILLED",
                    cumulative_filled_quantity="0.01",
                ),
                _venue_fact(
                    f"{action_id}-FILL",
                    VenueFactKind.FILL,
                    trade_id=trade_id,
                    last_quantity="0.01",
                ),
                _venue_fact(
                    f"{action_id}-COMMISSION",
                    VenueFactKind.COMMISSION,
                    trade_id=trade_id,
                ),
            )
        position_fact = SimpleNamespace(
            action_ref=None,
            received_at=NOW,
            venue_fact_id="position-zero-fact",
        )
        coordinator.actions["cancel-action"] = _action(
            "cancel-action",
            ExecutionActionKind.CANCEL,
            state=ExecutionActionState.UNKNOWN,
            terms={"action_profile": "CANCEL_ORDER"},
            cancel_target={
                "client_order_id": coordinator.actions[
                    "protection-action"
                ].client_order_id,
                "endpoint": "ALGO",
            },
        )
        boundary = ProductResponsibilityBoundary(
            loop=asyncio.get_running_loop(),
            coordinator=coordinator,
            fact_provider=lambda _activation: asyncio.sleep(
                0,
                result=_facts(
                    current_abs_position="0",
                    position_fact=position_fact,
                ),
            ),
            environment_id="demo-1",
        )

        await boundary.sync("activation-1")
        return coordinator

    coordinator = asyncio.run(scenario())

    assert [item["action_id"] for item in coordinator.reconciliations] == [
        "cancel-action",
        "entry-action",
        "protection-action",
    ]
    assert len(coordinator.closures) == 1
    assert coordinator.closures[0]["position_zero"] is True
    assert coordinator.closures[0]["open_order_refs"] == ()


@pytest.mark.parametrize("activation_first_fill", (False, True))
def test_running_entry_fill_does_not_close_before_risk_reduction_fill(
    activation_first_fill: bool,
) -> None:
    async def scenario() -> _Coordinator:
        coordinator = _Coordinator(_activation(first_fill=activation_first_fill))
        entry = _action(
            "entry-action",
            ExecutionActionKind.ENTRY,
            state=ExecutionActionState.OPEN,
            terms={},
        )
        coordinator.actions[entry.execution_action_id] = entry
        coordinator.facts[entry.execution_action_id] = (
            _venue_fact(
                "entry-action-ORDER_STATE",
                VenueFactKind.ORDER_STATE,
                status="FILLED",
            ),
            _venue_fact(
                "entry-action-FILL",
                VenueFactKind.FILL,
                trade_id="entry-trade",
            ),
            _venue_fact(
                "entry-action-COMMISSION",
                VenueFactKind.COMMISSION,
                trade_id="entry-trade",
            ),
        )
        position_fact = SimpleNamespace(
            action_ref=None,
            received_at=NOW,
            venue_fact_id="transient-zero-position-fact",
        )
        boundary = ProductResponsibilityBoundary(
            loop=asyncio.get_running_loop(),
            coordinator=coordinator,
            fact_provider=lambda _activation: asyncio.sleep(
                0,
                result=_facts(
                    current_abs_position="0",
                    position_fact=position_fact,
                ),
            ),
            environment_id="demo-1",
        )

        await boundary.sync("activation-1")
        return coordinator

    coordinator = asyncio.run(scenario())

    assert coordinator.reconciliations == []
    assert coordinator.closures == []
