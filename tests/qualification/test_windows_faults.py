from __future__ import annotations

from types import SimpleNamespace

from tools.qualification import verify_windows_faults as subject


class _Task:
    def __init__(self, *, enabled: bool, state: int) -> None:
        self.Enabled = enabled
        self.State = state


def test_disabled_task_is_already_in_a_valid_stopped_state(monkeypatch) -> None:
    tasks = {
        "app": _Task(enabled=False, state=subject.TASK_DISABLED),
        "executor": _Task(enabled=False, state=subject.TASK_DISABLED),
    }
    signals: list[str] = []
    monkeypatch.setattr(
        subject,
        "_signal_role",
        lambda _settings, role: signals.append(role),
    )
    monkeypatch.setattr(
        subject,
        "_processes_by_module",
        lambda: {"app": [], "executor": []},
    )

    subject._stop_running(SimpleNamespace(), tasks, ("executor", "app"))

    assert signals == []


def test_controlled_stop_suppresses_recovery_trigger_race(monkeypatch) -> None:
    task = _Task(enabled=True, state=subject.TASK_RUNNING)
    tasks = {
        "app": task,
        "executor": _Task(enabled=True, state=subject.TASK_READY),
    }
    enablement_while_signaled: list[bool] = []

    def signal(_settings: object, role: str) -> None:
        enablement_while_signaled.append(tasks[role].Enabled)
        tasks[role].State = subject.TASK_DISABLED

    monkeypatch.setattr(subject, "_signal_role", signal)
    monkeypatch.setattr(
        subject,
        "_processes_by_module",
        lambda: {"app": [], "executor": []},
    )

    subject._stop_running(SimpleNamespace(), tasks, ("app",))

    assert enablement_while_signaled == [False]
    assert task.Enabled is True


def test_task_enablement_can_be_snapshotted_and_restored() -> None:
    tasks = {
        "app": _Task(enabled=False, state=subject.TASK_DISABLED),
        "executor": _Task(enabled=True, state=subject.TASK_READY),
    }
    before = subject._task_enablement(tasks)

    subject._apply_task_enablement(tasks, {"app": True, "executor": True})
    assert subject._task_enablement(tasks) == {"app": True, "executor": True}

    subject._apply_task_enablement(tasks, before)
    assert subject._task_enablement(tasks) == before
