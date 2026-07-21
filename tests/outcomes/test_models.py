from __future__ import annotations

from datetime import UTC, datetime

import pytest

from halpha.domain_values import content_digest
from halpha.outcomes.models import (
    EvaluationResult,
    EvidencePurpose,
    PrimaryResult,
    Review,
    ReviewStatus,
)
from halpha.outcomes.service import _draft_evaluations, _owner_conclusion


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


def test_complete_review_requires_one_owner_conclusion() -> None:
    fields = _review_fields()
    fields.update({"status": ReviewStatus.COMPLETE, "evaluations": {}})
    with pytest.raises(ValueError, match="REVIEW_COMPLETION_INCOMPLETE"):
        Review(**fields, content_digest=content_digest(fields))

    fields["evaluations"] = _owner_conclusion(EvaluationResult.AS_EXPECTED, "")
    complete = Review(**fields, content_digest=content_digest(fields))
    assert complete.status is ReviewStatus.COMPLETE


def test_review_digest_drift_is_rejected() -> None:
    fields = _review_fields()
    with pytest.raises(ValueError, match="REVIEW_CONTENT_DIGEST_MISMATCH"):
        Review(**fields, content_digest="0" * 64)


def test_draft_review_contains_only_the_owner_conclusion() -> None:
    evaluations = _draft_evaluations()
    assert evaluations == {
        "owner_conclusion": {
            "result": "UNKNOWN",
            "reason": "",
            "evidence_refs": [],
        }
    }
