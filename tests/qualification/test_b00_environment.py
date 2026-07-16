from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _run_json_probe(relative_path: str) -> dict[str, object]:
    completed = subprocess.run(
        [sys.executable, str(REPOSITORY_ROOT / relative_path)],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def test_repository_venv_is_exact_and_isolated() -> None:
    evidence = _run_json_probe("tools/qualification/verify_venv.py")
    assert evidence["status"] == "QUALIFIED"
    assert evidence["errors"] == []


def test_b00_components_and_winvault_backend_are_exact() -> None:
    evidence = _run_json_probe("tools/qualification/verify_components.py")
    assert evidence["status"] == "QUALIFIED"
    assert evidence["errors"] == []
    assert evidence["keyring_backend"] == "keyring.backends.Windows.WinVaultKeyring"


def test_b00_lock_requires_hashes_and_official_index() -> None:
    lock_text = (REPOSITORY_ROOT / "requirements/b00.txt").read_text(encoding="utf-8")
    assert (
        "--index-url https://pypi.org/simple" in lock_text
        or "--index-url=https://pypi.org/simple" in lock_text
    )
    assert "--trusted-host" not in lock_text
    assert "--extra-index-url" not in lock_text
    assert "--hash=sha256:" in lock_text


def test_repository_venv_is_git_ignored() -> None:
    completed = subprocess.run(
        ["git", "check-ignore", ".venv"],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0


def test_windows_primitives_match_b00_contract() -> None:
    evidence = _run_json_probe("tools/qualification/probe_windows_primitives.py")
    assert evidence["status"] == "QUALIFIED"
    assert evidence["errors"] == []


def test_nautilus_node_and_controller_public_lifecycle() -> None:
    evidence = _run_json_probe("tools/qualification/probe_nautilus_lifecycle.py")
    assert evidence["status"] == "QUALIFIED"
    assert evidence["errors"] == []
