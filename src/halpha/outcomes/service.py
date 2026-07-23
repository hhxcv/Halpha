"""OUT application service built only from accepted authoritative references."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from psycopg import Connection

from halpha.domain_values import content_digest
from halpha.outcomes.models import (
    EvaluationResult,
    EvidencePurpose,
    OWNER_CONCLUSION_KEY,
    PrimaryResult,
    Review,
    ReviewStatus,
)
from halpha.outcomes.account_reconciliation import account_result_role
from halpha.outcomes.repository import OutcomeConflict, PostgreSQLOutcomeRepository
from halpha.outcomes.trade_result import summarize_trade_result


TERMINAL_ACTION_STATES = frozenset(
    {"NOT_SUBMITTED", "CLOSED", "HANDED_OVER"}
)
UNKNOWN_ACTION_STATES = frozenset({"SUBMITTING", "UNKNOWN"})


def review_id_for_activation(environment_id: str, activation_id: str) -> str:
    return str(
        uuid5(NAMESPACE_URL, f"urn:halpha:{environment_id}:review:{activation_id}")
    )


class OutcomeApplicationService:
    def __init__(self, connection: Connection[Any], environment_id: str) -> None:
        self._connection = connection
        self._environment_id = environment_id
        self._repository = PostgreSQLOutcomeRepository(connection, environment_id)

    def update_activation_review(
        self,
        activation_id: str,
        *,
        fact_cutoff: datetime,
        observed_at: datetime,
    ) -> Review:
        basis = self._collect_basis(activation_id, fact_cutoff=fact_cutoff)
        input_refs = basis["input_refs"]
        input_digest = content_digest(input_refs)
        latest = self._repository.get_latest_for_activation(
            activation_id, for_update=True
        )
        if latest is not None and _review_matches_basis(
            latest,
            basis=basis,
            input_digest=input_digest,
        ):
            return latest
        if latest is not None and latest.status is not ReviewStatus.SUPERSEDED:
            superseded = _replace_review(latest, status=ReviewStatus.SUPERSEDED)
            self._repository.replace_review(
                superseded,
                expected_content_digest=latest.content_digest,
            )
        version = 1 if latest is None else latest.review_version + 1
        review_id = review_id_for_activation(self._environment_id, activation_id)
        fields: dict[str, Any] = {
            "review_id": review_id,
            "review_version": version,
            "environment_id": self._environment_id,
            "activation_id": activation_id,
            "previous_version": latest.review_version if latest else None,
            "status": ReviewStatus.DRAFT,
            "primary_result": basis["primary_result"],
            "fact_cutoff": fact_cutoff,
            "input_refs": input_refs,
            "input_digest": input_digest,
            "account_result": basis["account_result"],
            "open_responsibilities": basis["open_responsibilities"],
            "evaluations": basis["evaluations"],
            "evidence_purpose": basis["evidence_purpose"],
            "created_at": observed_at,
        }
        review = Review(**fields, content_digest=content_digest(fields))
        self._repository.insert_review(review)
        return review

    def complete_activation_review(
        self,
        review_id: str,
        *,
        expected_version: int,
        conclusion: EvaluationResult,
        note: str,
    ) -> Review:
        current = self._repository.get_review(review_id, expected_version)
        if current.status is ReviewStatus.SUPERSEDED:
            raise OutcomeConflict("REVIEW_VERSION_CONFLICT")
        normalized = _owner_conclusion(conclusion, note)
        completed = _replace_review(
            current,
            status=ReviewStatus.COMPLETE,
            evaluations=normalized,
        )
        self._repository.replace_review(
            completed,
            expected_content_digest=current.content_digest,
        )
        return completed

    def read_review(self, review_id: str) -> dict[str, Any]:
        review = self._repository.get_review(review_id)
        return {"review": review.model_dump(mode="json")}

    def list_reviews(self) -> list[dict[str, Any]]:
        return [item.model_dump(mode="json") for item in self._repository.list_reviews()]

    def _collect_basis(
        self, activation_id: str, *, fact_cutoff: datetime
    ) -> dict[str, Any]:
        activation = self._connection.execute(
            """
            SELECT activation_id, plan_version_ref, environment_kind, authority_class,
                   account_ref, instrument_ref, decision_basis_ref, lifecycle, run_state,
                   protection_state,
                   responsibility_owner, takeover_scope, closure_digest, result_ref,
                   created_at, updated_at, state_version, direction
            FROM halpha.plan_activation
            WHERE environment_id = %s AND activation_id = %s
            """,
            (self._environment_id, activation_id),
        ).fetchone()
        if activation is None:
            raise OutcomeConflict("ACTIVATION_NOT_FOUND")
        if str(activation[7]) != "COMPLETED":
            raise OutcomeConflict("REVIEW_ACTIVATION_NOT_COMPLETE")
        plan = self._connection.execute(
            """
            SELECT plan_version_id, content_digest, fixed_at
            FROM halpha.trade_plan_version
            WHERE environment_id = %s AND plan_version_id = %s
            """,
            (self._environment_id, activation[1]),
        ).fetchone()
        events = self._connection.execute(
            """
            SELECT plan_event_id, content_digest, created_at
            FROM halpha.plan_event
            WHERE environment_id = %s AND activation_id = %s
            ORDER BY created_at, plan_event_id
            """,
            (self._environment_id, activation_id),
        ).fetchall()
        actions = self._connection.execute(
            """
            SELECT execution_action_id, state_version, state, state_digest,
                   closure_evidence_digest, updated_at, action_kind
            FROM halpha.execution_action
            WHERE environment_id = %s AND activation_id = %s
            ORDER BY created_at, execution_action_id
            """,
            (self._environment_id, activation_id),
        ).fetchall()
        facts = self._connection.execute(
            """
            SELECT venue_fact_id, schema_version, kind, content_digest, cutoff,
                   source_time, payload, action_ref, impact_scope,
                   attribution_class
            FROM halpha.venue_fact
            WHERE environment_id = %s AND cutoff <= %s
              AND (
                activation_ref = %s
                OR (
                  attribution_class IS NULL
                  AND impact_scope ->> 'account_episode_activation_id' = %s
                )
              )
            ORDER BY cutoff, venue_fact_id
            """,
            (self._environment_id, fact_cutoff, activation_id, activation_id),
        ).fetchall()
        commands = self._connection.execute(
            """
            SELECT c.command_id, c.content_digest, r.receipt_id, r.state_version,
                   r.content_digest, r.updated_at
            FROM halpha.command AS c
            JOIN halpha.receipt AS r
              ON r.environment_id = c.environment_id AND r.command_id = c.command_id
            WHERE c.environment_id = %s AND c.target_kind = 'PLAN_ACTIVATION'
              AND c.target_ref = %s
            ORDER BY c.submitted_at, c.command_id
            """,
            (self._environment_id, activation_id),
        ).fetchall()
        input_refs = {
            "activation": {
                "activation_id": str(activation[0]),
                "state_version": int(activation[16]),
                "closure_digest": str(activation[12]),
            },
            "plan_version": (
                {
                    "plan_version_id": str(plan[0]),
                    "content_digest": str(plan[1]),
                    "fixed_at": plan[2].isoformat(),
                }
                if plan is not None
                else {"plan_version_id": str(activation[1]), "missing": True}
            ),
            "plan_events": [
                {"plan_event_id": str(row[0]), "content_digest": str(row[1]), "at": row[2].isoformat()}
                for row in events
            ],
            "execution_actions": [
                {
                    "execution_action_id": str(row[0]),
                    "state_version": int(row[1]),
                    "state_digest": str(row[3]),
                    "closure_evidence_digest": str(row[4]) if row[4] else None,
                    "at": row[5].isoformat(),
                }
                for row in actions
            ],
            "venue_facts": [
                {
                    "venue_fact_id": str(row[0]),
                    "schema_version": int(row[1]),
                    "kind": str(row[2]),
                    "content_digest": str(row[3]),
                    "cutoff": row[4].isoformat(),
                }
                for row in facts
            ],
            "commands_and_receipts": [
                {
                    "command_id": str(row[0]),
                    "command_digest": str(row[1]),
                    "receipt_id": str(row[2]),
                    "receipt_version": int(row[3]),
                    "receipt_digest": str(row[4]),
                    "at": row[5].isoformat(),
                }
                for row in commands
            ],
        }
        states = {str(row[2]) for row in actions}
        open_action_refs = [
            str(row[0]) for row in actions if str(row[2]) not in TERMINAL_ACTION_STATES
        ]
        unknown_action_refs = [
            str(row[0]) for row in actions if str(row[2]) in UNKNOWN_ACTION_STATES
        ]
        takeover = str(activation[10]) == "USER" or activation[11] is not None
        has_fill = any(str(row[2]) == "FILL" for row in facts)
        has_external_closure = any(
            account_result_role(row[8]) is not None for row in facts
        )
        if takeover:
            primary_result = PrimaryResult.HANDED_OVER
        elif unknown_action_refs:
            primary_result = PrimaryResult.RESULT_UNKNOWN
        elif open_action_refs:
            primary_result = PrimaryResult.PARTIAL
        elif not actions or (states <= {"NOT_SUBMITTED", "CLOSED"} and not has_fill):
            primary_result = PrimaryResult.NO_ACTION
        else:
            primary_result = PrimaryResult.COMPLETED
        missing_refs = ["plan_version"] if plan is None else []
        evaluations = _draft_evaluations()
        trade_result = summarize_trade_result(
            direction=str(activation[17]),
            action_kinds={str(row[0]): str(row[6]) for row in actions},
            facts=(
                {
                    "kind": str(row[2]),
                    "payload": dict(row[6]),
                    "action_ref": str(row[7]) if row[7] is not None else None,
                    "source_time": row[5].isoformat() if row[5] is not None else None,
                    "result_role": account_result_role(row[8]),
                }
                for row in facts
            ),
        )
        return {
            "input_refs": input_refs,
            "primary_result": primary_result,
            "account_result": {
                "classification": (
                    "UNKNOWN"
                    if missing_refs or primary_result is PrimaryResult.RESULT_UNKNOWN
                    else (
                        "NO_EXTERNAL_CHANGE"
                        if not has_fill
                        else (
                            "ACCOUNT_FACTS_WITH_EXTERNAL_CLOSURE"
                            if has_external_closure
                            else "ATTRIBUTED_FACTS_AVAILABLE"
                        )
                    )
                ),
                "venue_fact_refs": [str(row[0]) for row in facts],
                "missing_refs": missing_refs,
                "trade_result": trade_result,
            },
            "open_responsibilities": {
                "execution_action_refs": open_action_refs,
                "unknown_action_refs": unknown_action_refs,
                "responsibility_owner": str(activation[10]),
                "takeover_scope": dict(activation[11]) if activation[11] else None,
            },
            "evaluations": evaluations,
            "evidence_purpose": (
                EvidencePurpose.SYSTEM_MECHANISM_EVIDENCE
                if str(activation[2]) == "DEMO"
                else EvidencePurpose.LIVE_ACTIVATION_REVIEW
            ),
        }

def _draft_evaluations() -> dict[str, dict[str, Any]]:
    return {
        OWNER_CONCLUSION_KEY: {
            "result": EvaluationResult.UNKNOWN.value,
            "reason": "",
            "evidence_refs": [],
        }
    }


def _review_matches_basis(
    review: Review,
    *,
    basis: dict[str, Any],
    input_digest: str,
) -> bool:
    """Reuse a review only when its facts and current derived result still match."""

    return (
        review.input_digest == input_digest
        and review.primary_result == basis["primary_result"]
        and review.account_result == basis["account_result"]
        and review.open_responsibilities == basis["open_responsibilities"]
        and review.evidence_purpose == basis["evidence_purpose"]
    )


def _owner_conclusion(
    conclusion: EvaluationResult,
    note: str,
) -> dict[str, dict[str, Any]]:
    return {
        OWNER_CONCLUSION_KEY: {
            "result": conclusion.value,
            "reason": note.strip(),
            "evidence_refs": [],
        }
    }


def _replace_review(
    review: Review,
    *,
    status: ReviewStatus,
    evaluations: dict[str, dict[str, Any]] | None = None,
    account_result: dict[str, Any] | None = None,
) -> Review:
    fields = review.model_dump(mode="python", exclude={"content_digest"})
    fields["status"] = status
    if evaluations is not None:
        fields["evaluations"] = evaluations
    if account_result is not None:
        fields["account_result"] = account_result
    return Review(**fields, content_digest=content_digest(fields))
