"""Private PostgreSQL persistence for Review."""

from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from halpha.outcomes.models import (
    EvidencePurpose,
    PrimaryResult,
    Review,
    ReviewStatus,
)


class OutcomeConflict(ValueError):
    """Stable OUT conflict result."""


class PostgreSQLOutcomeRepository:
    def __init__(self, connection: Connection[Any], environment_id: str) -> None:
        self._connection = connection
        self._environment_id = environment_id

    def insert_review(self, review: Review) -> None:
        if review.environment_id != self._environment_id:
            raise OutcomeConflict("REVIEW_ENVIRONMENT_MISMATCH")
        self._connection.execute(
            """
            INSERT INTO halpha.review (
              review_id, review_version, environment_id, activation_id,
              previous_version, status, primary_result, fact_cutoff,
              input_refs, input_digest, account_result, open_responsibilities,
              evaluations, evidence_purpose, content_digest, created_at
            ) VALUES (
              %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            """,
            (
                review.review_id,
                review.review_version,
                review.environment_id,
                review.activation_id,
                review.previous_version,
                review.status.value,
                review.primary_result.value,
                review.fact_cutoff,
                Jsonb(review.input_refs),
                review.input_digest,
                Jsonb(review.account_result),
                Jsonb(review.open_responsibilities),
                Jsonb(review.evaluations),
                review.evidence_purpose.value,
                review.content_digest,
                review.created_at,
            ),
        )

    def get_latest_for_activation(
        self, activation_id: str, *, for_update: bool = False
    ) -> Review | None:
        row = self._connection.execute(
            f"""
            SELECT review_id, review_version, environment_id, activation_id,
                   previous_version, status, primary_result, fact_cutoff,
                   input_refs, input_digest, account_result, open_responsibilities,
                   evaluations, evidence_purpose, content_digest, created_at
            FROM halpha.review
            WHERE environment_id = %s AND activation_id = %s
            ORDER BY review_version DESC
            LIMIT 1
            {"FOR UPDATE" if for_update else ""}
            """,
            (self._environment_id, activation_id),
        ).fetchone()
        return _review_from_row(row) if row is not None else None

    def get_review(self, review_id: str, version: int | None = None) -> Review:
        version_filter = "AND review_version = %s" if version is not None else ""
        parameters: tuple[Any, ...] = (
            (self._environment_id, review_id, version)
            if version is not None
            else (self._environment_id, review_id)
        )
        row = self._connection.execute(
            f"""
            SELECT review_id, review_version, environment_id, activation_id,
                   previous_version, status, primary_result, fact_cutoff,
                   input_refs, input_digest, account_result, open_responsibilities,
                   evaluations, evidence_purpose, content_digest, created_at
            FROM halpha.review
            WHERE environment_id = %s AND review_id = %s {version_filter}
            ORDER BY review_version DESC LIMIT 1
            """,
            parameters,
        ).fetchone()
        if row is None:
            raise OutcomeConflict("REVIEW_NOT_FOUND")
        return _review_from_row(row)

    def list_reviews(self) -> tuple[Review, ...]:
        rows = self._connection.execute(
            """
            SELECT DISTINCT ON (review_id)
                   review_id, review_version, environment_id, activation_id,
                   previous_version, status, primary_result, fact_cutoff,
                   input_refs, input_digest, account_result, open_responsibilities,
                   evaluations, evidence_purpose, content_digest, created_at
            FROM halpha.review
            WHERE environment_id = %s
            ORDER BY review_id, review_version DESC
            """,
            (self._environment_id,),
        ).fetchall()
        return tuple(_review_from_row(row) for row in rows)

    def replace_review(self, review: Review, *, expected_content_digest: str) -> None:
        result = self._connection.execute(
            """
            UPDATE halpha.review
            SET status = %s, primary_result = %s, account_result = %s,
                open_responsibilities = %s, evaluations = %s,
                evidence_purpose = %s, content_digest = %s
            WHERE environment_id = %s AND review_id = %s AND review_version = %s
              AND content_digest = %s
            """,
            (
                review.status.value,
                review.primary_result.value,
                Jsonb(review.account_result),
                Jsonb(review.open_responsibilities),
                Jsonb(review.evaluations),
                review.evidence_purpose.value,
                review.content_digest,
                self._environment_id,
                review.review_id,
                review.review_version,
                expected_content_digest,
            ),
        )
        if result.rowcount != 1:
            raise OutcomeConflict("REVIEW_VERSION_CONFLICT")


def _review_from_row(row: tuple[Any, ...]) -> Review:
    return Review(
        review_id=str(row[0]),
        review_version=int(row[1]),
        environment_id=str(row[2]),
        activation_id=str(row[3]),
        previous_version=int(row[4]) if row[4] is not None else None,
        status=ReviewStatus(str(row[5])),
        primary_result=PrimaryResult(str(row[6])),
        fact_cutoff=row[7],
        input_refs=dict(row[8]),
        input_digest=str(row[9]),
        account_result=dict(row[10]),
        open_responsibilities=dict(row[11]),
        evaluations=dict(row[12]),
        evidence_purpose=EvidencePurpose(str(row[13])),
        content_digest=str(row[14]),
        created_at=row[15],
    )
