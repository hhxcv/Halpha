from __future__ import annotations

from datetime import UTC, datetime

import pytest

from halpha.venue_integration.facts import build_venue_fact
from halpha.venue_integration.models import (
    BINANCE_USDM_VENUE_REF,
    VenueFactKind,
    VenueFactSourceClass,
)
from halpha.venue_integration.repository import (
    PostgreSQLExecutionActionRepository,
    PostgreSQLVenueFactRepository,
)


NOW = datetime(2026, 7, 24, 12, tzinfo=UTC)


def _fill():
    return build_venue_fact(
        venue_fact_id="10000000-0000-0000-0000-000000000031",
        environment_id="demo-main",
        venue_ref=BINANCE_USDM_VENUE_REF,
        account_ref="demo-owner",
        instrument_ref="BTCUSDT-PERP",
        kind=VenueFactKind.FILL,
        source_class=VenueFactSourceClass.VENUE_STREAM,
        source_object_id="trade-repository-1",
        source_sequence="stream-event-1",
        source_time=NOW,
        received_at=NOW,
        cutoff=NOW,
        payload={
            "trade_id": "trade-repository-1",
            "client_order_id": "a" * 32,
            "venue_order_ref": "venue-order-1",
            "last_price": "50000",
            "last_quantity": "0.001",
            "order_side": "BUY",
            "liquidity_side": "TAKER",
        },
    )


@pytest.mark.parametrize(("returned_row", "inserted"), ((("id",), True), (None, False)))
def test_fact_insert_reports_the_database_conflict_winner(
    returned_row: tuple[str] | None,
    inserted: bool,
) -> None:
    calls: list[tuple[str, tuple[object, ...]]] = []

    class Result:
        @staticmethod
        def fetchone():
            return returned_row

    class Connection:
        @staticmethod
        def execute(query: str, parameters: tuple[object, ...]):
            calls.append((query, parameters))
            return Result()

    repository = PostgreSQLVenueFactRepository(Connection(), "demo-main")

    assert repository.insert(_fill()) is inserted
    query, _parameters = calls[0]
    assert "ON CONFLICT DO NOTHING" in query
    assert "RETURNING venue_fact_id" in query
    assert "ON CONFLICT (" not in query


def test_trade_version_query_returns_all_null_safe_candidates() -> None:
    calls: list[tuple[str, tuple[object, ...]]] = []

    class Result:
        @staticmethod
        def fetchall():
            return []

    class Connection:
        @staticmethod
        def execute(query: str, parameters: tuple[object, ...]):
            calls.append((query, parameters))
            return Result()

    fact = _fill()
    repository = PostgreSQLVenueFactRepository(Connection(), "demo-main")

    assert repository.list_trade_versions(fact) == ()
    query, parameters = calls[0]
    assert "account_ref IS NOT DISTINCT FROM %s" in query
    assert "instrument_ref IS NOT DISTINCT FROM %s" in query
    assert "ORDER BY received_at, venue_fact_id" in query
    assert "LIMIT 1" not in query
    assert parameters == (
        "demo-main",
        VenueFactKind.FILL.value,
        "trade-repository-1",
        "demo-owner",
        "BTCUSDT-PERP",
    )


def test_event_attribution_excludes_never_called_but_keeps_called_handover() -> None:
    calls: list[tuple[str, tuple[object, ...]]] = []

    class Result:
        @staticmethod
        def fetchone():
            return None

    class Connection:
        @staticmethod
        def execute(query: str, parameters: tuple[object, ...]):
            calls.append((query, parameters))
            return Result()

    repository = PostgreSQLExecutionActionRepository(Connection(), "demo-main")

    assert repository.find_order_action_by_client_id("a" * 32) is None
    assert repository.find_order_action_by_venue_order_ref("venue-order-1") is None
    client_query, client_parameters = calls[0]
    venue_query, venue_parameters = calls[1]
    query = client_query
    parameters = client_parameters
    assert "'SUBMITTING', 'UNKNOWN', 'OPEN', 'NOT_SUBMITTED', 'CLOSED'" in " ".join(
        query.split()
    )
    assert "'READY'" not in query
    assert "state = 'HANDED_OVER' AND request_digest IS NOT NULL" in " ".join(
        query.split()
    )
    assert parameters == ("demo-main", "a" * 32)
    normalized_venue_query = " ".join(venue_query.split())
    assert "action_kind <> 'CANCEL'" in normalized_venue_query
    assert "venue_order_refs ? %s" in normalized_venue_query
    assert "'READY'" not in venue_query
    assert "state = 'HANDED_OVER' AND request_digest IS NOT NULL" in (
        normalized_venue_query
    )
    assert venue_parameters == ("demo-main", "venue-order-1")
