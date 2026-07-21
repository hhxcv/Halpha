from datetime import UTC, datetime

from halpha.outcomes.trade_result import summarize_trade_result


def _fact(
    kind: str,
    trade_id: str,
    action_ref: str,
    *,
    source_time: object | None = None,
    cutoff: object | None = None,
    **payload: str,
):
    return {
        "kind": kind,
        "action_ref": action_ref,
        "source_time": source_time,
        "cutoff": cutoff,
        "payload": {"trade_id": trade_id, **payload},
    }


def test_closed_long_result_uses_attributed_fills_and_actual_commissions() -> None:
    result = summarize_trade_result(
        direction="LONG",
        action_kinds={"entry": "ENTRY", "exit": "EXIT"},
        facts=(
            _fact(
                "FILL",
                "trade-1",
                "entry",
                source_time=datetime(2026, 7, 20, tzinfo=UTC),
                last_price="64704.60",
                last_quantity="0.0015",
                order_side="BUY",
                liquidity_side="TAKER",
            ),
            _fact(
                "COMMISSION",
                "trade-1",
                "entry",
                amount="0.03882276 USDT",
                currency="USDT",
            ),
            _fact(
                "FILL",
                "trade-2",
                "exit",
                source_time="2026-07-20T00:05:30+00:00",
                last_price="64699.50",
                last_quantity="0.0015",
                order_side="SELL",
                liquidity_side="MAKER",
            ),
            _fact(
                "COMMISSION",
                "trade-2",
                "exit",
                amount="0.03881970 USDT",
                currency="USDT",
            ),
        ),
    )

    assert result["position_quantity"] == "0"
    assert result["average_entry_price"] == "64704.6"
    assert result["average_exit_price"] == "64699.5"
    assert result["entry_notional"] == "97.0569"
    assert result["gross_pnl"] == "-0.00765"
    assert result["commission"] == "0.07764246"
    assert result["net_pnl"] == "-0.08529246"
    assert result["calculation_complete"] is True
    assert result["funding_included"] is False
    assert result["fills"] == [
        {
            "trade_id": "trade-1",
            "action_kind": "ENTRY",
            "price": "64704.6",
            "quantity": "0.0015",
            "notional": "97.0569",
            "order_side": "BUY",
            "liquidity_side": "TAKER",
            "fee": "0.03882276",
            "fee_currency": "USDT",
            "fill_time": "2026-07-20T00:00:00+00:00",
        },
        {
            "trade_id": "trade-2",
            "action_kind": "EXIT",
            "price": "64699.5",
            "quantity": "0.0015",
            "notional": "97.04925",
            "order_side": "SELL",
            "liquidity_side": "MAKER",
            "fee": "0.0388197",
            "fee_currency": "USDT",
            "fill_time": "2026-07-20T00:05:30+00:00",
        },
    ]
    assert result["fill_times_complete"] is True
    assert result["first_fill_time"] == "2026-07-20T00:00:00+00:00"
    assert result["last_fill_time"] == "2026-07-20T00:05:30+00:00"
    assert result["holding_duration_seconds"] == "330"


def test_open_short_result_exposes_cash_flow_for_current_mark_estimate() -> None:
    result = summarize_trade_result(
        direction="SHORT",
        action_kinds={"entry": "ENTRY"},
        facts=(
            _fact(
                "FILL",
                "trade-1",
                "entry",
                last_price="100",
                last_quantity="2",
            ),
            _fact(
                "COMMISSION",
                "trade-1",
                "entry",
                amount="0.1 USDT",
                currency="USDT",
            ),
        ),
    )

    assert result["position_quantity"] == "-2"
    assert result["fill_cash_flow"] == "200"
    assert result["average_entry_price"] == "100"
    assert result["net_pnl"] is None
    assert result["calculation_complete"] is True


def test_missing_commission_keeps_pnl_unknown() -> None:
    result = summarize_trade_result(
        direction="LONG",
        action_kinds={"entry": "ENTRY", "exit": "EXIT"},
        facts=(
            _fact(
                "FILL",
                "trade-1",
                "entry",
                last_price="100",
                last_quantity="1",
            ),
            _fact(
                "FILL",
                "trade-2",
                "exit",
                last_price="101",
                last_quantity="1",
            ),
        ),
    )

    assert result["closed"] is True
    assert result["commission_complete"] is False
    assert result["net_pnl"] is None
    assert result["fills"][0]["fee"] is None
    assert result["fills"][0]["fee_currency"] is None


def test_incomplete_source_times_keep_trade_timing_unknown() -> None:
    result = summarize_trade_result(
        direction="LONG",
        action_kinds={"entry": "ENTRY", "exit": "EXIT"},
        facts=(
            _fact(
                "FILL",
                "trade-1",
                "entry",
                source_time="2026-07-20T00:00:00+00:00",
                last_price="100",
                last_quantity="1",
            ),
            _fact(
                "COMMISSION",
                "trade-1",
                "entry",
                amount="0.1 USDT",
                currency="USDT",
            ),
            _fact(
                "FILL",
                "trade-2",
                "exit",
                cutoff="2026-07-20T00:05:30+00:00",
                last_price="101",
                last_quantity="1",
            ),
            _fact(
                "COMMISSION",
                "trade-2",
                "exit",
                amount="0.1 USDT",
                currency="USDT",
            ),
        ),
    )

    assert result["fills"][0]["fill_time"] == "2026-07-20T00:00:00+00:00"
    assert result["fills"][1]["fill_time"] is None
    assert result["fill_times_complete"] is False
    assert result["first_fill_time"] is None
    assert result["last_fill_time"] is None
    assert result["holding_duration_seconds"] is None


def test_conflicting_commissions_do_not_choose_a_fee_value() -> None:
    result = summarize_trade_result(
        direction="LONG",
        action_kinds={"entry": "ENTRY"},
        facts=(
            _fact(
                "FILL",
                "trade-1",
                "entry",
                last_price="100",
                last_quantity="1",
            ),
            _fact(
                "COMMISSION",
                "trade-1",
                "entry",
                amount="0.1 USDT",
                currency="USDT",
            ),
            _fact(
                "COMMISSION",
                "trade-1",
                "entry",
                amount="0.2 USDT",
                currency="USDT",
            ),
        ),
    )

    assert result["commission_complete"] is False
    assert result["calculation_complete"] is False
    assert result["fills"][0]["fee"] is None
    assert result["fills"][0]["fee_currency"] is None


def test_commission_without_a_matching_fill_keeps_result_incomplete() -> None:
    result = summarize_trade_result(
        direction="LONG",
        action_kinds={"entry": "ENTRY"},
        facts=(
            _fact(
                "FILL",
                "trade-1",
                "entry",
                last_price="100",
                last_quantity="1",
            ),
            _fact(
                "COMMISSION",
                "trade-1",
                "entry",
                amount="0.1 USDT",
                currency="USDT",
            ),
            _fact(
                "COMMISSION",
                "trade-without-fill",
                "entry",
                amount="0.2 USDT",
                currency="USDT",
            ),
        ),
    )

    assert result["commission_complete"] is False
    assert result["calculation_complete"] is False
    assert result["net_pnl"] is None
