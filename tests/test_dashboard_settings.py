from __future__ import annotations

from pathlib import Path

import pytest

from halpha.config import ConfigError, load_config
from halpha.dashboard.settings import (
    _dashboard_config_temp_path,
    dashboard_config_profile,
    dashboard_save_config_profile,
)


def test_dashboard_settings_profile_excludes_monitor_enable_control(tmp_path: Path) -> None:
    config = {
        "run": {"timezone": "Asia/Shanghai"},
        "dashboard": {"display_timezone": "Asia/Shanghai"},
        "monitor": {"enabled": True, "interval_seconds": 300},
    }

    profile = dashboard_config_profile(config, config_path=tmp_path / "config.local.yaml")

    fields = {field["path"]: field for field in profile["fields"]}
    assert profile["config"]["requires_confirmation"] is True
    assert "monitor.enabled" not in fields
    assert fields["monitor.interval_seconds"]["value"] == 300
    assert str(tmp_path) not in str(profile)


def test_dashboard_settings_save_requires_confirmation(tmp_path: Path) -> None:
    config = {"dashboard": {"display_timezone": "Asia/Shanghai"}}

    result = dashboard_save_config_profile(
        config,
        config_path=tmp_path / "config.local.yaml",
        request={"confirm": False, "changes": {"dashboard.display_timezone": "UTC"}},
    )

    assert result["status"] == "blocked"
    assert config["dashboard"]["display_timezone"] == "Asia/Shanghai"
    assert str(tmp_path) not in str(result)


def test_dashboard_settings_save_uses_unique_temp_file(tmp_path: Path) -> None:
    config_path = tmp_path / "config.local.yaml"

    first = _dashboard_config_temp_path(config_path)
    second = _dashboard_config_temp_path(config_path)

    assert first != second
    assert first.parent == tmp_path
    assert second.parent == tmp_path
    assert first.name.startswith(".config.local.yaml.")
    assert first.name.endswith(".dashboard-save.tmp")
    assert first.name != ".config.local.yaml.dashboard-save.tmp"


def test_dashboard_settings_save_cleans_temp_and_updates_config(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    result = dashboard_save_config_profile(
        config,
        config_path=config_path,
        request={"confirm": True, "changes": {"dashboard.display_timezone": "UTC"}},
    )

    assert result["status"] == "succeeded"
    assert result["changed_paths"] == ["dashboard.display_timezone"]
    assert config["dashboard"]["display_timezone"] == "UTC"
    assert not list(tmp_path.glob(".config.local.yaml.*.dashboard-save.tmp"))
    assert not (tmp_path / ".config.local.yaml.dashboard-save.tmp").exists()
    assert str(tmp_path) not in str(result)


def test_dashboard_settings_save_validation_failure_preserves_config_and_cleans_temp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = _write_config(tmp_path)
    original_text = config_path.read_text(encoding="utf-8")
    config = load_config(config_path)

    def fail_load_config(path: Path) -> dict[str, object]:
        raise ConfigError(f"invalid temporary config: {path}")

    monkeypatch.setattr("halpha.dashboard.settings.load_config", fail_load_config)

    result = dashboard_save_config_profile(
        config,
        config_path=config_path,
        request={"confirm": True, "changes": {"dashboard.display_timezone": "UTC"}},
    )

    assert result["status"] == "failed"
    assert config_path.read_text(encoding="utf-8") == original_text
    assert config["dashboard"]["display_timezone"] == "Asia/Shanghai"
    assert not list(tmp_path.glob(".config.local.yaml.*.dashboard-save.tmp"))
    assert str(tmp_path) not in str(result)


def _write_config(tmp_path: Path) -> Path:
    path = tmp_path / "config.local.yaml"
    path.write_text(
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
dashboard:
  display_timezone: Asia/Shanghai
""".strip(),
        encoding="utf-8",
    )
    return path
