from __future__ import annotations

from pathlib import Path

from halpha.inspection_artifacts import (
    inspection_json_artifact_status,
    inspection_overall_status,
    inspection_plain_artifact_status,
    read_inspection_json_object,
)


def test_read_inspection_json_object_reports_missing(tmp_path: Path) -> None:
    result = read_inspection_json_object(tmp_path / "state.json")

    assert result.status == "missing"
    assert result.is_missing is True
    assert result.data == {}
    assert result.error == "state.json was not found."


def test_read_inspection_json_object_reports_invalid_json(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    path.write_text("{not json", encoding="utf-8")

    result = read_inspection_json_object(path)

    assert result.status == "failed"
    assert result.is_failed is True
    assert result.data == {}
    assert result.error == "state.json is not valid JSON: Expecting property name enclosed in double quotes."


def test_read_inspection_json_object_reports_non_object_json(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    path.write_text("[]", encoding="utf-8")

    result = read_inspection_json_object(path)

    assert result.status == "failed"
    assert result.data == {}
    assert result.error == "state.json must be a JSON object."


def test_read_inspection_json_object_reports_read_error(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "state.json"

    def blocked_read_text(self: Path, *args: object, **kwargs: object) -> str:
        if self == path:
            raise OSError("permission denied")
        return original_read_text(self, *args, **kwargs)

    original_read_text = Path.read_text
    monkeypatch.setattr(Path, "read_text", blocked_read_text)

    result = read_inspection_json_object(path)

    assert result.status == "failed"
    assert result.data == {}
    assert result.error == "state.json could not be read: permission denied."


def test_inspection_artifact_status_helpers(tmp_path: Path) -> None:
    missing_error = "state.json was not found."
    invalid_error = "state.json is not valid JSON: bad."

    assert inspection_json_artifact_status({}, missing_error) == "missing"
    assert inspection_json_artifact_status({}, invalid_error) == "failed"
    assert inspection_json_artifact_status({"status": "warning"}, None) == "warning"
    assert inspection_json_artifact_status({"status": "succeeded"}, None) == "ok"
    assert inspection_plain_artifact_status(tmp_path / "missing.md", source_status="ok") == (
        "missing",
        "missing.md was not found.",
    )
    assert inspection_overall_status(["ok", "warning"]) == "warning"
    assert inspection_overall_status(["ok", "failed"]) == "failed"
