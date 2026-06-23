from __future__ import annotations

from pathlib import Path


DASHBOARD_CONTROL_ROOT = ".halpha/dashboard"


def dashboard_control_path(*parts: str) -> Path:
    return Path.cwd() / DASHBOARD_CONTROL_ROOT / Path(*parts)


def dashboard_control_ref(*parts: str) -> str:
    return Path(DASHBOARD_CONTROL_ROOT, *parts).as_posix()
