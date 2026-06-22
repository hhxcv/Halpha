from __future__ import annotations

from pathlib import Path

from halpha.dashboard.settings import dashboard_config_profile, dashboard_save_config_profile


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
