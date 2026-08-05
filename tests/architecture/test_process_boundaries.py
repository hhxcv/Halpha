from __future__ import annotations

import ast
from pathlib import Path

from halpha.configuration import load_settings
from halpha.process_contract import PROCESS_CONTRACTS, ProcessRole, preflight


ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = ROOT / "src" / "halpha"


def _imports_under(path: Path) -> set[str]:
    imports: set[str] = set()
    for source in sorted(path.rglob("*.py")):
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module)
    return imports


def _assert_no_prefix(imports: set[str], forbidden: tuple[str, ...]) -> None:
    violations = sorted(
        imported
        for imported in imports
        if any(imported == prefix or imported.startswith(f"{prefix}.") for prefix in forbidden)
    )
    assert violations == []


def test_app_source_cannot_import_executor_or_venue_capabilities() -> None:
    _assert_no_prefix(
        _imports_under(SOURCE_ROOT / "app"),
        ("halpha.executor", "halpha.venue_integration", "nautilus_trader"),
    )


def test_executor_source_cannot_import_web_owner_or_notification_capabilities() -> None:
    _assert_no_prefix(
        _imports_under(SOURCE_ROOT / "executor"),
        ("halpha.app", "halpha.user_workbench", "fastapi", "starlette", "smtplib", "email"),
    )


def test_process_secret_capabilities_are_not_shared() -> None:
    app = PROCESS_CONTRACTS[ProcessRole.APP]
    executor = PROCESS_CONTRACTS[ProcessRole.EXECUTOR]
    assert "binance_credentials" in app.forbidden_capabilities
    assert "csrf_signing_secret" in executor.forbidden_capabilities
    assert "local_web_api" in executor.forbidden_capabilities
    assert "smtp_credentials" in executor.forbidden_capabilities
    assert "nautilus_trading_node" in app.forbidden_capabilities
    assert "binance_public_read_only" in app.allowed_capabilities
    assert "binance_private_connection" in app.forbidden_capabilities


def test_preflight_starts_no_product_or_external_runtime() -> None:
    settings = load_settings(ROOT / "config" / "halpha.example.toml")
    report = preflight(ProcessRole.EXECUTOR, settings)
    assert report["status"] == "PREFLIGHT_OK"
    assert report["external_connections_started"] is False
    assert report["product_runtime_started"] is False
    assert report["runtime_real_write_gate"] == "CLOSED"
    assert report["configuration"]["validated"] is True
    assert "binance_api_key_reference" not in str(report)


def test_live_read_only_preflight_declares_the_capability_trimmed_composition() -> None:
    settings = load_settings(ROOT / "config" / "halpha.live-copy-read-only.example.toml")
    report = preflight(ProcessRole.EXECUTOR, settings)

    contract = report["process_contract"]
    assert set(contract["allowed_capabilities"]) == {
        "postgresql_executor_boundary",
        "binance_credential_reference",
        "binance_private_read_only",
        "binance_public_read_only",
        "nautilus_trading_node",
        "account_snapshot_observer",
        "venue_fact_append",
    }
    assert {
        "halpha_coordinator",
        "execution_client",
        "execution_action_repository",
        "persisted_action_capability",
        "venue_write",
    }.issubset(contract["forbidden_capabilities"])
    assert report["effective_composition"] == {
        "profile": "BINANCE_LIVE_READ_ONLY",
        "trading_authority": "NONE",
        "data_client_required": True,
        "trading_node_required": True,
        "read_only_mode": "PRIVATE_ACCOUNT_OBSERVATION",
        "binance_credentials_required": True,
        "execution_client_required": False,
        "product_database_required": True,
        "account_snapshot_observer_required": True,
        "venue_fact_append_required": True,
        "halpha_coordinator_required": False,
        "execution_action_repository_required": False,
        "persisted_action_capability_required": False,
        "venue_write_capability": "STRUCTURALLY_ABSENT",
    }


def test_public_forward_observation_keeps_private_capabilities_absent() -> None:
    configured = load_settings(
        ROOT / "config" / "halpha.live-copy-read-only.example.toml"
    )
    executor = configured.executor.model_dump(mode="json")
    executor["binance_api_key_reference"] = None
    executor["binance_api_secret_reference"] = None
    settings = load_settings(
        ROOT / "config" / "halpha.live-copy-read-only.example.toml",
        constructor_values={"executor": executor},
    )

    report = preflight(ProcessRole.EXECUTOR, settings)

    contract = report["process_contract"]
    assert "strategy_observation_adapter" in contract["allowed_capabilities"]
    assert "forward_observation_evidence" in contract["allowed_capabilities"]
    assert "binance_credentials" in contract["forbidden_capabilities"]
    assert "postgresql_executor_boundary" in contract["forbidden_capabilities"]
    assert report["effective_composition"]["read_only_mode"] == (
        "PUBLIC_FORWARD_OBSERVATION"
    )
    assert report["effective_composition"]["product_database_required"] is False


def test_only_the_qualified_nautilus_client_calls_adapter_private_write_hops() -> None:
    calls = {
        "_submit_persisted_order",
        "_cancel_persisted_order",
        "_query_persisted_order",
    }
    callers: set[str] = set()
    for source in sorted(SOURCE_ROOT.rglob("*.py")):
        if source.name == "adapter.py":
            continue
        text = source.read_text(encoding="utf-8")
        if any(f".{name}(" in text for name in calls):
            callers.add(source.relative_to(SOURCE_ROOT).as_posix())
    assert callers == {"venue_integration/nautilus_client.py"}


def test_demo_and_live_do_not_have_parallel_execution_implementations() -> None:
    sources = {
        source.relative_to(SOURCE_ROOT).as_posix(): source.read_text(encoding="utf-8")
        for source in sorted(SOURCE_ROOT.rglob("*.py"))
    }
    forbidden_types = {
        "DemoExecutionAction",
        "LiveExecutionAction",
        "DemoExecutionRepository",
        "LiveExecutionRepository",
        "SimulatedExecutionAction",
    }
    assert not any(
        forbidden in text
        for text in sources.values()
        for forbidden in forbidden_types
    )
