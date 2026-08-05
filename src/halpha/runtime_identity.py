"""Fail-closed checks for the repository-owned Python runtime."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import sys
from typing import Sequence


EXPECTED_PYTHON = (3, 13, 14)


class RuntimeIdentityError(RuntimeError):
    """Raised when a command is not running in the selected repository venv."""


@dataclass(frozen=True)
class RuntimeIdentity:
    python_version: str
    executable: str
    prefix: str
    repository_venv: str


def repository_root() -> Path:
    # Source checkouts and installed wheels both run from the repository-owned
    # ``.venv``.  Deriving the release root from the interpreter remains stable
    # after installation, unlike deriving it from ``halpha.__file__``.
    return Path(sys.prefix).resolve().parent


def _same_path(left: Path, right: Path) -> bool:
    return os.path.normcase(str(left.resolve())) == os.path.normcase(str(right.resolve()))


def validate_runtime_identity(
    repo_root: Path,
    *,
    version_info: Sequence[int],
    executable: Path,
    prefix: Path,
    base_prefix: Path,
) -> RuntimeIdentity:
    actual_version = tuple(version_info[:3])
    if actual_version != EXPECTED_PYTHON:
        raise RuntimeIdentityError(
            f"PYTHON_VERSION_MISMATCH expected={EXPECTED_PYTHON!r} actual={actual_version!r}"
        )

    if _same_path(prefix, base_prefix):
        raise RuntimeIdentityError("REPOSITORY_VENV_REQUIRED sys.prefix equals sys.base_prefix")

    expected_venv = repo_root.resolve() / ".venv"
    expected_executable = expected_venv / "Scripts" / "python.exe"
    if not _same_path(prefix, expected_venv):
        raise RuntimeIdentityError(
            f"VENV_PREFIX_MISMATCH expected={expected_venv} actual={prefix.resolve()}"
        )
    if not _same_path(executable, expected_executable):
        raise RuntimeIdentityError(
            f"PYTHON_EXECUTABLE_MISMATCH expected={expected_executable} actual={executable.resolve()}"
        )

    return RuntimeIdentity(
        python_version=".".join(str(part) for part in actual_version),
        executable=str(executable.resolve()),
        prefix=str(prefix.resolve()),
        repository_venv=str(expected_venv),
    )


def require_repository_runtime(repo_root: Path | None = None) -> RuntimeIdentity:
    root = repository_root() if repo_root is None else repo_root
    return validate_runtime_identity(
        root,
        version_info=sys.version_info,
        executable=Path(sys.executable),
        prefix=Path(sys.prefix),
        base_prefix=Path(sys.base_prefix),
    )
