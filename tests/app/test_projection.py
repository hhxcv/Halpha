from __future__ import annotations

from datetime import UTC, datetime, timedelta

import psycopg
import pytest
from pydantic import SecretStr

from halpha.app.projection import (
    PostgreSQLWorkbenchProjection,
    _executor_status_from_application_names,
    _project_account_snapshot,
)
from halpha.product_build import (
    EXECUTOR_STARTING_APPLICATION_NAME,
    executor_ready_application_name,
)


PRODUCT_BUILD_ID = "a" * 64


@pytest.mark.parametrize(
    ("names", "expected"),
    (
        ((executor_ready_application_name(PRODUCT_BUILD_ID),), ("READY", True)),
        ((EXECUTOR_STARTING_APPLICATION_NAME,), ("STARTING", None)),
        ((executor_ready_application_name("b" * 64),), ("BUILD_MISMATCH", False)),
        ((), ("UNAVAILABLE", None)),
        (
            (
                EXECUTOR_STARTING_APPLICATION_NAME,
                executor_ready_application_name(PRODUCT_BUILD_ID),
            ),
            ("AMBIGUOUS", None),
        ),
    ),
)
def test_executor_status_is_fail_closed_for_every_non_unique_ready_session(
    names: tuple[str, ...],
    expected: tuple[str, bool | None],
) -> None:
    assert _executor_status_from_application_names(
        names,
        product_build_id=PRODUCT_BUILD_ID,
    ) == expected


def test_live_read_only_projection_connection_forces_transactions_read_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: dict[str, object] = {}

    def capture_connect(**kwargs: object) -> object:
        observed.update(kwargs)
        return object()

    monkeypatch.setattr(psycopg, "connect", capture_connect)
    projection = PostgreSQLWorkbenchProjection(
        database_name="halpha_live",
        database_role_name="halpha_live_app_reader",
        password=SecretStr("test-secret"),
        environment_id="binance-live-primary",
        account_id="binance-usdm-copy-lead-primary",
        read_only=True,
    )

    projection._connect()

    assert observed["options"] == "-c default_transaction_read_only=on"
    assert observed["user"] == "halpha_live_app_reader"


def _account_payload() -> dict[str, object]:
    return {
        "schema": "HALPHA_BINANCE_USDM_ACCOUNT_SNAPSHOT_V2",
        "snapshot_complete": True,
        "read_only": True,
        "management_authority": "NONE",
        "ordinary_open_order_count": 2,
        "algo_open_order_count": 1,
        "ordinary_open_orders": [
            {
                "kind": "ORDINARY",
                "instrument_ref": "SOLUSDT-PERP",
                "symbol": "SOLUSDT",
                "order_id": "1002",
                "client_order_id": "external-order-2",
                "side": "BUY",
                "position_side": "SHORT",
                "order_type": "LIMIT",
                "status": "NEW",
                "time_in_force": "GTC",
                "price": "151",
                "trigger_price": "0",
                "quantity": "1.25",
                "executed_quantity": "0",
                "reduce_only": True,
                "close_position": False,
                "source_create_time_ms": 1785661200000,
                "source_update_time_ms": 1785661202000,
            },
            {
                "kind": "ORDINARY",
                "instrument_ref": "BTCUSDT-PERP",
                "symbol": "BTCUSDT",
                "order_id": "1001",
                "client_order_id": "external-order-1",
                "side": "SELL",
                "position_side": "LONG",
                "order_type": "LIMIT",
                "status": "NEW",
                "time_in_force": "GTC",
                "price": "70000",
                "trigger_price": "0",
                "quantity": "0.01",
                "executed_quantity": "0",
                "reduce_only": False,
                "close_position": False,
                "source_create_time_ms": 1785661190000,
                "source_update_time_ms": 1785661191000,
            },
        ],
        "algo_open_orders": [
            {
                "kind": "ALGO",
                "instrument_ref": "SOLUSDT-PERP",
                "symbol": "SOLUSDT",
                "order_id": "2001",
                "client_order_id": "external-algo-1",
                "side": "BUY",
                "position_side": "SHORT",
                "order_type": "STOP_MARKET",
                "status": "NEW",
                "time_in_force": "GTC",
                "price": "0",
                "trigger_price": "160",
                "quantity": "2.5",
                "executed_quantity": None,
                "reduce_only": True,
                "close_position": False,
                "source_create_time_ms": 1785661201000,
                "source_update_time_ms": 1785661203000,
            }
        ],
        "positions": [
            {
                "instrument_ref": "SOLUSDT-PERP",
                "symbol": "SOLUSDT",
                "direction": "SHORT",
                "position_side": "BOTH",
                "quantity": "-2.5",
                "absolute_quantity": "2.5",
                "entry_price": "152.25",
                "break_even_price": "152.31",
                "mark_price": "154",
                "unrealized_pnl": "-4.375",
                "liquidation_price": "271.8",
                "leverage": 3,
                "margin_mode": "CROSS",
                "notional": "-385",
                "isolated_margin": "0",
            }
        ],
    }


def test_current_account_snapshot_projects_external_position_without_claiming_it() -> None:
    observed_at = datetime(2026, 8, 2, 4, 0, tzinfo=UTC)

    projected = _project_account_snapshot(
        server_cutoff=observed_at + timedelta(seconds=30),
        fact_ref="snapshot-1",
        fact_cutoff=observed_at,
        payload=_account_payload(),
    )

    assert projected["account_snapshot_status"] == "CURRENT"
    assert projected["account_snapshot_age_seconds"] == 30
    assert projected["account_ordinary_open_order_count"] == 2
    assert projected["account_algo_open_order_count"] == 1
    assert [
        (order["kind"], order["order_id"])
        for order in projected["account_orders"]
    ] == [("ALGO", "2001"), ("ORDINARY", "1002"), ("ORDINARY", "1001")]
    assert projected["account_orders"][0]["fact_cutoff"] == (
        "2026-08-02T04:00:00Z"
    )
    assert projected["account_positions"] == [
        {
            "instrument_ref": "SOLUSDT-PERP",
            "symbol": "SOLUSDT",
            "direction": "SHORT",
            "position_side": "BOTH",
            "quantity": "-2.5",
            "absolute_quantity": "2.5",
            "entry_price": "152.25",
            "break_even_price": "152.31",
            "liquidation_price": "271.8",
            "isolated_margin": "0",
            "mark_price": "154",
            "unrealized_pnl": "-4.375",
            "leverage": 3,
            "margin_mode": "CROSS",
            "notional": "-385",
            "fact_cutoff": "2026-08-02T04:00:00Z",
            "snapshot_ref": "snapshot-1",
            "origin": "EXTERNAL_UNMANAGED",
        }
    ]


def test_snapshot_with_halpha_position_is_not_mislabelled_as_wholly_external() -> None:
    observed_at = datetime(2026, 8, 2, 4, 0, tzinfo=UTC)

    projected = _project_account_snapshot(
        server_cutoff=observed_at,
        fact_ref="snapshot-2",
        fact_cutoff=observed_at,
        payload=_account_payload(),
        attributed_instruments=("SOLUSDT-PERP",),
    )

    assert projected["account_positions"][0]["origin"] == (
        "ACCOUNT_TOTAL_WITH_HALPHA_ATTRIBUTION"
    )


def test_stale_snapshot_remains_visible_but_is_not_current() -> None:
    observed_at = datetime(2026, 8, 2, 4, 0, tzinfo=UTC)

    projected = _project_account_snapshot(
        server_cutoff=observed_at + timedelta(seconds=91),
        fact_ref="snapshot-3",
        fact_cutoff=observed_at,
        payload=_account_payload(),
    )

    assert projected["account_snapshot_status"] == "STALE"
    assert len(projected["account_positions"]) == 1


@pytest.mark.parametrize(
    "payload",
    (
        {**_account_payload(), "snapshot_complete": False},
        {**_account_payload(), "management_authority": "WRITE"},
        {**_account_payload(), "positions": [{"symbol": "SOLUSDT"}]},
    ),
)
def test_invalid_or_partial_snapshot_fails_closed(payload: dict[str, object]) -> None:
    observed_at = datetime(2026, 8, 2, 4, 0, tzinfo=UTC)

    projected = _project_account_snapshot(
        server_cutoff=observed_at,
        fact_ref="invalid-snapshot",
        fact_cutoff=observed_at,
        payload=payload,
    )

    assert projected == {
        "account_snapshot_status": "UNKNOWN",
        "account_snapshot_ref": None,
        "account_snapshot_cutoff": None,
        "account_snapshot_age_seconds": None,
        "account_ordinary_open_order_count": None,
        "account_algo_open_order_count": None,
        "account_positions": [],
        "account_orders": [],
    }
