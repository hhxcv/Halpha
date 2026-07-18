from __future__ import annotations

from datetime import UTC, datetime

import pytest

from halpha.domain_values import content_digest
from halpha.outcomes.models import (
    EVALUATION_KEYS,
    EvidencePurpose,
    PrimaryResult,
    Review,
    ReviewStatus,
)
from halpha.outcomes.service import _draft_evaluations


NOW = datetime(2026, 7, 17, 13, tzinfo=UTC)


def _review_fields() -> dict[str, object]:
    return {
        "review_id": "10000000-0000-0000-0000-000000000001",
        "review_version": 1,
        "environment_id": "demo-main",
        "activation_id": "10000000-0000-0000-0000-000000000002",
        "previous_version": None,
        "status": ReviewStatus.DRAFT,
        "primary_result": PrimaryResult.NO_ACTION,
        "fact_cutoff": NOW,
        "input_refs": {"activation": {"state_version": 4}},
        "input_digest": "a" * 64,
        "account_result": {"classification": "NO_EXTERNAL_CHANGE"},
        "open_responsibilities": {"execution_action_refs": []},
        "evaluations": {},
        "evidence_purpose": EvidencePurpose.SYSTEM_MECHANISM_EVIDENCE,
        "created_at": NOW,
    }


def test_demo_review_has_one_stable_record_shape_and_digest() -> None:
    fields = _review_fields()
    review = Review(**fields, content_digest=content_digest(fields))
    assert review.evidence_purpose is EvidencePurpose.SYSTEM_MECHANISM_EVIDENCE
    assert review.primary_result is PrimaryResult.NO_ACTION


def test_complete_review_requires_all_six_evaluations() -> None:
    fields = _review_fields()
    fields.update({"status": ReviewStatus.COMPLETE, "evaluations": {}})
    with pytest.raises(ValueError, match="REVIEW_COMPLETION_INCOMPLETE"):
        Review(**fields, content_digest=content_digest(fields))

    fields["evaluations"] = {
        key: {"result": "AS_EXPECTED", "reason": "evidence checked", "evidence_refs": []}
        for key in EVALUATION_KEYS
    }
    complete = Review(**fields, content_digest=content_digest(fields))
    assert complete.status is ReviewStatus.COMPLETE


def test_review_digest_drift_is_rejected() -> None:
    fields = _review_fields()
    with pytest.raises(ValueError, match="REVIEW_CONTENT_DIGEST_MISMATCH"):
        Review(**fields, content_digest="0" * 64)


def test_draft_plan_evaluation_uses_plan_event_count_not_action_count() -> None:
    evaluations = _draft_evaluations(
        primary_result=PrimaryResult.NO_ACTION,
        missing_refs=[],
        closure_digest="b" * 64,
        event_count=3,
        action_count=7,
        fact_count=2,
    )
    assert evaluations["plan"]["evidence_refs"] == ["plan_event_count:3"]
    assert evaluations["execution_facts"]["evidence_refs"] == [
        "actions:7",
        "facts:2",
    ]
