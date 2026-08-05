from __future__ import annotations

from datetime import UTC, datetime

import pytest

from halpha.app.api_models import ReviewResponse
from halpha.domain_values import content_digest
from halpha.outcomes.models import (
    EvidencePurpose,
    PrimaryResult,
    ReviewRevisionReason,
    ReviewStatus,
)


def _persisted_review_fields() -> dict[str, object]:
    return {
        "review_id": "10000000-0000-0000-0000-000000000001",
        "review_version": 1,
        "environment_id": "demo-main",
        "activation_id": "10000000-0000-0000-0000-000000000002",
        "previous_version": None,
        "revision_reason": ReviewRevisionReason.INITIAL_DERIVATION,
        "status": ReviewStatus.DRAFT,
        "primary_result": PrimaryResult.NO_ACTION,
        "fact_cutoff": datetime(2026, 7, 17, 13, tzinfo=UTC),
        "input_refs": {"activation": {"state_version": 4}},
        "input_digest": "a" * 64,
        "account_result": {"classification": "NO_EXTERNAL_CHANGE"},
        "open_responsibilities": {"execution_action_refs": []},
        "evaluations": {},
        "evidence_purpose": EvidencePurpose.SYSTEM_MECHANISM_EVIDENCE,
        "created_at": datetime(2026, 7, 17, 13, tzinfo=UTC),
    }


def test_review_response_projection_does_not_change_persisted_review_digest() -> None:
    fields = _persisted_review_fields()

    response = ReviewResponse(
        **fields,
        content_digest=content_digest(fields),
        trade_context={"instrument_ref": "BTCUSDT-PERP"},
        resolved_trade_result={"calculation_complete": False},
    )

    assert response.trade_context["instrument_ref"] == "BTCUSDT-PERP"


def test_review_response_still_rejects_persisted_review_digest_drift() -> None:
    fields = _persisted_review_fields()

    with pytest.raises(ValueError, match="REVIEW_CONTENT_DIGEST_MISMATCH"):
        ReviewResponse(
            **fields,
            content_digest="0" * 64,
            trade_context={},
            resolved_trade_result={},
        )
