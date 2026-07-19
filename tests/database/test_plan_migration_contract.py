from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REVISION = ROOT / "migrations/versions/20260717_0002_plan_runtime_fields.py"


def test_plan_migration_adds_embedded_values_without_record_families() -> None:
    source = REVISION.read_text(encoding="utf-8")
    assert "fixed_strategy_basis" in source
    assert "paused_at" in source
    assert "framework_strategy_id" in source
    assert "reconciliation_digest" in source
    assert "current_resume_command_ref" in source
    assert "entry_opportunity_consumed" in source
    assert "create_table" not in source


def test_stop_scope_version_migration_is_a_separate_linear_revision() -> None:
    source = (
        ROOT / "migrations/versions/20260717_0003_stop_scope_versions.py"
    ).read_text(encoding="utf-8")
    assert 'down_revision = "20260717_0002"' in source
    assert "uq_stop_state_account_scope_version" in source
    assert "uq_stop_state_activation_scope_version" in source
    assert "create_table" not in source


def test_plan_revision_is_linear_after_initial_schema() -> None:
    spec = importlib.util.spec_from_file_location("halpha_plan_revision", REVISION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.revision == "20260717_0002"
    assert module.down_revision == "20260717_0001"
