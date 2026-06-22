from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from halpha.config import ConfigError, load_config
from halpha.dashboard.settings import (
    CONFIG_PROFILE_FIELDS,
    CONFIG_PROFILE_SECTIONS,
    _dashboard_config_temp_path,
    dashboard_config_profile,
    dashboard_save_config_profile,
)


EXPECTED_EDITABLE_CONFIG_PATHS = {
    "codex.enabled",
    "dashboard.display_timezone",
    "macro_calendar.enabled",
    "market.derivatives.enabled",
    "market.enabled",
    "market.ohlcv.lookback.1d",
    "market.ohlcv.lookback.1h",
    "market.ohlcv.timeframes",
    "market.proxy.enabled",
    "market.source",
    "market.symbols",
    "monitor.cooldown_seconds",
    "monitor.interval_seconds",
    "monitor.max_cycles",
    "monitor.no_codex",
    "onchain_flow.enabled",
    "quant.enabled",
    "report.language",
    "report.title",
    "run.timezone",
    "text.enabled",
    "text.intelligence.allow_model_download",
    "text.intelligence.enabled",
    "text.max_items",
}
NON_EDITABLE_CONFIG_PATTERNS = (
    "codex.args",
    "codex.command",
    "codex.timeout_seconds",
    "market.ohlcv.storage_dir",
    "monitor.enabled",
    "monitor.output_dir",
    "monitor.target_stage",
    "quant.effectiveness_gates.**",
    "quant.engine",
    "quant.parameter_diagnostics.**",
    "quant.strategies[].**",
    "run.output_dir",
    "text.intelligence.model_cache_dir",
    "text.intelligence.models.**",
    "text.intelligence.thresholds.**",
    "text.sources[].**",
    "user_state.**",
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


def test_dashboard_settings_field_contract_is_explicit() -> None:
    paths = [str(field["path"]) for field in CONFIG_PROFILE_FIELDS]

    assert set(paths) == EXPECTED_EDITABLE_CONFIG_PATHS
    assert len(paths) == len(set(paths))
    for field in CONFIG_PROFILE_FIELDS:
        assert field["section"] in CONFIG_PROFILE_SECTIONS
        assert field["control"] in {"multi_select", "number", "select", "tags", "text", "toggle"}
        assert field["value_type"] in {"bool", "positive_int", "string", "string_list"}
        if field["control"] in {"multi_select", "select"}:
            assert field.get("options")
        assert str(field["description"]).strip()


def test_dashboard_settings_config_example_paths_are_classified() -> None:
    config = load_config(Path("config.example.yaml"))
    leaf_paths = set(_config_leaf_paths(config))
    classified_paths = {path for path in leaf_paths if path in EXPECTED_EDITABLE_CONFIG_PATHS or _is_non_editable_path(path)}

    assert EXPECTED_EDITABLE_CONFIG_PATHS <= leaf_paths
    assert classified_paths == leaf_paths


def test_dashboard_settings_profile_does_not_expose_local_private_config_values() -> None:
    config = load_config(Path("config.example.yaml"))
    profile = dashboard_config_profile(config, config_path=Path("config.example.yaml"))
    fields = {field["path"]: field for field in profile["fields"]}

    for forbidden in [
        "codex.args",
        "codex.command",
        "codex.timeout_seconds",
        "market.proxy.url",
        "monitor.enabled",
        "text.intelligence.model_cache_dir",
        "text.sources[].url",
        "user_state.path",
    ]:
        assert forbidden not in fields
    profile_text = str(profile)
    assert "https://cointelegraph.com/rss" not in profile_text
    assert "https://www.coindesk.com/arc/outboundfeeds/rss/" not in profile_text
    assert "user_state.local.yaml" not in profile_text


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


def _config_leaf_paths(value: Any, prefix: str = "") -> list[str]:
    if isinstance(value, dict):
        paths: list[str] = []
        for key, child in value.items():
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            paths.extend(_config_leaf_paths(child, child_prefix))
        return paths
    if isinstance(value, list):
        if not value:
            return [prefix]
        if all(not isinstance(item, (dict, list)) for item in value):
            return [prefix]
        paths = []
        for item in value:
            paths.extend(_config_leaf_paths(item, f"{prefix}[]"))
        return sorted(set(paths))
    return [prefix]


def _is_non_editable_path(path: str) -> bool:
    return any(_matches_pattern(path, pattern) for pattern in NON_EDITABLE_CONFIG_PATTERNS)


def _matches_pattern(path: str, pattern: str) -> bool:
    escaped = re.escape(pattern)
    regex = escaped.replace(r"\*\*", r".*").replace(r"\*", r"[^.]+")
    return re.fullmatch(regex, path) is not None
