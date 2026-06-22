from __future__ import annotations

import json
from json import JSONDecodeError
from pathlib import Path
from typing import Any


def ensure_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)
    path.write_text(f"{text}\n", encoding="utf-8")


def display_path(path: Path, *, base: Path | None = None) -> str:
    base_path = base or Path.cwd()
    try:
        return path.resolve().relative_to(base_path.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def config_base(config_path: Path) -> Path:
    parent = Path(config_path).parent
    if str(parent) in {"", "."}:
        return Path.cwd()
    return parent


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
    path = Path(value)
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
    external_ref: str = "<external-artifact>",
    rejected_name: str | None = None,
) -> str:
    if rejected_name and path.name == rejected_name:
        return external_ref
    target = path if path.is_absolute() else base / path
    try:
        return target.resolve().relative_to(base.resolve()).as_posix()
    except (OSError, ValueError):
        return external_ref
