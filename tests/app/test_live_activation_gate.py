from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
import pytest
from pydantic import SecretStr

from halpha.app.planning_api import (
    ActivationPayload,
    PlanDraftPayload,
    PostgreSQLPlanningApi,
)
from halpha.live_write_gate import LiveWriteGateStatus
from halpha.planning.registry import Direction, OneShotParameters


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
    payload = PlanDraftPayload(
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
                    "strategy_id": "ONE_SHOT_DONCHIAN_ATR_BREAKOUT",
                    "instrument_ref": "BTCUSDT-PERP",
                    "direction": "SHORT",
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
