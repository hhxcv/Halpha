"""App boundary for OUT review operations."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import psycopg
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from halpha.outcomes.repository import PostgreSQLOutcomeRepository
from halpha.outcomes.repository import OutcomeConflict
from halpha.outcomes.models import EvaluationResult
from halpha.outcomes.service import OutcomeApplicationService


class OutcomeApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ReviewRefreshPayload(OutcomeApiModel):
    expected_version: int = Field(gt=0)


class ReviewCompletionPayload(OutcomeApiModel):
    expected_version: int = Field(gt=0)
    conclusion: EvaluationResult
    note: str = Field(default="", max_length=2000)


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
            reviews = OutcomeApplicationService(
                connection, self._environment_id
            ).list_reviews()
            return self._attach_trade_context(connection, reviews)

    def read_review(self, review_id: str) -> dict[str, Any]:
        with self._connect() as connection, connection.transaction():
            result = OutcomeApplicationService(
                connection, self._environment_id
            ).read_review(review_id)
            result["review"] = self._attach_trade_context(
                connection, [result["review"]]
            )[0]
            return result

    def _attach_trade_context(
        self,
        connection: psycopg.Connection[Any],
        reviews: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        activation_ids = [str(item["activation_id"]) for item in reviews]
        if not activation_ids:
            return reviews
        rows = connection.execute(
            """
            SELECT a.activation_id, a.instrument_ref, a.direction, a.strategy_id,
                   v.max_notional, a.created_at, a.updated_at,
                   v.terms ->> 'plan_name',
                   v.terms ->> 'created_at',
                   v.terms ->> 'creator_kind'
            FROM halpha.plan_activation a
            LEFT JOIN halpha.trade_plan_version v
              ON v.environment_id = a.environment_id
             AND v.plan_version_id = a.plan_version_ref
            WHERE a.environment_id = %s AND a.activation_id::text = ANY(%s)
            """,
            (self._environment_id, activation_ids),
        ).fetchall()
        contexts = {
            str(row[0]): {
                "instrument_ref": str(row[1]),
                "direction": str(row[2]),
                "strategy_id": str(row[3]),
                "trade_amount": str(row[4]) if row[4] is not None else None,
                "activation_started_at": row[5].isoformat(),
                "activation_updated_at": row[6].isoformat(),
                "plan_name": str(row[7]) if row[7] is not None else None,
                "plan_created_at": str(row[8]) if row[8] is not None else None,
                "plan_creator_kind": str(row[9]) if row[9] is not None else None,
            }
            for row in rows
        }
        return [
            {**item, "trade_context": contexts.get(str(item["activation_id"]), {})}
            for item in reviews
        ]

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
                conclusion=payload.conclusion,
                note=payload.note,
            )
            return {"review": review.model_dump(mode="json")}
