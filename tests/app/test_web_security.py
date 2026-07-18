from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from pwdlib import PasswordHash

from halpha.app.projection import ProjectionUnavailable
from halpha.app.planning_api import PostgreSQLPlanningApi
from halpha.app.secrets import AppSecrets
from halpha.app.web import create_app
from halpha.capital.repository import CapitalConflict
from halpha.configuration import load_settings
from halpha.user_workbench.repository import CommandConflict


ROOT = Path(__file__).resolve().parents[2]
PASSWORD = "correct horse battery staple"
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
            "open_task_count": 0,
            "open_activation_count": 0,
            "database_name": "halpha_demo",
        }

    def availability(self) -> dict[str, Any]:
        if self.available:
            return {
                "database_available": True,
                "reason_code": None,
                "server_fact_cutoff": "2026-07-17T00:00:00Z",
            }
        return {
            "database_available": False,
            "reason_code": "DATABASE_UNAVAILABLE",
            "server_fact_cutoff": None,
        }

    def operations(self) -> dict[str, Any]:
        if not self.available:
            raise ProjectionUnavailable("DATABASE_UNAVAILABLE")
        return {
            "database_available": True,
            "server_fact_cutoff": "2026-07-17T00:00:00Z",
            "activations": self.activations,
        }


@pytest.fixture(scope="module")
def owner_hash() -> str:
    return PasswordHash.recommended().hash(PASSWORD)


def make_client(
    tmp_path: Path,
    owner_hash: str,
    *,
    projection: FakeProjection | None = None,
    clock: list[float] | None = None,
) -> TestClient:
    settings = load_settings(ROOT / "config" / "halpha.example.toml")
    app = create_app(
        settings,
        AppSecrets(
            database_password=SecretStr("database-test-secret"),
            owner_password_hash=SecretStr(owner_hash),
            session_signing_secret=SecretStr("session-test-secret-which-is-not-shared"),
            csrf_signing_secret=SecretStr("csrf-test-secret-which-is-not-shared"),
        ),
        repo_root=ROOT,
        projection=projection or FakeProjection(),
        now=(lambda: clock[0]) if clock is not None else (lambda: 1_000_000.0),
        static_dist=tmp_path / "missing-dist",
    )
    return TestClient(app, base_url=ORIGIN)


def csrf(client: TestClient) -> str:
    response = client.get("/operations")
    assert response.status_code == 200
    token = client.cookies.get("halpha_csrf")
    assert token
    return token


def login(client: TestClient, password: str = PASSWORD):
    return client.post(
        "/api/v1/session/login",
        json={"password": password},
        headers={"Origin": ORIGIN, "X-CSRFToken": csrf(client)},
    )


def test_login_session_and_authenticated_read_surface(
    tmp_path: Path, owner_hash: str
) -> None:
    client = make_client(tmp_path, owner_hash)
    assert client.get("/api/v1/overview").status_code == 401

    response = login(client)
    assert response.status_code == 200
    assert response.json() == {
        "status": "AUTHENTICATED",
        "absolute_expires_in_seconds": 1800,
    }
    cookie = response.headers["set-cookie"].lower()
    assert "halpha_owner_session=" in cookie
    assert "httponly" in cookie
    assert "samesite=strict" in cookie
    assert "; secure" not in cookie

    overview = client.get("/api/v1/overview")
    assert overview.status_code == 200
    assert overview.json()["environment_kind"] == "DEMO"
    assert overview.json()["runtime_real_write_gate"] == "CLOSED"
    assert overview.json()["open_task_count"] == 0
    assert "password" not in overview.text.lower()


def test_b02_strategy_schema_and_unsafe_transport_headers(
    tmp_path: Path, owner_hash: str
) -> None:
    client = make_client(tmp_path, owner_hash)
    assert login(client).status_code == 200
    strategies = client.get("/api/v1/strategies")
    assert strategies.status_code == 200
    assert strategies.json()[0]["strategy_id"] == "ONE_SHOT_DONCHIAN_ATR_BREAKOUT"
    schema = client.get(
        "/api/v1/strategies/ONE_SHOT_DONCHIAN_ATR_BREAKOUT/schema"
    )
    assert schema.status_code == 200
    assert schema.json()["additionalProperties"] is False
    missing_idempotency = client.post(
        "/api/v1/plans",
        json={},
        headers={
            "Origin": ORIGIN,
            "X-CSRFToken": client.cookies.get("halpha_csrf"),
        },
    )
    assert missing_idempotency.status_code == 422
    wrong_reauthentication = client.post(
        "/api/v1/activations",
        json={
            "plan_version_id": "plan-version",
            "capital_limit_version_id": "capital-limit",
            "quote_asset": "USDT",
            "owner_password": "wrong",
        },
        headers={
            "Origin": ORIGIN,
            "X-CSRFToken": client.cookies.get("halpha_csrf"),
            "Idempotency-Key": "activation-test",
        },
    )
    assert wrong_reauthentication.status_code == 401
    assert wrong_reauthentication.json()["detail"]["code"] == "REAUTHENTICATION_FAILED"
    status = client.get("/api/v1/settings/status").json()
    assert status["construction_package"] == "B04"
    assert status["runtime_real_write_gate"] == "CLOSED"
    untrusted_reconciliation = client.post(
        "/api/v1/activations/not-a-real-activation/resume",
        json={
            "expected_version": 1,
            "owner_password": PASSWORD,
            "reconciliation_digest": "a" * 64,
            "takeover_scope": {},
        },
        headers={
            "Origin": ORIGIN,
            "X-CSRFToken": client.cookies.get("halpha_csrf"),
            "Idempotency-Key": "untrusted-reconciliation",
        },
    )
    assert untrusted_reconciliation.status_code == 422


def test_csrf_host_origin_and_authorization_boundaries(
    tmp_path: Path, owner_hash: str
) -> None:
    client = make_client(tmp_path, owner_hash)
    token = csrf(client)
    assert client.post(
        "/api/v1/session/login",
        json={"password": PASSWORD},
        headers={"Origin": ORIGIN},
    ).status_code == 403
    assert client.post(
        "/api/v1/session/login",
        json={"password": PASSWORD},
        headers={"Origin": "http://example.test", "X-CSRFToken": token},
    ).status_code == 403
    assert client.post(
        "/api/v1/session/login",
        json={"password": PASSWORD},
        headers={"X-CSRFToken": token},
    ).status_code == 403
    assert client.get("/operations", headers={"Host": "example.test"}).status_code == 400
    bearer = client.get("/operations", headers={"Authorization": "Bearer forbidden"})
    assert bearer.status_code == 400
    assert bearer.json()["detail"]["code"] == "AUTHORIZATION_HEADER_FORBIDDEN"


def test_failed_login_limit_and_success_clear(tmp_path: Path, owner_hash: str) -> None:
    client = make_client(tmp_path, owner_hash)
    token = csrf(client)
    for _ in range(5):
        response = client.post(
            "/api/v1/session/login",
            json={"password": "wrong"},
            headers={"Origin": ORIGIN, "X-CSRFToken": token},
        )
        assert response.status_code == 401
    limited = client.post(
        "/api/v1/session/login",
        json={"password": PASSWORD},
        headers={"Origin": ORIGIN, "X-CSRFToken": token},
    )
    assert limited.status_code == 429
    assert int(limited.headers["Retry-After"]) > 0

    fresh = make_client(tmp_path, owner_hash)
    token = csrf(fresh)
    assert fresh.post(
        "/api/v1/session/login",
        json={"password": "wrong"},
        headers={"Origin": ORIGIN, "X-CSRFToken": token},
    ).status_code == 401
    assert login(fresh).status_code == 200
    assert fresh.post(
        "/api/v1/session/logout",
        json={},
        headers={"Origin": ORIGIN, "X-CSRFToken": fresh.cookies.get("halpha_csrf")},
    ).status_code == 200
    assert login(fresh).status_code == 200


def test_absolute_session_expiry_is_not_sliding(tmp_path: Path, owner_hash: str) -> None:
    clock = [1000.0]
    client = make_client(tmp_path, owner_hash, clock=clock)
    assert login(client).status_code == 200
    clock[0] = 2799.0
    assert client.get("/api/v1/overview").status_code == 200
    clock[0] = 2800.0
    assert client.get("/api/v1/overview").status_code == 401


def test_operations_remains_usable_without_static_dist(
    tmp_path: Path, owner_hash: str
) -> None:
    client = make_client(tmp_path, owner_hash)
    page = client.get("/operations")
    assert page.status_code == 200
    assert "same local-owner credential" in page.text
    assert "halpha_csrf" in client.cookies
    token = client.cookies.get("halpha_csrf")
    result = client.post(
        "/api/v1/session/login",
        data={"password": PASSWORD, "csrftoken": token},
        headers={"Origin": ORIGIN},
        follow_redirects=False,
    )
    assert result.status_code == 303
    operations = client.get("/operations")
    assert operations.status_code == 200
    assert "B02 · SAME-PROCESS LIMITED ENTRY" in operations.text
    assert "A Receipt is not a venue result" in operations.text
    assert "No non-completed activation exists" in operations.text
    script = client.get("/operations.js")
    assert script.status_code == 200
    assert script.headers["content-type"].startswith("application/javascript")
    assert "Idempotency-Key" in script.text
    direct = make_client(tmp_path, owner_hash).get("/overview", follow_redirects=False)
    assert direct.status_code == 307
    assert direct.headers["location"] == "/login"


def test_operations_projects_stable_recovery_state_and_three_controls(
    tmp_path: Path, owner_hash: str
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
        "authorization_valid_until": "2026-07-18T00:00:00+00:00",
        "latest_venue_cutoff": "2026-07-17T00:00:00+00:00",
        "allocation_status": "HELD",
        "max_margin": "100",
        "max_notional": "500",
        "max_allowed_loss": "25",
        "quote_asset": "USDT",
        "current_margin": "40",
        "current_notional": "200",
        "activation_loss": "3",
        "max_loss_reached": False,
        "stopped_categories": ["NEW_FUNDING"],
        "execution_actions": [
            {
                "action_kind": "PROTECTION",
                "state": "WORKING",
                "client_order_id": "0123456789abcdef0123456789abcdef",
                "updated_at": "2026-07-17T00:00:00+00:00",
            }
        ],
        "venue_facts": [
            {
                "kind": "POSITION_STATE",
                "source_object_id": "BTCUSDT",
                "cutoff": "2026-07-17T00:00:00+00:00",
            }
        ],
        "receipts": [
            {
                "intent": "EXIT_STRATEGY",
                "state": "PROCESSING",
                "receipt_id": "4f5040cc-4187-40a3-a141-f807a8b69393",
                "reason_code": "EXIT_RESPONSIBILITY_ACCEPTED",
                "updated_at": "2026-07-17T00:00:00+00:00",
            }
        ],
    }
    client = make_client(
        tmp_path,
        owner_hash,
        projection=FakeProjection(activations=[activation]),
    )
    assert login(client).status_code == 200
    operations = client.get("/operations")
    assert operations.status_code == 200
    assert "WRITER_CONTINUITY_LOST" in operations.text
    assert "NEW_FUNDING</dt><dd class=\"stopped\">STOPPED" in operations.text
    assert "PROTECTION</dt><dd class=\"clear\">CLEAR" in operations.text
    assert operations.text.count('class="control-button"') == 3
    assert 'data-intent="RESUME_ACTIVATION"' in operations.text
    assert 'data-intent="EXIT_STRATEGY"' in operations.text
    assert 'data-intent="USER_TAKEOVER"' in operations.text
    assert "<code>PROCESSING</code> means responsibility remains open" in operations.text
    assert "4f5040cc-4187-40a3-a141-f807a8b69393" in operations.text
    assert "POSITION_STATE" in operations.text
    assert "0123456789abcdef0123456789abcdef" in operations.text


def test_unavailable_database_is_truthful_and_fail_closed(
    tmp_path: Path, owner_hash: str
) -> None:
    client = make_client(tmp_path, owner_hash, projection=FakeProjection(available=False))
    assert login(client).status_code == 200
    overview = client.get("/api/v1/overview")
    assert overview.status_code == 503
    assert overview.json()["detail"]["code"] == "DATABASE_FACTS_UNAVAILABLE"
    status = client.get("/api/v1/settings/status")
    assert status.status_code == 200
    assert status.json()["database_available"] is False
    assert status.json()["database_reason_code"] == "DATABASE_UNAVAILABLE"
    operations = client.get("/operations")
    assert "Database</dt><dd>UNKNOWN" in operations.text


def test_security_headers_and_openapi_boundary(tmp_path: Path, owner_hash: str) -> None:
    client = make_client(tmp_path, owner_hash)
    response = client.get("/operations")
    assert response.headers["cache-control"] == "no-store"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert response.headers["referrer-policy"] == "same-origin"
    assert response.headers["x-content-type-options"] == "nosniff"
    schema = client.get("/api/v1/openapi.json").json()
    assert "/operations" not in schema["paths"]
    assert "/api/v1/session/login" in schema["paths"]
    serialized = str(schema).lower()
    assert "session-test-secret" not in serialized
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
    owner_hash: str,
    monkeypatch: pytest.MonkeyPatch,
    conflict: RuntimeError,
    code: str,
) -> None:
    def raise_conflict(_self: PostgreSQLPlanningApi) -> dict[str, Any]:
        raise conflict

    monkeypatch.setattr(PostgreSQLPlanningApi, "capital_snapshot", raise_conflict)
    client = make_client(tmp_path, owner_hash)
    assert login(client).status_code == 200
    response = client.get("/api/v1/capital")
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == code
