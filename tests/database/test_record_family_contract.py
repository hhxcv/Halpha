from __future__ import annotations

import importlib.util
from pathlib import Path

from halpha.database.record_families import PRODUCT_RECORD_FAMILIES, RECORD_FAMILY_OWNERS


ROOT = Path(__file__).resolve().parents[2]
REVISION = ROOT / "migrations" / "versions" / "20260717_0001_p0_record_families.py"


def _revision_module():
    spec = importlib.util.spec_from_file_location("halpha_initial_revision", REVISION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_exactly_sixteen_accepted_product_record_families() -> None:
    revision = _revision_module()
    assert len(PRODUCT_RECORD_FAMILIES) == 16
    assert set(revision.PRODUCT_TABLES) == set(PRODUCT_RECORD_FAMILIES)
    assert set(revision.DROP_ORDER) == set(PRODUCT_RECORD_FAMILIES)
    assert len(revision.DROP_ORDER) == 16
    assert list(RECORD_FAMILY_OWNERS.values()).count("TRADEPLAN") == 4
    assert list(RECORD_FAMILY_OWNERS.values()).count("DAT") == 1
    assert list(RECORD_FAMILY_OWNERS.values()).count("CAP") == 4
    assert list(RECORD_FAMILY_OWNERS.values()).count("EXE") == 1
    assert list(RECORD_FAMILY_OWNERS.values()).count("OUT") == 2
    assert list(RECORD_FAMILY_OWNERS.values()).count("UX") == 4


def test_deleted_record_families_are_not_reintroduced() -> None:
    forbidden = {
        "condition_evaluation",
        "observation",
        "fact_window",
        "fact_unknown",
        "fact_correction",
        "ingestion_checkpoint",
        "capital_authorization_check",
        "write_control",
        "submission_attempt",
        "protection_task",
        "reconciliation_item",
    }
    assert forbidden.isdisjoint(PRODUCT_RECORD_FAMILIES)


def test_execution_action_is_one_table_with_environment_pairing() -> None:
    source = REVISION.read_text(encoding="utf-8")
    assert source.count('"execution_action",\n') >= 2
    assert "ck_execution_action_authority_pair" in source
    assert "ck_execution_action_profile_pair" in source
    assert "uq_execution_action_source" in source
    assert "SIMULATED_ACTION" not in source
    assert "PENDING_ACTION" not in source


def test_app_is_not_granted_execution_or_venue_fact_writes() -> None:
    revision = _revision_module()
    source = REVISION.read_text(encoding="utf-8")
    app_block = source.split("app_write = (", 1)[1].split("executor_write = (", 1)[0]
    executor_block = source.split("executor_write = (", 1)[1].split(")\n    for table", 1)[0]
    assert '"execution_action"' not in app_block
    assert '"venue_fact"' not in app_block
    assert '"execution_action"' in executor_block
    assert '"venue_fact"' in executor_block
    assert len(revision.PRODUCT_TABLES) == 16


def test_migration_requires_an_in_memory_connection() -> None:
    env_source = (ROOT / "migrations" / "env.py").read_text(encoding="utf-8")
    launcher_source = (ROOT / "src" / "halpha" / "database" / "migrate.py").read_text(
        encoding="utf-8"
    )
    assert "MIGRATION_CONNECTION_ATTRIBUTE_REQUIRED" in env_source
    assert "sqlalchemy.url" not in env_source
    assert "PGPASSWORD" not in launcher_source
    assert "password=secret" in launcher_source


def test_database_qualification_uses_no_secret_environment_bridge() -> None:
    source = (ROOT / "tools" / "qualification" / "verify_database_boundary.py").read_text(
        encoding="utf-8"
    )
    assert "PGPASSWORD" not in source
    assert "password=secret" in source
    assert "cross_database_demo_app_to_live_rejected" in source
