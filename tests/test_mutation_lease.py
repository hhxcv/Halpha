from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from halpha.runtime.mutation_lease import MutationLeaseBlocked
from halpha.runtime.mutation_lease import acquire_mutation_lease


@pytest.fixture(autouse=True)
def _isolate_artifact_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


def test_mutation_lease_blocks_second_live_owner_without_private_paths(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    lease = acquire_mutation_lease(
        config_path=config_path,
        owner_kind="test",
        workflow="product_run",
        requested_by="CLI",
        owner_id="owner-a",
        owner_pid=os.getpid(),
    )

    try:
        with pytest.raises(MutationLeaseBlocked) as exc:
            acquire_mutation_lease(
                config_path=config_path,
                owner_kind="test",
                workflow="product_run",
                requested_by="Dashboard",
                owner_id="owner-b",
                owner_pid=os.getpid(),
            )
    finally:
        lease.release()

    details = exc.value.error_details
    assert exc.value.stage == "runtime_mutation_lease"
    assert exc.value.exit_code == 4
    assert "another mutating Halpha workflow" in str(exc.value)
    assert details["status"] == "blocked"
    assert details["database_ref"] == ".halpha/state.sqlite"
    assert details["private_values_embedded"] is False
    assert str(tmp_path) not in json.dumps(details, sort_keys=True)


def test_mutation_lease_reenters_for_same_owner_and_releases_idempotently(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    first = acquire_mutation_lease(
        config_path=config_path,
        owner_kind="pipeline",
        workflow="product_run",
        requested_by="CLI",
        owner_id="shared-owner",
        owner_pid=os.getpid(),
    )
    second = acquire_mutation_lease(
        config_path=config_path,
        owner_kind="pipeline",
        workflow="product_run",
        requested_by="CLI",
        owner_id="shared-owner",
        owner_pid=os.getpid(),
    )

    assert second.reentrant is True
    second.release()
    first.release()
    replacement = acquire_mutation_lease(
        config_path=config_path,
        owner_kind="pipeline",
        workflow="product_run",
        requested_by="CLI",
        owner_id="replacement-owner",
        owner_pid=os.getpid(),
    )
    replacement.release()


def test_mutation_lease_recovers_when_owner_pid_is_dead(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = _write_config(tmp_path)
    stale = acquire_mutation_lease(
        config_path=config_path,
        owner_kind="pipeline",
        workflow="product_run",
        requested_by="CLI",
        owner_id="stale-owner",
        owner_pid=12345,
    )
    monkeypatch.setattr("halpha.runtime.mutation_lease._pid_is_alive", lambda pid: False)

    replacement = acquire_mutation_lease(
        config_path=config_path,
        owner_kind="pipeline",
        workflow="product_run",
        requested_by="CLI",
        owner_id="replacement-owner",
        owner_pid=os.getpid(),
    )

    assert replacement.owner_id == "replacement-owner"
    replacement.release()
    stale.release()


def _write_config(tmp_path: Path) -> Path:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
run:
  output_dir: runs
market:
  enabled: false
text:
  enabled: false
  sources: []
report:
  language: zh-CN
codex:
  enabled: false
""".strip(),
        encoding="utf-8",
    )
    return config_path
