from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
import pytest
from pydantic import SecretStr, ValidationError

from halpha.app.planning_api import (
    ActivationPayload,
    ControlPayload,
    PlanCreatePayload,
    PostgreSQLPlanningApi,
)
from halpha.live_write_gate import LiveWriteGateStatus
from halpha.planning.order_policies import (
    CancelOnShockRule,
    ConditionGroup,
    InitialStopSpec,
    NumericComparator,
    ProfitRCondition,
    ProtectionPolicy,
    ProtectionStep,
    SteppedProtectionRule,
    TakeProfitLadderSpec,
    TakeProfitLevel,
)
from halpha.planning.order_schedule import (
    AmountDistribution,
    OrderScheduleSpec,
    ScheduleSubmissionMode,
    SinglePrice,
    VenueOrderPolicy,
    VenueOrderType,
    direct_allowed_action_profiles,
)
from halpha.planning.registry import (
    DIRECT_EXECUTION_REF,
    Direction,
    OneShotParameters,
)
from halpha.planning.transitions import ControlIntent


NOW = datetime(2026, 7, 18, 12, tzinfo=UTC)


def _status(
    *,
    consistent: bool | None = True,
    configured: str = "CLOSED",
) -> LiveWriteGateStatus:
    return LiveWriteGateStatus(
        configured_runtime_real_write_gate=configured,
        runtime_real_write_gate="CLOSED",
        product_build_id="a" * 64,
        product_build_consistent=consistent,
    )


def _api(status: LiveWriteGateStatus) -> PostgreSQLPlanningApi:
    return PostgreSQLPlanningApi(
        database_name="halpha_live",
        password=SecretStr("qualification-password"),
        environment_id="binance-live-primary",
        environment_kind="LIVE",
        authority_class="LIVE_REAL_CAPITAL",
        account_ref="binance-usdm-live-owner-primary",
        product_build_id="a" * 64,
        profile="BINANCE_LIVE_WRITE",
        gate_status_provider=lambda: status,
    )


def _payload() -> ActivationPayload:
    return ActivationPayload(plan_version_id="plan-version-live-001")


@pytest.mark.parametrize(
    ("status", "reason"),
    (
        (
            _status(consistent=False),
            "LIVE_WRITE_PRODUCT_BUILD_MISMATCH",
        ),
        (
            _status(configured="OPEN"),
            "LIVE_WRITE_GATE_MUST_BE_CLOSED_FOR_ACTIVATION",
        ),
    ),
)
def test_live_activation_rejects_before_database_mutation(
    status: LiveWriteGateStatus,
    reason: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api(status)
    monkeypatch.setattr(
        api,
        "_connect",
        lambda: pytest.fail("database must not be reached"),
    )
    with pytest.raises(ValueError, match=reason):
        api.activate(_payload(), idempotency_key="live-001", observed_at=NOW)


def test_activation_payload_rejects_legacy_capital_authorization_fields() -> None:
    with pytest.raises(ValueError):
        ActivationPayload(
            plan_version_id="plan-version-live-001",
            capital_limit_version_id="legacy-limit",  # type: ignore[call-arg]
        )


def test_live_plan_rejects_demo_immediate_entry_before_database_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api(_status())
    monkeypatch.setattr(
        api,
        "_connect",
        lambda: pytest.fail("database must not be reached"),
    )
    payload = PlanCreatePayload(
        plan_name="AI live boundary check",
        creator_kind="AI",
        strategy_id="ONE_SHOT_DONCHIAN_ATR_BREAKOUT",
        parameters={"demo_immediate_entry": True},
        instrument_ref="BTCUSDT-PERP",
        direction="LONG",
        target_exposure="100",
        max_margin="100",
        max_notional="100",
        max_allowed_loss="100",
        valid_minutes=15,
    )

    with pytest.raises(ValueError, match="DEMO_IMMEDIATE_ENTRY_REQUIRES_DEMO"):
        api.save_new_plan(
            payload,
            idempotency_key="demo-check-live-rejected",
            observed_at=NOW,
        )


def _direct_schedule(**updates: object) -> OrderScheduleSpec:
    values: dict[str, object] = {
        "price_distribution": SinglePrice(limit_price="100"),
        "amount_distribution": AmountDistribution(base_notional="20"),
        "protection_policy": ProtectionPolicy(
            initial_stop=InitialStopSpec(distance_bps="100"),
        ),
    }
    return OrderScheduleSpec(**{**values, **updates})


def _direct_payload(schedule: OrderScheduleSpec) -> PlanCreatePayload:
    return PlanCreatePayload(
        plan_name="AI direct capability boundary",
        creator_kind="AI",
        decision_basis={
            "kind": "DIRECT_EXECUTION",
            "decision_basis_ref": DIRECT_EXECUTION_REF,
            "parameters": {},
        },
        order_schedule_spec=schedule,
        instrument_ref="BTCUSDT-PERP",
        direction="LONG",
        target_exposure="100",
        max_margin="100",
        max_notional="100",
        max_allowed_loss="100",
        valid_minutes=15,
    )


@pytest.mark.parametrize(
    ("schedule", "reason"),
    (
        (
            _direct_schedule(
                entry_conditions=ConditionGroup(
                    items=(
                        ProfitRCondition(
                            comparator=NumericComparator.GTE,
                            threshold_r="1",
                        ),
                    )
                )
            ),
            "DIRECT_EXECUTION_PROFIT_R_UNSUPPORTED",
        ),
        (
            _direct_schedule(
                dynamic_rules=(
                    SteppedProtectionRule(
                        steps=(ProtectionStep(trigger_r="1", stop_r="0"),),
                    ),
                )
            ),
            "DIRECT_EXECUTION_STEPPED_PROTECTION_UNSUPPORTED",
        ),
        (
            _direct_schedule(
                dynamic_rules=(
                    CancelOnShockRule(
                        window_seconds=5,
                        adverse_move_bps="25",
                        max_triggers=2,
                    ),
                )
            ),
            "DIRECT_EXECUTION_CANCEL_ON_SHOCK_MAX_TRIGGERS_UNSUPPORTED",
        ),
        (
            _direct_schedule(
                submission_mode=ScheduleSubmissionMode.PREPROTECTED_PARALLEL,
            ),
            "PREPROTECTED_PARALLEL_NOT_VERIFIED",
        ),
        (
            _direct_schedule(
                protection_policy=ProtectionPolicy(
                    initial_stop=InitialStopSpec(distance_bps="100"),
                    take_profit_ladder=TakeProfitLadderSpec(
                        levels=(
                            TakeProfitLevel(
                                trigger_r="1",
                                quantity_fraction="0.5",
                            ),
                        )
                    ),
                ),
            ),
            "DIRECT_EXECUTION_TAKE_PROFIT_SPLIT_NOT_VERIFIED",
        ),
        (
            _direct_schedule(
                protection_policy=ProtectionPolicy(
                    initial_stop=InitialStopSpec(distance_bps="100"),
                    take_profit_ladder=TakeProfitLadderSpec(
                        levels=(
                            TakeProfitLevel(
                                trigger_r="1",
                                quantity_fraction="0.5",
                            ),
                            TakeProfitLevel(
                                trigger_r="2",
                                quantity_fraction="0.5",
                            ),
                        )
                    ),
                ),
            ),
            "DIRECT_EXECUTION_TAKE_PROFIT_SPLIT_NOT_VERIFIED",
        ),
    ),
)
def test_direct_plan_api_input_rejects_unconsumed_schedule_capabilities(
    schedule: OrderScheduleSpec,
    reason: str,
) -> None:
    with pytest.raises(ValidationError) as error:
        _direct_payload(schedule)

    assert {
        str(item.get("ctx", {}).get("error"))
        for item in error.value.errors(include_url=False)
    } == {reason}


def test_direct_plan_api_input_accepts_single_trigger_shock_rule() -> None:
    payload = _direct_payload(
        _direct_schedule(
            dynamic_rules=(
                CancelOnShockRule(
                    window_seconds=5,
                    adverse_move_bps="25",
                    max_triggers=1,
                ),
            )
        )
    )

    assert payload.order_schedule_spec is not None
    assert payload.order_schedule_spec.dynamic_rules[0].max_triggers == 1


def test_direct_limit_plan_gets_only_actions_its_schedule_can_use() -> None:
    assert direct_allowed_action_profiles(_direct_schedule()) == frozenset(
        {
            "ENTRY_LIMIT",
            "PROTECTIVE_STOP_REDUCE_ONLY",
            "CANCEL_ORDER",
            "REDUCE_OR_CLOSE_MARKET",
        }
    )


def test_direct_market_plan_gets_only_configured_take_profit_actions() -> None:
    schedule = _direct_schedule(
        price_distribution=SinglePrice(),
        venue_policy=VenueOrderPolicy(
            order_type=VenueOrderType.MARKET,
            time_in_force=None,
        ),
        protection_policy=ProtectionPolicy(
            initial_stop=InitialStopSpec(distance_bps="100"),
            take_profit_ladder=TakeProfitLadderSpec(
                levels=(
                    TakeProfitLevel(trigger_r="1", quantity_fraction="1"),
                )
            ),
        ),
    )

    assert direct_allowed_action_profiles(schedule) == frozenset(
        {
            "ENTRY_MARKET",
            "PROTECTIVE_STOP_REDUCE_ONLY",
            "REDUCE_OR_CLOSE_MARKET",
            "TAKE_PROFIT_1",
        }
    )


class _Context:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def transaction(self):
        return self


class _RowsConnection(_Context):
    def __init__(self, rows):
        self._rows = rows

    def execute(self, *_args):
        return self

    def fetchall(self):
        return self._rows


class _Document:
    def __init__(self, **values):
        self._values = values

    def model_dump(self, *, mode: str):
        assert mode == "json"
        return dict(self._values)


def test_user_takeover_scope_uses_the_server_command_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class _ControlService:
        def __init__(self, _connection, _environment_id):
            pass

        def submit(self, command, **_kwargs):
            captured["command"] = command
            return _Document(receipt_id="receipt-live-001")

    api = _api(_status())
    monkeypatch.setattr(api, "_connect", lambda: _Context())
    monkeypatch.setattr(
        "halpha.app.planning_api.ActivationControlService",
        _ControlService,
    )

    api.submit_control(
        "activation-live-001",
        ControlIntent.USER_TAKEOVER,
        ControlPayload(
            expected_version=1,
            takeover_scope={
                "command_ref": "user-controlled-command",
                "activation_id": "other-activation",
                "cutoff": "2000-01-01T00:00:00+00:00",
                "execution_responsibility": "USER",
            },
        ),
        idempotency_key="takeover-live-001",
        observed_at=NOW,
    )

    command = captured["command"]
    assert command.scope == {
        "command_ref": command.command_id,
        "activation_id": "activation-live-001",
        "cutoff": NOW.isoformat(),
        "execution_responsibility": "USER",
    }


def test_activation_preview_returns_the_fixed_protection_and_exit_terms(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parameters = OneShotParameters(
        direction=Direction.SHORT,
        confirmation_bars_1m=1,
        entry_valid_minutes=30,
        initial_stop_atr_multiple="1.0",
        max_hold_bars_15m=4,
        take_profit_1_r="1.0",
        take_profit_2_r="2.0",
    ).model_dump(mode="json")
    version = SimpleNamespace(
        plan_version_id="plan-version-live-001",
        plan_name=None,
        created_at=None,
        creator_kind=None,
        account_ref="binance-usdm-live-owner-primary",
        instrument_ref="BTCUSDT-PERP",
        direction=Direction.SHORT,
        strategy_basis=SimpleNamespace(
            strategy_id="ONE_SHOT_DONCHIAN_ATR_BREAKOUT",
            strategy_version="1.0.0",
            parameter_digest="b" * 64,
            product_build_id="a" * 64,
            normalized_parameters=parameters,
        ),
        requested_limits=SimpleNamespace(
            max_notional="500",
            model_dump=lambda **_kwargs: {
                "max_margin": "500",
                "max_notional": "500",
                "max_allowed_loss": "500",
            },
        ),
        valid_until=NOW,
        allowed_actions=frozenset({"ENTRY"}),
    )

    class _Repository:
        def __init__(self, *_args):
            pass

        @staticmethod
        def get_version(_plan_version_id):
            return version

    api = _api(_status())
    monkeypatch.setattr(api, "_connect", lambda: _Context())
    monkeypatch.setattr(
        "halpha.app.planning_api.PostgreSQLPlanningRepository",
        _Repository,
    )

    preview = api.activation_preview("plan-version-live-001")

    assert preview["strategy_parameters"] == parameters
    assert preview["strategy_parameters"]["initial_stop_atr_multiple"] == "1"
    assert preview["strategy_parameters"]["max_hold_bars_15m"] == 4


def test_plan_list_marks_a_fixed_plan_from_an_old_product_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api(_status())
    connection = _RowsConnection(
        [
            (
                "plan-001",
                1,
                "c" * 64,
                NOW,
                {
                    "plan_name": "AI short breakout",
                    "created_at": NOW.isoformat(),
                    "creator_kind": "AI",
                    "strategy_id": "ONE_SHOT_DONCHIAN_ATR_BREAKOUT",
                    "instrument_ref": "BTCUSDT-PERP",
                    "direction": "SHORT",
                    "parameters": {
                        "direction": "SHORT",
                        "channel_lookback_15m": 20,
                    },
                    "requested_limits": {"max_notional": "500"},
                    "valid_from": NOW.isoformat(),
                    "valid_until": "2026-07-18T13:00:00+00:00",
                },
                "plan-version-001",
                NOW,
                "d" * 64,
                "b" * 64,
                NOW.isoformat(),
            )
        ]
    )
    monkeypatch.setattr(api, "_connect", lambda: connection)

    plans = api.list_plans()

    assert plans[0]["fixed_product_build_id"] == "b" * 64
    assert plans[0]["fixed_valid_until"] == NOW.isoformat()
    assert plans[0]["product_build_consistent"] is False
    assert plans[0]["parameters"]["channel_lookback_15m"] == 20
    assert plans[0]["max_notional"] == "500"
    assert plans[0]["valid_until"] == "2026-07-18T13:00:00+00:00"
    assert plans[0]["plan_name"] == "AI short breakout"
    assert plans[0]["created_at"] == NOW.isoformat()
    assert plans[0]["creator_kind"] == "AI"


def test_live_activation_uses_the_plan_amount_without_opening_the_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class _Service:
        def __init__(self, _connection, _environment_id):
            pass

        def activate_version(self, **values):
            captured.update(values)
            return _Document(activation_id="activation-live-001")

    api = _api(_status())
    monkeypatch.setattr(api, "_connect", lambda: _Context())
    monkeypatch.setattr(
        "halpha.app.planning_api.PlanningApplicationService",
        _Service,
    )

    result = api.activate(
        _payload(),
        idempotency_key="live-001",
        observed_at=NOW,
    )

    assert "activation_terms" not in captured
    assert captured["environment_kind"].value == "LIVE"
    assert captured["authority_class"].value == "LIVE_REAL_CAPITAL"
    assert result["venue_write_created"] is False
    assert result["runtime_real_write_gate"] == "CLOSED"
