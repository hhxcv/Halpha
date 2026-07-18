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
from halpha.planning.transitions import (
    EventConflict,
    bar_source_identity,
    callback_allowed,
    complete_activation,
    consume_entry_opportunity,
    deadline_source_identity,
    enter_exit,
    enter_user_takeover,
    mark_writer_continuity_lost,
    proposed_action_from_strategy_proposal,
    resolve_existing_event,
    resume_activation,
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
        "authorization_version_ref": "authorization-1",
        "allocation_ref": "allocation-1",
        "account_ref": "account-1",
        "instrument_ref": "BTCUSDT-PERP",
        "direction": "LONG",
        "strategy_id": "ONE_SHOT_DONCHIAN_ATR_BREAKOUT",
        "framework_strategy_id": "HALPHA-TEST",
        "target_exposure": "0.1",
        "rule_state": {},
        "protection_state": ProtectionState.NONE,
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(updates)
    return PlanActivation(**values)


def test_bar_identity_is_stable_and_digest_conflict_is_not_a_second_event() -> None:
    identity = bar_source_identity(
        activation_id="activation-1",
        rule_id="ENTRY",
        bar_type="BTCUSDT-PERP-1-MINUTE-LAST-EXTERNAL",
        ts_event_ns=123,
    )
    assert identity == bar_source_identity(
        activation_id="activation-1",
        rule_id="ENTRY",
        bar_type="BTCUSDT-PERP-1-MINUTE-LAST-EXTERNAL",
        ts_event_ns=123,
    )
    assert resolve_existing_event(None, source_identity=identity, input_digest="a" * 64) is None
    fake = object.__new__(type("Event", (), {}))
    fake.source_identity = identity
    fake.input_digest = "a" * 64
    assert resolve_existing_event(fake, source_identity=identity, input_digest="a" * 64) is fake
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
        "source_identity": bar_source_identity(
            activation_id="activation-1",
            rule_id="ENTRY_BREAKOUT",
            bar_type="BTCUSDT-PERP.BINANCE-15-MINUTE-LAST-INTERNAL",
            ts_event_ns=123,
        ),
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


def test_writer_continuity_loss_pauses_before_callback_and_resume_is_narrow() -> None:
    paused = mark_writer_continuity_lost(_activation(), observed_at=NOW)
    assert paused.run_state is RunState.PAUSED
    assert paused.pause_reason == "WRITER_CONTINUITY_LOST"
    assert callback_allowed(paused) is False
    resumed = resume_activation(
        paused,
        command_id="command-1",
        reconciliation_digest="a" * 64,
        observed_at=NOW,
        active_stop_categories=(StopCategory.NEW_FUNDING,),
        authorization_current=True,
        facts_known=True,
    )
    assert resumed.run_state is RunState.ACTIVE
    assert callback_allowed(resumed) is True
    with pytest.raises(ValueError, match="ALL_WRITES_STOPPED"):
        resume_activation(
            paused,
            command_id="command-2",
            reconciliation_digest="b" * 64,
            observed_at=NOW,
            active_stop_categories=(StopCategory.ALL_WRITES,),
            authorization_current=True,
            facts_known=True,
        )


def test_app_or_notification_restart_does_not_call_continuity_transition() -> None:
    continuously_running = _activation()
    assert continuously_running.run_state is RunState.ACTIVE
    assert callback_allowed(continuously_running) is True


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
    assert callback_allowed(takeover) is False
    with pytest.raises(ValueError, match="CLOSURE_UNPROVEN"):
        complete_activation(takeover, closure_digest="", result_ref="review-1", observed_at=NOW)
    complete = complete_activation(
        takeover,
        closure_digest="c" * 64,
        result_ref="review-1",
        observed_at=NOW,
    )
    assert complete.lifecycle is PlanLifecycle.COMPLETED
    assert complete.entry_opportunity_consumed is True
