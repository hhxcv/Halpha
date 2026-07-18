from __future__ import annotations

import psycopg
import pytest
from pydantic import SecretStr

from halpha.app.outcomes_api import OutcomesApiUnavailable, PostgreSQLOutcomesApi


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
