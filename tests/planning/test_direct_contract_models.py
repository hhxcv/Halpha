from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from halpha.capital.models import AuthorityClass, EnvironmentKind
from halpha.domain_values import content_digest
from halpha.planning.models import (
    PERSISTED_HISTORY_CONTEXT_KEY,
    PlanActivation,
    PlanLifecycle,
    RequestedLimits,
    TradePlanContent,
    TradePlanVersion,
)
from halpha.planning.service import PlanningApplicationService
from halpha.planning.order_policies import (
    InitialStopSpec,
    ProtectionPolicy,
    TakeProfitLadderSpec,
    TakeProfitLevel,
)
from halpha.planning.order_schedule import (
    AmountDistribution,
    InstrumentOrderRules,
    OrderSchedulePreview,
    OrderScheduleSpec,
    SinglePrice,
    compile_order_schedule,
    direct_allowed_action_profiles,
)
from halpha.planning.registry import (
    DIRECT_EXECUTION_REF,
    Direction,
    DraftDecisionBasis,
    FixedDirectExecutionBasis,
)


NOW = datetime(2026, 7, 23, tzinfo=UTC)


def _spec() -> OrderScheduleSpec:
    return OrderScheduleSpec(
        price_distribution=SinglePrice(limit_price="100"),
        amount_distribution=AmountDistribution(base_notional="20"),
        protection_policy=ProtectionPolicy(
            initial_stop=InitialStopSpec(distance_bps="100"),
        ),
    )


def _historical_split_spec() -> OrderScheduleSpec:
    return OrderScheduleSpec(
        price_distribution=SinglePrice(limit_price="100"),
        amount_distribution=AmountDistribution(base_notional="20"),
        protection_policy=ProtectionPolicy(
            initial_stop=InitialStopSpec(distance_bps="100"),
            take_profit_ladder=TakeProfitLadderSpec(
                levels=(
                    TakeProfitLevel(trigger_r="1", quantity_fraction="0.5"),
                    TakeProfitLevel(trigger_r="2", quantity_fraction="0.5"),
                )
            ),
        ),
    )


def _historical_split_action_profiles() -> frozenset[str]:
    return frozenset(
        {
            "ENTRY_LIMIT",
            "PROTECTIVE_STOP_REDUCE_ONLY",
            "REDUCE_OR_CLOSE_MARKET",
            "CANCEL_ORDER",
            "TAKE_PROFIT_1",
            "TAKE_PROFIT_2",
        }
    )


def _snapshot(
    spec: OrderScheduleSpec | None = None,
    *,
    schedule_ref: str = "plan-version-direct",
    instrument_ref: str = "BTCUSDT-PERP",
    direction: Direction = Direction.LONG,
) -> OrderSchedulePreview:
    preview = compile_order_schedule(
        spec or _spec(),
        InstrumentOrderRules(
            source="BINANCE_DEMO_EXCHANGE_INFO",
            min_price="0.1",
            max_price="1000000",
            price_tick_size="0.1",
            limit_quantity_step="0.01",
            min_limit_quantity="0.01",
            max_limit_quantity="1000",
            market_quantity_step="0.1",
            min_market_quantity="0.1",
            max_market_quantity="100",
            min_notional="5",
            source_cutoff=NOW.isoformat(),
        ),
        venue_ref="BINANCE_USDM",
        instrument_ref=instrument_ref,
        direction=direction,
        max_notional="100",
        schedule_ref=schedule_ref,
    )
    assert preview.valid
    return preview


def _draft_content(*, allowed_actions: frozenset[str]) -> TradePlanContent:
    return TradePlanContent(
        plan_name="direct contract",
        created_at=NOW,
        creator_kind="AI",
        decision_basis=DraftDecisionBasis(
            kind="DIRECT_EXECUTION",
            decision_basis_ref=DIRECT_EXECUTION_REF,
            parameters={},
        ),
        order_schedule_spec=_spec(),
        environment_id="demo",
        environment_kind=EnvironmentKind.DEMO,
        authority_class=AuthorityClass.DEMO_VALIDATION,
        account_ref="demo-account",
        venue_ref="BINANCE_USDM",
        instrument_ref="BTCUSDT-PERP",
        direction=Direction.LONG,
        target_exposure="100",
        requested_limits=RequestedLimits(
            max_margin="100",
            max_notional="100",
            max_allowed_loss="10",
        ),
        valid_from=NOW,
        valid_until=NOW + timedelta(hours=1),
        allowed_actions=allowed_actions,
        terms={},
    )


def _fixed_version(*, allowed_actions: frozenset[str]) -> TradePlanVersion:
    return TradePlanVersion(
        plan_version_id="plan-version-direct",
        plan_id="plan-direct",
        environment_id="demo",
        fixed_at=NOW,
        plan_name="direct contract",
        created_at=NOW,
        creator_kind="AI",
        decision_basis=FixedDirectExecutionBasis(
            parameter_digest=content_digest({}),
            product_build_id="a" * 64,
        ),
        order_schedule_spec=_spec(),
        account_ref="demo-account",
        venue_ref="BINANCE_USDM",
        instrument_ref="BTCUSDT-PERP",
        direction=Direction.LONG,
        target_exposure="100",
        requested_limits=RequestedLimits(
            max_margin="100",
            max_notional="100",
            max_allowed_loss="10",
        ),
        valid_from=NOW,
        valid_until=NOW + timedelta(hours=1),
        allowed_actions=allowed_actions,
        terms={},
        content_digest="b" * 64,
    )


@pytest.mark.parametrize("model", (_draft_content, _fixed_version))
def test_direct_plan_models_require_the_exact_runtime_action_scope(model) -> None:
    expected = direct_allowed_action_profiles(_spec())

    assert model(allowed_actions=expected).allowed_actions == expected

    with pytest.raises(
        ValidationError,
        match="DIRECT_EXECUTION_ACTION_SCOPE_MISMATCH",
    ):
        model(allowed_actions=expected | {"TAKE_PROFIT_2"})

    with pytest.raises(
        ValidationError,
        match="DIRECT_EXECUTION_ACTION_SCOPE_MISMATCH",
    ):
        model(allowed_actions=expected - {"CANCEL_ORDER"})


def _activation(
    *,
    decision_basis_ref: str = DIRECT_EXECUTION_REF,
    snapshot: OrderSchedulePreview | None = None,
    lifecycle: PlanLifecycle = PlanLifecycle.RUNNING,
    closure_digest: str | None = None,
) -> PlanActivation:
    return PlanActivation(
        activation_id="activation-direct",
        environment_id="demo",
        environment_kind=EnvironmentKind.DEMO,
        authority_class=AuthorityClass.DEMO_VALIDATION,
        plan_version_ref="plan-version-direct",
        account_ref="demo-account",
        instrument_ref="BTCUSDT-PERP",
        direction=Direction.LONG,
        decision_basis_ref=decision_basis_ref,
        framework_strategy_id="HALPHA-DIRECT",
        order_schedule_snapshot=snapshot,
        target_exposure="100",
        lifecycle=lifecycle,
        rule_state={},
        closure_digest=closure_digest,
        created_at=NOW,
        updated_at=NOW,
    )


def test_direct_activation_requires_a_matching_snapshot() -> None:
    snapshot = _snapshot()

    assert _activation(snapshot=snapshot).order_schedule_snapshot == snapshot

    with pytest.raises(ValidationError, match="ORDER_SCHEDULE_SNAPSHOT_REQUIRED"):
        _activation()

    with pytest.raises(ValidationError, match="STRATEGY_ORDER_SCHEDULE_NOT_SUPPORTED"):
        _activation(
            decision_basis_ref="ONE_SHOT_DONCHIAN_ATR_BREAKOUT@1.0.1",
            snapshot=snapshot,
        )


def test_completed_activation_keeps_valid_history_outside_the_current_catalog() -> None:
    snapshot = _snapshot(_historical_split_spec())

    activation = _activation(
        snapshot=snapshot,
        lifecycle=PlanLifecycle.COMPLETED,
        closure_digest="historical-closure",
    )

    assert activation.order_schedule_snapshot == snapshot


def _historical_split_version() -> TradePlanVersion:
    current = _fixed_version(
        allowed_actions=direct_allowed_action_profiles(_spec()),
    )
    historical_spec = _historical_split_spec()
    payload = current.model_dump(mode="python")
    payload.update(
        {
            "order_schedule_spec": historical_spec,
            "allowed_actions": _historical_split_action_profiles(),
        }
    )
    return TradePlanVersion.model_validate(
        payload,
        context={PERSISTED_HISTORY_CONTEXT_KEY: True},
    )


def test_historical_version_is_readable_but_cannot_be_newly_activated() -> None:
    version = _historical_split_version()
    service = object.__new__(PlanningApplicationService)
    service._environment_id = "demo"
    service._planning = type(
        "HistoricalPlanning",
        (),
        {
            "get_version": staticmethod(lambda *_args, **_kwargs: version),
            "insert_activation": staticmethod(
                lambda *_args, **_kwargs: pytest.fail(
                    "unsupported history must not create a new activation"
                )
            ),
        },
    )()

    with pytest.raises(
        ValueError,
        match="DIRECT_EXECUTION_TAKE_PROFIT_SPLIT_NOT_VERIFIED",
    ):
        service.activate_version(
            plan_version_id=version.plan_version_id,
            activation_id="new-activation-from-history",
            environment_kind=EnvironmentKind.DEMO,
            authority_class=AuthorityClass.DEMO_VALIDATION,
            product_build_id=version.decision_basis.product_build_id,
            observed_at=NOW,
            order_schedule_snapshot=_snapshot(_historical_split_spec()),
        )


def test_historical_draft_is_readable_while_current_input_remains_strict() -> None:
    current = _draft_content(
        allowed_actions=direct_allowed_action_profiles(_spec()),
    )
    historical_spec = _historical_split_spec()
    payload = current.model_dump(mode="python")
    payload.update(
        {
            "order_schedule_spec": historical_spec,
            "allowed_actions": _historical_split_action_profiles(),
        }
    )

    with pytest.raises(
        ValidationError,
        match="DIRECT_EXECUTION_TAKE_PROFIT_SPLIT_NOT_VERIFIED",
    ):
        TradePlanContent.model_validate(payload)

    historical = TradePlanContent.model_validate(
        payload,
        context={PERSISTED_HISTORY_CONTEXT_KEY: True},
    )
    assert historical.order_schedule_spec == historical_spec


def test_history_context_skips_only_current_catalog_admission() -> None:
    current = _draft_content(
        allowed_actions=direct_allowed_action_profiles(_spec()),
    )
    payload = current.model_dump(mode="python")
    payload["allowed_actions"] = current.allowed_actions | {"TAKE_PROFIT_2"}

    hydrated = TradePlanContent.model_validate(
        payload,
        context={PERSISTED_HISTORY_CONTEXT_KEY: True},
    )
    assert "TAKE_PROFIT_2" in hydrated.allowed_actions

    payload["authority_class"] = AuthorityClass.LIVE_REAL_CAPITAL
    with pytest.raises(ValidationError, match="AUTHORITY_ENVIRONMENT_MISMATCH"):
        TradePlanContent.model_validate(
            payload,
            context={PERSISTED_HISTORY_CONTEXT_KEY: True},
        )


@pytest.mark.parametrize(
    "snapshot",
    (
        _snapshot(schedule_ref="other-version"),
        _snapshot(instrument_ref="ETHUSDT-PERP"),
        _snapshot(direction=Direction.SHORT),
    ),
)
def test_direct_activation_rejects_snapshot_identity_mismatches(
    snapshot: OrderSchedulePreview,
) -> None:
    with pytest.raises(ValidationError, match="ORDER_SCHEDULE_SNAPSHOT_MISMATCH"):
        _activation(snapshot=snapshot)
