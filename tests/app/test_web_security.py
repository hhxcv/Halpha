from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from halpha.app.planning_api import PostgreSQLPlanningApi
from halpha.public_market import (
    MarketBar,
    MarketContext,
    MarketContextProvider,
    MarketWindow,
)
from halpha.app.projection import ProjectionUnavailable
from halpha.app.secrets import AppSecrets
from halpha.app.web import create_app
from halpha.capital.repository import CapitalConflict
from halpha.configuration import load_settings
from halpha.planning.registry import Direction, OneShotParameters
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
        interval: Literal["1m", "15m"],
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


def make_client(
    tmp_path: Path,
    *,
    projection: FakeProjection | None = None,
    market_context_provider: MarketContextProvider | None = None,
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
        static_dist=tmp_path / "missing-dist",
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
