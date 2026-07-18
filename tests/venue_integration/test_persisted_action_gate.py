from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import pytest

from halpha.venue_integration.gateway import PersistedActionGate, VenueCallReceipt
from tests.venue_integration.test_execution_action import (
    NOW,
    _action,
    _cap_decision,
)
from halpha.capital.models import RiskClass
from halpha.venue_integration.transitions import begin_submission


@dataclass
class _MemoryRepository:
    action: object

    def get(self, execution_action_id: str):
        assert execution_action_id == self.action.execution_action_id
        return self.action


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
