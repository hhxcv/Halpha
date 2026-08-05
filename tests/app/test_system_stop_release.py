from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from pydantic import SecretStr, ValidationError

import halpha.app.planning_api as planning_api_module
from halpha.app.planning_api import (
    PostgreSQLPlanningApi,
    SystemStopReleasePayload,
)
from halpha.capital.models import (
    AuthorityClass,
    EnvironmentKind,
    StopCategory,
    StopStateVersion,
)
from halpha.planning.models import PlanActivation, PlanLifecycle, ProtectionState
from halpha.planning.repository import PlanningConflict


STOPPED_AT = datetime(2026, 7, 24, 12, 0, tzinfo=UTC)
SNAPSHOT_AT = STOPPED_AT + timedelta(seconds=30)
OBSERVED_AT = SNAPSHOT_AT + timedelta(seconds=1)


def _api(*, profile: str = "BINANCE_DEMO") -> PostgreSQLPlanningApi:
    return PostgreSQLPlanningApi(
        database_name="halpha_demo",
        database_role_name="halpha_demo_app",
        password=SecretStr("test-password"),
        environment_id="demo-main",
        environment_kind="DEMO",
        authority_class="DEMO_VALIDATION",
        account_ref="demo-owner",
        product_build_id="a" * 64,
        profile=profile,
    )


def _stop(**updates: object) -> StopStateVersion:
    values: dict[str, object] = {
        "stop_state_version_id": "stop-system-1",
        "environment_id": "demo-main",
        "environment_kind": EnvironmentKind.DEMO,
        "authority_class": AuthorityClass.DEMO_VALIDATION,
        "account_ref": "demo-owner",
        "activation_id": None,
        "version": 3,
        "stopped_categories": frozenset({StopCategory.NEW_RISK}),
        "reason": "SYSTEM_EXTERNAL_ACTIVITY",
        "source": "SYSTEM_EXTERNAL_ACTIVITY",
        "started_at": STOPPED_AT,
        "release_rules": {},
        "content_digest": "b" * 64,
    }
    values.update(updates)
    return StopStateVersion(**values)


def _activation(**updates: object) -> PlanActivation:
    values: dict[str, object] = {
        "activation_id": "activation-release",
        "environment_id": "demo-main",
        "environment_kind": EnvironmentKind.DEMO,
        "authority_class": AuthorityClass.DEMO_VALIDATION,
        "plan_version_ref": "plan-version-release",
        "account_ref": "demo-owner",
        "instrument_ref": "BTCUSDT-PERP",
        "direction": "LONG",
        "decision_basis_ref": "ONE_SHOT_DONCHIAN_ATR_BREAKOUT@1.0.1",
        "framework_strategy_id": "HALPHA-RELEASE",
        "target_exposure": "100",
        "lifecycle": PlanLifecycle.COMPLETED,
        "responsibility_owner": "USER",
        "state_version": 9,
        "rule_state": {},
        "protection_state": ProtectionState.NONE,
        "takeover_scope": {"command_ref": "takeover-release"},
        "closure_digest": "c" * 64,
        "created_at": STOPPED_AT - timedelta(minutes=5),
        "updated_at": SNAPSHOT_AT,
    }
    values.update(updates)
    return PlanActivation(**values)


def _snapshot_payload(**updates: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema": "HALPHA_BINANCE_USDM_ACCOUNT_SNAPSHOT_V2",
        "query_paths": [
            "/fapi/v3/positionRisk",
            "/fapi/v1/symbolConfig",
            "/fapi/v1/openOrders",
            "/fapi/v1/openAlgoOrders",
        ],
        "read_only": True,
        "snapshot_complete": True,
        "snapshot_started_at": STOPPED_AT.isoformat(),
        "management_authority": "NONE",
        "positions": [],
        "open_position_count": 0,
        "ordinary_open_orders": [],
        "algo_open_orders": [],
        "ordinary_open_order_count": 0,
        "algo_open_order_count": 0,
    }
    payload.update(updates)
    return payload


class _Result:
    def __init__(
        self,
        *,
        one: tuple[object, ...] | None = None,
        all_rows: tuple[tuple[object, ...], ...] = (),
    ) -> None:
        self._one = one
        self._all = all_rows

    def fetchone(self) -> tuple[object, ...] | None:
        return self._one

    def fetchall(self) -> tuple[tuple[object, ...], ...]:
        return self._all


class _EvidenceConnection:
    def __init__(
        self,
        *,
        payload: dict[str, object] | None = None,
        received_at: datetime = SNAPSHOT_AT,
        cutoff: datetime = SNAPSHOT_AT,
        open_activations: tuple[tuple[object, ...], ...] = (),
        open_actions: tuple[tuple[object, ...], ...] = (),
        later_account_facts: tuple[tuple[object, ...], ...] = (),
        missing_snapshot: bool = False,
    ) -> None:
        self.payload = payload or _snapshot_payload()
        self.received_at = received_at
        self.cutoff = cutoff
        self.open_activations = open_activations
        self.open_actions = open_actions
        self.later_account_facts = later_account_facts
        self.missing_snapshot = missing_snapshot
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def execute(
        self,
        query: str,
        parameters: tuple[object, ...],
    ) -> _Result:
        self.calls.append((query, parameters))
        if "kind = 'ACCOUNT_STATE'" in query:
            if self.missing_snapshot:
                return _Result()
            return _Result(
                one=(
                    "account-fact-1",
                    self.received_at,
                    self.cutoff,
                    self.payload,
                    "d" * 64,
                )
            )
        if "FROM halpha.plan_activation" in query:
            return _Result(all_rows=self.open_activations)
        if "FROM halpha.execution_action" in query:
            return _Result(all_rows=self.open_actions)
        if "received_at > %s" in query:
            return _Result(all_rows=self.later_account_facts)
        raise AssertionError(f"unexpected query: {query}")


def _evidence(
    monkeypatch: pytest.MonkeyPatch,
    connection: _EvidenceConnection,
    *,
    activation: PlanActivation | None = None,
    stop: StopStateVersion | None = None,
    observed_at: datetime = OBSERVED_AT,
) -> dict[str, object]:
    selected_activation = activation or _activation()
    monkeypatch.setattr(
        planning_api_module,
        "PostgreSQLPlanningRepository",
        lambda _connection, _environment_id: SimpleNamespace(
            get_activation=lambda _activation_id: selected_activation
        ),
    )
    return _api()._system_stop_release_evidence(
        connection,  # type: ignore[arg-type]
        activation_id=selected_activation.activation_id,
        current_stop=stop or _stop(),
        observed_at=observed_at,
    )


def test_release_evidence_accepts_fresh_fully_attributed_account_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evidence = _evidence(monkeypatch, _EvidenceConnection())

    assert evidence["eligible"] is True
    assert evidence["denial_reasons"] == []
    assert evidence["evidence_cutoff"] == SNAPSHOT_AT.isoformat()
    assert evidence["_reconciliation_digest"] != evidence[
        "_resolution_evidence_digest"
    ]
    public = _api()._public_system_stop_release_preview(evidence)
    assert public["eligible"] is True
    assert not any(key.startswith("_") for key in public)


def test_release_without_a_context_activation_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        planning_api_module,
        "PostgreSQLPlanningRepository",
        lambda _connection, _environment_id: SimpleNamespace(
            get_activation=lambda _activation_id: (_ for _ in ()).throw(
                PlanningConflict("ACTIVATION_NOT_FOUND")
            )
        ),
    )

    evidence = _api()._system_stop_release_evidence(
        _EvidenceConnection(),  # type: ignore[arg-type]
        activation_id="missing-activation",
        current_stop=_stop(),
        observed_at=OBSERVED_AT,
    )

    assert evidence["eligible"] is False
    assert evidence["denial_reasons"] == [
        "SYSTEM_STOP_RELEASE_CONTEXT_ACTIVATION_NOT_FOUND"
    ]


@pytest.mark.parametrize(
    ("connection", "reason"),
    (
        (
            _EvidenceConnection(missing_snapshot=True),
            "SYSTEM_STOP_RELEASE_ACCOUNT_SNAPSHOT_MISSING",
        ),
        (
            _EvidenceConnection(
                payload=_snapshot_payload(
                    query_paths=[
                        "/fapi/v3/positionRisk",
                        "/fapi/v1/symbolConfig",
                        "/fapi/v1/openOrders",
                    ]
                )
            ),
            "SYSTEM_STOP_RELEASE_ACCOUNT_SNAPSHOT_INVALID",
        ),
        (
            _EvidenceConnection(
                payload=_snapshot_payload(open_position_count=1)
            ),
            "SYSTEM_STOP_RELEASE_ACCOUNT_SNAPSHOT_INVALID",
        ),
        (
            _EvidenceConnection(
                payload=_snapshot_payload(
                    positions=[{"symbol": "BTCUSDT", "position_amount": "0.001"}],
                    open_position_count=1,
                )
            ),
            "SYSTEM_STOP_RELEASE_ACCOUNT_NOT_FLAT",
        ),
        (
            _EvidenceConnection(
                payload=_snapshot_payload(
                    ordinary_open_orders=[{"client_order_id": "ordinary-1"}],
                    algo_open_orders=[{"client_order_id": "algo-1"}],
                    ordinary_open_order_count=1,
                    algo_open_order_count=1,
                )
            ),
            "SYSTEM_STOP_RELEASE_OPEN_ORDERS_REMAIN",
        ),
        (
            _EvidenceConnection(
                later_account_facts=(("fact-new-1", "POSITION_STATE", "e" * 64),)
            ),
            "SYSTEM_STOP_RELEASE_NEW_UNCLAIMED_FACT",
        ),
    ),
)
def test_release_evidence_fails_closed_for_incomplete_or_unresolved_account_state(
    monkeypatch: pytest.MonkeyPatch,
    connection: _EvidenceConnection,
    reason: str,
) -> None:
    evidence = _evidence(monkeypatch, connection)

    assert evidence["eligible"] is False
    assert reason in evidence["denial_reasons"]


def test_release_evidence_rejects_running_halpha_activations_on_the_same_account(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _EvidenceConnection(
        open_activations=(("activation-running-other", "RUNNING"),)
    )

    evidence = _evidence(monkeypatch, connection)
    different_ref_evidence = _evidence(
        monkeypatch,
        _EvidenceConnection(
            open_activations=(
                ("activation-running-replacement", "RUNNING"),
            )
        ),
    )

    assert evidence["eligible"] is False
    assert "SYSTEM_STOP_RELEASE_ACCOUNT_ACTIVATIONS_OPEN" in evidence[
        "denial_reasons"
    ]
    assert evidence["_resolution_evidence_digest"] != different_ref_evidence[
        "_resolution_evidence_digest"
    ]
    activation_query, parameters = next(
        call
        for call in connection.calls
        if "FROM halpha.plan_activation" in call[0]
    )
    assert "account_ref = %s" in activation_query
    assert "lifecycle <> 'COMPLETED'" in activation_query
    assert parameters == ("demo-main", "demo-owner")


def test_release_rejects_another_unknown_action_on_the_same_account(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _EvidenceConnection(
        open_actions=(
            ("action-unknown-other-activation", "UNKNOWN", "client-unknown"),
        )
    )

    evidence = _evidence(monkeypatch, connection)
    different_ref_evidence = _evidence(
        monkeypatch,
        _EvidenceConnection(
            open_actions=(
                ("action-unknown-replacement", "UNKNOWN", "client-replacement"),
            )
        ),
    )

    assert evidence["eligible"] is False
    assert "SYSTEM_STOP_RELEASE_ACCOUNT_ACTIONS_OPEN" in evidence[
        "denial_reasons"
    ]
    assert evidence["_resolution_evidence_digest"] != different_ref_evidence[
        "_resolution_evidence_digest"
    ]
    action_query, parameters = next(
        call
        for call in connection.calls
        if "FROM halpha.execution_action" in call[0]
    )
    assert "account_ref = %s" in action_query
    assert "state NOT IN ('CLOSED', 'NOT_SUBMITTED', 'HANDED_OVER')" in (
        action_query
    )
    assert parameters == ("demo-main", "demo-owner")


def test_release_rejects_current_open_orders_even_when_action_owned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _snapshot_payload(
        ordinary_open_orders=[{"client_order_id": "owned-order"}],
        algo_open_orders=[{"client_order_id": "owned-protection"}],
        ordinary_open_order_count=1,
        algo_open_order_count=1,
    )
    connection = _EvidenceConnection(
        payload=payload,
        open_actions=(
            ("entry-action", "OPEN", "owned-order"),
            ("protection-action", "OPEN", "owned-protection"),
        ),
    )

    evidence = _evidence(monkeypatch, connection)

    assert evidence["eligible"] is False
    assert "SYSTEM_STOP_RELEASE_OPEN_ORDERS_REMAIN" in evidence[
        "denial_reasons"
    ]
    assert "SYSTEM_STOP_RELEASE_ACCOUNT_ACTIONS_OPEN" in evidence[
        "denial_reasons"
    ]


def test_release_rejects_nonzero_position_even_when_halpha_attributed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _snapshot_payload(
        positions=[
            {
                "symbol": "BTCUSDT",
                "position_amount": "0.001",
                "management_status": "HALPHA_ATTRIBUTED",
            }
        ],
        open_position_count=1,
    )

    evidence = _evidence(
        monkeypatch,
        _EvidenceConnection(payload=payload),
    )

    assert evidence["eligible"] is False
    assert "SYSTEM_STOP_RELEASE_ACCOUNT_NOT_FLAT" in evidence[
        "denial_reasons"
    ]


def test_release_rejects_action_bound_late_fill_after_flat_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _EvidenceConnection(
        later_account_facts=(("fact-late-fill", "FILL", "f" * 64),)
    )

    evidence = _evidence(monkeypatch, connection)

    assert evidence["eligible"] is False
    assert "SYSTEM_STOP_RELEASE_NEW_UNCLAIMED_FACT" in evidence[
        "denial_reasons"
    ]
    fact_query, parameters = next(
        call
        for call in connection.calls
        if "received_at > %s" in call[0]
    )
    assert "action_ref IS NULL" not in fact_query
    assert parameters == ("demo-main", "demo-owner", SNAPSHOT_AT)


def test_release_evidence_rejects_stale_or_pre_stop_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stale = _evidence(
        monkeypatch,
        _EvidenceConnection(),
        observed_at=SNAPSHOT_AT + timedelta(seconds=66),
    )
    predating = _evidence(
        monkeypatch,
        _EvidenceConnection(
            received_at=STOPPED_AT - timedelta(seconds=1),
            cutoff=STOPPED_AT - timedelta(seconds=1),
        ),
    )

    assert "SYSTEM_STOP_RELEASE_EVIDENCE_STALE" in stale["denial_reasons"]
    assert "SYSTEM_STOP_RELEASE_EVIDENCE_PREDATES_STOP" in predating[
        "denial_reasons"
    ]


def test_release_requires_completed_user_takeover_after_the_stop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    not_closed = _evidence(
        monkeypatch,
        _EvidenceConnection(),
        activation=_activation(
            lifecycle=PlanLifecycle.RUNNING,
            responsibility_owner="HALPHA",
            takeover_scope=None,
            closure_digest=None,
        ),
    )
    predating = _evidence(
        monkeypatch,
        _EvidenceConnection(),
        activation=_activation(updated_at=STOPPED_AT - timedelta(seconds=1)),
    )

    assert not_closed["denial_reasons"] == ["USER_TAKEOVER_CLOSURE_REQUIRED"]
    assert predating["denial_reasons"] == [
        "SYSTEM_STOP_RELEASE_CLOSURE_PREDATES_STOP"
    ]


def test_release_payload_cannot_upload_or_replace_server_evidence() -> None:
    with pytest.raises(ValidationError):
        SystemStopReleasePayload.model_validate(
            {
                "expected_stop_version": 3,
                "confirmation": "USER_CONFIRMED_SYSTEM_STOP_RELEASE",
                "reconciliation_digest": "f" * 64,
            }
        )


def test_live_read_only_rejects_release_before_database_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api(profile="BINANCE_LIVE_READ_ONLY")
    monkeypatch.setattr(
        api,
        "_connect",
        lambda: pytest.fail("database must not be reached"),
    )

    with pytest.raises(
        ValueError,
        match="LIVE_READ_ONLY_PRODUCT_MUTATION_FORBIDDEN",
    ):
        api.release_system_stop(
            "activation-release",
            SystemStopReleasePayload(
                expected_stop_version=3,
                confirmation="USER_CONFIRMED_SYSTEM_STOP_RELEASE",
            ),
            idempotency_key="release-read-only",
            observed_at=OBSERVED_AT,
        )


class _Transaction:
    def __enter__(self) -> None:
        return None

    def __exit__(self, *_args: object) -> None:
        return None


class _ReleaseConnection:
    def __enter__(self) -> "_ReleaseConnection":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def transaction(self) -> _Transaction:
        return _Transaction()


def test_release_submission_uses_only_recomputed_server_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    current = _stop()
    captured: list[object] = []
    repository = SimpleNamespace(
        find_stop_state=lambda _stop_id: None,
        lock_current_account_stop_state=lambda **_values: current,
    )
    released = current.model_copy(
        update={
            "stop_state_version_id": "stop-release",
            "version": 4,
            "stopped_categories": frozenset(),
            "source": "USER_SYSTEM_STOP_RELEASE",
        }
    )
    monkeypatch.setattr(api, "_connect", lambda: _ReleaseConnection())
    monkeypatch.setattr(
        planning_api_module,
        "PostgreSQLCapitalRepository",
        lambda _connection, _environment_id: repository,
    )
    monkeypatch.setattr(
        api,
        "_system_stop_release_evidence",
        lambda _connection, **_values: {
            "eligible": True,
            "denial_reasons": [],
            "_reconciliation_digest": "1" * 64,
            "_resolution_evidence_digest": "2" * 64,
            "_reconciliation_observed_at": SNAPSHOT_AT,
        },
    )
    monkeypatch.setattr(
        planning_api_module,
        "CapitalApplicationService",
        lambda _connection, _environment_id: SimpleNamespace(
            release_account_system_stop=lambda request: (
                captured.append(request) or released
            )
        ),
    )

    result = api.release_system_stop(
        "activation-release",
        SystemStopReleasePayload(
            expected_stop_version=3,
            confirmation="USER_CONFIRMED_SYSTEM_STOP_RELEASE",
        ),
        idempotency_key="release-write",
        observed_at=OBSERVED_AT,
    )

    assert result["effective"] is True
    assert result["replayed"] is False
    assert len(captured) == 1
    request = captured[0]
    assert request.expected_stop_content_digest == current.content_digest
    assert request.reconciliation_digest == "1" * 64
    assert request.resolution_evidence_digest == "2" * 64
    assert request.reconciliation_observed_at == SNAPSHOT_AT
