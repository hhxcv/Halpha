from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from halpha.storage import EXTERNAL_ARTIFACT_REF, display_path, resolve_local_ref, safe_local_ref, write_json


def test_write_json_preserves_stable_format(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "artifact.json"

    write_json(path, {"z": 1, "a": {"b": "值"}})

    assert path.read_text(encoding="utf-8") == '{\n  "a": {\n    "b": "值"\n  },\n  "z": 1\n}\n'
    assert json.loads(path.read_text(encoding="utf-8")) == {"a": {"b": "值"}, "z": 1}


def test_write_json_replaces_through_same_directory_temp_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "artifact.json"
    replacements: list[tuple[Path, Path]] = []
    original_replace = os.replace

    def replace(src: Path, dst: Path) -> None:
        replacements.append((Path(src), Path(dst)))
        original_replace(src, dst)

    monkeypatch.setattr("halpha.storage.os.replace", replace)

    write_json(path, {"ok": True})

    assert replacements
    src, dst = replacements[0]
    assert src.parent == path.parent
    assert src.name.startswith(".artifact.json.")
    assert src.name.endswith(".tmp")
    assert dst == path
    assert not src.exists()


def test_write_json_keeps_existing_file_and_cleans_temp_on_replace_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "artifact.json"
    path.write_text('{"old": true}\n', encoding="utf-8")

    def fail_replace(src: Path, dst: Path) -> None:
        raise OSError("replace failed")

    monkeypatch.setattr("halpha.storage.os.replace", fail_replace)

    with pytest.raises(OSError, match="replace failed"):
        write_json(path, {"new": True})

    assert path.read_text(encoding="utf-8") == '{"old": true}\n'
    assert list(tmp_path.glob(".artifact.json.*.tmp")) == []


def test_display_path_keeps_runtime_local_refs(tmp_path: Path) -> None:
    artifact = tmp_path / "runs" / "run-1" / "run_manifest.json"

    assert display_path(artifact, base=tmp_path) == "runs/run-1/run_manifest.json"
    assert display_path(Path("runs/run-1/run_manifest.json"), base=tmp_path) == "runs/run-1/run_manifest.json"


def test_display_path_bounds_external_absolute_refs(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside" / "private.txt"

    assert display_path(outside, base=tmp_path) == EXTERNAL_ARTIFACT_REF
    assert safe_local_ref(outside, base=tmp_path) == EXTERNAL_ARTIFACT_REF


def test_display_path_bounds_windows_shaped_external_refs(tmp_path: Path) -> None:
    windows_path = Path("C:/Users/private/project/config.yaml")

    assert display_path(windows_path, base=tmp_path) == EXTERNAL_ARTIFACT_REF
    assert safe_local_ref(windows_path, base=tmp_path) == EXTERNAL_ARTIFACT_REF


def test_local_ref_helpers_reject_traversal_like_refs(tmp_path: Path) -> None:
    rejected = resolve_local_ref("../private/config.yaml", base=tmp_path, rejected_name=".rejected")

    assert rejected == tmp_path / ".rejected"
    assert display_path(Path("."), base=tmp_path) == EXTERNAL_ARTIFACT_REF
    assert safe_local_ref(Path("."), base=tmp_path) == EXTERNAL_ARTIFACT_REF
    assert display_path(Path("../private/config.yaml"), base=tmp_path) == EXTERNAL_ARTIFACT_REF
    assert safe_local_ref(Path("../private/config.yaml"), base=tmp_path) == EXTERNAL_ARTIFACT_REF
