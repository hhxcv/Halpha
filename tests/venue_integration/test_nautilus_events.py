from __future__ import annotations

from halpha.capital.models import RiskClass
from halpha.venue_integration.models import (
    VenueFactAttributionClass,
    VenueFactKind,
    VenueFactSourceClass,
)
from halpha.venue_integration.nautilus_events import NautilusExecutionEventNormalizer
from halpha.venue_integration.service import _state_from_fact
from halpha.venue_integration.transitions import begin_submission
from tests.venue_integration.test_execution_action import NOW, _action, _cap_decision


class _Identifier:
    def __init__(self, value: str) -> None:
        self.value = value

    def __str__(self) -> str:
        return self.value


def _event(name: str, **updates: object) -> object:
    values = {
        "client_order_id": _Identifier("0123456789abcdef0123456789abcdef"),
        "venue_order_id": _Identifier("12345"),
        "account_id": _Identifier("BINANCE-DEMO-ACCOUNT"),
        "instrument_id": _Identifier("BTCUSDT-PERP.BINANCE"),
        "id": _Identifier("event-1"),
        "ts_event": 1_773_910_800_000_000_000,
        "reconciliation": False,
    }
    values.update(updates)
    return type(name, (), values)()


def _normalizer(action):
    return NautilusExecutionEventNormalizer(
        lambda client_order_id: (
            action if client_order_id == action.client_order_id else None
        ),
        environment_id="demo-main",
        leaves_quantity_for_client_order_id=lambda client_order_id: "0.000",
        fact_id_factory=iter(
            (
                "10000000-0000-0000-0000-000000000010",
                "10000000-0000-0000-0000-000000000011",
            )
        ).__next__,
    )


def test_order_accepted_maps_to_attributed_working_order_fact() -> None:
    action = begin_submission(
        _action(),
        capital_decision=_cap_decision(RiskClass.RISK_INCREASING),
        request_payload={"profile": "ENTRY_MARKET"},
        observed_at=NOW,
    )
    result = _normalizer(action).normalize(
        _event("OrderAccepted"),
        received_at=NOW,
    )
    assert result.action is action
    assert len(result.facts) == 1
    fact = result.facts[0]
    assert fact.kind is VenueFactKind.ORDER_STATE
    assert fact.source_class is VenueFactSourceClass.VENUE_STREAM
    assert fact.attribution_class is VenueFactAttributionClass.HALPHA_EXECUTION
    assert fact.payload["status"] == "WORKING"
    assert _state_from_fact(fact).value == "WORKING"


def test_fill_maps_trade_and_actual_commission_without_synthesizing_terminal_state() -> None:
    action = begin_submission(
        _action(),
        capital_decision=_cap_decision(RiskClass.RISK_INCREASING),
        request_payload={"profile": "ENTRY_MARKET"},
        observed_at=NOW,
    )
    result = _normalizer(action).normalize(
        _event(
            "OrderFilled",
            trade_id=_Identifier("trade-1"),
            last_px="50000.1",
            last_qty="0.001",
            commission="0.03 USDT",
            currency=_Identifier("USDT"),
            order_side="BUY",
            liquidity_side="TAKER",
        ),
        received_at=NOW,
    )
    assert tuple(fact.kind for fact in result.facts) == (
        VenueFactKind.FILL,
        VenueFactKind.COMMISSION,
    )
    assert result.facts[0].payload["leaves_quantity"] == "0.000"
    assert result.facts[0].payload["last_quantity"] == "0.001"
    assert result.facts[1].payload["amount"] == "0.03 USDT"
    assert _state_from_fact(result.facts[0]).value == "FILLED"


def test_fill_with_missing_or_invalid_leaves_quantity_stays_partial() -> None:
    action = begin_submission(
        _action(),
        capital_decision=_cap_decision(RiskClass.RISK_INCREASING),
        request_payload={"profile": "ENTRY_MARKET"},
        observed_at=NOW,
    )
    normalizer = NautilusExecutionEventNormalizer(
        lambda _client_order_id: action,
        environment_id="demo-main",
        leaves_quantity_for_client_order_id=lambda _client_order_id: None,
        fact_id_factory=lambda: "10000000-0000-0000-0000-000000000013",
    )
    result = normalizer.normalize(
        _event(
            "OrderFilled",
            trade_id=_Identifier("trade-unknown-leaves"),
            last_px="50000.1",
            last_qty="0.001",
        ),
        received_at=NOW,
    )

    assert _state_from_fact(result.facts[0]).value == "PARTIALLY_FILLED"


def test_unknown_client_identity_stays_external_unclaimed() -> None:
    normalizer = NautilusExecutionEventNormalizer(
        lambda client_order_id: None,
        environment_id="demo-main",
        fact_id_factory=lambda: "10000000-0000-0000-0000-000000000012",
    )
    result = normalizer.normalize(_event("OrderAccepted"), received_at=NOW)
    assert result.action is None
    assert result.facts[0].source_class is VenueFactSourceClass.EXTERNAL_UNCLAIMED
    assert result.facts[0].attribution_class is None
    assert result.facts[0].action_ref is None


def test_framework_denied_is_definitely_not_submitted_and_creates_no_venue_fact() -> None:
    action = begin_submission(
        _action(),
        capital_decision=_cap_decision(RiskClass.RISK_INCREASING),
        request_payload={"profile": "ENTRY_MARKET"},
        observed_at=NOW,
    )
    result = _normalizer(action).normalize(_event("OrderDenied"), received_at=NOW)
    assert result.definitely_not_submitted is True
    assert result.facts == ()


def test_deterministic_order_rejection_remains_a_terminal_venue_fact() -> None:
    action = begin_submission(
        _action(),
        capital_decision=_cap_decision(RiskClass.RISK_INCREASING),
        request_payload={"profile": "ENTRY_MARKET"},
        observed_at=NOW,
    )

    result = _normalizer(action).normalize(
        _event("OrderRejected", reason="MIN_NOTIONAL"),
        received_at=NOW,
    )

    assert result.result_unknown is False
    assert result.unknown_reason is None
    assert result.facts[0].payload["status"] == "REJECTED"
    assert result.facts[0].payload["reason"] == "MIN_NOTIONAL"


def test_binance_timeout_rejection_keeps_submission_result_unknown() -> None:
    action = begin_submission(
        _action(),
        capital_decision=_cap_decision(RiskClass.RISK_INCREASING),
        request_payload={"profile": "ENTRY_MARKET"},
        observed_at=NOW,
    )

    result = _normalizer(action).normalize(
        _event(
            "OrderRejected",
            reason=(
                "{'code': -1007, 'msg': 'Timeout waiting for response from backend "
                "server. Send status unknown; execution status unknown.'}"
            ),
        ),
        received_at=NOW,
    )

    assert result.result_unknown is True
    assert result.unknown_reason == "VENUE_SUBMISSION_RESULT_UNKNOWN"
    assert result.facts == ()


def test_nautilus_inflight_resolution_does_not_become_a_terminal_rejection() -> None:
    action = begin_submission(
        _action(),
        capital_decision=_cap_decision(RiskClass.RISK_INCREASING),
        request_payload={"profile": "ENTRY_MARKET"},
        observed_at=NOW,
    )

    result = _normalizer(action).normalize(
        _event("OrderRejected", reason="UNKNOWN", reconciliation=True),
        received_at=NOW,
    )

    assert result.result_unknown is True
    assert result.unknown_reason == "VENUE_SUBMISSION_RESULT_UNKNOWN"
    assert result.facts == ()


def test_ambiguous_server_and_transport_rejections_keep_submission_result_unknown() -> None:
    reasons = (
        "Non-JSON response (HTTP 200): <html><title>502 Bad Gateway</title></html>",
        "HTTP 408 Request Timeout",
        "HTTP/1.1 503 Service Unavailable",
        "Connection reset by peer",
    )

    for reason in reasons:
        action = begin_submission(
            _action(),
            capital_decision=_cap_decision(RiskClass.RISK_INCREASING),
            request_payload={"profile": "ENTRY_MARKET"},
            observed_at=NOW,
        )
        result = _normalizer(action).normalize(
            _event("OrderRejected", reason=reason),
            received_at=NOW,
        )

        assert result.result_unknown is True, reason
        assert result.unknown_reason == "VENUE_SUBMISSION_RESULT_UNKNOWN", reason
        assert result.facts == (), reason


def test_binance_error_code_5022_is_not_mistaken_for_http_502() -> None:
    action = begin_submission(
        _action(),
        capital_decision=_cap_decision(RiskClass.RISK_INCREASING),
        request_payload={"profile": "ENTRY_MARKET"},
        observed_at=NOW,
    )
    result = _normalizer(action).normalize(
        _event(
            "OrderRejected",
            reason=(
                "{'code': -5022, 'msg': 'Due to the order could not be executed as maker, "
                "the Post Only order will be rejected.'}"
            ),
        ),
        received_at=NOW,
    )

    assert result.result_unknown is False
    assert result.unknown_reason is None
    assert result.facts[0].payload["status"] == "REJECTED"
