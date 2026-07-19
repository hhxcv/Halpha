"""Deterministic, non-secret repository source identity helpers."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path, PurePosixPath
import re
from typing import Iterable, Mapping

from halpha.domain_values import content_digest


_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_TEXT_SOURCE_SUFFIXES = frozenset(
    {
        ".cjs",
        ".css",
        ".html",
        ".js",
        ".json",
        ".map",
        ".md",
        ".mjs",
        ".py",
        ".svg",
        ".toml",
        ".ts",
        ".tsx",
        ".txt",
        ".xml",
        ".yaml",
        ".yml",
    }
)

class SourceIdentityError(RuntimeError):
    """A sanitized source-identity failure."""


def source_file_sha256(path: Path) -> str:
    """Hash text with canonical LF line endings and binary files byte-exactly."""

    content = path.read_bytes()
    if path.suffix.lower() in _TEXT_SOURCE_SUFFIXES:
        content = content.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return sha256(content).hexdigest()


def _safe_relative_path(raw_path: str, *, code: str) -> PurePosixPath:
    path = PurePosixPath(raw_path)
    if (
        not raw_path
        or path.is_absolute()
        or path.as_posix() != raw_path
        or ".." in path.parts
        or "\\" in raw_path
        or ":" in raw_path
        or any(ord(character) < 32 for character in raw_path)
    ):
        raise SourceIdentityError(code)
    return path


def capture_source_sha256(
    root: Path,
    patterns: Iterable[str],
) -> dict[str, str]:
    """Hash selected files with platform-stable text and exact binary identity."""

    repository_root = root.resolve()
    files: set[Path] = set()
    for raw_pattern in patterns:
        _safe_relative_path(raw_pattern, code="SOURCE_IDENTITY_PATTERN_UNSAFE")
        matches = tuple(repository_root.glob(raw_pattern))
        if not matches:
            raise SourceIdentityError("SOURCE_IDENTITY_PATTERN_EMPTY")
        matched_file = False
        for match in matches:
            if match.is_symlink():
                raise SourceIdentityError("SOURCE_IDENTITY_SYMLINK_FORBIDDEN")
            resolved = match.resolve()
            if not resolved.is_relative_to(repository_root):
                raise SourceIdentityError("SOURCE_IDENTITY_PATH_OUTSIDE_REPOSITORY")
            if resolved.is_file():
                matched_file = True
                files.add(resolved)
        if not matched_file:
            raise SourceIdentityError("SOURCE_IDENTITY_PATTERN_EMPTY")
    if not files:
        raise SourceIdentityError("SOURCE_IDENTITY_FILE_SET_EMPTY")
    return {
        path.relative_to(repository_root).as_posix(): source_file_sha256(path)
        for path in sorted(files, key=lambda item: item.as_posix())
    }


def capture_stable_source_sha256(
    root: Path,
    patterns: Iterable[str],
) -> dict[str, str]:
    """Capture a source set twice and reject files changing during capture."""

    first = capture_source_sha256(root, patterns)
    second = capture_source_sha256(root, patterns)
    if first != second:
        raise SourceIdentityError("SOURCE_IDENTITY_CHANGED_DURING_CAPTURE")
    return second


def validate_source_sha256(value: Mapping[str, str]) -> dict[str, str]:
    """Validate and deterministically order one frozen source manifest."""

    if not value:
        raise SourceIdentityError("SOURCE_IDENTITY_MANIFEST_EMPTY")
    normalized: dict[str, str] = {}
    for raw_path, digest in value.items():
        _safe_relative_path(raw_path, code="SOURCE_IDENTITY_PATH_UNSAFE")
        if any(character in raw_path for character in "*?[]"):
            raise SourceIdentityError("SOURCE_IDENTITY_PATH_UNSAFE")
        if not isinstance(digest, str) or _SHA256_PATTERN.fullmatch(digest) is None:
            raise SourceIdentityError("SOURCE_IDENTITY_DIGEST_INVALID")
        normalized[raw_path] = digest
    return dict(sorted(normalized.items()))


def source_sha256_digest(value: Mapping[str, str]) -> str:
    """Return the canonical digest of a validated source manifest."""

    return content_digest(validate_source_sha256(value))


def require_source_sha256(
    root: Path,
    *,
    patterns: Iterable[str],
    expected: Mapping[str, str],
) -> dict[str, str]:
    """Reject file content or selected-file-set drift from a frozen manifest."""

    normalized = validate_source_sha256(expected)
    current = capture_source_sha256(root, patterns)
    if current != normalized:
        raise SourceIdentityError("SOURCE_IDENTITY_DRIFT")
    return current
