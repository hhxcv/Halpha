from __future__ import annotations

from pathlib import Path

from halpha.runtime.command_job_process import _posix_process_group_alive


def test_posix_process_group_alive_treats_zombie_only_group_as_exited(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _write_proc_stat(tmp_path, pid=101, state="Z", pgrp=7001)

    def fake_killpg(_pgid: int, _signal_number: int) -> None:
        raise AssertionError("proc scan should decide zombie-only process groups before killpg fallback")

    monkeypatch.setattr("halpha.runtime.command_job_process.os.killpg", fake_killpg, raising=False)

    assert _posix_process_group_alive(7001, proc_root=tmp_path) is False


def test_posix_process_group_alive_keeps_group_alive_when_any_member_is_running(tmp_path: Path) -> None:
    _write_proc_stat(tmp_path, pid=101, state="Z", pgrp=7001)
    _write_proc_stat(tmp_path, pid=102, state="S", pgrp=7001)

    assert _posix_process_group_alive(7001, proc_root=tmp_path) is True


def test_posix_process_group_alive_falls_back_to_killpg_without_proc(tmp_path: Path, monkeypatch) -> None:
    calls: list[tuple[int, int]] = []

    def fake_killpg(pgid: int, signal_number: int) -> None:
        calls.append((pgid, signal_number))

    monkeypatch.setattr("halpha.runtime.command_job_process.os.killpg", fake_killpg, raising=False)

    assert _posix_process_group_alive(7001, proc_root=tmp_path / "missing") is True
    assert calls == [(7001, 0)]


def _write_proc_stat(proc_root: Path, *, pid: int, state: str, pgrp: int) -> None:
    proc_dir = proc_root / str(pid)
    proc_dir.mkdir(parents=True)
    # Linux /proc/<pid>/stat fields after comm start with state, ppid, pgrp.
    fields = [
        state,
        "1",
        str(pgrp),
        "1",
        "0",
        "0",
        "0",
        "0",
        "0",
        "0",
        "0",
        "0",
        "0",
        "0",
        "0",
        "0",
        "0",
        "0",
        "0",
        str(10_000 + pid),
        "0",
    ]
    (proc_dir / "stat").write_text(f"{pid} (python) {' '.join(fields)}\n", encoding="utf-8")
