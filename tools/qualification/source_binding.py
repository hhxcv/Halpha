"""Qualification-facing wrapper for the single source-identity implementation."""

from pathlib import Path
from typing import Iterable

from halpha.source_identity import (
    SourceIdentityError,
    capture_source_sha256 as _capture_source_sha256,
)


class SourceBindingError(SourceIdentityError):
    """Backward-compatible qualification source-binding failure."""


def capture_source_sha256(
    root: Path,
    patterns: Iterable[str],
) -> dict[str, str]:
    try:
        return _capture_source_sha256(root, patterns)
    except SourceIdentityError as exc:
        raise SourceBindingError(
            str(exc).replace("SOURCE_IDENTITY_", "SOURCE_BINDING_", 1)
        ) from None


__all__ = ["SourceBindingError", "capture_source_sha256"]
