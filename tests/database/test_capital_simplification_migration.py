from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REVISION = (
    ROOT
    / "migrations"
    / "versions"
    / "20260720_0007_simplify_activation_capital.py"
)


def _revision_module():
    spec = importlib.util.spec_from_file_location("halpha_capital_simplification", REVISION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_capital_simplification_is_current_migration_head() -> None:
    revision = _revision_module()
    assert revision.revision == "20260720_0007"
    assert revision.down_revision == "20260718_0006"


def test_capital_simplification_removes_the_superseded_storage() -> None:
    source = REVISION.read_text(encoding="utf-8")
    assert "DROP TABLE IF EXISTS halpha.plan_allocation" in source
    assert "DROP TABLE IF EXISTS halpha.machine_authorization_version" in source
    assert "DROP TABLE IF EXISTS halpha.account_capital_limit_version" in source
    assert "DROP COLUMN IF EXISTS authorization_version_ref" in source
    assert "DROP COLUMN IF EXISTS allocation_ref" in source
    assert "NEW_RISK" in source
    assert "ALL_EXCHANGE_CHANGES" in source
