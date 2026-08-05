from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from halpha.capital.models import AuthorityClass, EnvironmentKind
from halpha.planning.models import PlanActivation, ProtectionState
from halpha.planning.service import PlanningApplicationService, _entry_valid_until
from halpha.planning.registry import DecisionBasisKind


NOW = datetime(2026, 7, 19, 22, 0, tzinfo=UTC)


def _version(*, entry_valid_minutes: int, plan_minutes: int) -> SimpleNamespace:
    return SimpleNamespace(
        decision_basis=SimpleNamespace(kind=DecisionBasisKind.STRATEGY_SIGNAL),
        strategy_basis=SimpleNamespace(
            normalized_parameters={"entry_valid_minutes": entry_valid_minutes}
        ),
        valid_until=NOW + timedelta(minutes=plan_minutes),
    )


def test_entry_deadline_uses_shorter_strategy_window() -> None:
    assert _entry_valid_until(
        _version(entry_valid_minutes=15, plan_minutes=20),
        activated_at=NOW,
    ) == NOW + timedelta(minutes=15)


def test_entry_deadline_never_exceeds_plan_validity() -> None:
    assert _entry_valid_until(
        _version(entry_valid_minutes=30, plan_minutes=20),
        activated_at=NOW,
    ) == NOW + timedelta(minutes=20)


def test_direct_execution_uses_the_plan_deadline() -> None:
    version = SimpleNamespace(
        decision_basis=SimpleNamespace(kind=DecisionBasisKind.DIRECT_EXECUTION),
        valid_until=NOW + timedelta(minutes=20),
    )

    assert _entry_valid_until(version, activated_at=NOW) == version.valid_until


def _activation() -> PlanActivation:
    return PlanActivation(
        activation_id="activation-direct-expiry",
        environment_id="demo-main",
        environment_kind=EnvironmentKind.DEMO,
        authority_class=AuthorityClass.DEMO_VALIDATION,
        plan_version_ref="version-direct-expiry",
        account_ref="demo-account",
        instrument_ref="BTCUSDT-PERP",
        direction="SHORT",
        decision_basis_ref="ONE_SHOT_DONCHIAN_ATR_BREAKOUT@1.0.1",
        framework_strategy_id="HALPHA-TEST",
        target_exposure="100",
        rule_state={},
        protection_state=ProtectionState.NONE,
        created_at=NOW,
        updated_at=NOW,
    )


class _PlanningRepository:
    def __init__(self) -> None:
        self.activation = _activation()
        self.event = None

    def get_activation(self, _activation_id: str, *, for_update: bool):
        assert for_update is True
        return self.activation

    def find_event_by_source(self, _activation_id: str, source_identity: str):
        if self.event is not None and self.event.source_identity == source_identity:
            return self.event
        return None

    def insert_event(self, event) -> None:
        self.event = event

    def update_activation(self, activation, *, expected_version: int) -> None:
        assert expected_version == self.activation.state_version
        self.activation = activation


def _service(repository: _PlanningRepository) -> PlanningApplicationService:
    service = object.__new__(PlanningApplicationService)
    service._planning = repository
    return service


def test_remaining_entry_expiry_consumes_at_its_own_deadline_idempotently() -> None:
    repository = _PlanningRepository()
    service = _service(repository)
    cutoff = NOW + timedelta(minutes=5)
    observed_at = cutoff + timedelta(seconds=1)

    consumed, event = service.expire_remaining_entry_opportunity(
        activation_id=repository.activation.activation_id,
        plan_event_id="remaining-expiry-event",
        source_cutoff=cutoff,
        observed_at=observed_at,
    )
    replayed, replayed_event = service.expire_remaining_entry_opportunity(
        activation_id=repository.activation.activation_id,
        plan_event_id="ignored-on-replay",
        source_cutoff=cutoff,
        observed_at=observed_at,
    )

    assert consumed.entry_opportunity_consumed is True
    assert event.rule_id == "ENTRY_REMAINING_EXPIRY"
    assert event.reason_code == "ENTRY_REMAINING_EXPIRED"
    assert event.no_action_reason == "ENTRY_REMAINING_EXPIRED"
    assert event.source_cutoff == cutoff
    assert replayed.entry_opportunity_consumed is True
    assert replayed_event is event


def test_remaining_entry_expiry_rejects_an_early_runtime_call() -> None:
    repository = _PlanningRepository()
    service = _service(repository)
    cutoff = NOW + timedelta(minutes=5)

    with pytest.raises(
        ValueError,
        match="ENTRY_REMAINING_DEADLINE_NOT_REACHED",
    ):
        service.expire_remaining_entry_opportunity(
            activation_id=repository.activation.activation_id,
            plan_event_id="remaining-expiry-event",
            source_cutoff=cutoff,
            observed_at=cutoff - timedelta(seconds=1),
        )

    assert repository.activation.entry_opportunity_consumed is False
    assert repository.event is None
