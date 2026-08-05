from __future__ import annotations

from datetime import timedelta

from nautilus_trader.model.enums import LiquiditySide, OrderSide
import pytest

from halpha.capital.models import RiskClass
from halpha.venue_integration.facts import latest_execution_status
from halpha.venue_integration.models import (
    BINANCE_USDM_VENUE_REF,
    VenueFactAttributionClass,
    VenueFactKind,
    VenueFactSourceClass,
)
from halpha.venue_integration.nautilus_events import NautilusExecutionEventNormalizer
from halpha.venue_integration.transitions import begin_submission, mark_not_submitted
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
        filled_quantity_for_client_order_id=lambda client_order_id: "0.001",
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
        _event("OrderAccepted", quantity="0.002"),
        received_at=NOW,
    )
    assert result.action is action
    assert len(result.facts) == 1
    fact = result.facts[0]
    assert fact.venue_ref == BINANCE_USDM_VENUE_REF
    assert fact.kind is VenueFactKind.ORDER_STATE
    assert fact.source_class is VenueFactSourceClass.VENUE_STREAM
    assert fact.attribution_class is VenueFactAttributionClass.HALPHA_EXECUTION
    assert fact.payload["status"] == "WORKING"
    assert fact.payload["venue_order_quantity"] == "0.002"
    assert latest_execution_status((fact,)) == "WORKING"


def test_reconciliation_acceptance_uses_framework_order_quantity_when_event_omits_it() -> None:
    action = begin_submission(
        _action(),
        capital_decision=_cap_decision(RiskClass.RISK_INCREASING),
        request_payload={"profile": "ENTRY_MARKET"},
        observed_at=NOW,
    )
    normalizer = NautilusExecutionEventNormalizer(
        lambda _client_order_id: action,
        environment_id="demo-main",
        order_quantity_for_client_order_id=lambda _client_order_id: "0.0015",
        fact_id_factory=lambda: "10000000-0000-0000-0000-000000000017",
    )

    result = normalizer.normalize(
        _event("OrderAccepted", reconciliation=True),
        received_at=NOW,
    )

    assert result.facts[0].payload["status"] == "WORKING"
    assert result.facts[0].payload["venue_order_quantity"] == "0.0015"


def test_event_order_quantity_takes_precedence_over_cache_projection() -> None:
    action = begin_submission(
        _action(),
        capital_decision=_cap_decision(RiskClass.RISK_INCREASING),
        request_payload={"profile": "ENTRY_MARKET"},
        observed_at=NOW,
    )
    cache_reads = 0

    def cache_quantity(_client_order_id: str) -> str:
        nonlocal cache_reads
        cache_reads += 1
        return "0.0015"

    normalizer = NautilusExecutionEventNormalizer(
        lambda _client_order_id: action,
        environment_id="demo-main",
        order_quantity_for_client_order_id=cache_quantity,
        fact_id_factory=lambda: "10000000-0000-0000-0000-000000000018",
    )

    result = normalizer.normalize(
        _event("OrderUpdated", quantity="0.002"),
        received_at=NOW,
    )

    assert result.facts[0].payload["venue_order_quantity"] == "0.002"
    assert cache_reads == 0


def test_normalizer_rejects_the_legacy_framework_venue_as_product_identity() -> None:
    with pytest.raises(ValueError, match="VENUE_REF_MISMATCH"):
        NautilusExecutionEventNormalizer(
            lambda _client_order_id: None,
            environment_id="demo-main",
            venue_ref="BINANCE",
        )


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
            order_side=OrderSide.BUY,
            liquidity_side=LiquiditySide.TAKER,
        ),
        received_at=NOW,
    )
    assert tuple(fact.kind for fact in result.facts) == (
        VenueFactKind.FILL,
        VenueFactKind.COMMISSION,
    )
    assert result.facts[0].payload["leaves_quantity"] == "0.000"
    assert result.facts[0].payload["last_quantity"] == "0.001"
    assert result.facts[0].payload["order_side"] == "BUY"
    assert result.facts[0].payload["liquidity_side"] == "TAKER"
    assert result.facts[1].payload["amount"] == "0.03 USDT"
    assert latest_execution_status((result.facts[0],)) == "FILLED"

    late_working = NautilusExecutionEventNormalizer(
        lambda _client_order_id: action,
        environment_id="demo-main",
        fact_id_factory=lambda: "10000000-0000-0000-0000-000000000014",
    ).normalize(
        _event(
            "OrderUpdated",
            id=_Identifier("event-2"),
            ts_event=1_773_910_801_000_000_000,
        ),
        received_at=NOW + timedelta(seconds=1),
    )
    assert latest_execution_status((*result.facts, *late_working.facts)) == "FILLED"


def test_trade_fact_identity_is_stable_across_stream_and_reconciliation() -> None:
    action = begin_submission(
        _action(),
        capital_decision=_cap_decision(RiskClass.RISK_INCREASING),
        request_payload={"profile": "ENTRY_MARKET"},
        observed_at=NOW,
    )
    normalizer = NautilusExecutionEventNormalizer(
        lambda _client_order_id: action,
        environment_id="demo-main",
        leaves_quantity_for_client_order_id=lambda _client_order_id: "0.001",
    )
    common = {
        "trade_id": _Identifier("trade-stable-1"),
        "last_px": "50000.10",
        "last_qty": "0.0010",
        "commission": "0.030 USDT",
        "currency": _Identifier("usdt"),
        "order_side": OrderSide.BUY,
        "liquidity_side": LiquiditySide.TAKER,
    }
    stream = normalizer.normalize(
        _event(
            "OrderFilled",
            id=_Identifier("stream-event"),
            reconciliation=False,
            **common,
        ),
        received_at=NOW,
    )
    query = NautilusExecutionEventNormalizer(
        lambda _client_order_id: action,
        environment_id="demo-main",
        leaves_quantity_for_client_order_id=lambda _client_order_id: "0",
    ).normalize(
        _event(
            "OrderFilled",
            id=_Identifier("random-reconciliation-event"),
            reconciliation=True,
            **common,
        ),
        received_at=NOW + timedelta(seconds=2),
    )

    assert stream.facts[0].venue_fact_id == query.facts[0].venue_fact_id
    assert stream.facts[1].venue_fact_id == query.facts[1].venue_fact_id
    assert stream.facts[0].source_class is VenueFactSourceClass.VENUE_STREAM
    assert query.facts[0].source_class is VenueFactSourceClass.VENUE_QUERY
    assert stream.facts[0].source_sequence != query.facts[0].source_sequence

    changed_fill = normalizer.normalize(
        _event("OrderFilled", **{**common, "last_qty": "0.002"}),
        received_at=NOW,
    )
    changed_liquidity = normalizer.normalize(
        _event(
            "OrderFilled",
            **{**common, "liquidity_side": LiquiditySide.MAKER},
        ),
        received_at=NOW,
    )
    changed_time = normalizer.normalize(
        _event(
            "OrderFilled",
            ts_event=1_773_910_801_000_000_000,
            **common,
        ),
        received_at=NOW,
    )
    changed_fee = normalizer.normalize(
        _event("OrderFilled", **{**common, "commission": "-0.001 USDT"}),
        received_at=NOW,
    )
    changed_currency = normalizer.normalize(
        _event(
            "OrderFilled",
            **{
                **common,
                "commission": "0.03 BNB",
                "currency": _Identifier("BNB"),
            },
        ),
        received_at=NOW,
    )

    assert changed_fill.facts[0].venue_fact_id != stream.facts[0].venue_fact_id
    assert changed_liquidity.facts[0].venue_fact_id != stream.facts[0].venue_fact_id
    assert changed_time.facts[0].venue_fact_id != stream.facts[0].venue_fact_id
    assert changed_fee.facts[0].venue_fact_id == stream.facts[0].venue_fact_id
    assert changed_fee.facts[1].venue_fact_id != stream.facts[1].venue_fact_id
    assert changed_currency.facts[0].venue_fact_id == stream.facts[0].venue_fact_id
    assert changed_currency.facts[1].venue_fact_id != stream.facts[1].venue_fact_id


def test_restart_reconciliation_fill_keeps_terminal_original_identity() -> None:
    submitting = begin_submission(
        _action(),
        capital_decision=_cap_decision(RiskClass.RISK_INCREASING),
        request_payload={"profile": "ENTRY_MARKET"},
        observed_at=NOW,
    )
    terminal = mark_not_submitted(
        submitting,
        reason_code="VENUE_QUERY_PROVED_ABSENT",
        observed_at=NOW + timedelta(seconds=1),
    )
    restarted = NautilusExecutionEventNormalizer(
        lambda client_order_id: (
            terminal if client_order_id == terminal.client_order_id else None
        ),
        environment_id="demo-main",
        leaves_quantity_for_client_order_id=lambda _client_order_id: "0.001",
    )

    result = restarted.normalize(
        _event(
            "OrderFilled",
            reconciliation=True,
            trade_id=_Identifier("trade-late-after-restart"),
            last_px="50000",
            last_qty="0.001",
            order_side=OrderSide.BUY,
            liquidity_side=LiquiditySide.TAKER,
        ),
        received_at=NOW + timedelta(seconds=2),
    )

    assert result.action is terminal
    assert result.facts[0].source_class is VenueFactSourceClass.VENUE_QUERY
    assert result.facts[0].action_ref == terminal.execution_action_id
    assert result.facts[0].payload["client_order_id"] == terminal.client_order_id


def test_restart_order_query_placeholder_does_not_fabricate_a_trade() -> None:
    submitting = begin_submission(
        _action(),
        capital_decision=_cap_decision(RiskClass.RISK_INCREASING),
        request_payload={"profile": "ENTRY_MARKET"},
        observed_at=NOW,
    )
    result = _normalizer(submitting).normalize(
        _event(
            "OrderFilled",
            reconciliation=True,
            trade_id=_Identifier("c3dbbc0b-8835-5ed6-a7bd-a93fc9be7912"),
            last_px="50000",
            last_qty="0.001",
            commission="0 USDT",
            currency=_Identifier("USDT"),
            order_side=OrderSide.SELL,
            liquidity_side=LiquiditySide.TAKER,
        ),
        received_at=NOW + timedelta(seconds=2),
    )

    assert [fact.kind for fact in result.facts] == [VenueFactKind.ORDER_STATE]
    assert result.facts[0].payload["status"] == "FILLED"
    assert result.facts[0].payload["cumulative_filled_quantity"] == "0.001"


def test_restart_reconciliation_recovers_original_identity_by_venue_order_ref() -> None:
    submitting = begin_submission(
        _action(),
        capital_decision=_cap_decision(RiskClass.RISK_INCREASING),
        request_payload={"profile": "ENTRY_MARKET"},
        observed_at=NOW,
    )
    terminal = mark_not_submitted(
        submitting,
        reason_code="VENUE_QUERY_PROVED_ABSENT",
        observed_at=NOW + timedelta(seconds=1),
    )
    restarted = NautilusExecutionEventNormalizer(
        lambda _client_order_id: None,
        environment_id="demo-main",
        action_for_venue_order_ref=lambda venue_order_ref: (
            terminal if venue_order_ref == "12345" else None
        ),
        fact_id_factory=lambda: "10000000-0000-0000-0000-000000000018",
    )

    result = restarted.normalize(
        _event(
            "OrderAccepted",
            client_order_id=_Identifier("framework-generated-uuid"),
            reconciliation=True,
        ),
        received_at=NOW + timedelta(seconds=2),
    )

    assert result.action is terminal
    assert result.client_order_id == terminal.client_order_id
    assert result.facts[0].source_class is VenueFactSourceClass.VENUE_QUERY
    assert result.facts[0].action_ref == terminal.execution_action_id
    assert result.facts[0].payload["client_order_id"] == terminal.client_order_id


def test_commission_without_currency_is_rejected_before_persistence() -> None:
    action = begin_submission(
        _action(),
        capital_decision=_cap_decision(RiskClass.RISK_INCREASING),
        request_payload={"profile": "ENTRY_MARKET"},
        observed_at=NOW,
    )

    with pytest.raises(
        ValueError,
        match="VENUE_TRADE_COMMISSION_CURRENCY_REQUIRED",
    ):
        _normalizer(action).normalize(
            _event(
                "OrderFilled",
                trade_id=_Identifier("trade-without-currency"),
                last_px="50000",
                last_qty="0.001",
                order_side=OrderSide.BUY,
                liquidity_side=LiquiditySide.TAKER,
                commission="0.03 USDT",
                currency=None,
            ),
            received_at=NOW,
        )


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

    assert latest_execution_status((result.facts[0],)) == "PARTIALLY_FILLED"


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
    assert result.facts[0].payload["cumulative_filled_quantity"] == "0"


def test_terminal_cancel_uses_authoritative_cumulative_fill() -> None:
    action = begin_submission(
        _action(),
        capital_decision=_cap_decision(RiskClass.RISK_INCREASING),
        request_payload={"profile": "ENTRY_MARKET"},
        observed_at=NOW,
    )

    result = _normalizer(action).normalize(
        _event("OrderCanceled"),
        received_at=NOW,
    )

    assert result.facts[0].payload["status"] == "CANCELLED"
    assert result.facts[0].payload["cumulative_filled_quantity"] == "0.001"


def test_terminal_cancel_preserves_venue_quantity_drift_in_cumulative_fill() -> None:
    action = begin_submission(
        _action(),
        capital_decision=_cap_decision(RiskClass.RISK_INCREASING),
        request_payload={"profile": "ENTRY_MARKET"},
        observed_at=NOW,
    )
    normalizer = NautilusExecutionEventNormalizer(
        lambda _client_order_id: action,
        environment_id="demo-main",
        leaves_quantity_for_client_order_id=lambda _client_order_id: "0.0005",
        filled_quantity_for_client_order_id=lambda _client_order_id: "0.0015",
        fact_id_factory=lambda: "10000000-0000-0000-0000-000000000016",
    )

    result = normalizer.normalize(
        _event("OrderCanceled"),
        received_at=NOW,
    )

    assert result.facts[0].payload["status"] == "CANCELLED"
    assert result.facts[0].payload["cumulative_filled_quantity"] == "0.0015"


def test_terminal_cancel_without_filled_quantity_does_not_invent_completeness() -> None:
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
        filled_quantity_for_client_order_id=lambda _client_order_id: None,
        fact_id_factory=lambda: "10000000-0000-0000-0000-000000000015",
    )

    result = normalizer.normalize(
        _event("OrderCanceled"),
        received_at=NOW,
    )

    assert result.facts[0].payload["status"] == "CANCELLED"
    assert "cumulative_filled_quantity" not in result.facts[0].payload


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


@pytest.mark.parametrize(
    "reason",
    (
        "{'code': -1000, 'msg': 'An unknown error occured while processing the request.'}",
        "{'code': -1006, 'msg': 'An unexpected response was received from the message bus.'}",
        "",
    ),
)
def test_binance_non_authoritative_rejections_keep_submission_result_unknown(
    reason: str,
) -> None:
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

    assert result.result_unknown is True
    assert result.unknown_reason == "VENUE_SUBMISSION_RESULT_UNKNOWN"
    assert result.facts == ()


def test_binance_business_rejection_remains_terminal() -> None:
    action = begin_submission(
        _action(),
        capital_decision=_cap_decision(RiskClass.RISK_INCREASING),
        request_payload={"profile": "ENTRY_MARKET"},
        observed_at=NOW,
    )

    result = _normalizer(action).normalize(
        _event(
            "OrderRejected",
            reason="{'code': -2019, 'msg': 'Margin is insufficient.'}",
        ),
        received_at=NOW,
    )

    assert result.result_unknown is False
    assert result.unknown_reason is None
    assert result.facts[0].payload["status"] == "REJECTED"


def test_binance_disconnected_failure_is_not_mistaken_for_unknown_execution() -> None:
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
                "{'code': -1001, 'msg': 'Internal error; unable to process your "
                "request. Please try again.'}"
            ),
        ),
        received_at=NOW,
    )

    assert result.result_unknown is False
    assert result.facts[0].payload["status"] == "REJECTED"


def test_recent_query_technical_rejection_cannot_close_original_order() -> None:
    action = begin_submission(
        _action(),
        capital_decision=_cap_decision(RiskClass.RISK_INCREASING),
        request_payload={"profile": "ENTRY_MARKET"},
        observed_at=NOW,
    )
    normalizer = NautilusExecutionEventNormalizer(
        lambda _client_order_id: action,
        environment_id="demo-main",
        query_was_recently_dispatched=lambda _client_order_id: True,
    )

    result = normalizer.normalize(
        _event(
            "OrderRejected",
            reason="{'code': -1003, 'msg': 'Too many requests.'}",
        ),
        received_at=NOW,
    )

    assert result.result_unknown is True
    assert result.facts == ()
    assert result.retry_after_seconds == 60.0


def test_absurd_ban_timestamp_is_bounded_to_the_documented_maximum() -> None:
    action = begin_submission(
        _action(),
        capital_decision=_cap_decision(RiskClass.RISK_INCREASING),
        request_payload={"profile": "ENTRY_MARKET"},
        observed_at=NOW,
    )
    normalizer = NautilusExecutionEventNormalizer(
        lambda _client_order_id: action,
        environment_id="demo-main",
        query_was_recently_dispatched=lambda _client_order_id: True,
    )
    far_future_ms = int((NOW + timedelta(days=3650)).timestamp() * 1000)

    result = normalizer.normalize(
        _event(
            "OrderRejected",
            reason=f"HTTP 418 IP banned until {far_future_ms}",
        ),
        received_at=NOW,
    )

    assert result.result_unknown is True
    assert result.retry_after_seconds == 3 * 24 * 60 * 60


def test_recent_query_marker_does_not_hide_a_business_rejection() -> None:
    action = begin_submission(
        _action(),
        capital_decision=_cap_decision(RiskClass.RISK_INCREASING),
        request_payload={"profile": "ENTRY_MARKET"},
        observed_at=NOW,
    )
    normalizer = NautilusExecutionEventNormalizer(
        lambda _client_order_id: action,
        environment_id="demo-main",
        query_was_recently_dispatched=lambda _client_order_id: True,
        fact_id_factory=lambda: "10000000-0000-0000-0000-000000000099",
    )

    result = normalizer.normalize(
        _event(
            "OrderRejected",
            reason="{'code': -2019, 'msg': 'Margin is insufficient.'}",
        ),
        received_at=NOW,
    )

    assert result.result_unknown is False
    assert result.facts[0].payload["status"] == "REJECTED"


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


@pytest.mark.parametrize(
    ("reason", "reconciliation"),
    (
        ("ORDER_NOT_FOUND_AT_VENUE", True),
        ("{'code': -2013, 'msg': 'Order does not exist.'}", False),
    ),
)
def test_single_not_found_result_does_not_become_terminal_rejection(
    reason: str,
    reconciliation: bool,
) -> None:
    action = begin_submission(
        _action(),
        capital_decision=_cap_decision(RiskClass.RISK_INCREASING),
        request_payload={"profile": "ENTRY_MARKET"},
        observed_at=NOW,
    )

    result = _normalizer(action).normalize(
        _event(
            "OrderRejected",
            reason=reason,
            reconciliation=reconciliation,
        ),
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
