from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from pydantic import SecretStr

from halpha.app.planning_api import ActivationPayload, PostgreSQLPlanningApi
from halpha.live_write_gate import LiveWriteGateStatus


NOW = datetime(2026, 7, 18, 12, tzinfo=UTC)


def _status(
    *,
    capability: str = "QUALIFIED",
    real_capital: str = "AUTHORIZED",
    configured: str = "CLOSED",
    account_limit: str = "limit-live-001",
) -> LiveWriteGateStatus:
    authorized = real_capital == "AUTHORIZED"
    return LiveWriteGateStatus(
        live_write_build_capability=capability,
        b05_real_capital_eligibility=real_capital,
        configured_runtime_real_write_gate=configured,
        runtime_real_write_gate="CLOSED",
        build_manifest_digest="a" * 64 if authorized else None,
        user_authorization_ref=(
            "owner-decision:b05-live-001" if authorized else None
        ),
        account_capital_limit_version_ref=account_limit if authorized else None,
        machine_authorization_version_ref=(
            "authorization-live-001" if configured == "OPEN" else None
        ),
        plan_allocation_ref=(
            "allocation-live-001" if configured == "OPEN" else None
        ),
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


def _payload(**updates: bool) -> ActivationPayload:
    values = {
        "plan_version_id": "plan-version-live-001",
        "capital_limit_version_id": "limit-live-001",
        "quote_asset": "USDT",
        "owner_password": "owner-password",
        "real_capital_acknowledged": True,
        "evidence_limitations_acknowledged": True,
        "online_monitoring_acknowledged": True,
    }
    values.update(updates)
    return ActivationPayload(**values)


@pytest.mark.parametrize(
    ("status", "reason"),
    (
        (
            _status(capability="NOT_QUALIFIED", real_capital="BLOCKED"),
            "LIVE_WRITE_BUILD_CAPABILITY_NOT_QUALIFIED",
        ),
        (
            _status(real_capital="BLOCKED"),
            "B05_REAL_CAPITAL_ELIGIBILITY_BLOCKED",
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


def test_live_activation_requires_each_explicit_owner_acknowledgement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api(_status())
    monkeypatch.setattr(
        api,
        "_connect",
        lambda: pytest.fail("database must not be reached"),
    )
    with pytest.raises(ValueError, match="LIVE_OWNER_ACKNOWLEDGEMENTS_REQUIRED"):
        api.activate(
            _payload(online_monitoring_acknowledged=False),
            idempotency_key="live-001",
            observed_at=NOW,
        )


def test_live_activation_rejects_unbound_capital_scope_before_database_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api(_status(account_limit="limit-live-authorized"))
    monkeypatch.setattr(
        api,
        "_connect",
        lambda: pytest.fail("database must not be reached"),
    )

    with pytest.raises(ValueError, match="B05_REAL_CAPITAL_SCOPE_MISMATCH"):
        api.activate(_payload(), idempotency_key="live-001", observed_at=NOW)


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


def test_live_activation_persists_acknowledgements_without_opening_the_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class _Service:
        def __init__(self, _connection, _environment_id):
            pass

        def activate_version(self, **values):
            captured.update(values)
            return (
                _Document(activation_id="activation-live-001"),
                SimpleNamespace(authorization_version_id="authorization-live-001"),
                _Document(allocation_id="allocation-live-001"),
            )

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

    assert captured["activation_terms"] == {
        "real_capital_acknowledged": True,
        "evidence_limitations_acknowledged": True,
        "online_monitoring_acknowledged": True,
    }
    assert result["venue_write_created"] is False
    assert result["runtime_real_write_gate"] == "CLOSED"
