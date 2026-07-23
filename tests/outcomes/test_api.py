from __future__ import annotations

from datetime import UTC, datetime
import psycopg
import pytest
from pydantic import SecretStr

from halpha.app.outcomes_api import OutcomesApiUnavailable, PostgreSQLOutcomesApi


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _Connection:
    def __init__(
        self,
        *,
        omit_exit_fact: bool = False,
        exit_fact_digest: str = "exit-fill-digest",
        decision_basis_ref: str = "ONE_SHOT_DONCHIAN_ATR_BREAKOUT",
    ) -> None:
        self._omit_exit_fact = omit_exit_fact
        self._exit_fact_digest = exit_fact_digest
        self._decision_basis_ref = decision_basis_ref

    def execute(self, query, parameters):
        if "FROM halpha.venue_fact" in query:
            assert parameters == (
                "demo-main",
                ["activation-1"],
                ["activation-1"],
            )
        else:
            assert parameters == ("demo-main", ["activation-1"])
        if "trade_plan_version" in query:
            return _Rows(
                [
                    (
                        "activation-1",
                        "BTCUSDT-PERP",
                        "LONG",
                        self._decision_basis_ref,
                        "300",
                        datetime(2026, 7, 20, 1, tzinfo=UTC),
                        datetime(2026, 7, 20, 2, tzinfo=UTC),
                        "AI BTC breakout",
                        "2026-07-20T00:30:00+00:00",
                        "AI",
                    )
                ]
            )
        if "FROM halpha.execution_action" in query:
            return _Rows(
                [
                    (
                        "activation-1",
                        "entry-action",
                        "ENTRY",
                    ),
                    (
                        "activation-1",
                        "exit-action",
                        "EXIT",
                    ),
                ]
            )
        assert "FROM halpha.venue_fact" in query
        rows = [
            (
                "activation-1",
                "entry-fill",
                1,
                "FILL",
                "entry-fill-digest",
                {
                    "trade_id": "trade-1",
                    "last_price": "100",
                    "last_quantity": "1",
                },
                "entry-action",
                datetime(2026, 7, 20, 1, tzinfo=UTC),
                None,
                "HALPHA_EXECUTION",
            ),
            (
                "activation-1",
                "entry-fee",
                1,
                "COMMISSION",
                "entry-fee-digest",
                {"trade_id": "trade-1", "amount": "0.1", "currency": "USDT"},
                "entry-action",
                datetime(2026, 7, 20, 1, tzinfo=UTC),
                None,
                "HALPHA_EXECUTION",
            ),
            (
                "activation-1",
                "exit-fill",
                1,
                "FILL",
                self._exit_fact_digest,
                {
                    "trade_id": "trade-2",
                    "last_price": "101",
                    "last_quantity": "1",
                },
                "exit-action",
                datetime(2026, 7, 20, 1, 5, tzinfo=UTC),
                None,
                "HALPHA_EXECUTION",
            ),
            (
                "activation-1",
                "exit-fee",
                1,
                "COMMISSION",
                "exit-fee-digest",
                {"trade_id": "trade-2", "amount": "0.1", "currency": "USDT"},
                "exit-action",
                datetime(2026, 7, 20, 1, 5, tzinfo=UTC),
                None,
                "HALPHA_EXECUTION",
            ),
        ]
        return _Rows(
            [row for row in rows if not self._omit_exit_fact or row[1] != "exit-fill"]
        )


def _review() -> dict[str, object]:
    return {
        "review_id": "review-1",
        "activation_id": "activation-1",
        "input_refs": {
            "execution_actions": [
                {
                    "execution_action_id": "entry-action",
                    "state_version": 2,
                    "state_digest": "entry-action-digest",
                },
                {
                    "execution_action_id": "exit-action",
                    "state_version": 3,
                    "state_digest": "exit-action-digest",
                },
            ],
            "venue_facts": [
                {
                    "venue_fact_id": "entry-fill",
                    "schema_version": 1,
                    "kind": "FILL",
                    "content_digest": "entry-fill-digest",
                },
                {
                    "venue_fact_id": "entry-fee",
                    "schema_version": 1,
                    "kind": "COMMISSION",
                    "content_digest": "entry-fee-digest",
                },
                {
                    "venue_fact_id": "exit-fill",
                    "schema_version": 1,
                    "kind": "FILL",
                    "content_digest": "exit-fill-digest",
                },
                {
                    "venue_fact_id": "exit-fee",
                    "schema_version": 1,
                    "kind": "COMMISSION",
                    "content_digest": "exit-fee-digest",
                },
            ],
        },
        "account_result": {
            "trade_result": {
                "average_exit_price": None,
                "net_pnl": "999",
            }
        },
    }


def test_outcomes_database_failure_is_sanitized(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_connect(**kwargs):
        raise psycopg.OperationalError("secret-database-detail")

    monkeypatch.setattr(psycopg, "connect", fail_connect)
    api = PostgreSQLOutcomesApi(
        database_name="halpha_demo",
        password=SecretStr("secret-password"),
        environment_id="demo-main",
    )
    with pytest.raises(
        OutcomesApiUnavailable,
        match="OUTCOMES_DATABASE_UNAVAILABLE type=OperationalError",
    ) as captured:
        api._connect()
    rendered = str(captured.value)
    assert "secret-database-detail" not in rendered
    assert "secret-password" not in rendered


def test_review_projection_adds_compact_trade_context() -> None:
    api = PostgreSQLOutcomesApi(
        database_name="halpha_demo",
        password=SecretStr("secret-password"),
        environment_id="demo-main",
    )

    result = api._attach_trade_context(
        _Connection(),  # type: ignore[arg-type]
        [_review()],
    )

    assert result[0]["trade_context"] == {
        "instrument_ref": "BTCUSDT-PERP",
        "direction": "LONG",
        "strategy_id": "ONE_SHOT_DONCHIAN_ATR_BREAKOUT",
        "decision_basis_ref": "ONE_SHOT_DONCHIAN_ATR_BREAKOUT",
        "trade_amount": "300",
        "activation_started_at": "2026-07-20T01:00:00+00:00",
        "activation_updated_at": "2026-07-20T02:00:00+00:00",
        "plan_name": "AI BTC breakout",
        "plan_created_at": "2026-07-20T00:30:00+00:00",
        "plan_creator_kind": "AI",
    }
    assert result[0]["resolved_trade_result"] == {
        "fill_count": 2,
        "fills": [
            {
                "trade_id": "trade-1",
                "action_kind": "ENTRY",
                "price": "100",
                "quantity": "1",
                "notional": "100",
                "order_side": None,
                "liquidity_side": None,
                "fee": "0.1",
                "fee_currency": "USDT",
                "fill_time": "2026-07-20T01:00:00+00:00",
            },
            {
                "trade_id": "trade-2",
                "action_kind": "EXIT",
                "price": "101",
                "quantity": "1",
                "notional": "101",
                "order_side": None,
                "liquidity_side": None,
                "fee": "0.1",
                "fee_currency": "USDT",
                "fill_time": "2026-07-20T01:05:00+00:00",
            },
        ],
        "position_quantity": "0",
        "average_entry_price": "100",
        "average_exit_price": "101",
        "entry_notional": "100",
        "fill_cash_flow": "1",
        "commission": "0.2",
        "commission_complete": True,
        "calculation_complete": True,
        "closed": True,
        "gross_pnl": "1",
        "net_pnl": "0.8",
        "currency": "USDT",
        "funding_included": False,
        "fill_times_complete": True,
        "first_fill_time": "2026-07-20T01:00:00+00:00",
        "last_fill_time": "2026-07-20T01:05:00+00:00",
        "holding_duration_seconds": "300",
        "result_scope": "HALPHA_ATTRIBUTED_ACTIONS",
        "external_closure_fill_count": 0,
        "strategy_attribution_complete": True,
        "unresolved_refs": [],
    }


def test_review_projection_keeps_direct_execution_as_a_decision_basis() -> None:
    api = PostgreSQLOutcomesApi(
        database_name="halpha_demo",
        password=SecretStr("secret-password"),
        environment_id="demo-main",
    )

    result = api._attach_trade_context(
        _Connection(decision_basis_ref="DIRECT_EXECUTION@1"),  # type: ignore[arg-type]
        [_review()],
    )[0]["trade_context"]

    assert result["decision_basis_ref"] == "DIRECT_EXECUTION@1"
    assert result["strategy_id"] is None


def test_review_projection_keeps_result_unknown_when_a_referenced_fact_is_missing() -> None:
    api = PostgreSQLOutcomesApi(
        database_name="halpha_demo",
        password=SecretStr("secret-password"),
        environment_id="demo-main",
    )

    result = api._attach_trade_context(
        _Connection(omit_exit_fact=True),  # type: ignore[arg-type]
        [_review()],
    )[0]["resolved_trade_result"]

    assert result["calculation_complete"] is False
    assert result["gross_pnl"] is None
    assert result["net_pnl"] is None
    assert result["unresolved_refs"] == ["venue_fact:exit-fill"]


def test_review_projection_rejects_a_snapshot_digest_mismatch() -> None:
    api = PostgreSQLOutcomesApi(
        database_name="halpha_demo",
        password=SecretStr("secret-password"),
        environment_id="demo-main",
    )

    result = api._attach_trade_context(
        _Connection(exit_fact_digest="different-digest"),  # type: ignore[arg-type]
        [_review()],
    )[0]["resolved_trade_result"]

    assert result["calculation_complete"] is False
    assert result["gross_pnl"] is None
    assert result["net_pnl"] is None
    assert result["unresolved_refs"] == [
        "venue_fact:exit-fill:snapshot_mismatch"
    ]
