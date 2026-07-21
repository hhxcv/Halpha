from __future__ import annotations

from datetime import UTC, datetime

from halpha.domain_values import content_digest
from halpha.outcomes.models import (
    EvidencePurpose,
    PrimaryResult,
    Review,
    ReviewStatus,
)
from halpha.outcomes.service import _review_matches_basis


def _review(*, account_result: dict[str, object]) -> Review:
    fields = {
        "review_id": "10000000-0000-0000-0000-000000000001",
        "review_version": 1,
        "environment_id": "demo-main",
        "activation_id": "20000000-0000-0000-0000-000000000001",
        "previous_version": None,
        "status": ReviewStatus.DRAFT,
        "primary_result": PrimaryResult.COMPLETED,
        "fact_cutoff": datetime(2026, 7, 20, tzinfo=UTC),
        "input_refs": {"activation": {"state_version": 9}},
        "input_digest": "a" * 64,
        "account_result": account_result,
        "open_responsibilities": {
            "execution_action_refs": [],
            "unknown_action_refs": [],
        },
        "evaluations": {
            "owner_conclusion": {
                "result": "AS_EXPECTED",
                "reason": "",
                "evidence_refs": [],
            }
        },
        "evidence_purpose": EvidencePurpose.SYSTEM_MECHANISM_EVIDENCE,
        "created_at": datetime(2026, 7, 20, tzinfo=UTC),
    }
    return Review(**fields, content_digest=content_digest(fields))


def _basis(account_result: dict[str, object]) -> dict[str, object]:
    return {
        "primary_result": PrimaryResult.COMPLETED,
        "account_result": account_result,
        "open_responsibilities": {
            "execution_action_refs": [],
            "unknown_action_refs": [],
        },
        "evidence_purpose": EvidencePurpose.SYSTEM_MECHANISM_EVIDENCE,
    }


def test_review_is_reused_when_facts_and_derived_result_match() -> None:
    result = {"trade_result": {"net_pnl": "1.25"}}

    assert _review_matches_basis(
        _review(account_result=result),
        basis=_basis(result),
        input_digest="a" * 64,
    )


def test_changed_derived_result_creates_a_new_review_version() -> None:
    assert not _review_matches_basis(
        _review(account_result={"trade_result": None}),
        basis=_basis({"trade_result": {"net_pnl": "-0.08"}}),
        input_digest="a" * 64,
    )
