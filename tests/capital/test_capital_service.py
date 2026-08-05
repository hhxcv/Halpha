from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from halpha.capital.models import (
    AccountSystemStopReleaseRequest,
    AccountSystemStopSource,
    AuthorityClass,
    EnvironmentKind,
    StopCategory,
    StopStateVersion,
)
from halpha.capital.repository import CapitalConflict
from halpha.capital.service import CapitalApplicationService
from halpha.domain_values import content_digest


def _service(
    *categories: StopCategory,
    source: str = "USER_CONTROL",
) -> CapitalApplicationService:
    service = object.__new__(CapitalApplicationService)
    service._planning = SimpleNamespace(
        get_activation=lambda _activation_id: SimpleNamespace(
            activation_id="activation-1",
            account_ref="account-1",
        )
    )
    service._capital = SimpleNamespace(
        lock_current_stop_states=lambda **_values: (
            SimpleNamespace(
                stopped_categories=frozenset(categories),
                source=source,
            ),
        )
    )
    return service


def test_new_risk_state_is_visible_before_strategy_proposal() -> None:
    assert _service().new_risk_allowed("activation-1") is True
    assert (
        _service(StopCategory.NEW_RISK).new_risk_allowed("activation-1")
        is False
    )
    assert (
        _service(StopCategory.ALL_EXCHANGE_CHANGES).new_risk_allowed(
            "activation-1"
        )
        is False
    )


def test_only_unresolved_system_external_activity_is_an_attribution_conflict() -> None:
    assert _service().external_activity_conflict("activation-1") is False
    assert (
        _service(
            StopCategory.NEW_RISK,
            source="SYSTEM_EXTERNAL_ACTIVITY",
        ).external_activity_conflict("activation-1")
        is True
    )
    assert (
        _service(
            StopCategory.ALL_EXCHANGE_CHANGES,
            source="USER_CONTROL",
        ).external_activity_conflict("activation-1")
        is False
    )


class _StopRepository:
    def __init__(self) -> None:
        self.states = []

    def lock_current_stop_states(self, **_values):
        return tuple(self.states[-1:])

    def lock_current_account_stop_state(self, **_values):
        return self.states[-1] if self.states else None

    def insert_stop_state(self, state) -> None:
        self.states.append(state)


def _stateful_service() -> tuple[CapitalApplicationService, _StopRepository]:
    repository = _StopRepository()
    service = object.__new__(CapitalApplicationService)
    service._environment_id = "demo-1"
    service._connection = SimpleNamespace(transaction=lambda: nullcontext())
    service._planning = SimpleNamespace(
        get_activation=lambda _activation_id: SimpleNamespace(
            activation_id="activation-1",
            account_ref="account-1",
        )
    )
    service._capital = repository
    return service, repository


def _record_stop(
    service: CapitalApplicationService,
    method_name: str,
    *,
    evidence_digest: str,
):
    return getattr(service, method_name)(
        stop_state_version_id=f"stop-{len(service._capital.states) + 1}",
        environment_kind=EnvironmentKind.DEMO,
        authority_class=AuthorityClass.DEMO_VALIDATION,
        account_ref="account-1",
        evidence_digest=evidence_digest,
        observed_at=datetime(2026, 7, 24, 13, tzinfo=UTC),
    )


def _release_request(
    current,
    **updates: object,
) -> AccountSystemStopReleaseRequest:
    values: dict[str, object] = {
        "new_stop_state_version_id": f"stop-{current.version + 1}",
        "environment_id": "demo-1",
        "environment_kind": EnvironmentKind.DEMO,
        "authority_class": AuthorityClass.DEMO_VALIDATION,
        "account_ref": "account-1",
        "resolution_activation_id": "activation-1",
        "expected_version": current.version,
        "expected_stop_content_digest": current.content_digest,
        "expected_source": AccountSystemStopSource(current.source),
        "reconciliation_digest": "1" * 64,
        "resolution_evidence_digest": "2" * 64,
        "reconciliation_observed_at": datetime(
            2026, 7, 24, 13, 0, 10, tzinfo=UTC
        ),
        "submitted_at": datetime(2026, 7, 24, 13, 0, 11, tzinfo=UTC),
        "resolution_status": "NO_UNRESOLVED_ACCOUNT_STOP_CAUSE",
        "confirmation": "USER_CONFIRMED_SYSTEM_STOP_RELEASE",
    }
    values.update(updates)
    return AccountSystemStopReleaseRequest(**values)


def test_attributed_action_anomaly_stops_entry_without_blocking_exit_attribution() -> None:
    service, repository = _stateful_service()

    state = _record_stop(
        service,
        "stop_new_risk_for_attributed_action_anomaly",
        evidence_digest="a" * 64,
    )

    assert state.source == "SYSTEM_ATTRIBUTED_ACTION_ANOMALY"
    assert service.new_risk_allowed("activation-1") is False
    assert service.external_activity_conflict("activation-1") is False
    assert repository.states == [state]


def test_attributed_anomaly_cannot_hide_an_existing_external_activity_conflict() -> None:
    service, repository = _stateful_service()
    external = _record_stop(
        service,
        "stop_new_risk_for_external_activity",
        evidence_digest="b" * 64,
    )

    retained = _record_stop(
        service,
        "stop_new_risk_for_attributed_action_anomaly",
        evidence_digest="c" * 64,
    )

    assert retained is external
    assert repository.states == [external]
    assert service.external_activity_conflict("activation-1") is True


def test_account_system_stop_versions_are_bounded_until_resolution() -> None:
    service, repository = _stateful_service()
    anomaly = _record_stop(
        service,
        "stop_new_risk_for_attributed_action_anomaly",
        evidence_digest="d" * 64,
    )
    repeated_anomaly = _record_stop(
        service,
        "stop_new_risk_for_attributed_action_anomaly",
        evidence_digest="e" * 64,
    )
    external = _record_stop(
        service,
        "stop_new_risk_for_external_activity",
        evidence_digest="f" * 64,
    )
    repeated_external = _record_stop(
        service,
        "stop_new_risk_for_external_activity",
        evidence_digest="0" * 64,
    )

    assert repeated_anomaly is anomaly
    assert repeated_external is external
    assert [state.source for state in repository.states] == [
        "SYSTEM_ATTRIBUTED_ACTION_ANOMALY",
        "SYSTEM_EXTERNAL_ACTIVITY",
    ]
    assert service.external_activity_conflict("activation-1") is True


def test_system_stop_preserves_existing_categories_rules_and_loss_latch() -> None:
    service, repository = _stateful_service()
    fields = {
        "stop_state_version_id": "stop-existing-loss-latch",
        "environment_id": "demo-1",
        "environment_kind": EnvironmentKind.DEMO,
        "authority_class": AuthorityClass.DEMO_VALIDATION,
        "account_ref": "account-1",
        "activation_id": None,
        "version": 4,
        "stopped_categories": frozenset(
            {StopCategory.ALL_EXCHANGE_CHANGES}
        ),
        "reason": "EXISTING_LOSS_LATCH",
        "source": "SYSTEM_LOSS_LATCH",
        "started_at": datetime(2026, 7, 24, 12, tzinfo=UTC),
        "loss_latch_digest": "9" * 64,
        "release_rules": {
            "ALL_EXCHANGE_CHANGES": {"user_releasable": False}
        },
    }
    current = StopStateVersion(
        **fields,
        content_digest=content_digest(fields),
    )
    repository.states.append(current)

    stopped = _record_stop(
        service,
        "stop_new_risk_for_external_activity",
        evidence_digest="8" * 64,
    )

    assert stopped.version == 5
    assert stopped.stopped_categories == frozenset(
        {
            StopCategory.NEW_RISK,
            StopCategory.ALL_EXCHANGE_CHANGES,
        }
    )
    assert stopped.loss_latch_digest == "9" * 64
    assert stopped.release_rules["ALL_EXCHANGE_CHANGES"] == {
        "user_releasable": False
    }


def test_explicit_system_stop_release_appends_evidence_and_restores_new_risk() -> None:
    service, repository = _stateful_service()
    stopped = _record_stop(
        service,
        "stop_new_risk_for_external_activity",
        evidence_digest="a" * 64,
    )

    released = service.release_account_system_stop(_release_request(stopped))

    assert repository.states == [stopped, released]
    assert released.version == stopped.version + 1
    assert released.source == "USER_SYSTEM_STOP_RELEASE"
    assert released.stopped_categories == frozenset()
    assert released.release_rules["system_stop_release"] == {
        "released_stop_state_version_id": stopped.stop_state_version_id,
        "released_stop_version": stopped.version,
        "released_stop_content_digest": stopped.content_digest,
        "released_source": stopped.source,
        "resolution_activation_id": "activation-1",
        "reconciliation_digest": "1" * 64,
        "resolution_evidence_digest": "2" * 64,
        "reconciliation_observed_at": "2026-07-24T13:00:10+00:00",
        "confirmation": "USER_CONFIRMED_SYSTEM_STOP_RELEASE",
    }
    assert "prior_release_rules" not in released.release_rules
    assert service.new_risk_allowed("activation-1") is True
    assert service.external_activity_conflict("activation-1") is False


def test_system_stop_release_replay_fails_on_expected_version() -> None:
    service, _repository = _stateful_service()
    stopped = _record_stop(
        service,
        "stop_new_risk_for_attributed_action_anomaly",
        evidence_digest="b" * 64,
    )
    request = _release_request(stopped)
    service.release_account_system_stop(request)

    with pytest.raises(CapitalConflict, match="SYSTEM_STOP_VERSION_CONFLICT"):
        service.release_account_system_stop(
            request.model_copy(update={"new_stop_state_version_id": "stop-3"})
        )


@pytest.mark.parametrize(
    ("updates", "reason"),
    (
        ({"expected_version": 2}, "SYSTEM_STOP_VERSION_CONFLICT"),
        ({"expected_stop_content_digest": "3" * 64}, "SYSTEM_STOP_CONTENT_CONFLICT"),
        (
            {"expected_source": AccountSystemStopSource.EXTERNAL_ACTIVITY},
            "SYSTEM_STOP_SOURCE_CONFLICT",
        ),
    ),
)
def test_system_stop_release_binds_the_exact_current_stop(
    updates: dict[str, object],
    reason: str,
) -> None:
    service, repository = _stateful_service()
    stopped = _record_stop(
        service,
        "stop_new_risk_for_attributed_action_anomaly",
        evidence_digest="c" * 64,
    )

    with pytest.raises(CapitalConflict, match=reason):
        service.release_account_system_stop(
            _release_request(stopped, **updates)
        )

    assert repository.states == [stopped]
    assert service.new_risk_allowed("activation-1") is False


def test_system_stop_release_reconciliation_must_follow_the_stop() -> None:
    service, repository = _stateful_service()
    stopped = _record_stop(
        service,
        "stop_new_risk_for_external_activity",
        evidence_digest="d" * 64,
    )
    request = _release_request(
        stopped,
        reconciliation_observed_at=stopped.started_at - timedelta(seconds=1),
        submitted_at=stopped.started_at,
    )

    with pytest.raises(
        CapitalConflict,
        match="SYSTEM_STOP_RELEASE_EVIDENCE_PREDATES_STOP",
    ):
        service.release_account_system_stop(request)

    assert repository.states == [stopped]


def test_system_stop_release_request_rejects_stale_evidence() -> None:
    service, _repository = _stateful_service()
    stopped = _record_stop(
        service,
        "stop_new_risk_for_external_activity",
        evidence_digest="e" * 64,
    )

    with pytest.raises(ValueError, match="SYSTEM_STOP_RELEASE_EVIDENCE_STALE"):
        _release_request(
            stopped,
            submitted_at=datetime(2026, 7, 24, 13, 1, 16, tzinfo=UTC),
        )
