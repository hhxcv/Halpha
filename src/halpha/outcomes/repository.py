"""Private PostgreSQL persistence for Review and ImprovementHandoff."""

from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from halpha.outcomes.models import (
    EvidencePurpose,
    ImprovementHandoff,
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

    def insert_handoff(self, handoff: ImprovementHandoff) -> None:
        result = self._connection.execute(
            """
            INSERT INTO halpha.improvement_handoff (
              improvement_handoff_id, environment_id, review_id, review_version,
              handoff_version, target_owner, observable_problem, evidence_refs,
              impact_scope, expected_change, problem_digest, content_digest, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (environment_id, review_id, review_version, target_owner, problem_digest)
            DO NOTHING
            """,
            (
                handoff.improvement_handoff_id,
                handoff.environment_id,
                handoff.review_id,
                handoff.review_version,
                handoff.handoff_version,
                handoff.target_owner,
                handoff.observable_problem,
                Jsonb(handoff.evidence_refs),
                Jsonb(handoff.impact_scope),
                handoff.expected_change,
                handoff.problem_digest,
                handoff.content_digest,
                handoff.created_at,
            ),
        )
        if result.rowcount == 1:
            return
        existing = self._connection.execute(
            """
            SELECT content_digest
            FROM halpha.improvement_handoff
            WHERE environment_id = %s AND review_id = %s AND review_version = %s
              AND target_owner = %s AND problem_digest = %s
            """,
            (
                self._environment_id,
                handoff.review_id,
                handoff.review_version,
                handoff.target_owner,
                handoff.problem_digest,
            ),
        ).fetchone()
        if existing is None or str(existing[0]) != handoff.content_digest:
            raise OutcomeConflict("IMPROVEMENT_HANDOFF_CONFLICT")

    def list_handoffs(self, *, target_owner: str | None = None) -> tuple[ImprovementHandoff, ...]:
        owner_filter = "AND target_owner = %s" if target_owner else ""
        parameters = (
            (self._environment_id, target_owner)
            if target_owner
            else (self._environment_id,)
        )
        rows = self._connection.execute(
            f"""
            SELECT improvement_handoff_id, environment_id, review_id, review_version,
                   handoff_version, target_owner, observable_problem, evidence_refs,
                   impact_scope, expected_change, problem_digest, content_digest, created_at
            FROM halpha.improvement_handoff
            WHERE environment_id = %s {owner_filter}
            ORDER BY created_at, improvement_handoff_id
            """,
            parameters,
        ).fetchall()
        return tuple(_handoff_from_row(row) for row in rows)


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


def _handoff_from_row(row: tuple[Any, ...]) -> ImprovementHandoff:
    return ImprovementHandoff(
        improvement_handoff_id=str(row[0]),
        environment_id=str(row[1]),
        review_id=str(row[2]),
        review_version=int(row[3]),
        handoff_version=int(row[4]),
        target_owner=str(row[5]),
        observable_problem=str(row[6]),
        evidence_refs=dict(row[7]),
        impact_scope=dict(row[8]),
        expected_change=str(row[9]),
        problem_digest=str(row[10]),
        content_digest=str(row[11]),
        created_at=row[12],
    )
