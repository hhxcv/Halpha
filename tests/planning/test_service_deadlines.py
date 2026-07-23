from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from halpha.planning.service import _entry_valid_until
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
