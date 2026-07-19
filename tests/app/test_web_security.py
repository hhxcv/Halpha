from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from halpha.app.planning_api import PostgreSQLPlanningApi
from halpha.app.projection import ProjectionUnavailable
from halpha.app.secrets import AppSecrets
from halpha.app.web import create_app
from halpha.capital.repository import CapitalConflict
from halpha.configuration import load_settings
from halpha.user_workbench.repository import CommandConflict


ROOT = Path(__file__).resolve().parents[2]
ORIGIN = "http://127.0.0.1:8765"


class FakeProjection:
    def __init__(
        self,
        *,
        available: bool = True,
        activations: list[dict[str, Any]] | None = None,
    ) -> None:
        self.available = available
        self.activations = activations or []

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


def make_client(
    tmp_path: Path,
    *,
    projection: FakeProjection | None = None,
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
    client = make_client(tmp_path)

    strategies = client.get("/api/v1/strategies")
    schema = client.get(
        "/api/v1/strategies/ONE_SHOT_DONCHIAN_ATR_BREAKOUT/schema"
    )
    status = client.get("/api/v1/settings/status")

    assert strategies.status_code == 200
    assert strategies.json()[0]["strategy_id"] == "ONE_SHOT_DONCHIAN_ATR_BREAKOUT"
    assert schema.status_code == 200
    assert schema.json()["additionalProperties"] is False
    assert status.status_code == 200
    assert status.json()["runtime_real_write_gate"] == "CLOSED"


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
    assert "SAME-PROCESS LIMITED ENTRY" in operations.text
    assert "A Receipt is not a venue result" in operations.text
    assert "No non-completed activation exists" in operations.text
    assert "password" not in operations.text.lower()
    assert "sign out" not in operations.text.lower()
    assert "halpha_csrf" in client.cookies
    assert script.status_code == 200
    assert "Idempotency-Key" in script.text
    assert "password" not in script.text.lower()
    assert missing_static.status_code == 503
    assert client.get("/login").status_code == 404


def test_operations_projects_stable_recovery_state_and_three_controls(
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
        "plan_valid_until": "2026-07-18T00:00:00+00:00",
        "latest_venue_cutoff": "2026-07-17T00:00:00+00:00",
        "max_margin": "100",
        "max_notional": "500",
        "max_allowed_loss": "25",
        "quote_asset": "USDT",
        "activation_loss": "3",
        "max_loss_reached": False,
        "stopped_categories": ["NEW_RISK"],
        "execution_actions": [],
        "venue_facts": [],
        "receipts": [],
    }
    client = make_client(
        tmp_path,
        projection=FakeProjection(activations=[activation]),
    )

    operations = client.get("/operations")

    assert operations.status_code == 200
    assert "WRITER_CONTINUITY_LOST" in operations.text
    assert "NEW_RISK</dt><dd class=\"stopped\">STOPPED" in operations.text
    assert operations.text.count('class="control-button"') == 3
    assert 'data-intent="RESUME_ACTIVATION"' in operations.text
    assert 'data-intent="EXIT_STRATEGY"' in operations.text
    assert 'data-intent="USER_TAKEOVER"' in operations.text


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
    assert "Database</dt><dd>UNKNOWN" in operations.text


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
