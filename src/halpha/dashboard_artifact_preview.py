from __future__ import annotations

import json
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from .storage import config_base


MAX_PREVIEW_CHARS = 20_000
MAX_PREVIEW_ROWS = 100


def dashboard_artifact_preview(config: dict[str, Any], *, config_path: Path, artifact_path: str) -> dict[str, Any]:
    base = config_base(config_path)
    resolved = _resolve_preview_path(artifact_path, base=base)
    if isinstance(resolved, dict):
        return resolved

    path, safe_path = resolved
    redactor = _DashboardPreviewRedactor(config, config_path=config_path)
    if not path.exists():
        return _artifact_preview_error(safe_path, "missing", f"{safe_path} was not found.")
    if not path.is_file():
        return _artifact_preview_error(safe_path, "unsupported", f"{safe_path} is not a file.")
    suffix = path.suffix.lower()
    if suffix in {".sqlite", ".db", ".parquet", ".arrow", ".feather"}:
        return _artifact_preview_error(
            safe_path,
            "unsupported",
            f"{suffix} previews are not expanded by the dashboard artifact preview API.",
        )
    if suffix == ".json":
        return _json_preview(path, safe_path, redactor=redactor)
    if suffix == ".jsonl":
        return _jsonl_preview(path, safe_path, redactor=redactor)
    if suffix in {".md", ".markdown"}:
        return _text_preview(path, safe_path, preview_kind="markdown", redactor=redactor)
    if suffix in {".txt", ".log", ".csv", ".yaml", ".yml"}:
        return _text_preview(path, safe_path, preview_kind="text", redactor=redactor)
    return _artifact_preview_error(
        safe_path,
        "unsupported",
        f"{suffix or 'unknown'} files are not supported by the dashboard artifact preview API.",
    )


def _resolve_preview_path(artifact_path: str, *, base: Path) -> tuple[Path, str] | dict[str, Any]:
    if not artifact_path or not artifact_path.strip():
        return _artifact_preview_error("", "rejected", "artifact path is required.")
    raw_path = artifact_path.replace("\\", "/").strip()
    path = Path(raw_path)
    if path.is_absolute():
        return _artifact_preview_error(raw_path, "rejected", "artifact path must be repo-relative.")
    parts = path.parts
    if any(part in {"", ".", ".."} for part in parts):
        return _artifact_preview_error(raw_path, "rejected", "artifact path must not contain traversal segments.")
    if not parts or parts[0] not in {"runs", "data"}:
        return _artifact_preview_error(raw_path, "rejected", "artifact path must start with runs/ or data/.")
    resolved = (base / path).resolve()
    try:
        resolved.relative_to(base.resolve())
    except ValueError:
        return _artifact_preview_error(raw_path, "rejected", "artifact path must stay under the configured project root.")
    return resolved, path.as_posix()


class _DashboardPreviewRedactor:
    _private_key_parts = {
        "account",
        "cookie",
        "credential",
        "endpoint",
        "host",
        "password",
        "path",
        "port",
        "private",
        "proxy",
        "secret",
        "token",
        "url",
        "user",
    }

    def __init__(self, config: dict[str, Any], *, config_path: Path) -> None:
        self.private_values = _dashboard_private_values(config, config_path=config_path)

    def redact_value(self, value: Any, *, key: str | None = None) -> Any:
        if key and self._is_private_key(key):
            return "<redacted>"
        if isinstance(value, dict):
            return {str(item_key): self.redact_value(item, key=str(item_key)) for item_key, item in value.items()}
        if isinstance(value, list):
            return [self.redact_value(item) for item in value]
        if isinstance(value, str):
            return self.redact_text(value)
        return value

    def redact_text(self, text: str) -> str:
        redacted = text
        for value in self.private_values:
            redacted = redacted.replace(value, "<redacted>")
        return "\n".join(self._redact_private_line(line) for line in redacted.split("\n"))

    def _redact_private_line(self, line: str) -> str:
        stripped = line.lstrip()
        key, separator, value = stripped.partition(":")
        if not separator or not value:
            return line
        clean_key = key.strip().strip("'\"")
        if not clean_key or not self._is_private_key(clean_key):
            return line
        indent = line[: len(line) - len(stripped)]
        return f"{indent}{key}: <redacted>"

    @staticmethod
    def _is_private_key(key: str) -> bool:
        lowered = key.lower()
        if lowered == "report":
            return False
        return any(part in lowered for part in _DashboardPreviewRedactor._private_key_parts)


def _dashboard_private_values(config: dict[str, Any], *, config_path: Path) -> list[str]:
    values = set()
    base = config_base(config_path)
    if base.is_absolute():
        values.update({str(base), base.as_posix()})
    if config_path.is_absolute():
        values.update({str(config_path), config_path.as_posix()})
    try:
        values.update({str(config_path.resolve()), config_path.resolve().as_posix()})
    except OSError:
        pass

    def visit(value: Any, key_path: tuple[str, ...]) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                visit(item, (*key_path, str(key)))
            return
        if isinstance(value, list):
            for item in value:
                visit(item, key_path)
            return
        if not isinstance(value, str) or not value:
            return
        if any(_DashboardPreviewRedactor._is_private_key(key) for key in key_path):
            values.add(value)

    visit(config, ())
    return sorted(values, key=len, reverse=True)


def _json_preview(path: Path, safe_path: str, *, redactor: _DashboardPreviewRedactor) -> dict[str, Any]:
    text, truncated, error = _read_bounded_text(path)
    if error:
        return _artifact_preview_error(safe_path, "failed", error)
    if truncated:
        return _artifact_preview_payload(
            safe_path,
            "json",
            redactor.redact_text(text),
            truncated=True,
            warnings=["JSON file was truncated before parsing."],
        )
    try:
        loaded = json.loads(text)
    except JSONDecodeError as exc:
        return _artifact_preview_error(safe_path, "failed", f"{safe_path} is not valid JSON: {exc.msg}.")
    preview, omitted = _bounded_json(redactor.redact_value(loaded))
    return _artifact_preview_payload(
        safe_path,
        "json",
        preview,
        truncated=False,
        omitted=omitted,
    )


def _jsonl_preview(path: Path, safe_path: str, *, redactor: _DashboardPreviewRedactor) -> dict[str, Any]:
    text, truncated, error = _read_bounded_text(path)
    if error:
        return _artifact_preview_error(safe_path, "failed", error)
    records: list[Any] = []
    parse_errors: list[str] = []
    lines = text.splitlines()
    for index, line in enumerate(lines[:MAX_PREVIEW_ROWS]):
        if not line.strip():
            continue
        try:
            records.append(redactor.redact_value(json.loads(line)))
        except JSONDecodeError as exc:
            parse_errors.append(f"line {index + 1}: {exc.msg}")
            records.append(redactor.redact_text(line))
    omitted_rows = max(0, len(lines) - MAX_PREVIEW_ROWS)
    warnings = []
    if truncated:
        warnings.append("JSONL file was truncated.")
    if parse_errors:
        warnings.append(f"{len(parse_errors)} JSONL line(s) could not be parsed.")
    return _artifact_preview_payload(
        safe_path,
        "jsonl",
        records,
        truncated=truncated or omitted_rows > 0,
        omitted={"rows": omitted_rows, "parse_errors": len(parse_errors)},
        warnings=warnings,
    )


def _text_preview(
    path: Path,
    safe_path: str,
    *,
    preview_kind: str,
    redactor: _DashboardPreviewRedactor,
) -> dict[str, Any]:
    text, truncated, error = _read_bounded_text(path)
    if error:
        return _artifact_preview_error(safe_path, "failed", error)
    return _artifact_preview_payload(safe_path, preview_kind, redactor.redact_text(text), truncated=truncated)


def _read_bounded_text(path: Path) -> tuple[str, bool, str | None]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            text = handle.read(MAX_PREVIEW_CHARS + 1)
    except UnicodeDecodeError:
        return "", False, f"{path.name} is not valid UTF-8 text."
    except OSError as exc:
        return "", False, f"{path.name} could not be read: {exc}"
    truncated = len(text) > MAX_PREVIEW_CHARS
    return text[:MAX_PREVIEW_CHARS], truncated, None


def _bounded_json(value: Any) -> tuple[Any, dict[str, int]]:
    omitted: dict[str, int] = {}
    if isinstance(value, list):
        omitted_count = max(0, len(value) - MAX_PREVIEW_ROWS)
        if omitted_count:
            omitted["items"] = omitted_count
        return value[:MAX_PREVIEW_ROWS], omitted
    if isinstance(value, dict):
        preview: dict[str, Any] = {}
        for key, item in sorted(value.items()):
            if isinstance(item, list):
                preview[str(key)] = item[:MAX_PREVIEW_ROWS]
                omitted_count = max(0, len(item) - MAX_PREVIEW_ROWS)
                if omitted_count:
                    omitted[f"{key}.items"] = omitted_count
            elif isinstance(item, dict):
                preview[str(key)] = _bounded_mapping(item)
            elif isinstance(item, (str, int, float, bool)) or item is None:
                preview[str(key)] = item
            else:
                preview[str(key)] = str(item)
        return preview, omitted
    return value, omitted


def _bounded_mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    bounded: dict[str, Any] = {}
    for key, item in sorted(value.items()):
        if isinstance(item, (str, int, float, bool)) or item is None:
            bounded[str(key)] = item
    return bounded


def _artifact_preview_payload(
    path: str,
    preview_kind: str,
    preview: Any,
    *,
    truncated: bool,
    omitted: dict[str, int] | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "artifact_type": "dashboard_artifact_preview",
        "status": "available",
        "path": path,
        "kind": preview_kind,
        "truncated": truncated,
        "omitted": omitted or {},
        "preview": preview,
        "warnings": warnings or [],
        "errors": [],
    }


def _artifact_preview_error(path: str, status: str, message: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "artifact_type": "dashboard_artifact_preview",
        "status": status,
        "path": path,
        "kind": "unknown",
        "truncated": False,
        "omitted": {},
        "preview": None,
        "warnings": [message] if status in {"missing", "rejected", "unsupported"} else [],
        "errors": [message] if status == "failed" else [],
    }
