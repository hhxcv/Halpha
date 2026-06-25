from __future__ import annotations

import shutil
from pathlib import Path

import pytest


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
