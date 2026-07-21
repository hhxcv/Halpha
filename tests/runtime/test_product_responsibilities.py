from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from halpha.capital.models import AuthorityClass, EnvironmentKind, StopCategory
from halpha.planning.models import PlanActivation
from halpha.planning.transitions import enter_exit, record_first_fill
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
        strategy_id="ONE_SHOT_DONCHIAN_ATR_BREAKOUT",
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
) -> SimpleNamespace:
    payload: dict[str, object] = {}
    if status is not None:
        payload["status"] = status
    if trade_id is not None:
        payload["trade_id"] = trade_id
    if kind is VenueFactKind.FILL:
        payload["leaves_quantity"] = leaves_quantity
    return SimpleNamespace(
        venue_fact_id=fact_id,
        kind=kind,
        payload=payload,
        source_time=NOW,
        cutoff=NOW,
        received_at=NOW,
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
        self.applied_facts = []
        self.submissions: list[tuple[str, dict[str, object]]] = []
        self.reconciliations: list[dict[str, object]] = []
        self.closures: list[dict[str, object]] = []
        self.unknown_queries: list[tuple[str, datetime]] = []
        self.absent_actions: list[tuple[str, str, datetime]] = []

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

    def close_activation(self, **kwargs: object) -> str:
        self.closures.append(kwargs)
        return "c" * 64


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
        position_fact = SimpleNamespace(
            action_ref=None,
            received_at=NOW,
            venue_fact_id="position-fact",
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
        facts = iter(
            _facts(
                position_fact=SimpleNamespace(
                    action_ref=None,
                    received_at=NOW,
                    venue_fact_id=f"position-fact-{index}",
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
                terms={},
            )
            trade_id = f"{action_id}-trade"
            coordinator.facts[action_id] = (
                _venue_fact(
                    f"{action_id}-ORDER_STATE",
                    VenueFactKind.ORDER_STATE,
                    status="FILLED",
                ),
                _venue_fact(
                    f"{action_id}-FILL",
                    VenueFactKind.FILL,
                    trade_id=trade_id,
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
