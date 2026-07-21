from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from halpha.planning.service import _entry_valid_until


NOW = datetime(2026, 7, 19, 22, 0, tzinfo=UTC)


def _version(*, entry_valid_minutes: int, plan_minutes: int) -> SimpleNamespace:
    return SimpleNamespace(
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
