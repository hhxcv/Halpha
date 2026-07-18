from __future__ import annotations

from pathlib import Path

from tools.provisioning.provision_windows_tasks import (
    REQUIRED_ACCOUNT_RIGHTS,
    TASK_ACCOUNT_VAULT_SERVICE,
    TASK_INSTANCES_IGNORE_NEW,
    TASK_TRIGGER_DAILY,
    USER_FLAGS,
    WATCHDOG_DURATION,
    WATCHDOG_INTERVAL,
    WATCHDOG_START_BOUNDARY,
    _generate_password,
)


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "provisioning" / "provision_windows_tasks.py"


def test_task_identity_password_is_generated_without_process_transport() -> None:
    first = _generate_password()
    second = _generate_password()
    assert len(first) == 50
    assert first != second
    assert TASK_ACCOUNT_VAULT_SERVICE not in first


def test_task_accounts_are_batch_only_nonexpiring_users() -> None:
    assert "SeBatchLogonRight" in REQUIRED_ACCOUNT_RIGHTS
    assert "SeDenyInteractiveLogonRight" in REQUIRED_ACCOUNT_RIGHTS
    assert "SeDenyRemoteInteractiveLogonRight" in REQUIRED_ACCOUNT_RIGHTS
    assert USER_FLAGS
    assert TASK_INSTANCES_IGNORE_NEW == 2
    assert TASK_TRIGGER_DAILY == 2
    assert WATCHDOG_START_BOUNDARY == "2000-01-01T00:00:00"
    assert WATCHDOG_INTERVAL == "PT1M"
    assert WATCHDOG_DURATION == "P1D"


def test_provisioner_has_no_command_line_or_file_password_bridge() -> None:
    source = SCRIPT.read_text(encoding="utf-8").lower()
    assert "schtasks" not in source
    assert "subprocess" not in source
    assert "password_transport\": \"in_process_com_only" in source
    assert "<password>" in source  # export scan, never XML construction
    assert "pgpassword" not in source
    assert '"backup", "backup", app_user, "halpha.backup", "backup", "daily"' in source
    assert 'watchdog.id = "minutewatchdog"' in source
    assert "settings.restartcount" not in source
    assert "settings.restartinterval" not in source
