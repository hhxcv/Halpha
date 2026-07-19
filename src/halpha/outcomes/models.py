"""Stable values for activation reviews."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, model_validator

from halpha.domain_values import content_digest


class OutcomeModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ReviewStatus(StrEnum):
    DRAFT = "DRAFT"
    COMPLETE = "COMPLETE"
    SUPERSEDED = "SUPERSEDED"


class PrimaryResult(StrEnum):
    NO_ACTION = "NO_ACTION"
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    RESULT_UNKNOWN = "RESULT_UNKNOWN"
    HANDED_OVER = "HANDED_OVER"


class EvaluationResult(StrEnum):
    AS_EXPECTED = "AS_EXPECTED"
    ISSUE_FOUND = "ISSUE_FOUND"
    UNKNOWN = "UNKNOWN"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class EvidencePurpose(StrEnum):
    SYSTEM_MECHANISM_EVIDENCE = "SYSTEM_MECHANISM_EVIDENCE"
    LIVE_ACTIVATION_REVIEW = "LIVE_ACTIVATION_REVIEW"


EVALUATION_KEYS = frozenset(
    {
        "account_result",
        "plan",
        "capital_authority",
        "execution_facts",
        "interaction",
        "system_maintenance",
    }
)


class Review(OutcomeModel):
    review_id: str
    review_version: int
    environment_id: str
    activation_id: str
    previous_version: int | None
    status: ReviewStatus
    primary_result: PrimaryResult
    fact_cutoff: datetime
    input_refs: dict[str, Any]
    input_digest: str
    account_result: dict[str, Any]
    open_responsibilities: dict[str, Any]
    evaluations: dict[str, dict[str, Any]]
    evidence_purpose: EvidencePurpose
    content_digest: str
    created_at: datetime

    @model_validator(mode="after")
    def validate_review(self) -> Review:
        if self.review_version <= 0:
            raise ValueError("REVIEW_VERSION_CONFLICT")
        if self.previous_version is not None and self.previous_version >= self.review_version:
            raise ValueError("REVIEW_VERSION_CONFLICT")
        if self.status is ReviewStatus.COMPLETE:
            if set(self.evaluations) != EVALUATION_KEYS:
                raise ValueError("REVIEW_COMPLETION_INCOMPLETE")
            if any(
                item.get("result") not in {value.value for value in EvaluationResult}
                or not isinstance(item.get("reason"), str)
                or not item.get("reason")
                for item in self.evaluations.values()
            ):
                raise ValueError("REVIEW_COMPLETION_INCOMPLETE")
        basis = self.model_dump(mode="python", exclude={"content_digest"})
        if self.content_digest != content_digest(basis):
            raise ValueError("REVIEW_CONTENT_DIGEST_MISMATCH")
        return self
