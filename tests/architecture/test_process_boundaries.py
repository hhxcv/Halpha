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
    settings = load_settings(ROOT / "config" / "halpha.live-read-only.example.toml")
    report = preflight(ProcessRole.EXECUTOR, settings)

    assert report["effective_composition"] == {
        "profile": "BINANCE_LIVE_READ_ONLY",
        "trading_authority": "NONE",
        "data_client_required": True,
        "trading_node_required": True,
        "binance_credentials_required": False,
        "execution_client_required": False,
        "product_database_required": False,
        "halpha_coordinator_required": False,
        "execution_action_repository_required": False,
        "persisted_action_capability_required": False,
        "venue_write_capability": "STRUCTURALLY_ABSENT",
    }


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
