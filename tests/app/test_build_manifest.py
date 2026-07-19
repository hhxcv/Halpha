from __future__ import annotations

from pathlib import Path

from halpha.build_manifest import (
    DEFAULT_ARTIFACT_SPECS,
    SCHEMA_VERSION,
    ArtifactSpec,
    _artifact_bindings,
)

def test_missing_product_input_is_reported_without_evidence_semantics(tmp_path: Path) -> None:
    binding = _artifact_bindings(tmp_path, (ArtifactSpec("runtime", "runtime.txt"),))[0]

    assert binding == {
        "name": "runtime",
        "path": "runtime.txt",
        "required": True,
        "status": "MISSING",
        "sha256": None,
        "file_count": 0,
    }


def test_schema_three_binds_only_product_inputs() -> None:
    names = {spec.name for spec in DEFAULT_ARTIFACT_SPECS}
    assert SCHEMA_VERSION == 3
    assert names == {
        "python_runtime_lock",
        "npm_lock",
        "halpha_wheel",
        "database_migrations",
        "frontend_dist",
        "strategy_registry",
        "nonsecret_runtime_config",
        "nonsecret_live_write_config",
        "windows_task_definitions",
    }
    assert len(names) == len(DEFAULT_ARTIFACT_SPECS)
