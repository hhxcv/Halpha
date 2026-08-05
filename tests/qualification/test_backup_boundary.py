from pathlib import Path

from tools.qualification import verify_backup_boundary


class _RunningTask:
    State = verify_backup_boundary.TASK_STATE_RUNNING

    def Stop(self, flags: int) -> None:
        assert flags == 0
        self.State = verify_backup_boundary.TASK_STATE_READY


def test_backup_qualification_stops_a_running_task_before_deletion() -> None:
    task = _RunningTask()

    verify_backup_boundary._stop_task_before_delete(task)

    assert task.State == verify_backup_boundary.TASK_STATE_READY


def test_secret_scan_targets_the_actual_backup_log_directory() -> None:
    source = Path(verify_backup_boundary.__file__).read_text(
        encoding="utf-8"
    )

    assert '"logs" / "maintenance" / "backup"' in source
    assert "BACKUP_MANIFEST_KEYS" in source
