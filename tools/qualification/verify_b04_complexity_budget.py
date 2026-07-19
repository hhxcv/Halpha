"""Qualify that the implemented P0 topology stays small and single-path."""

from __future__ import annotations

import argparse
import ast
from datetime import UTC, datetime
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tomllib
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from halpha.backup import POSTGRESQL_VERSION
from halpha.database.record_families import (
    PRODUCT_RECORD_FAMILIES,
    RECORD_FAMILY_OWNERS,
)
from halpha.process_contract import PROCESS_CONTRACTS, ProcessRole
from halpha.executor.runtime import build_product_node_config


DEFAULT_OUTPUT = ROOT / "build/qualification/b04-complexity-budget.json"
MIGRATION_PATH = Path("migrations/versions/20260717_0001_p0_record_families.py")
EXPECTED_PROCESS_ENTRYPOINTS = {
    "halpha-app": "halpha.app.__main__:main",
    "halpha-executor": "halpha.executor.__main__:main",
}
EXPECTED_AUXILIARY_ENTRYPOINTS = {
    "halpha-auth": "halpha.app.auth_cli:main",
    "halpha-backup": "halpha.backup:main",
    "halpha-control": "halpha.control:main",
}
EXPECTED_ACTION_REPOSITORY_USERS = {
    "executor/coordinator.py",
    "executor/runtime.py",
    "venue_integration/gateway.py",
    "venue_integration/repository.py",
    "venue_integration/service.py",
}
ALTERNATIVE_DATABASE_IMPORT_PREFIXES = (
    "aiomysql",
    "asyncpg",
    "cassandra",
    "clickhouse",
    "duckdb",
    "motor",
    "mysql",
    "pymongo",
    "pymysql",
    "redis",
)
PARALLEL_EXECUTION_TYPE_NAMES = {
    "DemoExecutionAction",
    "LiveExecutionAction",
    "DemoExecutionRepository",
    "LiveExecutionRepository",
    "SimulatedExecutionAction",
}


class B04ComplexityError(RuntimeError):
    """Sanitized B04 complexity qualification failure."""


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _python_sources(root: Path) -> dict[str, str]:
    source_root = root / "src/halpha"
    return {
        path.relative_to(source_root).as_posix(): path.read_text(encoding="utf-8")
        for path in sorted(source_root.rglob("*.py"))
    }


def _class_inventory(sources: dict[str, str]) -> dict[str, str]:
    inventory: dict[str, str] = {}
    for relative, text in sources.items():
        tree = ast.parse(text, filename=relative)
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                inventory[f"{relative}:{node.name}"] = node.name
    return inventory


def _imports(sources: dict[str, str]) -> set[str]:
    imported: set[str] = set()
    for relative, text in sources.items():
        tree = ast.parse(text, filename=relative)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
    return imported


def _callers(sources: dict[str, str], names: Iterable[str]) -> set[str]:
    calls = tuple(f".{name}(" for name in names)
    return {
        relative
        for relative, text in sources.items()
        if relative != "planning/adapter.py" and any(call in text for call in calls)
    }


def _revision_module(root: Path) -> Any:
    path = root / MIGRATION_PATH
    spec = importlib.util.spec_from_file_location("halpha_b04_complexity_revision", path)
    if spec is None or spec.loader is None:
        raise B04ComplexityError("B04_COMPLEXITY_MIGRATION_IMPORT_UNAVAILABLE")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _git_head(root: Path) -> str:
    return subprocess.run(
        ("git", "rev-parse", "HEAD"),
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.strip()


def build_evidence(root: Path = ROOT) -> dict[str, Any]:
    root = root.resolve()
    sources = _python_sources(root)
    classes = _class_inventory(sources)
    imports = _imports(sources)
    revision = _revision_module(root)
    pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    scripts = pyproject["project"]["scripts"]
    runtime_requirements = (root / "requirements/runtime.in").read_text(
        encoding="utf-8"
    )

    process_roles = {role.value for role in ProcessRole}
    product_entrypoints = {
        name: scripts.get(name) for name in sorted(process_roles)
    }
    auxiliary_entrypoints = {
        name: scripts.get(name) for name in sorted(EXPECTED_AUXILIARY_ENTRYPOINTS)
    }
    repository_users = {
        relative
        for relative, text in sources.items()
        if "PostgreSQLExecutionActionRepository" in text
    }
    private_write_callers = _callers(
        sources,
        (
            "_submit_persisted_order",
            "_cancel_persisted_order",
            "_query_persisted_order",
        ),
    )
    alternative_database_imports = sorted(
        imported
        for imported in imports
        if any(
            imported == prefix or imported.startswith(f"{prefix}.")
            for prefix in ALTERNATIVE_DATABASE_IMPORT_PREFIXES
        )
    )
    parallel_execution_types = sorted(
        forbidden
        for forbidden in PARALLEL_EXECUTION_TYPE_NAMES
        if any(forbidden in text for text in sources.values())
    )
    database_driver_lines = sorted(
        line.strip()
        for line in runtime_requirements.splitlines()
        if line.strip().lower().startswith(
            ("psycopg", "asyncpg", "redis", "pymongo", "pymysql", "mysqlclient")
        )
    )
    read_only_node, read_only_provider, read_only_data, read_only_execution = (
        build_product_node_config(
            "BINANCE_LIVE_READ_ONLY",
            api_key=None,
            api_secret=None,
            log_directory=Path("logs"),
        )
    )

    checks = {
        "record_family_inventory_matches_the_migration": (
            len(set(PRODUCT_RECORD_FAMILIES)) == len(PRODUCT_RECORD_FAMILIES)
            and set(revision.PRODUCT_TABLES) == set(PRODUCT_RECORD_FAMILIES)
            and set(revision.DROP_ORDER) == set(PRODUCT_RECORD_FAMILIES)
            and set(RECORD_FAMILY_OWNERS) == set(PRODUCT_RECORD_FAMILIES)
        ),
        "runtime_ownership_matches_the_process_contract": set(PROCESS_CONTRACTS)
        == set(ProcessRole),
        "runtime_process_inventory_is_exactly_two": (
            process_roles == set(EXPECTED_PROCESS_ENTRYPOINTS)
            and product_entrypoints == EXPECTED_PROCESS_ENTRYPOINTS
            and auxiliary_entrypoints == EXPECTED_AUXILIARY_ENTRYPOINTS
        ),
        "authoritative_database_product_is_only_postgresql": database_driver_lines
        == ["psycopg[binary]==3.3.4"]
        and alternative_database_imports == [],
        "real_risk_authorization_path_is_single_cap_repository": {
            identity
            for identity in classes
            if identity.endswith(":PostgreSQLCapitalRepository")
        }
        == {"capital/repository.py:PostgreSQLCapitalRepository"},
        "venue_write_pipeline_is_single_qualified_client": (
            private_write_callers == {"venue_integration/nautilus_client.py"}
            and repository_users == EXPECTED_ACTION_REPOSITORY_USERS
            and {
                identity
                for identity in classes
                if identity.endswith(":NautilusVenueExecutionClient")
            }
            == {"venue_integration/nautilus_client.py:NautilusVenueExecutionClient"}
            and parallel_execution_types == []
        ),
        "no_general_worker_or_database_platform_import_is_present": (
            alternative_database_imports == []
            and not any(
                imported == prefix or imported.startswith(f"{prefix}.")
                for imported in imports
                for prefix in ("celery", "dramatiq", "kafka", "kombu", "rq")
            )
        ),
        "live_read_only_reuses_executor_without_a_write_topology": (
            read_only_data.instrument_provider is read_only_provider
            and read_only_data.api_key is None
            and read_only_data.api_secret is None
            and read_only_provider.query_commission_rates is False
            and read_only_execution is None
            and read_only_node.exec_clients == {}
            and read_only_node.exec_engine.reconciliation is False
            and read_only_node.exec_engine.generate_missing_orders is False
            and read_only_node.controller is not None
            and read_only_node.controller.controller_path
            == "halpha.executor.runtime:HalphaRuntimeController"
        ),
    }

    evidence: dict[str, Any] = {
        "schema_version": 1,
        "stage": "B04_IMPLEMENTED_COMPLEXITY_BUDGET",
        "observed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "source_revision": _git_head(root),
        "workflow_run_id": None,
        "workflow_conclusion": "NOT_RUN_UNCOMMITTED",
        "superseded_by": None,
        "checks": checks,
        "observations": {
            "physical_record_family_count": len(PRODUCT_RECORD_FAMILIES),
            "record_family_owners": dict(sorted(RECORD_FAMILY_OWNERS.items())),
            "runtime_process_entrypoints": product_entrypoints,
            "auxiliary_one_shot_entrypoints": auxiliary_entrypoints,
            "authoritative_database_products": [f"PostgreSQL {POSTGRESQL_VERSION}"],
            "database_driver_requirements": database_driver_lines,
            "real_risk_authorization_paths": [
                "capital/repository.py:PostgreSQLCapitalRepository"
            ],
            "real_venue_write_pipelines": [
                "venue_integration/nautilus_client.py:NautilusVenueExecutionClient"
            ],
            "execution_action_repository_users": sorted(repository_users),
            "private_persisted_write_hop_callers": sorted(private_write_callers),
            "parallel_execution_types": parallel_execution_types,
            "alternative_database_imports": alternative_database_imports,
            "persistent_worker_delta": 0,
            "record_family_delta": 0,
            "runtime_process_delta": 0,
            "database_product_delta": 0,
            "venue_write_pipeline_delta": 0,
            "live_read_only_topology": {
                "product_process": "halpha-executor",
                "data_client_count": len(read_only_node.data_clients),
                "binance_credential_count": 0,
                "instrument_commission_query_enabled": read_only_provider.query_commission_rates,
                "execution_client_count": len(read_only_node.exec_clients),
                "execution_reconciliation_enabled": read_only_node.exec_engine.reconciliation,
                "new_persistent_worker_count": 0,
                "new_record_family_count": 0,
                "new_write_pipeline_count": 0,
            },
        },
        "source_sha256": {
            relative: _sha256_file(root / relative)
            for relative in (
                MIGRATION_PATH.as_posix(),
                "pyproject.toml",
                "requirements/runtime.in",
                "src/halpha/database/record_families.py",
                "src/halpha/process_contract.py",
                "src/halpha/app/notifications.py",
                "src/halpha/executor/coordinator.py",
                "src/halpha/executor/runtime.py",
                "src/halpha/executor/forward_observation.py",
                "src/halpha/source_identity.py",
                "src/halpha/venue_integration/nautilus_client.py",
                "src/halpha/venue_integration/repository.py",
                "tools/qualification/verify_b04_complexity_budget.py",
            )
        },
        "scope": "STATIC_IMPLEMENTATION_INVENTORY_NO_DATABASE_OR_VENUE_CONNECTION",
        "errors": [],
    }
    evidence["status"] = (
        "QUALIFIED" if checks and all(checks.values()) else "REJECTED"
    )
    if evidence["status"] != "QUALIFIED":
        evidence["errors"] = sorted(name for name, passed in checks.items() if not passed)
    evidence["evidence_digest"] = sha256(_canonical(evidence)).hexdigest()
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    root = args.repository_root.resolve()
    output = args.output.resolve()
    if not output.is_relative_to(root):
        raise B04ComplexityError("B04_COMPLEXITY_OUTPUT_OUTSIDE_REPOSITORY")
    evidence = build_evidence(root)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(f"{output.suffix}.tmp")
    temporary.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    temporary.replace(output)
    print(json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if evidence["status"] == "QUALIFIED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
