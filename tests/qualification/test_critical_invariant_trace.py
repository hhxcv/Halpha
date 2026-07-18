from __future__ import annotations

import json
from pathlib import Path

from tools.qualification.verify_critical_invariant_trace import (
    DEFAULT_REGISTRY,
    DELIVERY_HORIZONS,
    REQUIRED_FIELDS,
    compute_record_digest,
    validate_registry,
)


def test_current_registry_is_exact_and_current() -> None:
    registry = json.loads(DEFAULT_REGISTRY.read_text(encoding="utf-8"))
    errors, actual_digests = validate_registry(registry)
    assert errors == []
    assert {record["delivery_horizon"] for record in registry["records"]} == DELIVERY_HORIZONS
    assert all(set(record) == REQUIRED_FIELDS for record in registry["records"])
    assert actual_digests == {
        record["requirement_id"]: record["evidence_digest"]
        for record in registry["records"]
    }


def test_tracked_file_change_invalidates_digest(tmp_path: Path) -> None:
    (tmp_path / "spec.md").write_text("accepted", encoding="utf-8")
    (tmp_path / "implementation.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "test_impl.py").write_text("def test_value(): pass\n", encoding="utf-8")
    record = {
        "requirement_id": "TEST-001",
        "spec_source": ["spec.md"],
        "delivery_horizon": "P0_REQUIRED",
        "implementation_paths": ["implementation.py"],
        "forbidden_calls": ["forbidden.call"],
        "tests": ["test_impl.py"],
        "build_gate": ["pytest test_impl.py"],
        "evidence_digest": "PENDING",
        "implementation_status": "PARTIAL",
        "deviation_status": "NONE",
    }
    before = compute_record_digest(record, root=tmp_path, baseline_patterns=())
    (tmp_path / "implementation.py").write_text("VALUE = 2\n", encoding="utf-8")
    after = compute_record_digest(record, root=tmp_path, baseline_patterns=())
    assert before != after
