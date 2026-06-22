from __future__ import annotations

from typing import Any


def bounded_exception_diagnostic(
    exc: BaseException,
    *,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    diagnostic: dict[str, Any] = {
        "exception_type": type(exc).__name__,
        "traceback_embedded": False,
    }
    if context:
        diagnostic["context"] = {
            str(key): value
            for key, value in sorted(context.items())
            if isinstance(value, (str, int, float, bool)) or value is None
        }
    return diagnostic
