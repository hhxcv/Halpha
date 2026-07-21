from __future__ import annotations

from contextlib import nullcontext
from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import SecretStr

from halpha.executor.continuity import (
    ExecutorContinuityUnavailable,
    PostgreSQLExecutorContinuityGuard,
)
from halpha.planning.service import PlanningApplicationService
from halpha.planning.repository import PostgreSQLPlanningRepository


class FakeConnection:
    def __enter__(self) -> "FakeConnection":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def transaction(self) -> nullcontext[None]:
        return nullcontext()


def test_executor_startup_pauses_before_readiness(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[datetime] = []
    connection = FakeConnection()

    def connector(**kwargs: Any) -> FakeConnection:
        assert kwargs["dbname"] == "halpha_demo"
        assert kwargs["user"] == "halpha_demo_executor"
        assert kwargs["password"] == "database-secret"
        return connection

    def pause(
        _self: PlanningApplicationService,
        observed_at: datetime,
    ) -> int:
        calls.append(observed_at)
        return 3

    monkeypatch.setattr(
        PlanningApplicationService,
        "pause_for_writer_continuity_loss",
        pause,
    )
    observed_at = datetime(2026, 7, 17, 10, tzinfo=UTC)
    count = PostgreSQLExecutorContinuityGuard(
        database_name="halpha_demo",
        password=SecretStr("database-secret"),
        environment_id="binance-demo-primary",
        connector=connector,
    ).pause_open_activations(observed_at)
    assert count == 3
    assert calls == [observed_at]


def test_database_continuity_failure_is_sanitized_and_fail_closed() -> None:
    def unavailable(**_kwargs: Any) -> FakeConnection:
        raise OSError("database-secret must not escape")

    guard = PostgreSQLExecutorContinuityGuard(
        database_name="halpha_demo",
        password=SecretStr("database-secret"),
        environment_id="binance-demo-primary",
        connector=unavailable,
    )
    with pytest.raises(
        ExecutorContinuityUnavailable,
        match="EXECUTOR_CONTINUITY_GUARD_FAILED type=OSError",
    ) as caught:
        guard.pause_open_activations(datetime.now(UTC))
    assert "database-secret" not in str(caught.value)


def test_app_spa_and_notification_sources_do_not_import_executor_guard() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[2] / "src" / "halpha"
    for source in (
        root / "app" / "__main__.py",
        root / "app" / "web.py",
        root / "app" / "notifications.py",
    ):
        assert "executor.continuity" not in source.read_text(encoding="utf-8")


def test_empty_activation_is_reactivated_without_fake_reconciliation() -> None:
    statements: list[str] = []

    class Cursor:
        rowcount = 2

    class RecordingConnection:
        @staticmethod
        def execute(statement: str, _parameters: object) -> Cursor:
            statements.append(" ".join(statement.split()))
            return Cursor()

    observed_at = datetime(2026, 7, 20, 4, tzinfo=UTC)
    count = PostgreSQLPlanningRepository(
        RecordingConnection(),  # type: ignore[arg-type]
        "binance-demo-primary",
    ).pause_all_open_for_writer_continuity_loss(observed_at)

    assert count == 2
    assert "has_entry_fill OR pending_action_digest IS NOT NULL OR EXISTS" in statements[0]
    assert "run_state = 'ACTIVE'" in statements[1]
    assert "has_entry_fill = FALSE" in statements[1]
    assert "NOT EXISTS" in statements[1]
