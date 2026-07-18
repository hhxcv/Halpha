from __future__ import annotations

from pathlib import Path
import sys

import pytest

from halpha.runtime_identity import (
    EXPECTED_PYTHON,
    RuntimeIdentityError,
    repository_root,
    require_repository_runtime,
    validate_runtime_identity,
)


def test_actual_test_process_uses_selected_repository_venv() -> None:
    identity = require_repository_runtime()
    assert identity.python_version == "3.13.14"
    assert Path(identity.executable).name.lower() == "python.exe"
    assert repository_root() == Path(__file__).resolve().parents[2]


def test_rejects_wrong_python_version(tmp_path: Path) -> None:
    venv = tmp_path / ".venv"
    executable = venv / "Scripts" / "python.exe"
    with pytest.raises(RuntimeIdentityError, match="PYTHON_VERSION_MISMATCH"):
        validate_runtime_identity(
            tmp_path,
            version_info=(3, 13, 13),
            executable=executable,
            prefix=venv,
            base_prefix=tmp_path / "python313",
        )


def test_rejects_global_interpreter(tmp_path: Path) -> None:
    base = tmp_path / "python313"
    with pytest.raises(RuntimeIdentityError, match="REPOSITORY_VENV_REQUIRED"):
        validate_runtime_identity(
            tmp_path,
            version_info=EXPECTED_PYTHON,
            executable=base / "python.exe",
            prefix=base,
            base_prefix=base,
        )


def test_rejects_venv_outside_repository(tmp_path: Path) -> None:
    other = tmp_path / "other-venv"
    with pytest.raises(RuntimeIdentityError, match="VENV_PREFIX_MISMATCH"):
        validate_runtime_identity(
            tmp_path,
            version_info=EXPECTED_PYTHON,
            executable=other / "Scripts" / "python.exe",
            prefix=other,
            base_prefix=tmp_path / "python313",
        )


def test_test_interpreter_version_is_exact() -> None:
    assert tuple(sys.version_info[:3]) == EXPECTED_PYTHON
