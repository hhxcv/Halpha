from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REVISION = ROOT / "migrations" / "versions" / "20260720_0008_remove_unowned_records.py"


def test_record_cleanup_is_current_migration_head() -> None:
    spec = importlib.util.spec_from_file_location("halpha_record_cleanup", REVISION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.revision == "20260720_0008"
    assert module.down_revision == "20260720_0007"


def test_record_cleanup_removes_only_unowned_tables() -> None:
    source = REVISION.read_text(encoding="utf-8")
    assert "DROP TABLE IF EXISTS halpha.improvement_handoff" in source
    assert "DROP TABLE IF EXISTS halpha.notification" in source
    assert "DROP TABLE IF EXISTS halpha.task" in source
