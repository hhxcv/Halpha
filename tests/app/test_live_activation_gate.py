from __future__ import annotations

from datetime import UTC, datetime
import pytest
from pydantic import SecretStr

from halpha.app.planning_api import ActivationPayload, PostgreSQLPlanningApi
from halpha.live_write_gate import LiveWriteGateStatus


NOW = datetime(2026, 7, 18, 12, tzinfo=UTC)


def _status(
    *,
    capability: str = "QUALIFIED",
    configured: str = "CLOSED",
) -> LiveWriteGateStatus:
    return LiveWriteGateStatus(
        live_write_build_capability=capability,
        configured_runtime_real_write_gate=configured,
        runtime_real_write_gate="CLOSED",
        build_manifest_digest="a" * 64 if capability == "QUALIFIED" else None,
    )


def _api(status: LiveWriteGateStatus) -> PostgreSQLPlanningApi:
    return PostgreSQLPlanningApi(
        database_name="halpha_live",
        password=SecretStr("qualification-password"),
        environment_id="binance-live-primary",
        environment_kind="LIVE",
        authority_class="LIVE_REAL_CAPITAL",
        account_ref="binance-usdm-live-owner-primary",
        build_digest="a" * 64,
        profile="BINANCE_LIVE_WRITE",
        gate_status_provider=lambda: status,
    )


def _payload() -> ActivationPayload:
    return ActivationPayload(plan_version_id="plan-version-live-001")


@pytest.mark.parametrize(
    ("status", "reason"),
    (
        (
            _status(capability="NOT_QUALIFIED"),
            "LIVE_WRITE_BUILD_CAPABILITY_NOT_QUALIFIED",
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


class _Context:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def transaction(self):
        return self


class _Document:
    def __init__(self, **values):
        self._values = values

    def model_dump(self, *, mode: str):
        assert mode == "json"
        return dict(self._values)


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
