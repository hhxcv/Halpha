"""Read producer-owned registrations for independently managed local services."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
from typing import Any


REGISTRY_ENVIRONMENT_VARIABLE = "HALPHA_EXTERNAL_SERVICE_REGISTRY"
SCHEMA_VERSION = 1
SERVICE_ID_PATTERN = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")


@dataclass(frozen=True)
class ExternalServiceRegistration:
    service_id: str
    pid: int
    listeners: tuple[str, ...]


def registry_directory() -> Path:
    override = os.environ.get(REGISTRY_ENVIRONMENT_VARIABLE)
    if override:
        return Path(override).expanduser().resolve()
    local_data = os.environ.get("LOCALAPPDATA")
    if local_data:
        return Path(local_data) / "Halpha" / "external-services"
    return Path.home() / ".local" / "share" / "Halpha" / "external-services"


def _parse_registration(value: Any) -> ExternalServiceRegistration:
    if not isinstance(value, dict) or value.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported schema")
    service_id = value.get("service_id")
    if not isinstance(service_id, str) or SERVICE_ID_PATTERN.fullmatch(service_id) is None:
        raise ValueError("invalid service id")
    pid = value.get("pid")
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        raise ValueError("invalid pid")
    listeners = value.get("listeners")
    if (
        not isinstance(listeners, list)
        or not listeners
        or any(not isinstance(item, str) or not item for item in listeners)
    ):
        raise ValueError("invalid listeners")
    return ExternalServiceRegistration(
        service_id=service_id,
        pid=pid,
        listeners=tuple(sorted(set(listeners))),
    )


def read_external_service_registrations(
    directory: Path | None = None,
) -> tuple[tuple[ExternalServiceRegistration, ...], tuple[str, ...]]:
    root = directory or registry_directory()
    if not root.exists():
        return (), ()
    if not root.is_dir():
        return (), ("EXTERNAL_REGISTRY_NOT_A_DIRECTORY",)
    registrations: list[ExternalServiceRegistration] = []
    warnings: list[str] = []
    service_ids: set[str] = set()
    try:
        paths = sorted(root.glob("*.json"), key=lambda path: path.name.casefold())
    except OSError as exc:
        return (), (f"EXTERNAL_REGISTRY_READ_FAILED:type={type(exc).__name__}",)
    for path in paths:
        try:
            registration = _parse_registration(
                json.loads(path.read_text(encoding="utf-8"))
            )
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            warnings.append(
                f"EXTERNAL_REGISTRATION_INVALID:{path.name}:type={type(exc).__name__}"
            )
            continue
        if registration.service_id in service_ids:
            warnings.append(
                f"EXTERNAL_REGISTRATION_DUPLICATE:{registration.service_id}"
            )
            continue
        service_ids.add(registration.service_id)
        registrations.append(registration)
    return tuple(registrations), tuple(sorted(warnings))
