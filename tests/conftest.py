from __future__ import annotations

from datetime import datetime, timezone
import re
import shutil
from pathlib import Path

import pytest


TEST_OUTPUT_ROOT = Path("test-output") / "pytest"
TEST_OUTPUT_KEEP = 10
_SESSION_DIR_RE = re.compile(r"\d{8}T\d{6}Z(?:-\d{2})?")


def pytest_configure(config: pytest.Config) -> None:
    repo_root = Path(str(config.rootpath))
    output_root = repo_root / TEST_OUTPUT_ROOT
    session_dir = _create_test_output_session_dir(output_root)
    _prune_test_output_sessions(output_root, keep=TEST_OUTPUT_KEEP)

    config.option.basetemp = str(session_dir / "tmp")
    config._halpha_test_output_dir = session_dir


@pytest.fixture(scope="session")
def test_output_dir(request: pytest.FixtureRequest) -> Path:
    return Path(str(request.config._halpha_test_output_dir))


@pytest.fixture
def isolate_artifact_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


@pytest.fixture(autouse=True)
def _reject_repo_root_run_artifacts(request: pytest.FixtureRequest):
    repo_root = Path(str(request.config.rootpath))
    runs_dir = repo_root / "runs"
    before = _run_dirs(runs_dir)

    yield

    created = sorted(_run_dirs(runs_dir) - before)
    if not created:
        return
    for name in created:
        path = runs_dir / name
        if path.is_dir():
            shutil.rmtree(path)
    pytest.fail(
        "Tests must not write run artifacts under repo-root runs/: "
        + ", ".join(f"runs/{name}" for name in created)
    )


def _run_dirs(runs_dir: Path) -> set[str]:
    if not runs_dir.is_dir():
        return set()
    return {path.name for path in runs_dir.iterdir() if path.is_dir()}


def _create_test_output_session_dir(output_root: Path) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for suffix in [""] + [f"-{index:02d}" for index in range(1, 100)]:
        session_dir = output_root / f"{timestamp}{suffix}"
        try:
            session_dir.mkdir(parents=True, exist_ok=False)
        except FileExistsError:
            continue
        return session_dir
    raise RuntimeError("could not create a unique pytest output directory")


def _prune_test_output_sessions(output_root: Path, *, keep: int) -> None:
    sessions = sorted(_test_output_sessions(output_root), key=lambda path: path.name, reverse=True)
    for session_dir in sessions[keep:]:
        _remove_test_output_session(output_root, session_dir)


def _test_output_sessions(output_root: Path) -> list[Path]:
    if not output_root.is_dir():
        return []
    return [
        path
        for path in output_root.iterdir()
        if path.is_dir() and not path.is_symlink() and _SESSION_DIR_RE.fullmatch(path.name)
    ]


def _remove_test_output_session(output_root: Path, session_dir: Path) -> None:
    if session_dir.parent != output_root or not _SESSION_DIR_RE.fullmatch(session_dir.name):
        raise RuntimeError(f"refusing to remove unexpected pytest output directory: {session_dir}")
    shutil.rmtree(session_dir)
