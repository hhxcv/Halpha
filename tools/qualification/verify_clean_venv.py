"""Rebuild an isolated qualification venv from the exact hash lock."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from typing import Any, Sequence


EXPECTED_PYTHON = "3.13.14"


class CleanVenvQualificationError(RuntimeError):
    """Sanitized isolated-venv qualification failure."""


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _run(command: Sequence[str], *, cwd: Path) -> str:
    result = subprocess.run(
        list(command),
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        executable = Path(command[0]).name
        raise CleanVenvQualificationError(
            f"CLEAN_VENV_COMMAND_FAILED executable={executable} code={result.returncode}"
        )
    return result.stdout.strip()


def qualify(
    root: Path,
    *,
    base_python: Path,
    venv_path: Path,
    lock_path: Path,
    wheel_path: Path,
) -> dict[str, Any]:
    if venv_path.exists():
        raise CleanVenvQualificationError("CLEAN_VENV_PATH_ALREADY_EXISTS")
    for path, reason in (
        (base_python, "BASE_PYTHON_MISSING"),
        (lock_path, "CLEAN_VENV_LOCK_MISSING"),
        (wheel_path, "CLEAN_VENV_WHEEL_MISSING"),
    ):
        if not path.is_file():
            raise CleanVenvQualificationError(reason)
    base_version = _run(
        (str(base_python), "-c", "import platform; print(platform.python_version())"),
        cwd=root,
    )
    if base_version != EXPECTED_PYTHON:
        raise CleanVenvQualificationError(
            f"CLEAN_VENV_PYTHON_VERSION_MISMATCH expected={EXPECTED_PYTHON} actual={base_version}"
        )
    _run((str(base_python), "-m", "venv", str(venv_path)), cwd=root)
    python = venv_path / "Scripts" / "python.exe"
    _run(
        (
            str(python),
            "-m",
            "pip",
            "install",
            "--require-hashes",
            "--disable-pip-version-check",
            "-r",
            str(lock_path),
        ),
        cwd=root,
    )
    _run(
        (
            str(python),
            "-m",
            "pip",
            "install",
            "--no-deps",
            "--force-reinstall",
            str(wheel_path),
        ),
        cwd=root,
    )
    pip_check = _run((str(python), "-m", "pip", "check"), cwd=root)
    runtime_version = _run(
        (str(python), "-c", "import platform; print(platform.python_version())"),
        cwd=root,
    )
    package_inventory = json.loads(
        _run((str(python), "-m", "pip", "list", "--format=json"), cwd=root)
    )
    import_path = _run(
        (str(python), "-c", "import halpha; print(halpha.__file__)"),
        cwd=root,
    )
    app_preflight = json.loads(
        _run(
            (
                str(python),
                "-m",
                "halpha.app",
                "--config",
                str(root / "config" / "halpha.toml"),
                "--preflight-only",
            ),
            cwd=root,
        )
    )
    executor_preflight = json.loads(
        _run(
            (
                str(python),
                "-m",
                "halpha.executor",
                "--config",
                str(root / "config" / "halpha.toml"),
                "--preflight-only",
            ),
            cwd=root,
        )
    )
    site_packages = (venv_path / "Lib" / "site-packages").resolve()
    import_from_isolated_venv = Path(import_path).resolve().is_relative_to(site_packages)
    evidence: dict[str, Any] = {
        "schema_version": 1,
        "observed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "base_python": str(base_python),
        "base_python_version": base_version,
        "isolated_venv": str(venv_path.relative_to(root)),
        "runtime_python_version": runtime_version,
        "lock": {
            "path": str(lock_path.relative_to(root)).replace("\\", "/"),
            "sha256": _sha256_file(lock_path),
            "install_mode": "PIP_REQUIRE_HASHES",
        },
        "wheel": {
            "path": str(wheel_path.relative_to(root)).replace("\\", "/"),
            "sha256": _sha256_file(wheel_path),
            "install_mode": "NO_DEPS_FORCE_REINSTALL",
        },
        "installed_package_count": len(package_inventory),
        "pip_check": pip_check,
        "halpha_import_from_isolated_venv": import_from_isolated_venv,
        "app_preflight": app_preflight,
        "executor_preflight": executor_preflight,
    }
    evidence["status"] = (
        "QUALIFIED"
        if runtime_version == EXPECTED_PYTHON
        and pip_check == "No broken requirements found."
        and import_from_isolated_venv
        and app_preflight.get("status") == "PREFLIGHT_OK"
        and executor_preflight.get("status") == "PREFLIGHT_OK"
        else "REJECTED"
    )
    canonical = json.dumps(
        evidence,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    evidence["evidence_digest"] = sha256(canonical.encode("utf-8")).hexdigest()
    return evidence


def _write(path: Path, evidence: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-python", type=Path, required=True)
    parser.add_argument("--venv", type=Path, required=True)
    parser.add_argument("--lock", type=Path, required=True)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    root = Path.cwd().resolve()
    venv_path = args.venv.resolve()
    output = args.output.resolve()
    if not venv_path.is_relative_to(root / "build") or not output.is_relative_to(root):
        raise CleanVenvQualificationError("CLEAN_VENV_PATH_OUTSIDE_QUALIFICATION_SCOPE")
    evidence = qualify(
        root,
        base_python=args.base_python.resolve(),
        venv_path=venv_path,
        lock_path=args.lock.resolve(),
        wheel_path=args.wheel.resolve(),
    )
    _write(output, evidence)
    print(json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if evidence["status"] == "QUALIFIED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
