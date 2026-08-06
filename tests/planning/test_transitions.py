from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from halpha.capital.models import AuthorityClass, EnvironmentKind, StopCategory
from halpha.domain_values import content_digest
from halpha.planning.models import (
    PlanActivation,
    PlanLifecycle,
    ProtectionState,
    RunState,
)
from halpha.planning.order_policies import (
    ConditionFacts,
    ConditionResult,
    RuntimeConditionState,
)
from halpha.planning.transitions import (
    EventConflict,
    complete_activation,
    consume_entry_opportunity,
    deadline_source_identity,
    enter_exit,
    enter_user_takeover,
    proposed_action_from_strategy_proposal,
    record_runtime_condition_state,
    resolve_existing_event,
    resume_activation,
    update_protection_projection,
)
from halpha.planning.strategies.one_shot import RiskDirection, StrategyProposal


NOW = datetime(2026, 7, 17, 8, tzinfo=UTC)


def _activation(**updates: object) -> PlanActivation:
    values: dict[str, object] = {
        "activation_id": "activation-1",
        "environment_id": "demo-1",
        "environment_kind": EnvironmentKind.DEMO,
        "authority_class": AuthorityClass.DEMO_VALIDATION,
        "plan_version_ref": "plan-version-1",
        "account_ref": "account-1",
        "instrument_ref": "BTCUSDT-PERP",
        "direction": "LONG",
        "decision_basis_ref": "ONE_SHOT_DONCHIAN_ATR_BREAKOUT@1.0.1",
        "framework_strategy_id": "HALPHA-TEST",
        "target_exposure": "0.1",
        "rule_state": {},
        "protection_state": ProtectionState.NONE,
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(updates)
    return PlanActivation(**values)


def test_protection_gap_cannot_be_erased_by_an_unrelated_working_fact() -> None:
    activation = _activation(protection_state=ProtectionState.GAP)

    with pytest.raises(ValueError, match="PROTECTION_STATE_INVALID"):
        update_protection_projection(
            activation,
            protection_state=ProtectionState.WORKING,
            pending_action_digest="a" * 64,
            observed_at=NOW,
        )

    closed = update_protection_projection(
        activation,
        protection_state=ProtectionState.CLOSED,
        pending_action_digest=None,
        observed_at=NOW,
    )
    assert closed.protection_state is ProtectionState.CLOSED


def test_digest_conflict_is_not_a_second_event() -> None:
    identity = "activation-1:BAR:target-cutoff:source-cutoff"
    assert (
        resolve_existing_event(None, source_identity=identity, input_digest="a" * 64)
        is None
    )
    fake = object.__new__(type("Event", (), {}))
    fake.source_identity = identity
    fake.input_digest = "a" * 64
    assert (
        resolve_existing_event(fake, source_identity=identity, input_digest="a" * 64)
        is fake
    )
    with pytest.raises(EventConflict, match="FACT_CONFLICT"):
        resolve_existing_event(fake, source_identity=identity, input_digest="b" * 64)


def test_deadline_identity_is_stable_and_changes_only_with_its_source() -> None:
    deadline = NOW + timedelta(hours=1)
    identity = deadline_source_identity(
        activation_id="activation-1",
        rule_id="ENTRY_DEADLINE",
        deadline=deadline,
    )
    assert identity == deadline_source_identity(
        activation_id="activation-1",
        rule_id="ENTRY_DEADLINE",
        deadline=deadline,
    )
    assert identity != deadline_source_identity(
        activation_id="activation-1",
        rule_id="ENTRY_DEADLINE",
        deadline=deadline + timedelta(seconds=1),
    )


def test_strategy_proposal_normalizes_to_non_executable_proposed_action() -> None:
    proposal_fields = {
        "strategy_id": "ONE_SHOT_DONCHIAN_ATR_BREAKOUT",
        "activation_id": "activation-1",
        "rule_id": "ENTRY_BREAKOUT",
        "source_identity": "activation-1:BAR:target-cutoff:source-cutoff",
        "source_cutoff": NOW,
        "input_digest": "d" * 64,
        "instrument_id": "BTCUSDT-PERP.BINANCE",
        "direction": "LONG",
        "action_profile": "ENTRY_MARKET",
        "risk_direction": RiskDirection.INCREASE,
        "quantity": "0.1",
        "reference_price": "5000",
        "reference_source": "TEST",
        "reason_code": "ENTRY_BREAKOUT_CONFIRMED",
        "valid_until": NOW + timedelta(seconds=30),
    }
    proposal = StrategyProposal(
        **proposal_fields,
        proposal_digest=content_digest(proposal_fields),
    )
    action = proposed_action_from_strategy_proposal(_activation(), proposal)
    assert action.environment_id == "demo-1"
    assert action.instrument_ref == "BTCUSDT-PERP"
    assert action.action_profile == "ENTRY_MARKET"
    assert action.order_type == "MARKET"
    assert action.reduce_only is False
    with pytest.raises(EventConflict, match="FACT_CONFLICT"):
        proposed_action_from_strategy_proposal(
            _activation(),
            proposal.model_copy(update={"proposal_digest": "f" * 64}),
        )


def test_resume_is_narrow_after_writer_continuity_pause() -> None:
    paused = _activation(
        run_state=RunState.PAUSED,
        pause_reason="WRITER_CONTINUITY_LOST",
        paused_at=NOW,
    )
    resumed = resume_activation(
        paused,
        command_id="command-1",
        reconciliation_digest="a" * 64,
        observed_at=NOW,
        active_stop_categories=(StopCategory.NEW_RISK,),
        plan_current=True,
        facts_known=True,
    )
    assert resumed.run_state is RunState.ACTIVE
    with pytest.raises(ValueError, match="ALL_EXCHANGE_CHANGES_STOPPED"):
        resume_activation(
            paused,
            command_id="command-2",
            reconciliation_digest="b" * 64,
            observed_at=NOW,
            active_stop_categories=(StopCategory.ALL_EXCHANGE_CHANGES,),
            plan_current=True,
            facts_known=True,
        )


@pytest.mark.parametrize(
    ("updates", "expected_reason"),
    (
        ({"entry_opportunity_consumed": True}, "ENTRY_OPPORTUNITY_CONSUMED"),
        (
            {
                "rule_state": {
                    "deadlines": {
                        "entry_valid_until": (NOW - timedelta(seconds=1)).isoformat()
                    }
                }
            },
            "ENTRY_WINDOW_EXPIRED",
        ),
    ),
)
def test_continuity_resume_cannot_reopen_a_completed_entry_phase(
    updates: dict[str, object],
    expected_reason: str,
) -> None:
    paused = _activation(
        run_state=RunState.PAUSED,
        pause_reason="WRITER_CONTINUITY_LOST",
        paused_at=NOW,
        **updates,
    )

    with pytest.raises(ValueError, match=expected_reason):
        resume_activation(
            paused,
            command_id="command-reopen",
            reconciliation_digest="c" * 64,
            observed_at=NOW,
            active_stop_categories=(),
            plan_current=True,
            facts_known=True,
        )


def test_one_cycle_exit_takeover_and_completion_are_latched() -> None:
    consumed = consume_entry_opportunity(_activation(), observed_at=NOW)
    assert consumed.entry_opportunity_consumed is True
    assert consume_entry_opportunity(consumed, observed_at=NOW) == consumed
    exiting = enter_exit(consumed, observed_at=NOW)
    assert exiting.lifecycle is PlanLifecycle.EXITING
    takeover = enter_user_takeover(
        exiting,
        takeover_scope={"command_ref": "command-1", "cutoff": NOW.isoformat()},
        observed_at=NOW,
    )
    assert takeover.lifecycle is PlanLifecycle.USER_TAKEOVER
    with pytest.raises(ValueError, match="CLOSURE_UNPROVEN"):
        complete_activation(
            takeover, closure_digest="", result_ref="review-1", observed_at=NOW
        )
    complete = complete_activation(
        takeover,
        closure_digest="c" * 64,
        result_ref="review-1",
        observed_at=NOW,
    )
    assert complete.lifecycle is PlanLifecycle.COMPLETED
    assert complete.entry_opportunity_consumed is True


def test_runtime_condition_state_persists_semantic_changes_without_tick_churn() -> None:
    initial = RuntimeConditionState(
        result=ConditionResult.TRUE,
        item_results=(ConditionResult.TRUE,),
        phase="PRE_SUBMIT_RECHECK",
        source_cutoff=NOW,
        evaluated_at=NOW,
        facts=ConditionFacts(
            mark_price="100",
            bid_price="99.9",
            ask_price="100.1",
        ),
        submission_ready=False,
        blocking_reason="DIRECT_POST_ONLY_WOULD_TAKE",
    )
    activation = _activation()
    recorded = record_runtime_condition_state(
        activation,
        state_key="DIRECT_ENTRY",
        state=initial,
    )
    assert recorded.state_version == activation.state_version + 1
    assert (
        recorded.rule_state["condition_judgements"]["DIRECT_ENTRY"]["blocking_reason"]
        == "DIRECT_POST_ONLY_WOULD_TAKE"
    )

    unchanged = record_runtime_condition_state(
        recorded,
        state_key="DIRECT_ENTRY",
        state=initial.model_copy(
            update={
                "source_cutoff": NOW + timedelta(seconds=1),
                "evaluated_at": NOW + timedelta(seconds=1),
            }
        ),
    )
    assert unchanged is recorded

    ready = record_runtime_condition_state(
        recorded,
        state_key="DIRECT_ENTRY",
        state=initial.model_copy(
            update={
                "source_cutoff": NOW + timedelta(seconds=2),
                "evaluated_at": NOW + timedelta(seconds=2),
                "submission_ready": True,
                "blocking_reason": None,
            }
        ),
    )
    assert ready.state_version == recorded.state_version + 1
    assert (
        ready.rule_state["condition_judgements"]["DIRECT_ENTRY"]["submission_ready"]
        is True
    )
