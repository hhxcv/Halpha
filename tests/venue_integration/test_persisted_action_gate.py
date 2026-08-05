from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import pytest

from halpha.venue_integration.gateway import PersistedActionGate, VenueCallReceipt
from halpha.domain_values import content_digest
from halpha.venue_integration.models import execution_action_state_digest
from tests.venue_integration.test_execution_action import (
    NOW,
    _action,
    _cap_decision,
    _proposed,
)
from halpha.capital.models import RiskClass
from halpha.planning.models import ProposedActionKind
from halpha.venue_integration.transitions import begin_submission


@dataclass
class _MemoryRepository:
    action: object
    target: object | None = None

    def get(self, execution_action_id: str):
        assert execution_action_id == self.action.execution_action_id
        return self.action

    def find_order_action_by_client_id(self, client_order_id: str):
        if (
            self.target is not None
            and self.target.client_order_id == client_order_id
        ):
            return self.target
        return None


class _Client:
    def __init__(self) -> None:
        self.submit_calls = 0

    def submit_order(self, action):
        self.submit_calls += 1
        return VenueCallReceipt(
            source_object_id=action.client_order_id,
            source_sequence="1",
            source_time=datetime.now(UTC),
            status="ACKNOWLEDGED",
            payload={"status": "ACKNOWLEDGED"},
        )

    def cancel_order(self, action):
        raise AssertionError("unexpected cancel")

    def query_order(self, action):
        raise AssertionError("unexpected query")


def test_gate_requires_committed_submitting_identity_and_consumes_permit_once() -> None:
    submitting = begin_submission(
        _action(),
        capital_decision=_cap_decision(RiskClass.RISK_INCREASING),
        request_payload={"order_type": "MARKET"},
        observed_at=NOW,
    )
    repository = _MemoryRepository(submitting)
    client = _Client()
    gate = PersistedActionGate(
        repository,
        client,
        environment_id="demo-main",
        execution_profile_ref="BINANCE_DEMO",
        account_ref="demo-owner",
    )
    permit = gate.authorize_committed_submission(
        submitting.execution_action_id,
        expected_state_digest=submitting.state_digest,
    )
    receipt = gate.execute_once(permit)
    assert receipt.status == "ACKNOWLEDGED"
    assert client.submit_calls == 1
    with pytest.raises(RuntimeError, match="SUBMISSION_RESULT_UNKNOWN"):
        gate.execute_once(permit)
    assert client.submit_calls == 1


def test_new_gate_after_restart_has_no_permit_for_existing_submitting_action() -> None:
    submitting = begin_submission(
        _action(),
        capital_decision=_cap_decision(RiskClass.RISK_INCREASING),
        request_payload={"order_type": "MARKET"},
        observed_at=NOW,
    )
    repository = _MemoryRepository(submitting)
    client = _Client()
    old_gate = PersistedActionGate(
        repository,
        client,
        environment_id="demo-main",
        execution_profile_ref="BINANCE_DEMO",
        account_ref="demo-owner",
    )
    permit = old_gate.authorize_committed_submission(
        submitting.execution_action_id,
        expected_state_digest=submitting.state_digest,
    )
    restarted_gate = PersistedActionGate(
        repository,
        client,
        environment_id="demo-main",
        execution_profile_ref="BINANCE_DEMO",
        account_ref="demo-owner",
    )
    with pytest.raises(RuntimeError, match="SUBMISSION_RESULT_UNKNOWN"):
        restarted_gate.execute_once(permit)
    assert client.submit_calls == 0


@pytest.mark.parametrize(
    "malformation",
    ("risk_class", "reduce_only_type", "infinite_quantity"),
)
def test_gate_rejects_malformed_persisted_economics_before_venue_call(
    malformation: str,
) -> None:
    submitting = begin_submission(
        _action(),
        capital_decision=_cap_decision(RiskClass.RISK_INCREASING),
        request_payload={"order_type": "MARKET"},
        observed_at=NOW,
    )
    if malformation == "risk_class":
        malformed = submitting.model_copy(
            update={"action_class": RiskClass.RISK_REDUCING}
        )
    elif malformation == "reduce_only_type":
        terms = {**submitting.action_terms, "reduce_only": "false"}
        malformed = submitting.model_copy(
            update={
                "action_terms": terms,
                "action_terms_digest": content_digest(terms),
            }
        )
    else:
        terms = {**submitting.action_terms, "quantity": "Infinity"}
        malformed = submitting.model_copy(
            update={
                "action_terms": terms,
                "action_terms_digest": content_digest(terms),
            }
        )
    malformed = malformed.model_copy(
        update={"state_digest": execution_action_state_digest(malformed)}
    )
    repository = _MemoryRepository(malformed)
    client = _Client()
    gate = PersistedActionGate(
        repository,
        client,
        environment_id="demo-main",
        execution_profile_ref="BINANCE_DEMO",
        account_ref="demo-owner",
    )

    with pytest.raises(ValueError, match="ACTION_PROFILE_MISMATCH"):
        gate.authorize_committed_submission(
            malformed.execution_action_id,
            expected_state_digest=malformed.state_digest,
        )
    assert client.submit_calls == 0


def test_gate_rejects_reduce_market_when_reduce_only_is_false() -> None:
    action = _action(
        _proposed(
            kind=ProposedActionKind.EXIT,
            profile="REDUCE_OR_CLOSE_MARKET",
            reduce_only=True,
        )
    )
    submitting = begin_submission(
        action,
        capital_decision=_cap_decision(RiskClass.RISK_REDUCING),
        request_payload={"order_type": "MARKET"},
        observed_at=NOW,
    )
    terms = {**submitting.action_terms, "reduce_only": False}
    malformed = submitting.model_copy(
        update={
            "action_terms": terms,
            "action_terms_digest": content_digest(terms),
        }
    )
    malformed = malformed.model_copy(
        update={"state_digest": execution_action_state_digest(malformed)}
    )
    repository = _MemoryRepository(malformed)
    client = _Client()
    gate = PersistedActionGate(
        repository,
        client,
        environment_id="demo-main",
        execution_profile_ref="BINANCE_DEMO",
        account_ref="demo-owner",
    )

    with pytest.raises(ValueError, match="ACTION_PROFILE_MISMATCH"):
        gate.authorize_committed_submission(
            malformed.execution_action_id,
            expected_state_digest=malformed.state_digest,
        )
    assert client.submit_calls == 0


def test_gate_rejects_exit_without_structured_responsibility_role() -> None:
    action = _action(
        _proposed(
            kind=ProposedActionKind.EXIT,
            profile="REDUCE_OR_CLOSE_MARKET",
            reduce_only=True,
        )
    )
    submitting = begin_submission(
        action,
        capital_decision=_cap_decision(RiskClass.RISK_REDUCING),
        request_payload={"order_type": "MARKET"},
        observed_at=NOW,
    )
    terms = dict(submitting.action_terms)
    terms.pop("exit_responsibility_role")
    malformed = submitting.model_copy(
        update={
            "action_terms": terms,
            "action_terms_digest": content_digest(terms),
        }
    )
    malformed = malformed.model_copy(
        update={"state_digest": execution_action_state_digest(malformed)}
    )
    repository = _MemoryRepository(malformed)
    client = _Client()
    gate = PersistedActionGate(
        repository,
        client,
        environment_id="demo-main",
        execution_profile_ref="BINANCE_DEMO",
        account_ref="demo-owner",
    )

    with pytest.raises(ValueError, match="EXIT_RESPONSIBILITY_ROLE_INVALID"):
        gate.authorize_committed_submission(
            malformed.execution_action_id,
            expected_state_digest=malformed.state_digest,
        )
    assert client.submit_calls == 0


def test_cancel_gate_requires_the_exact_same_activation_target() -> None:
    target = begin_submission(
        _action(),
        capital_decision=_cap_decision(RiskClass.RISK_INCREASING),
        request_payload={"order_type": "MARKET"},
        observed_at=NOW,
    )
    cancel = begin_submission(
        _action(
            _proposed(
                kind=ProposedActionKind.CANCEL,
                profile="CANCEL_ORDER",
                order_type="CANCEL",
                quantity=None,
                cancel_target={
                    "client_order_id": target.client_order_id,
                    "endpoint": "ORDINARY",
                },
            )
        ),
        capital_decision=_cap_decision(RiskClass.RISK_NEUTRAL),
        request_payload={"order_type": "CANCEL"},
        observed_at=NOW,
    )
    client = _Client()
    repository = _MemoryRepository(cancel, target)
    gate = PersistedActionGate(
        repository,
        client,
        environment_id="demo-main",
        execution_profile_ref="BINANCE_DEMO",
        account_ref="demo-owner",
    )

    permit = gate.authorize_committed_submission(
        cancel.execution_action_id,
        expected_state_digest=cancel.state_digest,
    )
    assert permit.action_id == cancel.execution_action_id

    cross_activation_target = target.model_copy(
        update={"activation_id": "different-activation"}
    )
    repository.target = cross_activation_target
    with pytest.raises(RuntimeError, match="AUTHORIZATION_MISMATCH"):
        gate.execute_once(permit)

    mismatched_gate = PersistedActionGate(
        _MemoryRepository(cancel, cross_activation_target),
        client,
        environment_id="demo-main",
        execution_profile_ref="BINANCE_DEMO",
        account_ref="demo-owner",
    )
    with pytest.raises(RuntimeError, match="AUTHORIZATION_MISMATCH"):
        mismatched_gate.authorize_committed_submission(
            cancel.execution_action_id,
            expected_state_digest=cancel.state_digest,
        )
