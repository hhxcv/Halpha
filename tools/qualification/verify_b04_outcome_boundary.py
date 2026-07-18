"""Qualify the B04 Review/ImprovementHandoff boundary on PostgreSQL."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path
import sys
from typing import Any
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from halpha.executor.coordinator import HalphaCoordinator
from halpha.outcomes.models import EVALUATION_KEYS
from halpha.outcomes.repository import OutcomeConflict
from halpha.outcomes.service import OutcomeApplicationService
from halpha.venue_integration.gateway import PersistedActionGate
from halpha.venue_integration.repository import PostgreSQLExecutionActionRepository
from tools.qualification.verify_b02_database_boundary import (
    _cleanup,
    _connect,
    _create_and_activate,
    _insert_limit,
)
from tools.qualification.verify_b03_execution_boundary import (
    _NoWriteClient,
    _executor_connect,
)


DEFAULT_OUTPUT = ROOT / "build/qualification/b04-outcome-boundary.json"


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    now = datetime.now(UTC)
    environment_id = f"qualification-b04-outcome-{uuid4()}"
    account_ref = f"qualification-account-{uuid4()}"
    checks: dict[str, bool] = {}
    observations: dict[str, Any] = {}
    errors: list[str] = []
    app_connection = _connect()
    executor_connection = None
    try:
        limit_id = str(uuid4())
        with app_connection.transaction():
            _insert_limit(
                app_connection,
                environment_id=environment_id,
                account_ref=account_ref,
                limit_id=limit_id,
                now=now,
            )
            ids = _create_and_activate(
                app_connection,
                environment_id=environment_id,
                account_ref=account_ref,
                limit_id=limit_id,
                now=now,
                instrument_ref="BTCUSDT-PERP",
                limits=("50", "250", "25"),
            )

        executor_connection = _executor_connect()
        action_repository = PostgreSQLExecutionActionRepository(
            executor_connection, environment_id
        )
        coordinator = HalphaCoordinator(
            executor_connection,
            PersistedActionGate(
                action_repository,
                _NoWriteClient(),
                environment_id=environment_id,
                execution_profile_ref="BINANCE_DEMO",
                account_ref=account_ref,
            ),
            environment_id=environment_id,
            environment_kind="DEMO",
            authority_class="DEMO_VALIDATION",
            execution_profile_ref="BINANCE_DEMO",
            account_ref=account_ref,
            runtime_real_write_gate="CLOSED",
        )
        closure_digest = coordinator.close_activation(
            activation_id=ids["activation_id"],
            cutoff=now,
            position_zero=True,
            open_order_refs=(),
            external_activity_conflict=False,
            fees_complete=True,
            funding_complete=True,
            user_takeover=False,
            handover_command_ref=None,
            fact_refs=(),
            result_ref="ignored-legacy-caller-ref",
            observed_at=now,
        )

        with app_connection.transaction():
            service = OutcomeApplicationService(app_connection, environment_id)
            reviews_before_read = service.list_reviews()
            review = reviews_before_read[0]
            reread = service.read_review(review["review_id"])
            reviews_after_read = service.list_reviews()
            checks["closure_derives_one_demo_system_mechanism_review"] = (
                len(reviews_before_read) == 1
                and review["primary_result"] == "NO_ACTION"
                and review["evidence_purpose"] == "SYSTEM_MECHANISM_EVIDENCE"
                and review["input_refs"]["activation"]["closure_digest"]
                == closure_digest
            )
            checks["review_reads_are_strictly_read_only"] = (
                reviews_before_read == reviews_after_read
                and reread["review"]["review_id"] == review["review_id"]
            )
            replay = service.update_activation_review(
                ids["activation_id"],
                fact_cutoff=now,
                observed_at=now,
            )
            checks["same_activation_inputs_replay_original_review_version"] = (
                replay.review_id == review["review_id"]
                and replay.review_version == review["review_version"] == 1
                and replay.input_digest == review["input_digest"]
            )
            evaluations = {
                key: {
                    "result": (
                        "ISSUE_FOUND" if key == "system_maintenance" else "AS_EXPECTED"
                    ),
                    "reason": f"qualification evaluation for {key}",
                    "evidence_refs": [closure_digest],
                }
                for key in EVALUATION_KEYS
            }
            issue = {
                "target_owner": "OUT",
                "observable_problem": "Qualification fixture issue proves stable handoff identity.",
                "evidence_refs": {"closure_digest": closure_digest},
                "impact_scope": {"qualification_only": True},
                "expected_change": "Keep one handoff for repeated completion.",
            }
            completed, first_handoffs = service.complete_activation_review(
                review["review_id"],
                expected_version=1,
                evaluations=evaluations,
                issues=(issue,),
                no_improvement_reason=None,
                observed_at=now,
            )
            repeated, repeated_handoffs = service.complete_activation_review(
                review["review_id"],
                expected_version=1,
                evaluations=evaluations,
                issues=(issue,),
                no_improvement_reason=None,
                observed_at=now,
            )
            stored_handoffs = service.list_improvement_handoffs("OUT")
            checks["complete_requires_six_evaluations_and_is_idempotent"] = (
                set(completed.evaluations) == EVALUATION_KEYS
                and completed.status.value == "COMPLETE"
                and repeated.content_digest == completed.content_digest
            )
            checks["issue_forms_one_stable_improvement_handoff"] = (
                len(first_handoffs) == len(repeated_handoffs) == len(stored_handoffs) == 1
                and first_handoffs[0].improvement_handoff_id
                == repeated_handoffs[0].improvement_handoff_id
                == stored_handoffs[0]["improvement_handoff_id"]
            )
            conflicting_issue = {
                **issue,
                "expected_change": "A different payload for the same stable issue must conflict.",
            }
            conflicting_handoff_rejected = False
            try:
                service.complete_activation_review(
                    review["review_id"],
                    expected_version=1,
                    evaluations=evaluations,
                    issues=(conflicting_issue,),
                    no_improvement_reason=None,
                    observed_at=now,
                )
            except OutcomeConflict as exc:
                conflicting_handoff_rejected = (
                    str(exc) == "IMPROVEMENT_HANDOFF_CONFLICT"
                )
            checks["same_handoff_identity_with_different_content_conflicts"] = (
                conflicting_handoff_rejected
                and len(service.list_improvement_handoffs("OUT")) == 1
            )
            observations.update(
                {
                    "review_id": review["review_id"],
                    "review_version": 1,
                    "handoff_count": len(stored_handoffs),
                    "record_family_delta": 0,
                    "venue_write_performed": False,
                }
            )
    except Exception as exc:
        errors.append(f"B04_OUTCOME_BOUNDARY_FAILED:{type(exc).__name__}:{exc}")
    finally:
        try:
            with app_connection.transaction():
                app_connection.execute(
                    "DELETE FROM halpha.improvement_handoff WHERE environment_id = %s",
                    (environment_id,),
                )
                app_connection.execute(
                    "DELETE FROM halpha.review WHERE environment_id = %s",
                    (environment_id,),
                )
                _cleanup(app_connection, environment_id)
        except Exception as exc:
            errors.append(f"B04_OUTCOME_CLEANUP_FAILED:{type(exc).__name__}")
        if executor_connection is not None:
            executor_connection.close()
        app_connection.close()

    checks["qualification_records_cleaned"] = not errors
    evidence: dict[str, Any] = {
        "stage": "B04_OUTCOME_BOUNDARY",
        "observed_at": datetime.now(UTC).isoformat(),
        "environment_kind": "DEMO",
        "authority_class": "DEMO_VALIDATION",
        "checks": checks,
        "observations": observations,
        "errors": errors,
        "venue_write_performed": False,
    }
    evidence["status"] = (
        "QUALIFIED" if checks and all(checks.values()) and not errors else "REJECTED"
    )
    evidence["evidence_digest"] = sha256(_canonical(evidence)).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if evidence["status"] == "QUALIFIED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
