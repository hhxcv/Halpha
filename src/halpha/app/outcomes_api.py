"""App boundary for OUT review operations."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import psycopg
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from halpha.outcomes.repository import PostgreSQLOutcomeRepository
from halpha.outcomes.repository import OutcomeConflict
from halpha.outcomes.service import OutcomeApplicationService


class OutcomeApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ReviewRefreshPayload(OutcomeApiModel):
    expected_version: int = Field(gt=0)


class ReviewCompletionPayload(OutcomeApiModel):
    expected_version: int = Field(gt=0)
    evaluations: dict[str, dict[str, Any]]


class OutcomesApiUnavailable(RuntimeError):
    """Sanitized failure to reach the OUT application database boundary."""


class PostgreSQLOutcomesApi:
    def __init__(
        self,
        *,
        database_name: str,
        password: SecretStr,
        environment_id: str,
    ) -> None:
        self._database_name = database_name
        self._password = password
        self._environment_id = environment_id

    def _connect(self) -> psycopg.Connection[Any]:
        try:
            return psycopg.connect(
                host="127.0.0.1",
                port=5432,
                dbname=self._database_name,
                user=f"{self._database_name}_app",
                password=self._password.get_secret_value(),
                connect_timeout=2,
            )
        except Exception as exc:
            raise OutcomesApiUnavailable(
                f"OUTCOMES_DATABASE_UNAVAILABLE type={type(exc).__name__}"
            ) from None

    def list_reviews(self) -> list[dict[str, Any]]:
        with self._connect() as connection, connection.transaction():
            return OutcomeApplicationService(
                connection, self._environment_id
            ).list_reviews()

    def read_review(self, review_id: str) -> dict[str, Any]:
        with self._connect() as connection, connection.transaction():
            return OutcomeApplicationService(
                connection, self._environment_id
            ).read_review(review_id)

    def refresh_review(
        self, review_id: str, payload: ReviewRefreshPayload
    ) -> dict[str, Any]:
        with self._connect() as connection, connection.transaction():
            repository = PostgreSQLOutcomeRepository(connection, self._environment_id)
            current = repository.get_review(review_id, payload.expected_version)
            latest = repository.get_latest_for_activation(
                current.activation_id,
                for_update=True,
            )
            if latest is None or latest.review_version != payload.expected_version:
                raise OutcomeConflict("REVIEW_VERSION_CONFLICT")
            refreshed = OutcomeApplicationService(
                connection, self._environment_id
            ).update_activation_review(
                current.activation_id,
                fact_cutoff=datetime.now(UTC),
                observed_at=datetime.now(UTC),
            )
            return refreshed.model_dump(mode="json")

    def complete_review(
        self, review_id: str, payload: ReviewCompletionPayload
    ) -> dict[str, Any]:
        with self._connect() as connection, connection.transaction():
            review = OutcomeApplicationService(
                connection, self._environment_id
            ).complete_activation_review(
                review_id,
                expected_version=payload.expected_version,
                evaluations=payload.evaluations,
            )
            return {"review": review.model_dump(mode="json")}
