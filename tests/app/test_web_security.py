from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from starlette.websockets import WebSocketDisconnect

from halpha.app.planning_api import PostgreSQLPlanningApi
from halpha.public_market import (
    MarketBar,
    MarketContext,
    MarketContextProvider,
    MarketInterval,
    MarketWindow,
)
from halpha.public_market_stream import (
    MarketStreamBar,
    MarketStreamQuote,
    MarketStreamStatus,
    PublicMarketStreamProvider,
)
from halpha.public_instrument_rules import InstrumentRulesProvider
from halpha.app.projection import ProjectionUnavailable
from halpha.app.secrets import AppSecrets
from halpha.app.web import create_app
from halpha.capital.repository import CapitalConflict
from halpha.configuration import load_settings
from halpha.planning.registry import Direction, OneShotParameters
from halpha.planning.order_schedule import InstrumentOrderRules
from halpha.user_workbench.repository import CommandConflict


ROOT = Path(__file__).resolve().parents[2]
ORIGIN = "http://127.0.0.1:8765"


class FakeProjection:
    def __init__(
        self,
        *,
        available: bool = True,
        activations: list[dict[str, Any]] | None = None,
        executor_status: str = "READY",
    ) -> None:
        self.available = available
        self.activations = activations or []
        self.projected_executor_status = executor_status

    def overview(self) -> dict[str, Any]:
        if not self.available:
            raise ProjectionUnavailable("DATABASE_UNAVAILABLE")
        return {
            "database_available": True,
            "server_fact_cutoff": "2026-07-17T00:00:00Z",
            "open_activation_count": 0,
            "database_name": "halpha_demo",
        }

    def availability(self) -> dict[str, Any]:
        return {
            "database_available": self.available,
            "reason_code": None if self.available else "DATABASE_UNAVAILABLE",
            "server_fact_cutoff": (
                "2026-07-17T00:00:00Z" if self.available else None
            ),
        }

    def operations(self) -> dict[str, Any]:
        if not self.available:
            raise ProjectionUnavailable("DATABASE_UNAVAILABLE")
        return {
            "database_available": True,
            "server_fact_cutoff": "2026-07-17T00:00:00Z",
            "activations": self.activations,
        }

    def executor_status(self, product_build_id: str) -> dict[str, Any]:
        return {
            "status": self.projected_executor_status,
            "checked_at": "2026-07-17T00:00:01Z",
            "product_build_consistent": (
                True
                if self.projected_executor_status == "READY"
                else False
                if self.projected_executor_status == "BUILD_MISMATCH"
                else None
            ),
            "product_build_id": product_build_id,
        }


class FakeMarketContext:
    async def fetch(self, instrument_ref: str, lookback: int) -> MarketContext:
        return MarketContext(
            instrument_ref=instrument_ref,
            source="BINANCE_DEMO_PUBLIC",
            source_cutoff=datetime(2026, 7, 20, tzinfo=UTC),
            latest_closed_1m_at=datetime(2026, 7, 20, tzinfo=UTC),
            latest_closed_15m_at=datetime(2026, 7, 20, tzinfo=UTC),
            channel_lookback_15m=lookback,
            bid_price="100",
            ask_price="101",
            reference_price="100.5",
            latest_close_1m="100.25",
            latest_volume_1m="12.5",
            latest_trade_count_1m=8,
            latest_close_15m="100",
            channel_upper="102",
            channel_lower="98",
            atr_14="2",
            long_breakout_gap_pct="1.492537313432835820895522388",
            short_breakout_gap_pct="2.48756218905472636815920398",
        )

    async def fetch_window(
        self,
        instrument_ref: str,
        interval: MarketInterval,
        start_at: datetime,
        end_at: datetime,
    ) -> MarketWindow:
        return MarketWindow(
            instrument_ref=instrument_ref,
            interval=interval,
            source="BINANCE_DEMO_PUBLIC",
            source_cutoff=end_at,
            bars=(
                MarketBar(
                    open_at=start_at,
                    close_at=end_at,
                    open="100",
                    high="102",
                    low="99",
                    close="101",
                    volume="12.5",
                ),
            ),
        )


class FakeInstrumentRules:
    async def fetch(self, instrument_ref: str) -> InstrumentOrderRules:
        assert instrument_ref == "BTCUSDT-PERP"
        return InstrumentOrderRules(
            source="BINANCE_DEMO_EXCHANGE_INFO",
            min_price="0.1",
            max_price="1000000",
            price_tick_size="0.1",
            limit_quantity_step="0.001",
            min_limit_quantity="0.001",
            max_limit_quantity="1000",
            market_quantity_step="0.01",
            min_market_quantity="0.01",
            max_market_quantity="100",
            min_notional="5",
            source_cutoff="2026-07-23T00:00:00+00:00",
        )


class FakeMarketStream:
    def stream(self, instrument_ref: str):
        async def events():
            yield MarketStreamStatus(
                state="LIVE",
                source="BINANCE_DEMO_PUBLIC",
                observed_at=datetime(2026, 7, 20, tzinfo=UTC),
            )
            yield MarketStreamQuote(
                instrument_ref=instrument_ref,
                source="BINANCE_DEMO_PUBLIC",
                source_cutoff=datetime(2026, 7, 20, tzinfo=UTC),
                received_at=datetime(2026, 7, 20, tzinfo=UTC),
                bid_price="100",
                ask_price="101",
                reference_price="100.5",
            )

        return events()

    async def close(self) -> None:
        return None


def make_client(
    tmp_path: Path,
    *,
    projection: FakeProjection | None = None,
    market_context_provider: MarketContextProvider | None = None,
    market_stream_provider: PublicMarketStreamProvider | None = None,
    instrument_rules_provider: InstrumentRulesProvider | None = None,
    monotonic_provider: Callable[[], float] | None = None,
) -> TestClient:
    settings = load_settings(ROOT / "config" / "halpha.example.toml")
    app = create_app(
        settings,
        AppSecrets(
            database_password=SecretStr("database-test-secret"),
            csrf_signing_secret=SecretStr("csrf-test-secret-which-is-not-shared"),
        ),
        repo_root=ROOT,
        projection=projection or FakeProjection(),
        market_context_provider=market_context_provider,
        market_stream_provider=market_stream_provider,
        instrument_rules_provider=instrument_rules_provider,
        static_dist=tmp_path / "missing-dist",
        monotonic_provider=monotonic_provider,
    )
    return TestClient(app, base_url=ORIGIN)


def csrf(client: TestClient) -> str:
    response = client.get("/operations")
    assert response.status_code == 200
    token = client.cookies.get("halpha_csrf")
    assert token
    return token


def test_read_surface_is_available_without_login(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    overview = client.get("/api/v1/overview")

    assert overview.status_code == 200
    assert overview.json()["environment_kind"] == "DEMO"
    assert overview.json()["runtime_real_write_gate"] == "CLOSED"
    assert client.post("/api/v1/session/login").status_code == 403
    assert client.get("/api/v1/session/logout").status_code == 404


def test_public_market_websocket_is_read_only_and_same_origin(tmp_path: Path) -> None:
    client = make_client(
        tmp_path,
        market_stream_provider=FakeMarketStream(),
    )

    with client.websocket_connect(
        "/api/v1/market-stream?instrument_ref=BTCUSDT-PERP",
        headers={"host": "127.0.0.1:8765", "origin": ORIGIN},
    ) as websocket:
        status = websocket.receive_json()
        quote = websocket.receive_json()

    assert status["type"] == "status"
    assert status["state"] == "LIVE"
    assert quote["type"] == "quote"
    assert quote["reference_price"] == "100.5"


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"origin": "https://attacker.example"},
        {"origin": ORIGIN, "authorization": "Bearer forbidden"},
    ],
)
def test_public_market_websocket_rejects_non_local_or_authorized_clients(
    tmp_path: Path,
    headers: dict[str, str],
) -> None:
    client = make_client(
        tmp_path,
        market_stream_provider=FakeMarketStream(),
    )

    with pytest.raises(WebSocketDisconnect) as caught:
        with client.websocket_connect(
            "/api/v1/market-stream?instrument_ref=BTCUSDT-PERP",
            headers={"host": "127.0.0.1:8765", **headers},
        ):
            pass

    assert caught.value.code == 1008


def test_strategy_and_status_reads_need_no_session(tmp_path: Path) -> None:
    client = make_client(
        tmp_path,
        market_context_provider=FakeMarketContext(),
    )

    strategies = client.get("/api/v1/strategies")
    schema = client.get(
        "/api/v1/strategies/ONE_SHOT_DONCHIAN_ATR_BREAKOUT/schema"
    )
    status = client.get("/api/v1/settings/status")
    market = client.get(
        "/api/v1/market-context?instrument_ref=BTCUSDT-PERP&channel_lookback_15m=20"
    )
    market_window = client.get(
        "/api/v1/market-window",
        params={
            "instrument_ref": "BTCUSDT-PERP",
            "interval": "1m",
            "start_at": "2026-07-20T00:00:00Z",
            "end_at": "2026-07-20T00:01:00Z",
        },
    )
    naive_market_window = client.get(
        "/api/v1/market-window",
        params={
            "instrument_ref": "BTCUSDT-PERP",
            "interval": "1m",
            "start_at": "2026-07-20T00:00:00",
            "end_at": "2026-07-20T00:01:00",
        },
    )

    assert strategies.status_code == 200
    assert strategies.json()[0]["strategy_id"] == "ONE_SHOT_DONCHIAN_ATR_BREAKOUT"
    assert strategies.json()[0]["plan_key_parameters"][0] == {
        "parameter_key": "demo_immediate_entry",
        "label": "入场模式",
        "display_format": "BOOLEAN_LABEL",
        "unit": None,
        "true_label": "Demo 流程检查",
        "false_label": "自然突破信号",
    }
    assert "Donchian 通道" in strategies.json()[0]["value_logic"]
    assert "15 分钟通道突破" in strategies.json()[0]["applicable_scenarios"]
    assert "ATR 止损和两档止盈" in strategies.json()[0]["execution_behavior"]
    assert schema.status_code == 200
    assert schema.json()["additionalProperties"] is False
    assert status.status_code == 200
    assert status.json()["runtime_real_write_gate"] == "CLOSED"
    assert status.json()["executor_status"] == "READY"
    assert status.json()["app_executor_product_build_consistent"] is True
    assert market.status_code == 200
    assert market.json()["reference_price"] == "100.5"
    assert market_window.status_code == 200
    assert market_window.json()["bars"][0]["close"] == "101"
    assert naive_market_window.status_code == 422
    assert naive_market_window.json()["detail"]["code"] == "MARKET_WINDOW_TIMEZONE_REQUIRED"


def test_market_window_query_cannot_switch_away_from_the_app_environment(
    tmp_path: Path,
) -> None:
    class RecordingMarketContext(FakeMarketContext):
        def __init__(self, source: str) -> None:
            self.source = source
            self.window_calls = 0

        async def fetch_window(
            self,
            instrument_ref: str,
            interval: MarketInterval,
            start_at: datetime,
            end_at: datetime,
        ) -> MarketWindow:
            self.window_calls += 1
            window = await super().fetch_window(
                instrument_ref,
                interval,
                start_at,
                end_at,
            )
            return window.model_copy(update={"source": self.source})

    environment_provider = RecordingMarketContext("BINANCE_DEMO_PUBLIC")
    client = make_client(
        tmp_path,
        market_context_provider=environment_provider,
    )
    params = {
        "instrument_ref": "BTCUSDT-PERP",
        "interval": "1m",
        "start_at": "2026-07-20T00:00:00Z",
        "end_at": "2026-07-20T00:01:00Z",
    }

    review_response = client.get("/api/v1/market-window", params=params)
    reference_response = client.get(
        "/api/v1/market-window",
        params={**params, "purpose": "PUBLIC_REFERENCE"},
    )

    assert review_response.status_code == 200
    assert review_response.json()["source"] == "BINANCE_DEMO_PUBLIC"
    assert reference_response.status_code == 200
    assert reference_response.json()["source"] == "BINANCE_DEMO_PUBLIC"
    assert environment_provider.window_calls == 2


def test_demo_app_rejects_cross_environment_http_market_sources(
    tmp_path: Path,
) -> None:
    class LiveMarketContext(FakeMarketContext):
        async def fetch(
            self,
            instrument_ref: str,
            lookback: int,
        ) -> MarketContext:
            context = await super().fetch(instrument_ref, lookback)
            return context.model_copy(update={"source": "BINANCE_LIVE_PUBLIC"})

        async def fetch_window(
            self,
            instrument_ref: str,
            interval: MarketInterval,
            start_at: datetime,
            end_at: datetime,
        ) -> MarketWindow:
            window = await super().fetch_window(
                instrument_ref,
                interval,
                start_at,
                end_at,
            )
            return window.model_copy(update={"source": "BINANCE_LIVE_PUBLIC"})

    client = make_client(
        tmp_path,
        market_context_provider=LiveMarketContext(),
    )
    market = client.get(
        "/api/v1/market-context",
        params={
            "instrument_ref": "BTCUSDT-PERP",
            "channel_lookback_15m": 20,
        },
    )
    window = client.get(
        "/api/v1/market-window",
        params={
            "instrument_ref": "BTCUSDT-PERP",
            "interval": "1m",
            "start_at": "2026-07-20T00:00:00Z",
            "end_at": "2026-07-20T00:01:00Z",
        },
    )

    assert market.status_code == 503
    assert market.json()["detail"] == {"code": "MARKET_SOURCE_ENVIRONMENT_MISMATCH"}
    assert window.status_code == 503
    assert window.json()["detail"] == {"code": "MARKET_SOURCE_ENVIRONMENT_MISMATCH"}


@pytest.mark.parametrize(
    "cross_environment_event",
    (
        MarketStreamStatus(
            state="LIVE",
            source="BINANCE_LIVE_PUBLIC",
            observed_at=datetime(2026, 7, 20, tzinfo=UTC),
        ),
        MarketStreamQuote(
            instrument_ref="BTCUSDT-PERP",
            source="BINANCE_LIVE_PUBLIC",
            source_cutoff=datetime(2026, 7, 20, tzinfo=UTC),
            received_at=datetime(2026, 7, 20, tzinfo=UTC),
            bid_price="100",
            ask_price="101",
            reference_price="100.5",
        ),
        MarketStreamBar(
            instrument_ref="BTCUSDT-PERP",
            interval="1m",
            source="BINANCE_LIVE_PUBLIC",
            source_cutoff=datetime(2026, 7, 20, tzinfo=UTC),
            received_at=datetime(2026, 7, 20, tzinfo=UTC),
            closed=False,
            bar=MarketBar(
                open_at=datetime(2026, 7, 20, tzinfo=UTC),
                close_at=datetime(2026, 7, 20, 0, 1, tzinfo=UTC),
                open="100",
                high="102",
                low="99",
                close="101",
                volume="12.5",
            ),
        ),
    ),
)
def test_demo_app_rejects_cross_environment_stream_source(
    tmp_path: Path,
    cross_environment_event: MarketStreamStatus | MarketStreamQuote | MarketStreamBar,
) -> None:
    class LiveMarketStream(FakeMarketStream):
        def stream(self, instrument_ref: str):
            async def events():
                yield MarketStreamStatus(
                    state="LIVE",
                    source="BINANCE_DEMO_PUBLIC",
                    observed_at=datetime(2026, 7, 20, tzinfo=UTC),
                )
                yield cross_environment_event

            return events()

    client = make_client(
        tmp_path,
        market_stream_provider=LiveMarketStream(),
    )

    with pytest.raises(WebSocketDisconnect) as caught:
        with client.websocket_connect(
            "/api/v1/market-stream?instrument_ref=BTCUSDT-PERP",
            headers={"host": "127.0.0.1:8765", "origin": ORIGIN},
        ) as websocket:
            websocket.receive_json()
            websocket.receive_json()

    assert caught.value.code == 1013
    assert caught.value.reason == "MARKET_SOURCE_ENVIRONMENT_MISMATCH"


def test_market_order_preview_uses_the_current_environment_server_quote(
    tmp_path: Path,
) -> None:
    client = make_client(
        tmp_path,
        market_context_provider=FakeMarketContext(),
        instrument_rules_provider=FakeInstrumentRules(),
    )
    token = csrf(client)

    response = client.post(
        "/api/v1/order-schedules/preview",
        headers={"Origin": ORIGIN, "X-CSRFToken": token},
        json={
            "schedule_ref": "demo-market-preview",
            "instrument_ref": "BTCUSDT-PERP",
            "direction": "LONG",
            "max_notional": "100",
            "reference_price": "999",
            "spec": {
                "price_distribution": {"kind": "SINGLE"},
                "amount_distribution": {
                    "mode": "FIXED",
                    "base_notional": "10",
                },
                "venue_policy": {
                    "order_type": "MARKET",
                    "time_in_force": None,
                },
                "protection_policy": {
                    "initial_stop": {"distance_bps": "100"},
                },
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["reference_price"] == "100.5"


def test_market_order_preview_rejects_a_cross_environment_quote(
    tmp_path: Path,
) -> None:
    class LiveMarketContext(FakeMarketContext):
        async def fetch(
            self,
            instrument_ref: str,
            lookback: int,
        ) -> MarketContext:
            context = await super().fetch(instrument_ref, lookback)
            return context.model_copy(update={"source": "BINANCE_LIVE_PUBLIC"})

    client = make_client(
        tmp_path,
        market_context_provider=LiveMarketContext(),
        instrument_rules_provider=FakeInstrumentRules(),
    )
    token = csrf(client)

    response = client.post(
        "/api/v1/order-schedules/preview",
        headers={"Origin": ORIGIN, "X-CSRFToken": token},
        json={
            "schedule_ref": "cross-environment-market-preview",
            "instrument_ref": "BTCUSDT-PERP",
            "direction": "LONG",
            "max_notional": "100",
            "spec": {
                "price_distribution": {"kind": "SINGLE"},
                "amount_distribution": {
                    "mode": "FIXED",
                    "base_notional": "10",
                },
                "venue_policy": {
                    "order_type": "MARKET",
                    "time_in_force": None,
                },
                "protection_policy": {
                    "initial_stop": {"distance_bps": "100"},
                },
            },
        },
    )

    assert response.status_code == 503
    assert response.json()["detail"] == {"code": "MARKET_SOURCE_ENVIRONMENT_MISMATCH"}


def test_order_preview_rejects_cross_environment_instrument_rules(
    tmp_path: Path,
) -> None:
    class LiveInstrumentRules(FakeInstrumentRules):
        async def fetch(self, instrument_ref: str) -> InstrumentOrderRules:
            rules = await super().fetch(instrument_ref)
            return rules.model_copy(update={"source": "BINANCE_LIVE_EXCHANGE_INFO"})

    client = make_client(
        tmp_path,
        instrument_rules_provider=LiveInstrumentRules(),
    )
    token = csrf(client)

    response = client.post(
        "/api/v1/order-schedules/preview",
        headers={"Origin": ORIGIN, "X-CSRFToken": token},
        json={
            "schedule_ref": "cross-environment-rules-preview",
            "instrument_ref": "BTCUSDT-PERP",
            "direction": "LONG",
            "max_notional": "100",
            "spec": {
                "price_distribution": {
                    "kind": "SINGLE",
                    "limit_price": "100",
                },
                "amount_distribution": {
                    "mode": "FIXED",
                    "base_notional": "10",
                },
                "venue_policy": {
                    "order_type": "LIMIT",
                    "time_in_force": "GTC",
                },
                "protection_policy": {
                    "initial_stop": {"distance_bps": "100"},
                },
            },
        },
    )

    assert response.status_code == 503
    assert response.json()["detail"] == {
        "code": "INSTRUMENT_RULES_SOURCE_ENVIRONMENT_MISMATCH"
    }


def test_order_schedule_preview_uses_server_rules_and_returns_all_legs(
    tmp_path: Path,
) -> None:
    client = make_client(
        tmp_path,
        instrument_rules_provider=FakeInstrumentRules(),
    )
    token = csrf(client)

    response = client.post(
        "/api/v1/order-schedules/preview",
        headers={"Origin": ORIGIN, "X-CSRFToken": token},
        json={
            "schedule_ref": "schedule-preview-1",
            "instrument_ref": "BTCUSDT-PERP",
            "direction": "LONG",
            "max_notional": "100",
            "spec": {
                "price_distribution": {
                    "kind": "LADDER",
                    "lower_price": "10",
                    "upper_price": "30",
                    "level_count": 5,
                },
                "amount_distribution": {
                    "mode": "FIXED",
                    "base_notional": "10",
                },
                "venue_policy": {
                    "order_type": "LIMIT",
                    "time_in_force": "GTC",
                    "post_only": True,
                },
                "protection_policy": {
                    "initial_stop": {"distance_bps": "100"},
                },
            },
        },
    )

    assert response.status_code == 200
    preview = response.json()
    assert preview["valid"] is True
    assert [leg["price"] for leg in preview["legs"]] == [
        "10",
        "15",
        "20",
        "25",
        "30",
    ]
    assert preview["instrument_rules"]["source"] == "BINANCE_DEMO_EXCHANGE_INFO"


@pytest.mark.parametrize(
    ("decision_basis_kind", "submission_mode", "expected_code"),
    (
        (
            "DIRECT_EXECUTION",
            "PREPROTECTED_PARALLEL",
            "PREPROTECTED_PARALLEL_NOT_VERIFIED",
        ),
        (
            "STRATEGY_SIGNAL",
            "SERIAL_PROTECTED",
            "STRATEGY_ORDER_SCHEDULE_NOT_SUPPORTED",
        ),
    ),
)
def test_order_schedule_preview_uses_the_persisted_capability_catalog(
    tmp_path: Path,
    decision_basis_kind: str,
    submission_mode: str,
    expected_code: str,
) -> None:
    class RulesMustNotBeFetched:
        async def fetch(self, _instrument_ref: str) -> InstrumentOrderRules:
            pytest.fail("unsupported schedule must be rejected before rules lookup")

    client = make_client(
        tmp_path,
        instrument_rules_provider=RulesMustNotBeFetched(),
    )
    token = csrf(client)

    response = client.post(
        "/api/v1/order-schedules/preview",
        headers={"Origin": ORIGIN, "X-CSRFToken": token},
        json={
            "schedule_ref": "unsupported-schedule-preview",
            "decision_basis_kind": decision_basis_kind,
            "instrument_ref": "BTCUSDT-PERP",
            "direction": "LONG",
            "max_notional": "100",
            "spec": {
                "price_distribution": {
                    "kind": "SINGLE",
                    "limit_price": "100",
                },
                "amount_distribution": {
                    "mode": "FIXED",
                    "base_notional": "10",
                },
                "venue_policy": {
                    "order_type": "LIMIT",
                    "time_in_force": "GTC",
                },
                "submission_mode": submission_mode,
                "protection_policy": {
                    "initial_stop": {"distance_bps": "100"},
                },
            },
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == {"code": expected_code}


def test_csrf_host_origin_and_authorization_boundaries(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    token = csrf(client)
    endpoint = "/api/v1/settings/test-email"

    assert client.post(endpoint, headers={"Origin": ORIGIN}).status_code == 403
    assert client.post(
        endpoint,
        headers={"Origin": "http://example.test", "X-CSRFToken": token},
    ).status_code == 403
    assert client.post(endpoint, headers={"X-CSRFToken": token}).status_code == 403
    assert client.post(
        endpoint,
        headers={"Origin": ORIGIN, "X-CSRFToken": token},
    ).status_code == 409
    assert client.get("/operations", headers={"Host": "example.test"}).status_code == 400
    bearer = client.get("/operations", headers={"Authorization": "Bearer forbidden"})
    assert bearer.status_code == 400
    assert bearer.json()["detail"]["code"] == "AUTHORIZATION_HEADER_FORBIDDEN"


def test_operations_remains_usable_without_static_dist_or_password(
    tmp_path: Path,
) -> None:
    client = make_client(tmp_path)

    operations = client.get("/operations")
    script = client.get("/operations.js")
    missing_static = client.get("/overview", follow_redirects=False)

    assert operations.status_code == 200
    assert "故障接管" in operations.text
    assert "当前环境没有未结束的策略运行" in operations.text
    assert "命令被接受不代表 Binance 已经撤单、保护或平仓" in operations.text
    assert 'href="https://demo.binance.com/"' in operations.text
    assert "password" not in operations.text.lower()
    assert "sign out" not in operations.text.lower()
    assert "halpha_csrf" in client.cookies
    assert script.status_code == 200
    assert "Idempotency-Key" in script.text
    assert "stop-new-risk" in script.text
    assert "RESUME_ACTIVATION" not in script.text
    assert "password" not in script.text.lower()
    assert missing_static.status_code == 503
    assert client.get("/login").status_code == 404


def test_operations_projects_only_core_fallback_facts_and_controls(
    tmp_path: Path,
) -> None:
    activation = {
        "activation_id": "f75cb14b-73df-4da4-9f21-3c2d4d28cad1",
        "account_ref": "demo-account",
        "instrument_ref": "BTCUSDT-PERP",
        "direction": "LONG",
        "lifecycle": "RUNNING",
        "run_state": "PAUSED",
        "pause_reason": "WRITER_CONTINUITY_LOST",
        "state_version": 2,
        "protection_state": "WORKING",
        "latest_venue_cutoff": "2026-07-17T00:00:00+00:00",
        "stopped_categories": ["NEW_RISK"],
    }
    client = make_client(
        tmp_path,
        projection=FakeProjection(activations=[activation]),
    )

    operations = client.get("/operations")

    assert operations.status_code == 200
    assert "WRITER_CONTINUITY_LOST" in operations.text
    assert "新增风险</dt><dd class=\"stopped\">已停止" in operations.text
    assert operations.text.count('class="control-button"') == 3
    assert 'data-intent="STOP_NEW_RISK"' in operations.text
    assert 'data-intent="EXIT_STRATEGY"' in operations.text
    assert 'data-intent="USER_TAKEOVER"' in operations.text
    assert 'data-intent="RESUME_ACTIVATION"' not in operations.text
    assert "2026-07-17 08:00:00 UTC+8" in operations.text
    assert "<table" not in operations.text
    assert "show-more" not in operations.text


def test_unavailable_database_is_truthful_and_fail_closed(tmp_path: Path) -> None:
    client = make_client(tmp_path, projection=FakeProjection(available=False))

    overview = client.get("/api/v1/overview")
    status = client.get("/api/v1/settings/status")
    operations = client.get("/operations")

    assert overview.status_code == 503
    assert overview.json()["detail"]["code"] == "DATABASE_FACTS_UNAVAILABLE"
    assert status.status_code == 200
    assert status.json()["database_available"] is False
    assert status.json()["database_reason_code"] == "DATABASE_UNAVAILABLE"
    assert "数据库</dt><dd>不可用" in operations.text
    assert "所有控制保持关闭" in operations.text


def test_security_headers_and_openapi_have_no_auth_contract(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    response = client.get("/operations")
    schema = client.get("/api/v1/openapi.json").json()

    assert response.headers["cache-control"] == "no-store"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert response.headers["referrer-policy"] == "same-origin"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "/operations" not in schema["paths"]
    assert all("/session/" not in path for path in schema["paths"])
    serialized = str(schema).lower()
    assert "owner_password" not in serialized
    assert "sessionresponse" not in serialized
    assert "database-test-secret" not in serialized


@pytest.mark.parametrize(
    ("conflict", "code"),
    (
        (CapitalConflict("ACCOUNT_LIMIT_EXCEEDED"), "ACCOUNT_LIMIT_EXCEEDED"),
        (CommandConflict("IDEMPOTENCY_CONTENT_CONFLICT"), "IDEMPOTENCY_CONTENT_CONFLICT"),
    ),
)
def test_domain_conflicts_are_stable_http_409(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    conflict: RuntimeError,
    code: str,
) -> None:
    def raise_conflict(_self: PostgreSQLPlanningApi, _plan_id: str) -> dict[str, Any]:
        raise conflict

    monkeypatch.setattr(PostgreSQLPlanningApi, "get_plan", raise_conflict)
    response = make_client(tmp_path).get("/api/v1/plans/00000000-0000-0000-0000-000000000000")

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == code


def test_validation_errors_are_sanitized_to_one_stable_code(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_validation(_self: PostgreSQLPlanningApi, _plan_id: str) -> dict[str, Any]:
        OneShotParameters(
            direction=Direction.LONG,
            take_profit_1_r="0.75",
            take_profit_2_r="1.5",
        )
        raise AssertionError("validation should have failed")

    monkeypatch.setattr(PostgreSQLPlanningApi, "get_plan", raise_validation)
    response = make_client(tmp_path).get(
        "/api/v1/plans/00000000-0000-0000-0000-000000000000"
    )

    assert response.status_code == 409
    assert response.json()["detail"] == {"code": "PARAMETER_OUT_OF_RANGE"}


def test_activation_preview_projects_executor_readiness(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        PostgreSQLPlanningApi,
        "activation_preview",
        lambda _self, plan_version_id: {"plan_version_id": plan_version_id},
    )
    client = make_client(
        tmp_path,
        projection=FakeProjection(executor_status="STARTING"),
    )
    token = csrf(client)

    response = client.post(
        "/api/v1/plan-versions/plan-version-001/activation-preview",
        headers={"Origin": ORIGIN, "X-CSRFToken": token},
    )

    assert response.status_code == 200
    assert response.json()["executor_status"] == "STARTING"
    assert response.json()["executor_status_checked_at"] == "2026-07-17T00:00:01Z"


def test_activation_rejects_before_mutation_when_executor_is_not_ready(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        PostgreSQLPlanningApi,
        "activate",
        lambda *_args, **_kwargs: pytest.fail("activation must not be created"),
    )
    monkeypatch.setattr(
        PostgreSQLPlanningApi,
        "activation_replay",
        lambda *_args, **_kwargs: None,
    )
    client = make_client(
        tmp_path,
        projection=FakeProjection(executor_status="UNAVAILABLE"),
    )
    token = csrf(client)

    response = client.post(
        "/api/v1/activations",
        json={"plan_version_id": "plan-version-001"},
        headers={
            "Origin": ORIGIN,
            "X-CSRFToken": token,
            "Idempotency-Key": "executor-unavailable-001",
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == {"code": "EXECUTOR_NOT_READY"}


def test_activation_replays_committed_result_before_current_readiness_or_preview(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    replay = {
        "activation": {"activation_id": "activation-existing-001"},
        "venue_write_created": False,
        "runtime_real_write_gate": "CLOSED",
    }
    monkeypatch.setattr(
        PostgreSQLPlanningApi,
        "activation_replay",
        lambda *_args, **_kwargs: replay,
    )
    monkeypatch.setattr(
        PostgreSQLPlanningApi,
        "activation_preview",
        lambda *_args, **_kwargs: pytest.fail("replay must not refresh the preview"),
    )
    client = make_client(
        tmp_path,
        projection=FakeProjection(executor_status="UNAVAILABLE"),
    )
    token = csrf(client)

    response = client.post(
        "/api/v1/activations",
        json={
            "plan_version_id": "plan-version-001",
            "expected_schedule_digest": None,
        },
        headers={
            "Origin": ORIGIN,
            "X-CSRFToken": token,
            "Idempotency-Key": "activation-replay-001",
        },
    )

    assert response.status_code == 201
    assert response.json() == replay


def _direct_activation_preview(plan_version_id: str) -> dict[str, Any]:
    return {
        "plan_version_id": plan_version_id,
        "decision_basis_kind": "DIRECT_EXECUTION",
        "venue_ref": "BINANCE_USDM",
        "instrument_ref": "BTCUSDT-PERP",
        "direction": "LONG",
        "trade_amount": "100",
        "order_schedule_spec": {
            "price_distribution": {
                "kind": "SINGLE",
                "limit_price": "100",
            },
            "amount_distribution": {
                "mode": "FIXED",
                "base_notional": "10",
            },
            "venue_policy": {
                "order_type": "LIMIT",
                "time_in_force": "GTC",
            },
            "protection_policy": {
                "initial_stop": {"distance_bps": "100"},
            },
        },
    }


def test_activation_uses_the_exact_order_schedule_snapshot_from_preview(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan_version_id = "direct-plan-version-001"
    captured: dict[str, Any] = {}
    instrument_rules = FakeInstrumentRules()
    instrument_rules_calls = 0
    fetch_instrument_rules = instrument_rules.fetch

    async def counted_fetch(instrument_ref: str) -> InstrumentOrderRules:
        nonlocal instrument_rules_calls
        instrument_rules_calls += 1
        rules = await fetch_instrument_rules(instrument_ref)
        if instrument_rules_calls == 2:
            return rules.model_copy(
                update={"source_cutoff": "2026-07-23T00:01:00+00:00"}
            )
        return rules

    monkeypatch.setattr(instrument_rules, "fetch", counted_fetch)
    monkeypatch.setattr(
        PostgreSQLPlanningApi,
        "activation_preview",
        lambda _self, requested_id: _direct_activation_preview(requested_id),
    )
    monkeypatch.setattr(
        PostgreSQLPlanningApi,
        "activation_replay",
        lambda *_args, **_kwargs: None,
    )

    def activate(
        _self: PostgreSQLPlanningApi,
        _payload: Any,
        **kwargs: Any,
    ) -> dict[str, Any]:
        captured["snapshot"] = kwargs["order_schedule_snapshot"]
        return {
            "activation": {"activation_id": "activation-direct-001"},
            "venue_write_created": False,
            "runtime_real_write_gate": "CLOSED",
        }

    monkeypatch.setattr(PostgreSQLPlanningApi, "activate", activate)
    client = make_client(
        tmp_path,
        instrument_rules_provider=instrument_rules,
    )
    token = csrf(client)
    headers = {"Origin": ORIGIN, "X-CSRFToken": token}

    preview_response = client.post(
        f"/api/v1/plan-versions/{plan_version_id}/activation-preview",
        headers=headers,
    )
    assert preview_response.status_code == 200
    preview_snapshot = preview_response.json()["order_schedule_snapshot"]

    activation_response = client.post(
        "/api/v1/activations",
        json={
            "plan_version_id": plan_version_id,
            "expected_schedule_digest": preview_response.json()[
                "expected_schedule_digest"
            ],
        },
        headers={
            **headers,
            "Idempotency-Key": "activation-direct-preview-hit-001",
        },
    )

    assert activation_response.status_code == 201
    assert instrument_rules_calls == 2
    assert captured["snapshot"].schedule_digest == preview_snapshot["schedule_digest"]
    assert captured["snapshot"].source_cutoff == "2026-07-23T00:01:00+00:00"
    assert (
        captured["snapshot"].instrument_rules.source_cutoff
        == "2026-07-23T00:01:00+00:00"
    )


def test_direct_activation_rejects_changed_current_instrument_rules(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan_version_id = "direct-plan-version-rule-change"

    class ChangingInstrumentRules(FakeInstrumentRules):
        def __init__(self) -> None:
            self.calls = 0

        async def fetch(self, instrument_ref: str) -> InstrumentOrderRules:
            self.calls += 1
            rules = await super().fetch(instrument_ref)
            if self.calls == 2:
                return rules.model_copy(
                    update={
                        "price_tick_size": "1",
                        "source_cutoff": "2026-07-23T00:01:00+00:00",
                    }
                )
            return rules

    instrument_rules = ChangingInstrumentRules()
    monkeypatch.setattr(
        PostgreSQLPlanningApi,
        "activation_preview",
        lambda _self, requested_id: _direct_activation_preview(requested_id),
    )
    monkeypatch.setattr(
        PostgreSQLPlanningApi,
        "activation_replay",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        PostgreSQLPlanningApi,
        "activate",
        lambda *_args, **_kwargs: pytest.fail("changed rules must not activate"),
    )
    client = make_client(
        tmp_path,
        instrument_rules_provider=instrument_rules,
    )
    token = csrf(client)
    headers = {"Origin": ORIGIN, "X-CSRFToken": token}
    preview_response = client.post(
        f"/api/v1/plan-versions/{plan_version_id}/activation-preview",
        headers=headers,
    )
    assert preview_response.status_code == 200

    activation_response = client.post(
        "/api/v1/activations",
        json={
            "plan_version_id": plan_version_id,
            "expected_schedule_digest": preview_response.json()[
                "expected_schedule_digest"
            ],
        },
        headers={
            **headers,
            "Idempotency-Key": "activation-direct-rule-change-001",
        },
    )

    assert activation_response.status_code == 409
    assert activation_response.json()["detail"] == {
        "code": "ACTIVATION_PREVIEW_STALE"
    }
    assert instrument_rules.calls == 2


def test_direct_activation_rejects_changed_current_reference_price(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan_version_id = "direct-plan-version-reference-change"

    class ChangingMarketContext(FakeMarketContext):
        def __init__(self) -> None:
            self.calls = 0

        async def fetch(self, instrument_ref: str, lookback: int) -> MarketContext:
            self.calls += 1
            context = await super().fetch(instrument_ref, lookback)
            if self.calls == 2:
                return context.model_copy(
                    update={
                        "bid_price": "101",
                        "ask_price": "102",
                        "reference_price": "101.5",
                        "source_cutoff": datetime(2026, 7, 20, 0, 1, tzinfo=UTC),
                    }
                )
            return context

    def preview(_self: PostgreSQLPlanningApi, requested_id: str) -> dict[str, Any]:
        result = _direct_activation_preview(requested_id)
        result["order_schedule_spec"] = {
            **result["order_schedule_spec"],
            "price_distribution": {"kind": "SINGLE"},
            "venue_policy": {
                "order_type": "MARKET",
                "time_in_force": None,
            },
        }
        return result

    market_context = ChangingMarketContext()
    monkeypatch.setattr(PostgreSQLPlanningApi, "activation_preview", preview)
    monkeypatch.setattr(
        PostgreSQLPlanningApi,
        "activation_replay",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        PostgreSQLPlanningApi,
        "activate",
        lambda *_args, **_kwargs: pytest.fail(
            "changed reference price must not activate"
        ),
    )
    client = make_client(
        tmp_path,
        market_context_provider=market_context,
        instrument_rules_provider=FakeInstrumentRules(),
    )
    token = csrf(client)
    headers = {"Origin": ORIGIN, "X-CSRFToken": token}
    preview_response = client.post(
        f"/api/v1/plan-versions/{plan_version_id}/activation-preview",
        headers=headers,
    )
    assert preview_response.status_code == 200

    activation_response = client.post(
        "/api/v1/activations",
        json={
            "plan_version_id": plan_version_id,
            "expected_schedule_digest": preview_response.json()[
                "expected_schedule_digest"
            ],
        },
        headers={
            **headers,
            "Idempotency-Key": "activation-direct-reference-change-001",
        },
    )

    assert activation_response.status_code == 409
    assert activation_response.json()["detail"] == {
        "code": "ACTIVATION_PREVIEW_STALE"
    }
    assert market_context.calls == 2


def test_direct_activation_without_a_trusted_preview_is_stale(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        PostgreSQLPlanningApi,
        "activation_preview",
        lambda _self, requested_id: _direct_activation_preview(requested_id),
    )
    monkeypatch.setattr(
        PostgreSQLPlanningApi,
        "activation_replay",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        PostgreSQLPlanningApi,
        "activate",
        lambda *_args, **_kwargs: pytest.fail("stale preview must not activate"),
    )
    client = make_client(
        tmp_path,
        instrument_rules_provider=FakeInstrumentRules(),
    )
    token = csrf(client)

    response = client.post(
        "/api/v1/activations",
        json={
            "plan_version_id": "direct-plan-version-without-preview",
            "expected_schedule_digest": "a" * 64,
        },
        headers={
            "Origin": ORIGIN,
            "X-CSRFToken": token,
            "Idempotency-Key": "activation-direct-preview-missing-001",
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == {"code": "ACTIVATION_PREVIEW_STALE"}


def test_direct_activation_rejects_a_digest_other_than_the_cached_preview(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan_version_id = "direct-plan-version-digest-mismatch"
    monkeypatch.setattr(
        PostgreSQLPlanningApi,
        "activation_preview",
        lambda _self, requested_id: _direct_activation_preview(requested_id),
    )
    monkeypatch.setattr(
        PostgreSQLPlanningApi,
        "activation_replay",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        PostgreSQLPlanningApi,
        "activate",
        lambda *_args, **_kwargs: pytest.fail("mismatched preview must not activate"),
    )
    client = make_client(
        tmp_path,
        instrument_rules_provider=FakeInstrumentRules(),
    )
    token = csrf(client)
    headers = {"Origin": ORIGIN, "X-CSRFToken": token}
    preview_response = client.post(
        f"/api/v1/plan-versions/{plan_version_id}/activation-preview",
        headers=headers,
    )
    assert preview_response.status_code == 200
    expected_digest = preview_response.json()["expected_schedule_digest"]
    mismatched_digest = (
        ("0" if expected_digest[0] != "0" else "1") + expected_digest[1:]
    )

    response = client.post(
        "/api/v1/activations",
        json={
            "plan_version_id": plan_version_id,
            "expected_schedule_digest": mismatched_digest,
        },
        headers={
            **headers,
            "Idempotency-Key": "activation-direct-preview-mismatch-001",
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == {"code": "ACTIVATION_PREVIEW_STALE"}


def test_direct_activation_rejects_an_expired_cached_preview(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan_version_id = "direct-plan-version-expired-preview"
    current_monotonic = [100.0]
    monkeypatch.setattr(
        PostgreSQLPlanningApi,
        "activation_preview",
        lambda _self, requested_id: _direct_activation_preview(requested_id),
    )
    monkeypatch.setattr(
        PostgreSQLPlanningApi,
        "activation_replay",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        PostgreSQLPlanningApi,
        "activate",
        lambda *_args, **_kwargs: pytest.fail("expired preview must not activate"),
    )
    client = make_client(
        tmp_path,
        instrument_rules_provider=FakeInstrumentRules(),
        monotonic_provider=lambda: current_monotonic[0],
    )
    token = csrf(client)
    headers = {"Origin": ORIGIN, "X-CSRFToken": token}
    preview_response = client.post(
        f"/api/v1/plan-versions/{plan_version_id}/activation-preview",
        headers=headers,
    )
    assert preview_response.status_code == 200

    current_monotonic[0] += 60.0
    response = client.post(
        "/api/v1/activations",
        json={
            "plan_version_id": plan_version_id,
            "expected_schedule_digest": preview_response.json()[
                "expected_schedule_digest"
            ],
        },
        headers={
            **headers,
            "Idempotency-Key": "activation-direct-preview-expired-001",
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == {"code": "ACTIVATION_PREVIEW_STALE"}


def test_strategy_activation_without_an_order_schedule_does_not_require_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def preview(_self: PostgreSQLPlanningApi, plan_version_id: str) -> dict[str, Any]:
        return {
            "plan_version_id": plan_version_id,
            "venue_ref": "BINANCE_USDM",
            "instrument_ref": "BTCUSDT-PERP",
            "direction": "LONG",
            "trade_amount": "100",
            "order_schedule_spec": None,
        }

    def activate(
        _self: PostgreSQLPlanningApi,
        _payload: Any,
        **kwargs: Any,
    ) -> dict[str, Any]:
        captured["snapshot"] = kwargs["order_schedule_snapshot"]
        return {
            "activation": {"activation_id": "activation-strategy-001"},
            "venue_write_created": False,
            "runtime_real_write_gate": "CLOSED",
        }

    monkeypatch.setattr(PostgreSQLPlanningApi, "activation_preview", preview)
    monkeypatch.setattr(
        PostgreSQLPlanningApi,
        "activation_replay",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(PostgreSQLPlanningApi, "activate", activate)
    client = make_client(tmp_path)
    token = csrf(client)

    response = client.post(
        "/api/v1/activations",
        json={
            "plan_version_id": "strategy-plan-version-no-schedule",
            "expected_schedule_digest": None,
        },
        headers={
            "Origin": ORIGIN,
            "X-CSRFToken": token,
            "Idempotency-Key": "activation-strategy-no-preview-001",
        },
    )

    assert response.status_code == 201
    assert captured["snapshot"] is None
