from __future__ import annotations

from contextlib import suppress
import json
from json import JSONDecodeError
import os
from pathlib import Path
import time
from typing import Any
from uuid import uuid4


EXTERNAL_ARTIFACT_REF = "<external-artifact>"


def ensure_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)
    _atomic_write_text(path, f"{text}\n")


def _atomic_write_text(path: Path, text: str) -> None:
    temp_path = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temp_path.open("w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        _replace_with_retry(temp_path, path)
    finally:
        with suppress(OSError):
            if temp_path.exists():
                temp_path.unlink()


def _replace_with_retry(source: Path, target: Path) -> None:
    delays = (0.02, 0.05, 0.1, 0.25, 0.5, 1.0)
    for delay in (*delays, None):
        try:
            os.replace(source, target)
            return
        except OSError as exc:
            if delay is None or not _is_retryable_replace_error(exc):
                raise
            time.sleep(delay)


def _is_retryable_replace_error(exc: OSError) -> bool:
    return isinstance(exc, PermissionError) or getattr(exc, "winerror", None) in {5, 32}


def display_path(path: Path, *, base: Path | None = None, external_ref: str = EXTERNAL_ARTIFACT_REF) -> str:
    base_path = base or Path.cwd()
    if not path.is_absolute():
        if _unsafe_relative_ref(path):
            return external_ref
        return path.as_posix()
    try:
        return path.resolve().relative_to(base_path.resolve()).as_posix()
    except (OSError, ValueError):
        return external_ref


def config_base(config_path: Path) -> Path:
    parent = Path(config_path).parent
    if str(parent) in {"", "."}:
        return Path.cwd()
    return parent


def runtime_root(config_path: Path | None = None) -> Path:
    return Path.cwd()


def artifact_base(config_path: Path | None = None) -> Path:
    return runtime_root(config_path)


def resolve_runtime_path(path: Path | str, *, config_path: Path | None = None) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else runtime_root(config_path) / candidate


def resolve_artifact_path(path: Path | str, *, config_path: Path | None = None) -> Path:
    return resolve_runtime_path(path, config_path=config_path)


def read_json_object(path: Path, *, external_ref_name: str | None = None) -> tuple[dict[str, Any], str | None]:
    if external_ref_name and path.name == external_ref_name:
        return {}, "external artifact reference was rejected."
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}, f"{path.name} was not found."
    except OSError as exc:
        return {}, f"{path.name} could not be read: {exc}."
    except JSONDecodeError as exc:
        return {}, f"{path.name} is not valid JSON: {exc.msg}."
    if not isinstance(loaded, dict):
        return {}, f"{path.name} must be a JSON object."
    return loaded, None


def resolve_local_ref(value: str, *, base: Path, rejected_name: str) -> Path:
    raw = str(value or "").replace("\\", "/").strip()
    path = Path(raw)
    if not raw or (not path.is_absolute() and _unsafe_relative_ref(path)):
        return base / rejected_name
    target = path if path.is_absolute() else base / path
    try:
        target.resolve().relative_to(base.resolve())
    except (OSError, ValueError):
        return base / rejected_name
    return target


def safe_local_ref(
    path: Path,
    *,
    base: Path,
    external_ref: str = EXTERNAL_ARTIFACT_REF,
    rejected_name: str | None = None,
) -> str:
    if rejected_name and path.name == rejected_name:
        return external_ref
    if not path.is_absolute() and _unsafe_relative_ref(path):
        return external_ref
    target = path if path.is_absolute() else base / path
    try:
        return target.resolve().relative_to(base.resolve()).as_posix()
    except (OSError, ValueError):
        return external_ref


def _unsafe_relative_ref(path: Path) -> bool:
    text = str(path).strip()
    if text in {"", "."}:
        return True
    if _looks_like_absolute_path_text(text):
        return True
    return any(part in {"", ".", ".."} for part in path.parts)


def _looks_like_absolute_path_text(value: str) -> bool:
    text = value.strip().replace("\\", "/")
    return text.startswith("/") or _has_windows_drive(text)


def _has_windows_drive(value: str) -> bool:
    return len(value) >= 2 and value[0].isalpha() and value[1] == ":"
