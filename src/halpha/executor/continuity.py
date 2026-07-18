"""Executor startup boundary for P0 manual activation resume."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

import psycopg
from pydantic import SecretStr

from halpha.planning.service import PlanningApplicationService


class ExecutorContinuityUnavailable(RuntimeError):
    """A sanitized failure which prevents Executor readiness."""


class PostgreSQLExecutorContinuityGuard:
    """Pause open activations before a new Executor announces readiness."""

    def __init__(
        self,
        *,
        database_name: str,
        password: SecretStr,
        environment_id: str,
        connector: Callable[..., Any] = psycopg.connect,
    ) -> None:
        self._database_name = database_name
        self._password = password
        self._environment_id = environment_id
        self._connector = connector

    def pause_open_activations(self, observed_at: datetime) -> int:
        try:
            with self._connector(
                host="127.0.0.1",
                port=5432,
                dbname=self._database_name,
                user=f"{self._database_name}_executor",
                password=self._password.get_secret_value(),
                connect_timeout=2,
            ) as connection, connection.transaction():
                return PlanningApplicationService(
                    connection,
                    self._environment_id,
                ).pause_for_writer_continuity_loss(observed_at)
        except Exception as exc:
            raise ExecutorContinuityUnavailable(
                f"EXECUTOR_CONTINUITY_GUARD_FAILED type={type(exc).__name__}"
            ) from None
