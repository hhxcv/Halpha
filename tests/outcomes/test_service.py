from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from halpha.domain_values import content_digest
from halpha.outcomes.models import (
    EvaluationResult,
    EvidencePurpose,
    PrimaryResult,
    Review,
    ReviewClassification,
    ReviewRevisionReason,
    ReviewStatus,
    StageReview,
    StageReviewCreator,
)
from halpha.outcomes.repository import OutcomeConflict
from halpha.outcomes.service import (
    OutcomeApplicationService,
    _review_matches_basis,
    _unknown_result_action_refs,
)


def _review(
    *,
    account_result: dict[str, object],
    primary_result: PrimaryResult = PrimaryResult.COMPLETED,
) -> Review:
    fields = {
        "review_id": "10000000-0000-0000-0000-000000000001",
        "review_version": 1,
        "environment_id": "demo-main",
        "activation_id": "20000000-0000-0000-0000-000000000001",
        "previous_version": None,
        "revision_reason": ReviewRevisionReason.INITIAL_DERIVATION,
        "status": ReviewStatus.DRAFT,
        "primary_result": primary_result,
        "fact_cutoff": datetime(2026, 7, 20, tzinfo=UTC),
        "input_refs": {"activation": {"state_version": 9}},
        "input_digest": "a" * 64,
        "account_result": account_result,
        "open_responsibilities": {
            "execution_action_refs": [],
            "unknown_action_refs": [],
        },
        "evaluations": {},
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


def test_called_handover_remains_a_result_unknown_reference() -> None:
    assert _unknown_result_action_refs([
        (
            "called-handover",
            3,
            "HANDED_OVER",
            "state-digest",
            None,
            datetime(2026, 7, 29, 3, 1, tzinfo=UTC),
            "ENTRY",
            datetime(2026, 7, 29, 3, 0, tzinfo=UTC),
        ),
        (
            "not-called-handover",
            2,
            "HANDED_OVER",
            "state-digest",
            None,
            datetime(2026, 7, 29, 3, 1, tzinfo=UTC),
            "ENTRY",
            None,
        ),
        (
            "unknown",
            2,
            "UNKNOWN",
            "state-digest",
            None,
            datetime(2026, 7, 29, 3, 1, tzinfo=UTC),
            "ENTRY",
            datetime(2026, 7, 29, 3, 0, tzinfo=UTC),
        ),
    ]) == ["called-handover", "unknown"]


class _Reviews:
    def __init__(self, versions: list[Review]) -> None:
        self.versions = versions
        self.locked: list[str] = []
        self.stage_reviews: list[StageReview] = []

    def lock_activation(self, activation_id: str) -> None:
        self.locked.append(activation_id)

    def get_latest_for_activation(self, activation_id: str) -> Review | None:
        assert activation_id == self.versions[0].activation_id
        return self.versions[-1] if self.versions else None

    def get_review(self, review_id: str, version: int | None = None) -> Review:
        matches = [
            item
            for item in self.versions
            if item.review_id == review_id
            and (version is None or item.review_version == version)
        ]
        if not matches:
            raise OutcomeConflict("REVIEW_NOT_FOUND")
        return matches[-1]

    def insert_review(self, review: Review) -> None:
        self.versions.append(review)

    def list_review_versions(self, review_id: str) -> tuple[Review, ...]:
        return tuple(
            sorted(
                (item for item in self.versions if item.review_id == review_id),
                key=lambda item: item.review_version,
                reverse=True,
            )
        )

    def list_reviews(self) -> tuple[Review, ...]:
        latest: dict[str, Review] = {}
        for review in self.versions:
            current = latest.get(review.review_id)
            if current is None or review.review_version > current.review_version:
                latest[review.review_id] = review
        return tuple(latest.values())

    def get_stage_review_by_idempotency_key(
        self,
        idempotency_key: str,
    ) -> StageReview | None:
        return next(
            (
                review
                for review in self.stage_reviews
                if review.idempotency_key == idempotency_key
            ),
            None,
        )

    def insert_stage_review(self, review: StageReview) -> bool:
        if self.get_stage_review_by_idempotency_key(review.idempotency_key):
            return False
        self.stage_reviews.append(review)
        return True

    def list_stage_reviews(self) -> tuple[StageReview, ...]:
        return tuple(reversed(self.stage_reviews))


def _service(
    initial: Review,
    *,
    basis: dict[str, object] | None = None,
) -> tuple[OutcomeApplicationService, _Reviews]:
    repository = _Reviews([initial])
    service = object.__new__(OutcomeApplicationService)
    service._environment_id = initial.environment_id
    service._repository = repository
    if basis is not None:
        service._collect_basis = lambda *_args, **_kwargs: basis
    return service, repository


def test_changed_facts_append_a_draft_without_mutating_v1() -> None:
    initial = _review(account_result={"trade_result": {"net_pnl": "1.25"}})
    new_input_refs = {"activation": {"state_version": 10}}
    basis = {
        **_basis({"trade_result": {"net_pnl": "1.10"}}),
        "input_refs": new_input_refs,
        "evaluations": {},
    }
    service, repository = _service(initial, basis=basis)
    observed_at = initial.created_at + timedelta(minutes=5)

    result = service.update_activation_review(
        initial.activation_id,
        fact_cutoff=observed_at,
        observed_at=observed_at,
        expected_version=1,
    )

    assert repository.locked == [initial.activation_id]
    assert repository.versions[0] is initial
    assert repository.versions[0].status is ReviewStatus.DRAFT
    assert result.review_version == 2
    assert result.previous_version == 1
    assert (
        result.revision_reason
        is ReviewRevisionReason.AUTHORITATIVE_FACTS_CHANGED
    )
    assert result.status is ReviewStatus.DRAFT
    assert result.input_digest == content_digest(new_input_refs)


def test_completion_appends_and_preserves_the_draft() -> None:
    initial = _review(account_result={"trade_result": {"net_pnl": "1.25"}})
    service, repository = _service(initial)
    observed_at = initial.created_at + timedelta(minutes=5)

    result = service.complete_activation_review(
        initial.review_id,
        expected_version=1,
        conclusion=ReviewClassification.USABLE_SAMPLE,
        note="边界与结果一致",
        observed_at=observed_at,
    )

    assert repository.versions[0] is initial
    assert repository.versions[0].status is ReviewStatus.DRAFT
    assert result.review_version == 2
    assert result.previous_version == 1
    assert (
        result.revision_reason
        is ReviewRevisionReason.OWNER_EVALUATION_CHANGED
    )
    assert result.status is ReviewStatus.COMPLETE
    assert result.evaluations["owner_conclusion"]["reason"] == "边界与结果一致"


@pytest.mark.parametrize(
    "classification",
    [
        ReviewClassification.TOOLING_ISSUE,
        ReviewClassification.VALIDATION_TRADE,
    ],
)
def test_remediation_classification_requires_a_reason_without_append(
    classification: ReviewClassification,
) -> None:
    initial = _review(account_result={"trade_result": {"net_pnl": "1.25"}})
    service, repository = _service(initial)

    with pytest.raises(
        ValueError, match="REVIEW_CLASSIFICATION_REASON_REQUIRED"
    ):
        service.complete_activation_review(
            initial.review_id,
            expected_version=1,
            conclusion=classification,
            note="  ",
            observed_at=initial.created_at + timedelta(minutes=5),
        )

    assert repository.versions == [initial]


def test_historical_classification_cannot_be_submitted_again() -> None:
    initial = _review(account_result={"trade_result": {"net_pnl": "1.25"}})
    service, repository = _service(initial)

    with pytest.raises(
        ValueError, match="REVIEW_CLASSIFICATION_NOT_SUBMITTABLE"
    ):
        service.complete_activation_review(
            initial.review_id,
            expected_version=1,
            conclusion=EvaluationResult.UNKNOWN,  # type: ignore[arg-type]
            note="",
            observed_at=initial.created_at + timedelta(minutes=5),
        )

    assert repository.versions == [initial]


def test_trade_presence_limits_sample_and_no_trade_classifications() -> None:
    traded = _review(account_result={"trade_result": {"net_pnl": "1.25"}})
    traded_service, traded_repository = _service(traded)
    with pytest.raises(ValueError, match="REVIEW_NO_TRADE_REQUIRES_NO_ACTION"):
        traded_service.complete_activation_review(
            traded.review_id,
            expected_version=1,
            conclusion=ReviewClassification.NO_TRADE,
            note="",
            observed_at=traded.created_at + timedelta(minutes=5),
        )
    assert traded_repository.versions == [traded]

    no_trade = _review(
        account_result={"trade_result": None},
        primary_result=PrimaryResult.NO_ACTION,
    )
    no_trade_service, no_trade_repository = _service(no_trade)
    with pytest.raises(
        ValueError, match="REVIEW_USABLE_SAMPLE_REQUIRES_COMPLETED_TRADE"
    ):
        no_trade_service.complete_activation_review(
            no_trade.review_id,
            expected_version=1,
            conclusion=ReviewClassification.USABLE_SAMPLE,
            note="",
            observed_at=no_trade.created_at + timedelta(minutes=5),
        )

    unresolved = _review(
        account_result={"trade_result": None},
        primary_result=PrimaryResult.RESULT_UNKNOWN,
    )
    unresolved_service, unresolved_repository = _service(unresolved)
    with pytest.raises(
        ValueError, match="REVIEW_USABLE_SAMPLE_REQUIRES_COMPLETED_TRADE"
    ):
        unresolved_service.complete_activation_review(
            unresolved.review_id,
            expected_version=1,
            conclusion=ReviewClassification.USABLE_SAMPLE,
            note="",
            observed_at=unresolved.created_at + timedelta(minutes=5),
        )
    assert unresolved_repository.versions == [unresolved]

    completed = no_trade_service.complete_activation_review(
        no_trade.review_id,
        expected_version=1,
        conclusion=ReviewClassification.NO_TRADE,
        note="",
        observed_at=no_trade.created_at + timedelta(minutes=6),
    )
    assert completed.evaluations["owner_conclusion"]["result"] == "NO_TRADE"
    assert len(no_trade_repository.versions) == 2


def test_validation_trade_requires_a_completed_or_partial_trade() -> None:
    no_trade = _review(
        account_result={"trade_result": None},
        primary_result=PrimaryResult.NO_ACTION,
    )
    service, repository = _service(no_trade)

    with pytest.raises(
        ValueError,
        match="REVIEW_VALIDATION_TRADE_REQUIRES_COMPLETED_TRADE",
    ):
        service.complete_activation_review(
            no_trade.review_id,
            expected_version=1,
            conclusion=ReviewClassification.VALIDATION_TRADE,
            note="验证退出责任闭环",
            observed_at=no_trade.created_at + timedelta(minutes=5),
        )

    assert repository.versions == [no_trade]


def test_repeating_the_same_complete_evaluation_is_idempotent() -> None:
    initial = _review(account_result={"trade_result": {"net_pnl": "1.25"}})
    service, repository = _service(initial)
    first = service.complete_activation_review(
        initial.review_id,
        expected_version=1,
        conclusion=ReviewClassification.USABLE_SAMPLE,
        note="边界与结果一致",
        observed_at=initial.created_at + timedelta(minutes=5),
    )

    repeated = service.complete_activation_review(
        initial.review_id,
        expected_version=1,
        conclusion=ReviewClassification.USABLE_SAMPLE,
        note="边界与结果一致",
        observed_at=initial.created_at + timedelta(minutes=6),
    )

    assert repeated is first
    assert len(repository.versions) == 2


def test_stage_review_freezes_exact_review_versions_and_metrics() -> None:
    first = _review(
        account_result={
            "trade_result": {
                "calculation_complete": True,
                "closed": True,
                "net_pnl": "2.5",
                "commission": "0.5",
                "entry_notional": "100",
            }
        }
    )
    second_fields = first.model_dump(mode="python", exclude={"content_digest"})
    second_fields.update(
        {
            "review_id": "10000000-0000-0000-0000-000000000002",
            "activation_id": "20000000-0000-0000-0000-000000000002",
            "fact_cutoff": first.fact_cutoff + timedelta(hours=1),
            "account_result": {
                "trade_result": {
                    "calculation_complete": True,
                    "closed": True,
                    "net_pnl": "-1",
                    "commission": "0.2",
                    "entry_notional": "100",
                }
            },
        }
    )
    second = Review(
        **second_fields,
        content_digest=content_digest(second_fields),
    )
    repository = _Reviews([first, second])
    service = object.__new__(OutcomeApplicationService)
    service._environment_id = first.environment_id
    service._repository = repository

    result = service.create_stage_review(
        idempotency_key="stage-review-1",
        title="近期两笔交易复盘",
        range_start=first.fact_cutoff,
        range_end=second.fact_cutoff,
        problem_analysis="费用后收益不足。",
        improvement_plan="下一组只验证低费用入场。",
        creator_kind=StageReviewCreator.HUMAN,
        observed_at=second.fact_cutoff + timedelta(minutes=1),
    )

    assert [item["review_id"] for item in result.source_review_refs] == [
        first.review_id,
        second.review_id,
    ]
    assert result.metrics_snapshot == {
        "review_count": 2,
        "reliable_trade_count": 2,
        "pending_evaluation_count": 2,
        "net_pnl": "1.5",
        "commission": "0.7",
        "total_entry_notional": "200",
        "notional_return_percent": "0.7500",
        "wins": 1,
        "win_rate_percent": "50.0",
        "current_streak_kind": "LOSS",
        "current_streak_count": 1,
    }

    replay = service.create_stage_review(
        idempotency_key="stage-review-1",
        title="近期两笔交易复盘",
        range_start=first.fact_cutoff,
        range_end=second.fact_cutoff,
        problem_analysis="费用后收益不足。",
        improvement_plan="下一组只验证低费用入场。",
        creator_kind=StageReviewCreator.HUMAN,
        observed_at=second.fact_cutoff + timedelta(minutes=2),
    )
    assert replay is result
    assert len(repository.stage_reviews) == 1


def test_stage_review_rejects_empty_range_and_idempotency_conflict() -> None:
    initial = _review(account_result={"trade_result": None})
    service, repository = _service(initial)

    with pytest.raises(ValueError, match="STAGE_REVIEW_SOURCE_EMPTY"):
        service.create_stage_review(
            idempotency_key="outside",
            title="空范围",
            range_start=initial.fact_cutoff + timedelta(days=1),
            range_end=initial.fact_cutoff + timedelta(days=2),
            problem_analysis="没有样本。",
            improvement_plan="重新选择范围。",
            creator_kind=StageReviewCreator.HUMAN,
            observed_at=initial.fact_cutoff,
        )

    service.create_stage_review(
        idempotency_key="same-key",
        title="原复盘",
        range_start=initial.fact_cutoff,
        range_end=initial.fact_cutoff,
        problem_analysis="问题。",
        improvement_plan="方案。",
        creator_kind=StageReviewCreator.HUMAN,
        observed_at=initial.fact_cutoff,
    )
    with pytest.raises(
        OutcomeConflict,
        match="STAGE_REVIEW_IDEMPOTENCY_CONFLICT",
    ):
        service.create_stage_review(
            idempotency_key="same-key",
            title="不同复盘",
            range_start=initial.fact_cutoff,
            range_end=initial.fact_cutoff,
            problem_analysis="问题。",
            improvement_plan="方案。",
            creator_kind=StageReviewCreator.HUMAN,
            observed_at=initial.fact_cutoff,
        )
    assert len(repository.stage_reviews) == 1


def test_repeating_the_same_fact_refresh_with_old_version_replays_v2() -> None:
    initial = _review(account_result={"trade_result": {"net_pnl": "1.25"}})
    new_input_refs = {"activation": {"state_version": 10}}
    basis = {
        **_basis({"trade_result": {"net_pnl": "1.10"}}),
        "input_refs": new_input_refs,
        "evaluations": {},
    }
    service, repository = _service(initial, basis=basis)
    observed_at = initial.created_at + timedelta(minutes=5)
    first = service.update_activation_review(
        initial.activation_id,
        fact_cutoff=observed_at,
        observed_at=observed_at,
        expected_version=1,
    )

    repeated = service.update_activation_review(
        initial.activation_id,
        fact_cutoff=observed_at,
        observed_at=observed_at + timedelta(seconds=1),
        expected_version=1,
    )

    assert repeated is first
    assert len(repository.versions) == 2


def test_changed_owner_evaluation_appends_another_complete_version() -> None:
    initial = _review(account_result={"trade_result": {"net_pnl": "1.25"}})
    service, repository = _service(initial)
    first = service.complete_activation_review(
        initial.review_id,
        expected_version=1,
        conclusion=ReviewClassification.USABLE_SAMPLE,
        note="最初判断",
        observed_at=initial.created_at + timedelta(minutes=5),
    )

    corrected = service.complete_activation_review(
        initial.review_id,
        expected_version=2,
        conclusion=ReviewClassification.TRADE_DECISION_ISSUE,
        note="后续确认存在问题",
        observed_at=initial.created_at + timedelta(minutes=6),
    )

    assert first.status is ReviewStatus.COMPLETE
    assert corrected.review_version == 3
    assert corrected.previous_version == 2
    assert corrected.status is ReviewStatus.COMPLETE
    assert repository.versions[1] is first


def test_stale_completion_version_is_rejected_without_append() -> None:
    initial = _review(account_result={"trade_result": {"net_pnl": "1.25"}})
    service, repository = _service(initial)
    service.complete_activation_review(
        initial.review_id,
        expected_version=1,
        conclusion=ReviewClassification.USABLE_SAMPLE,
        note="first",
        observed_at=initial.created_at + timedelta(minutes=5),
    )

    with pytest.raises(OutcomeConflict, match="REVIEW_VERSION_CONFLICT"):
        service.complete_activation_review(
            initial.review_id,
            expected_version=1,
            conclusion=ReviewClassification.TRADE_DECISION_ISSUE,
            note="stale",
            observed_at=initial.created_at + timedelta(minutes=6),
        )

    assert len(repository.versions) == 2


def test_read_review_returns_latest_and_all_immutable_versions() -> None:
    initial = _review(account_result={"trade_result": {"net_pnl": "1.25"}})
    service, _repository = _service(initial)
    completed = service.complete_activation_review(
        initial.review_id,
        expected_version=1,
        conclusion=ReviewClassification.USABLE_SAMPLE,
        note="complete",
        observed_at=initial.created_at + timedelta(minutes=5),
    )

    result = service.read_review(initial.review_id)

    assert result["review"]["review_version"] == completed.review_version
    assert [
        item["review_version"]
        for item in result["versions"]
    ] == [2, 1]
