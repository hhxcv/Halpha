"""Stable values for activation reviews."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from halpha.domain_values import content_digest


class OutcomeModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ReviewStatus(StrEnum):
    DRAFT = "DRAFT"
    COMPLETE = "COMPLETE"


class ReviewRevisionReason(StrEnum):
    INITIAL_DERIVATION = "INITIAL_DERIVATION"
    AUTHORITATIVE_FACTS_CHANGED = "AUTHORITATIVE_FACTS_CHANGED"
    OWNER_EVALUATION_CHANGED = "OWNER_EVALUATION_CHANGED"


class PrimaryResult(StrEnum):
    NO_ACTION = "NO_ACTION"
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    RESULT_UNKNOWN = "RESULT_UNKNOWN"
    HANDED_OVER = "HANDED_OVER"


class EvaluationResult(StrEnum):
    USABLE_SAMPLE = "USABLE_SAMPLE"
    TRADE_DECISION_ISSUE = "TRADE_DECISION_ISSUE"
    TOOLING_ISSUE = "TOOLING_ISSUE"
    VALIDATION_TRADE = "VALIDATION_TRADE"
    NO_TRADE = "NO_TRADE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"

    # Historical persisted values remain readable but are not accepted by the
    # current review-completion command.
    AS_EXPECTED = "AS_EXPECTED"
    ISSUE_FOUND = "ISSUE_FOUND"
    UNKNOWN = "UNKNOWN"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class ReviewClassification(StrEnum):
    USABLE_SAMPLE = EvaluationResult.USABLE_SAMPLE.value
    TRADE_DECISION_ISSUE = EvaluationResult.TRADE_DECISION_ISSUE.value
    TOOLING_ISSUE = EvaluationResult.TOOLING_ISSUE.value
    VALIDATION_TRADE = EvaluationResult.VALIDATION_TRADE.value
    NO_TRADE = EvaluationResult.NO_TRADE.value
    INSUFFICIENT_EVIDENCE = EvaluationResult.INSUFFICIENT_EVIDENCE.value


REVIEW_CLASSIFICATIONS_REQUIRING_REASON = frozenset(
    {
        ReviewClassification.TRADE_DECISION_ISSUE,
        ReviewClassification.TOOLING_ISSUE,
        ReviewClassification.VALIDATION_TRADE,
        ReviewClassification.INSUFFICIENT_EVIDENCE,
    }
)


class EvidencePurpose(StrEnum):
    SYSTEM_MECHANISM_EVIDENCE = "SYSTEM_MECHANISM_EVIDENCE"
    LIVE_ACTIVATION_REVIEW = "LIVE_ACTIVATION_REVIEW"


class StageReviewCreator(StrEnum):
    HUMAN = "HUMAN"
    AI = "AI"


OWNER_CONCLUSION_KEY = "owner_conclusion"
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
    revision_reason: ReviewRevisionReason
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
        if self.review_version == 1 and (
            self.previous_version is not None
            or self.revision_reason is not ReviewRevisionReason.INITIAL_DERIVATION
        ):
            raise ValueError("REVIEW_VERSION_CONFLICT")
        if self.review_version > 1 and (
            self.previous_version != self.review_version - 1
            or self.revision_reason is ReviewRevisionReason.INITIAL_DERIVATION
        ):
            raise ValueError("REVIEW_VERSION_CONFLICT")
        if self.status is ReviewStatus.COMPLETE:
            keys = set(self.evaluations)
            if keys == {OWNER_CONCLUSION_KEY}:
                item = self.evaluations[OWNER_CONCLUSION_KEY]
                if (
                    item.get("result") not in {value.value for value in EvaluationResult}
                    or not isinstance(item.get("reason"), str)
                    or not isinstance(item.get("evidence_refs"), list)
                ):
                    raise ValueError("REVIEW_COMPLETION_INCOMPLETE")
                if (
                    item.get("result")
                    in {
                        value.value
                        for value in REVIEW_CLASSIFICATIONS_REQUIRING_REASON
                    }
                    and not item["reason"].strip()
                ):
                    raise ValueError("REVIEW_CLASSIFICATION_REASON_REQUIRED")
            elif keys != EVALUATION_KEYS:
                raise ValueError("REVIEW_COMPLETION_INCOMPLETE")
            elif any(
                item.get("result") not in {value.value for value in EvaluationResult}
                or not isinstance(item.get("reason"), str)
                or not item.get("reason")
                for item in self.evaluations.values()
            ):
                raise ValueError("REVIEW_COMPLETION_INCOMPLETE")
        basis = self.model_dump(
            mode="python",
            include=set(Review.model_fields) - {"content_digest"},
        )
        if self.content_digest != content_digest(basis):
            raise ValueError("REVIEW_CONTENT_DIGEST_MISMATCH")
        return self


class StageReview(OutcomeModel):
    stage_review_id: str
    environment_id: str
    idempotency_key: str
    request_digest: str
    title: str = Field(min_length=1, max_length=160)
    range_start: datetime
    range_end: datetime
    source_review_refs: list[dict[str, Any]]
    metrics_snapshot: dict[str, Any]
    problem_analysis: str = Field(min_length=1, max_length=8000)
    improvement_plan: str = Field(min_length=1, max_length=8000)
    creator_kind: StageReviewCreator
    content_digest: str
    created_at: datetime

    @model_validator(mode="after")
    def validate_stage_review(self) -> StageReview:
        if self.range_start > self.range_end:
            raise ValueError("STAGE_REVIEW_RANGE_INVALID")
        if not self.title.strip():
            raise ValueError("STAGE_REVIEW_TITLE_REQUIRED")
        if not self.problem_analysis.strip():
            raise ValueError("STAGE_REVIEW_PROBLEM_ANALYSIS_REQUIRED")
        if not self.improvement_plan.strip():
            raise ValueError("STAGE_REVIEW_IMPROVEMENT_PLAN_REQUIRED")
        if not self.source_review_refs:
            raise ValueError("STAGE_REVIEW_SOURCE_EMPTY")
        basis = self.model_dump(mode="python", exclude={"content_digest"})
        if self.content_digest != content_digest(basis):
            raise ValueError("STAGE_REVIEW_CONTENT_DIGEST_MISMATCH")
        return self
