from __future__ import annotations

import subprocess
import sys
from typing import Any


def hidden_subprocess_kwargs(
    *,
    new_process_group: bool = False,
    detached: bool = False,
    platform: str | None = None,
) -> dict[str, Any]:
    """Return subprocess kwargs that keep Windows background launches invisible."""

    if (platform or sys.platform) != "win32":
        return {}

    creationflags = 0
    if new_process_group:
        creationflags |= int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
    if detached:
        creationflags |= int(getattr(subprocess, "DETACHED_PROCESS", 0))
    creationflags |= int(getattr(subprocess, "CREATE_NO_WINDOW", 0))

    kwargs: dict[str, Any] = {}
    if creationflags:
        kwargs["creationflags"] = creationflags

    startupinfo = _hidden_startupinfo()
    if startupinfo is not None:
        kwargs["startupinfo"] = startupinfo
    return kwargs


def _hidden_startupinfo() -> Any | None:
    startupinfo_factory = getattr(subprocess, "STARTUPINFO", None)
    if startupinfo_factory is None:
        return None
    startupinfo = startupinfo_factory()
    startupinfo.dwFlags |= int(getattr(subprocess, "STARTF_USESHOWWINDOW", 1))
    startupinfo.wShowWindow = int(getattr(subprocess, "SW_HIDE", 0))
    return startupinfo
