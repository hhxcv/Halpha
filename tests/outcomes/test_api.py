from __future__ import annotations

from datetime import UTC, datetime
import psycopg
import pytest
from pydantic import SecretStr

from halpha.app.outcomes_api import OutcomesApiUnavailable, PostgreSQLOutcomesApi


class _Rows:
    def fetchall(self):
        return [
            (
                "activation-1",
                "BTCUSDT-PERP",
                "LONG",
                "ONE_SHOT_DONCHIAN_ATR_BREAKOUT",
                "300",
                datetime(2026, 7, 20, 1, tzinfo=UTC),
                datetime(2026, 7, 20, 2, tzinfo=UTC),
            )
        ]


class _Connection:
    def execute(self, query, parameters):
        assert "trade_plan_version" in query
        assert parameters == ("demo-main", ["activation-1"])
        return _Rows()


def test_outcomes_database_failure_is_sanitized(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_connect(**kwargs):
        raise psycopg.OperationalError("secret-database-detail")

    monkeypatch.setattr(psycopg, "connect", fail_connect)
    api = PostgreSQLOutcomesApi(
        database_name="halpha_demo",
        password=SecretStr("secret-password"),
        environment_id="demo-main",
    )
    with pytest.raises(
        OutcomesApiUnavailable,
        match="OUTCOMES_DATABASE_UNAVAILABLE type=OperationalError",
    ) as captured:
        api._connect()
    rendered = str(captured.value)
    assert "secret-database-detail" not in rendered
    assert "secret-password" not in rendered


def test_review_projection_adds_compact_trade_context() -> None:
    api = PostgreSQLOutcomesApi(
        database_name="halpha_demo",
        password=SecretStr("secret-password"),
        environment_id="demo-main",
    )

    result = api._attach_trade_context(
        _Connection(),  # type: ignore[arg-type]
        [{"review_id": "review-1", "activation_id": "activation-1"}],
    )

    assert result[0]["trade_context"] == {
        "instrument_ref": "BTCUSDT-PERP",
        "direction": "LONG",
        "strategy_id": "ONE_SHOT_DONCHIAN_ATR_BREAKOUT",
        "trade_amount": "300",
        "activation_started_at": "2026-07-20T01:00:00+00:00",
        "activation_updated_at": "2026-07-20T02:00:00+00:00",
    }
