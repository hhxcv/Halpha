from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

from halpha.capital.models import AuthorityClass, EnvironmentKind, StopCategory
from halpha.planning.models import PlanActivation
from halpha.planning.transitions import record_first_fill
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


def _facts() -> ProductRiskReductionFacts:
    return ProductRiskReductionFacts(
        checked_at=NOW,
        conservative_price="100",
        available_margin="1000",
        actual_margin_mode="ISOLATED",
        actual_leverage="5",
        activation_current_notional="1",
        account_current_notional="1",
        activation_current_margin="0.2",
        current_abs_position="0.01",
    )


def _action(
    action_id: str,
    kind: ExecutionActionKind,
    *,
    state: ExecutionActionState,
    terms: dict[str, object],
) -> SimpleNamespace:
    return SimpleNamespace(
        execution_action_id=action_id,
        activation_id="activation-1",
        action_kind=kind,
        state=state,
        action_terms=terms,
    )


class _Coordinator:
    def __init__(self, activation: PlanActivation) -> None:
        self.activation = activation
        self.actions: dict[str, SimpleNamespace] = {}
        self.facts: dict[str, tuple[SimpleNamespace, ...]] = {}
        self.protection_checks = []
        self.take_profit_checks = []
        self.submissions: list[tuple[str, dict[str, object]]] = []

    def get_activation_snapshot(self, _activation_id: str) -> PlanActivation:
        return self.activation

    def get_execution_action(self, action_id: str) -> SimpleNamespace:
        return self.actions[action_id]

    def list_execution_actions(self, _activation_id: str) -> tuple[SimpleNamespace, ...]:
        return tuple(self.actions.values())

    def list_venue_facts_for_action(self, action_id: str) -> tuple[SimpleNamespace, ...]:
        return self.facts.get(action_id, ())

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
            state=ExecutionActionState.FILLED,
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


def test_working_protection_creates_and_submits_two_fixed_take_profits() -> None:
    async def scenario() -> _Coordinator:
        coordinator = _Coordinator(_activation(first_fill=True))
        protection = _action(
            "protection-action",
            ExecutionActionKind.PROTECTION,
            state=ExecutionActionState.WORKING,
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
