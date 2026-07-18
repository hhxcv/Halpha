"""OUT application service built only from accepted authoritative references."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from psycopg import Connection

from halpha.domain_values import content_digest
from halpha.outcomes.models import (
    EVALUATION_KEYS,
    EvaluationResult,
    EvidencePurpose,
    ImprovementHandoff,
    PrimaryResult,
    Review,
    ReviewStatus,
)
from halpha.outcomes.repository import OutcomeConflict, PostgreSQLOutcomeRepository


TERMINAL_ACTION_STATES = frozenset(
    {"NOT_SUBMITTED", "RECONCILED", "HANDED_OVER"}
)
UNKNOWN_ACTION_STATES = frozenset({"SUBMITTING", "SUBMITTED_UNKNOWN"})


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
        if latest is not None and latest.input_digest == input_digest:
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
        evaluations: dict[str, dict[str, Any]],
        issues: tuple[dict[str, Any], ...],
        no_improvement_reason: str | None,
        observed_at: datetime,
    ) -> tuple[Review, tuple[ImprovementHandoff, ...]]:
        current = self._repository.get_review(review_id, expected_version)
        if current.status is ReviewStatus.SUPERSEDED:
            raise OutcomeConflict("REVIEW_VERSION_CONFLICT")
        normalized = _validate_evaluations(evaluations)
        issue_found = any(
            item["result"] == EvaluationResult.ISSUE_FOUND.value
            for item in normalized.values()
        )
        if issue_found and not issues:
            raise OutcomeConflict("REVIEW_COMPLETION_INCOMPLETE")
        if not issues and not no_improvement_reason:
            raise OutcomeConflict("REVIEW_COMPLETION_INCOMPLETE")
        completed = _replace_review(
            current,
            status=ReviewStatus.COMPLETE,
            evaluations=normalized,
            account_result={
                **current.account_result,
                "improvement_disposition": (
                    {"handoff_count": len(issues)}
                    if issues
                    else {"no_action_reason": no_improvement_reason}
                ),
            },
        )
        self._repository.replace_review(
            completed,
            expected_content_digest=current.content_digest,
        )
        handoffs = tuple(
            self._build_handoff(completed, issue, observed_at=observed_at)
            for issue in issues
        )
        for handoff in handoffs:
            self._repository.insert_handoff(handoff)
        return completed, handoffs

    def read_review(self, review_id: str) -> dict[str, Any]:
        review = self._repository.get_review(review_id)
        handoffs = tuple(
            item
            for item in self._repository.list_handoffs()
            if item.review_id == review.review_id
            and item.review_version == review.review_version
        )
        return {
            "review": review.model_dump(mode="json"),
            "improvement_handoffs": [item.model_dump(mode="json") for item in handoffs],
        }

    def list_reviews(self) -> list[dict[str, Any]]:
        return [item.model_dump(mode="json") for item in self._repository.list_reviews()]

    def list_improvement_handoffs(self, target_owner: str | None = None) -> list[dict[str, Any]]:
        return [
            item.model_dump(mode="json")
            for item in self._repository.list_handoffs(target_owner=target_owner)
        ]

    def _collect_basis(
        self, activation_id: str, *, fact_cutoff: datetime
    ) -> dict[str, Any]:
        activation = self._connection.execute(
            """
            SELECT activation_id, plan_version_ref, authorization_version_ref,
                   allocation_ref, environment_kind, authority_class, account_ref,
                   instrument_ref, strategy_id, lifecycle, run_state, protection_state,
                   responsibility_owner, takeover_scope, closure_digest, result_ref,
                   created_at, updated_at, state_version
            FROM halpha.plan_activation
            WHERE environment_id = %s AND activation_id = %s
            """,
            (self._environment_id, activation_id),
        ).fetchone()
        if activation is None:
            raise OutcomeConflict("ACTIVATION_NOT_FOUND")
        if str(activation[9]) != "COMPLETED":
            raise OutcomeConflict("REVIEW_ACTIVATION_NOT_COMPLETE")
        plan = self._connection.execute(
            """
            SELECT plan_version_id, content_digest, fixed_at
            FROM halpha.trade_plan_version
            WHERE environment_id = %s AND plan_version_id = %s
            """,
            (self._environment_id, activation[1]),
        ).fetchone()
        allocation = self._connection.execute(
            """
            SELECT allocation_id, state_version, status, reservation_digest,
                   closure_digest, released_at
            FROM halpha.plan_allocation
            WHERE environment_id = %s AND activation_id = %s
            """,
            (self._environment_id, activation_id),
        ).fetchone()
        authorization = self._connection.execute(
            """
            SELECT authorization_version_id, version, content_digest, valid_until
            FROM halpha.machine_authorization_version
            WHERE environment_id = %s AND authorization_version_id = %s
            """,
            (self._environment_id, activation[2]),
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
                   closure_evidence_digest, updated_at
            FROM halpha.execution_action
            WHERE environment_id = %s AND activation_id = %s
            ORDER BY created_at, execution_action_id
            """,
            (self._environment_id, activation_id),
        ).fetchall()
        facts = self._connection.execute(
            """
            SELECT venue_fact_id, schema_version, kind, content_digest, cutoff
            FROM halpha.venue_fact
            WHERE environment_id = %s AND activation_ref = %s AND cutoff <= %s
            ORDER BY cutoff, venue_fact_id
            """,
            (self._environment_id, activation_id, fact_cutoff),
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
                "state_version": int(activation[18]),
                "closure_digest": str(activation[14]),
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
            "authorization": (
                {
                    "authorization_version_id": str(authorization[0]),
                    "version": int(authorization[1]),
                    "content_digest": str(authorization[2]),
                    "valid_until": authorization[3].isoformat(),
                }
                if authorization is not None
                else {"authorization_version_id": str(activation[2]), "missing": True}
            ),
            "allocation": (
                {
                    "allocation_id": str(allocation[0]),
                    "state_version": int(allocation[1]),
                    "status": str(allocation[2]),
                    "reservation_digest": str(allocation[3]),
                    "closure_digest": str(allocation[4]),
                    "released_at": allocation[5].isoformat() if allocation[5] else None,
                }
                if allocation is not None
                else {"allocation_id": str(activation[3]), "missing": True}
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
        takeover = str(activation[12]) == "USER" or activation[13] is not None
        has_fill = any(str(row[2]) == "FILL" for row in facts)
        if takeover:
            primary_result = PrimaryResult.HANDED_OVER
        elif unknown_action_refs:
            primary_result = PrimaryResult.RESULT_UNKNOWN
        elif open_action_refs:
            primary_result = PrimaryResult.PARTIAL
        elif not actions or (states <= {"NOT_SUBMITTED", "RECONCILED"} and not has_fill):
            primary_result = PrimaryResult.NO_ACTION
        else:
            primary_result = PrimaryResult.COMPLETED
        missing_refs = [
            name
            for name, value in (
                ("plan_version", plan),
                ("authorization", authorization),
                ("allocation", allocation),
            )
            if value is None
        ]
        evaluations = _draft_evaluations(
            primary_result=primary_result,
            missing_refs=missing_refs,
            closure_digest=str(activation[14]),
            event_count=len(events),
            action_count=len(actions),
            fact_count=len(facts),
        )
        return {
            "input_refs": input_refs,
            "primary_result": primary_result,
            "account_result": {
                "classification": (
                    "UNKNOWN"
                    if missing_refs or primary_result is PrimaryResult.RESULT_UNKNOWN
                    else ("NO_EXTERNAL_CHANGE" if not has_fill else "ATTRIBUTED_FACTS_AVAILABLE")
                ),
                "venue_fact_refs": [str(row[0]) for row in facts],
                "missing_refs": missing_refs,
            },
            "open_responsibilities": {
                "execution_action_refs": open_action_refs,
                "unknown_action_refs": unknown_action_refs,
                "responsibility_owner": str(activation[12]),
                "takeover_scope": dict(activation[13]) if activation[13] else None,
            },
            "evaluations": evaluations,
            "evidence_purpose": (
                EvidencePurpose.SYSTEM_MECHANISM_EVIDENCE
                if str(activation[4]) == "DEMO"
                else EvidencePurpose.LIVE_ACTIVATION_REVIEW
            ),
        }

    def _build_handoff(
        self,
        review: Review,
        issue: dict[str, Any],
        *,
        observed_at: datetime,
    ) -> ImprovementHandoff:
        required = {
            "target_owner",
            "observable_problem",
            "evidence_refs",
            "impact_scope",
            "expected_change",
        }
        if set(issue) != required:
            raise OutcomeConflict("IMPROVEMENT_HANDOFF_INVALID")
        problem_basis = {
            "review_id": review.review_id,
            "review_version": review.review_version,
            "target_owner": issue["target_owner"],
            "observable_problem": issue["observable_problem"],
        }
        problem_digest = content_digest(problem_basis)
        handoff_id = str(
            uuid5(
                NAMESPACE_URL,
                f"urn:halpha:{self._environment_id}:handoff:{review.review_id}:{review.review_version}:{issue['target_owner']}:{problem_digest}",
            )
        )
        fields = {
            "improvement_handoff_id": handoff_id,
            "environment_id": self._environment_id,
            "review_id": review.review_id,
            "review_version": review.review_version,
            "handoff_version": 1,
            "target_owner": str(issue["target_owner"]),
            "observable_problem": str(issue["observable_problem"]),
            "evidence_refs": dict(issue["evidence_refs"]),
            "impact_scope": dict(issue["impact_scope"]),
            "expected_change": str(issue["expected_change"]),
            "problem_digest": problem_digest,
            "created_at": observed_at,
        }
        return ImprovementHandoff(
            **fields,
            content_digest=content_digest(fields),
        )


def _draft_evaluations(
    *,
    primary_result: PrimaryResult,
    missing_refs: list[str],
    closure_digest: str,
    event_count: int,
    action_count: int,
    fact_count: int,
) -> dict[str, dict[str, Any]]:
    unknown = bool(missing_refs) or primary_result is PrimaryResult.RESULT_UNKNOWN
    base_result = (
        EvaluationResult.UNKNOWN.value
        if unknown
        else EvaluationResult.AS_EXPECTED.value
    )
    return {
        "system_maintenance": {
            "result": base_result,
            "reason": "System mechanism evidence is evaluated before strategy behavior.",
            "evidence_refs": [closure_digest],
        },
        "plan": {
            "result": base_result,
            "reason": "Plan lifecycle is reconstructed from the activation and ordered plan events.",
            "evidence_refs": [f"plan_event_count:{event_count}"],
        },
        "capital_authority": {
            "result": base_result,
            "reason": "Authorization and allocation are referenced without copying their lifecycle.",
            "evidence_refs": [f"missing:{','.join(missing_refs)}" if missing_refs else "references:complete"],
        },
        "execution_facts": {
            "result": base_result,
            "reason": "Execution actions and venue facts remain separate authoritative references.",
            "evidence_refs": [f"actions:{action_count}", f"facts:{fact_count}"],
        },
        "interaction": {
            "result": EvaluationResult.UNKNOWN.value,
            "reason": "Owner evaluation is required before completion.",
            "evidence_refs": [],
        },
        "account_result": {
            "result": (
                EvaluationResult.NOT_APPLICABLE.value
                if primary_result is PrimaryResult.NO_ACTION
                else base_result
            ),
            "reason": "Only attributed venue facts can support the account result.",
            "evidence_refs": [f"facts:{fact_count}"],
        },
    }


def _validate_evaluations(
    evaluations: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    if set(evaluations) != EVALUATION_KEYS:
        raise OutcomeConflict("REVIEW_COMPLETION_INCOMPLETE")
    allowed = {item.value for item in EvaluationResult}
    normalized: dict[str, dict[str, Any]] = {}
    for key, item in evaluations.items():
        if set(item) != {"result", "reason", "evidence_refs"}:
            raise OutcomeConflict("REVIEW_COMPLETION_INCOMPLETE")
        if item["result"] not in allowed or not str(item["reason"]).strip():
            raise OutcomeConflict("REVIEW_COMPLETION_INCOMPLETE")
        if not isinstance(item["evidence_refs"], list):
            raise OutcomeConflict("REVIEW_COMPLETION_INCOMPLETE")
        normalized[key] = {
            "result": str(item["result"]),
            "reason": str(item["reason"]).strip(),
            "evidence_refs": [str(value) for value in item["evidence_refs"]],
        }
    return normalized


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
