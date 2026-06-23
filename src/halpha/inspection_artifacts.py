from __future__ import annotations

import json
from dataclasses import dataclass
from json import JSONDecodeError
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class InspectionJsonRead:
    data: dict[str, Any]
    status: str
    error: str | None

    @property
    def is_missing(self) -> bool:
        return self.status == "missing"

    @property
    def is_failed(self) -> bool:
        return self.status == "failed"


def read_inspection_json_object(path: Path) -> InspectionJsonRead:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return InspectionJsonRead({}, "missing", f"{path.name} was not found.")
    except OSError as exc:
        return InspectionJsonRead({}, "failed", f"{path.name} could not be read: {exc}.")
    except JSONDecodeError as exc:
        return InspectionJsonRead({}, "failed", f"{path.name} is not valid JSON: {exc.msg}.")
    if not isinstance(loaded, dict):
        return InspectionJsonRead({}, "failed", f"{path.name} must be a JSON object.")
    return InspectionJsonRead(loaded, "available", None)


def inspection_error_is_missing(error: str | None) -> bool:
    return bool(error and " was not found." in error)


def inspection_json_artifact_status(data: dict[str, Any], error: str | None) -> str:
    if error:
        return "missing" if inspection_error_is_missing(error) else "failed"
    status = str(data.get("status") or "").lower()
    if status in {"failed", "degraded", "warning", "partial", "skipped", "not_generated"}:
        return status
    return "ok"


def inspection_plain_artifact_status(path: Path, *, source_status: str) -> tuple[str, str | None]:
    if not path.is_file():
        return "missing", f"{path.name} was not found."
    status = source_status.lower()
    if status in {"failed", "degraded", "warning", "partial", "skipped", "not_generated"}:
        return status, None
    return "ok", None


def inspection_overall_status(statuses: list[str]) -> str:
    if "failed" in statuses:
        return "failed"
    if "degraded" in statuses:
        return "degraded"
    if "warning" in statuses:
        return "warning"
    return "ok"
