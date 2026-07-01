from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from halpha.config import ConfigError, load_config
from halpha.dashboard.settings import (
    CONFIG_PROFILE_FIELDS,
    CONFIG_PROFILE_SECTIONS,
    LIVE_TRIGGER_THRESHOLD_FIELDS,
    _dashboard_config_temp_path,
    dashboard_config_ref,
    dashboard_config_profile,
    dashboard_save_config_profile,
)
from halpha.live.contracts import (
    LIVE_DATA_TYPES,
    LIVE_REPORT_TRIGGER_JOB_INTENTS,
    LIVE_TRIGGER_IDS,
)
from halpha.live.triggers import LiveTriggerEvaluator


LIVE_EDITABLE_CONFIG_PATHS = {
    "live.enabled",
    "live.tick_seconds",
    "live.reports.daily.enabled",
    *(
        f"live.collections.{data_type}.{suffix}"
        for data_type in LIVE_DATA_TYPES
        for suffix in ("enabled", "cadence_seconds", "lookback_seconds")
    ),
    "live.collections.macro_calendar.lookahead_seconds",
    *(
        f"live.reports.triggers.{trigger_id}.{suffix}"
        for trigger_id in LIVE_TRIGGER_IDS
        for suffix in ("enabled", "cooldown_seconds", "job_intent", "confirm_codex")
    ),
    *(
        f"live.reports.triggers.{trigger_id}.{field_name}"
        for trigger_id, field_specs in LIVE_TRIGGER_THRESHOLD_FIELDS.items()
        for field_name, _label, _value_type, _description in field_specs
    ),
}


EXPECTED_EDITABLE_CONFIG_PATHS = {
    "codex.enabled",
    "dashboard.display_timezone",
    "dashboard.timestamp_date_order",
    "dashboard.timestamp_hour_cycle",
    *LIVE_EDITABLE_CONFIG_PATHS,
    "macro_calendar.data_classes",
    "macro_calendar.enabled",
    "macro_calendar.lookahead_days",
    "macro_calendar.lookback_days",
    "macro_calendar.regions",
    "macro_calendar.source",
    "market.anomalies.enabled",
    "market.derivatives.data_classes",
    "market.derivatives.enabled",
    "market.derivatives.lookback.12h",
    "market.derivatives.lookback.15m",
    "market.derivatives.lookback.1d",
    "market.derivatives.lookback.1h",
    "market.derivatives.lookback.2h",
    "market.derivatives.lookback.30m",
    "market.derivatives.lookback.4h",
    "market.derivatives.lookback.5m",
    "market.derivatives.lookback.6h",
    "market.derivatives.lookback.8h",
    "market.derivatives.periods",
    "market.derivatives.source",
    "market.derivatives.symbols",
    "market.enabled",
    "market.ohlcv.lookback.15m",
    "market.ohlcv.lookback.1d",
    "market.ohlcv.lookback.1h",
    "market.ohlcv.lookback.1m",
    "market.ohlcv.lookback.1M",
    "market.ohlcv.lookback.1w",
    "market.ohlcv.lookback.4h",
    "market.ohlcv.lookback.5m",
    "market.ohlcv.sources",
    "market.ohlcv.timeframes",
    "market.proxy.enabled",
    "market.source",
    "market.symbols",
    "monitor.cooldown_seconds",
    "monitor.failure_backoff_max_seconds",
    "monitor.interval_seconds",
    "monitor.max_cycles",
    "monitor.no_codex",
    "onchain_flow.assets",
    "onchain_flow.chains",
    "onchain_flow.data_classes",
    "onchain_flow.enabled",
    "onchain_flow.lookback_days",
    "onchain_flow.source",
    "quant.enabled",
    "report.language",
    "report.title",
    "run.timezone",
    "text.enabled",
    "text.intelligence.allow_model_download",
    "text.intelligence.enabled",
    "text.intelligence.model_cache_dir",
    "text.intelligence.models.classifier.name",
    "text.intelligence.models.classifier.provider",
    "text.intelligence.models.classifier.revision",
    "text.intelligence.models.embedding.name",
    "text.intelligence.models.embedding.provider",
    "text.intelligence.models.embedding.revision",
    "text.intelligence.models.ner.name",
    "text.intelligence.models.ner.provider",
    "text.intelligence.models.ner.revision",
    "text.intelligence.models.sentiment.name",
    "text.intelligence.models.sentiment.provider",
    "text.intelligence.models.sentiment.revision",
    "text.intelligence.thresholds.classifier_accept_score",
    "text.intelligence.thresholds.classifier_top_margin",
    "text.intelligence.thresholds.duplicate_similarity",
    "text.intelligence.thresholds.entity_accept_score",
    "text.intelligence.thresholds.max_topic_window_hours",
    "text.intelligence.thresholds.same_topic_similarity",
    "text.max_items",
}
NON_EDITABLE_CONFIG_PATTERNS = (
    "codex.args",
    "codex.command",
    "codex.timeout_seconds",
    "logging.output_dir",
    "macro_calendar.source_url",
    "market.ohlcv.storage_dir",
    "market.proxy.url",
    "monitor.enabled",
    "monitor.output_dir",
    "monitor.source_cadence_seconds.*",
    "monitor.target_stage",
    "onchain_flow.chain_activity_source_url",
    "onchain_flow.network_congestion_source_url",
    "onchain_flow.stablecoin_source_url",
    "quant.effectiveness_gates.**",
    "quant.engine",
    "quant.parameter_diagnostics.**",
    "quant.strategies[].**",
    "run.output_dir",
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
        assert field["value_type"] in {
            "bool",
            "positive_int",
            "positive_number",
            "string",
            "string_list",
            "unit_interval_number",
        }
        if field["control"] in {"multi_select", "select"}:
            assert field.get("options")
        assert str(field["description"]).strip()


def test_dashboard_settings_config_example_paths_are_classified() -> None:
    config = load_config(Path("config.example.yaml"))
    leaf_paths = set(_config_leaf_paths(config))
    classified_paths = {path for path in leaf_paths if path in EXPECTED_EDITABLE_CONFIG_PATHS or _is_non_editable_path(path)}

    assert classified_paths == leaf_paths


def test_dashboard_settings_profile_does_not_expose_local_private_config_values() -> None:
    config = load_config(Path("config.example.yaml"))
    profile = dashboard_config_profile(config, config_path=Path("config.example.yaml"))
    fields = {field["path"]: field for field in profile["fields"]}

    for forbidden in [
        "codex.args",
        "codex.command",
        "codex.timeout_seconds",
        "macro_calendar.source_url",
        "market.proxy.url",
        "monitor.enabled",
        "onchain_flow.chain_activity_source_url",
        "onchain_flow.network_congestion_source_url",
        "onchain_flow.stablecoin_source_url",
        "live.reports.triggers.market_breakout.codex_authorization",
        "text.sources[].url",
        "user_state.path",
    ]:
        assert forbidden not in fields
    profile_text = str(profile)
    assert "https://cointelegraph.com/rss" not in profile_text
    assert "https://www.coindesk.com/arc/outboundfeeds/rss/" not in profile_text
    assert "user_state.local.yaml" not in profile_text
    assert "config_digest" not in profile_text


def test_dashboard_config_ref_rejects_traversal_like_relative_path() -> None:
    assert dashboard_config_ref(Path("../private/config.yaml")) == "<external-config>"
    assert dashboard_config_ref(Path("config.yaml")) == "config.yaml"


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
        request={
            "confirm": True,
            "changes": {
                "dashboard.display_timezone": "UTC",
                "dashboard.timestamp_hour_cycle": "12h",
                "dashboard.timestamp_date_order": "year_last",
            },
        },
    )

    assert result["status"] == "succeeded"
    assert result["changed_paths"] == [
        "dashboard.display_timezone",
        "dashboard.timestamp_date_order",
        "dashboard.timestamp_hour_cycle",
    ]
    assert config["dashboard"]["display_timezone"] == "UTC"
    assert config["dashboard"]["timestamp_hour_cycle"] == "12h"
    assert config["dashboard"]["timestamp_date_order"] == "year_last"
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


def test_dashboard_settings_enabling_capabilities_materializes_editable_defaults(tmp_path: Path) -> None:
    config_path = _write_market_enabled_config(tmp_path)
    config = load_config(config_path)

    result = dashboard_save_config_profile(
        config,
        config_path=config_path,
        request={
            "confirm": True,
            "changes": {
                "macro_calendar.enabled": True,
                "onchain_flow.enabled": True,
                "market.derivatives.enabled": True,
            },
        },
    )

    assert result["status"] == "succeeded"
    assert result["changed_paths"] == [
        "macro_calendar.enabled",
        "market.derivatives.enabled",
        "onchain_flow.enabled",
    ]
    saved = load_config(config_path)
    assert saved["market"]["derivatives"] == {
        "enabled": True,
        "source": "binance_usdm",
        "symbols": ["BTCUSDT", "ETHUSDT"],
        "data_classes": ["funding_rate", "open_interest", "premium_index"],
        "periods": ["1h", "4h", "1d"],
        "lookback": {"1h": 720, "4h": 180, "1d": 90},
    }
    assert saved["macro_calendar"] == {
        "enabled": True,
        "source": "federal_reserve_fomc",
        "data_classes": ["central_bank_event"],
        "regions": ["US"],
        "lookback_days": 7,
        "lookahead_days": 45,
    }
    assert saved["onchain_flow"] == {
        "enabled": True,
        "source": "public_aggregate",
        "data_classes": [
            "stablecoin_supply",
            "chain_activity",
            "network_congestion",
            "exchange_flow_availability",
        ],
        "assets": ["ALL_STABLECOINS", "BTC"],
        "chains": ["all", "bitcoin"],
        "lookback_days": 7,
    }
    assert str(tmp_path) not in str(result)


def test_dashboard_settings_derivatives_periods_materialize_matching_lookback(tmp_path: Path) -> None:
    config_path = _write_market_enabled_config(tmp_path)
    config = load_config(config_path)

    result = dashboard_save_config_profile(
        config,
        config_path=config_path,
        request={
            "confirm": True,
            "changes": {
                "market.derivatives.enabled": True,
                "market.derivatives.periods": ["8h"],
            },
        },
    )

    assert result["status"] == "succeeded"
    saved = load_config(config_path)
    assert saved["market"]["derivatives"]["periods"] == ["8h"]
    assert saved["market"]["derivatives"]["lookback"] == {"8h": 90}
    assert str(tmp_path) not in str(result)


def test_dashboard_settings_ohlcv_timeframes_materialize_matching_lookback(tmp_path: Path) -> None:
    config_path = _write_market_enabled_ohlcv_config(tmp_path)
    config = load_config(config_path)

    result = dashboard_save_config_profile(
        config,
        config_path=config_path,
        request={
            "confirm": True,
            "changes": {
                "market.ohlcv.timeframes": ["1m", "4h", "1M"],
            },
        },
    )

    assert result["status"] == "succeeded"
    saved = load_config(config_path)
    assert saved["market"]["ohlcv"]["timeframes"] == ["1m", "4h", "1M"]
    assert saved["market"]["ohlcv"]["lookback"] == {
        "1m": 1440,
        "4h": 720,
        "1M": 120,
    }
    assert str(tmp_path) not in str(result)


def test_dashboard_settings_enabling_text_intelligence_materializes_model_defaults(tmp_path: Path) -> None:
    config_path = _write_text_enabled_config(tmp_path)
    config = load_config(config_path)

    result = dashboard_save_config_profile(
        config,
        config_path=config_path,
        request={
            "confirm": True,
            "changes": {
                "text.intelligence.enabled": True,
            },
        },
    )

    assert result["status"] == "succeeded"
    assert result["changed_paths"] == ["text.intelligence.enabled"]
    saved = load_config(config_path)
    assert saved["text"]["intelligence"] == {
        "enabled": True,
        "model_cache_dir": "data/models/text",
        "allow_model_download": False,
        "models": {
            "embedding": {
                "provider": "sentence_transformers",
                "name": "sentence-transformers/all-MiniLM-L6-v2",
                "revision": "pinned",
            },
            "classifier": {
                "provider": "transformers_zero_shot",
                "name": "facebook/bart-large-mnli",
                "revision": "pinned",
            },
            "sentiment": {
                "provider": "transformers_text_classification",
                "name": "ProsusAI/finbert",
                "revision": "pinned",
            },
            "ner": {
                "provider": "gliner",
                "name": "urchade/gliner_medium-v2.1",
                "revision": "pinned",
            },
        },
        "thresholds": {
            "duplicate_similarity": 0.92,
            "same_topic_similarity": 0.82,
            "classifier_accept_score": 0.65,
            "classifier_top_margin": 0.1,
            "entity_accept_score": 0.5,
            "max_topic_window_hours": 48,
        },
    }
    assert str(tmp_path) not in str(result)


def test_dashboard_settings_accepts_text_intelligence_threshold_changes(tmp_path: Path) -> None:
    config_path = _write_text_enabled_config(tmp_path)
    config = load_config(config_path)

    result = dashboard_save_config_profile(
        config,
        config_path=config_path,
        request={
            "confirm": True,
            "changes": {
                "text.intelligence.enabled": True,
                "text.intelligence.thresholds.duplicate_similarity": 0.9,
            },
        },
    )

    assert result["status"] == "succeeded"
    saved = load_config(config_path)
    assert saved["text"]["intelligence"]["thresholds"]["duplicate_similarity"] == 0.9
    assert str(tmp_path) not in str(result)


def test_dashboard_settings_live_section_exposes_safe_controls(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    profile = dashboard_config_profile(config, config_path=config_path)
    fields = {field["path"]: field for field in profile["fields"]}

    assert "Live" in profile["sections"]
    assert fields["live.enabled"]["value"] is False
    assert fields["live.tick_seconds"]["value"] == 30
    assert fields["live.collections.ohlcv.enabled"]["value"] is False
    assert fields["live.collections.macro_calendar.lookahead_seconds"]["value"] == 3888000
    assert fields["live.reports.triggers.market_breakout.job_intent"]["options"] == list(
        LIVE_REPORT_TRIGGER_JOB_INTENTS
    )
    assert fields["live.reports.triggers.market_breakout.confirm_codex"]["virtual"] is True
    assert fields["live.reports.triggers.market_breakout.confirm_codex"]["value"] is False
    assert "live.reports.triggers.market_breakout.codex_authorization" not in fields


def test_dashboard_settings_save_live_collection_and_trigger_round_trip(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    result = dashboard_save_config_profile(
        config,
        config_path=config_path,
        request={
            "confirm": True,
            "changes": {
                "live.enabled": True,
                "live.tick_seconds": 15,
                "live.reports.daily.enabled": True,
                "live.collections.text_event.enabled": True,
                "live.collections.text_event.cadence_seconds": 600,
                "live.collections.text_event.lookback_seconds": 7200,
                "live.collections.macro_calendar.enabled": True,
                "live.reports.triggers.data_quality_degraded.enabled": True,
                "live.reports.triggers.data_quality_degraded.cooldown_seconds": 900,
                "live.reports.triggers.data_quality_degraded.job_intent": "run_no_codex",
                "live.reports.triggers.data_quality_degraded.min_failed_targets": 2,
            },
        },
    )

    assert result["status"] == "succeeded"
    saved = load_config(config_path)
    assert saved["live"]["enabled"] is True
    assert saved["live"]["tick_seconds"] == 15
    assert saved["live"]["reports"]["daily"]["enabled"] is True
    assert saved["live"]["collections"]["text_event"] == {
        "enabled": True,
        "cadence_seconds": 600,
        "lookback_seconds": 7200,
    }
    assert saved["live"]["collections"]["macro_calendar"] == {
        "enabled": True,
        "cadence_seconds": 3600,
        "lookback_seconds": 604800,
        "lookahead_seconds": 3888000,
    }
    assert saved["live"]["reports"]["triggers"]["data_quality_degraded"] == {
        "enabled": True,
        "cooldown_seconds": 900,
        "job_intent": "run_no_codex",
        "min_failed_targets": 2,
        "min_stale_targets": 1,
    }
    assert str(tmp_path) not in str(result)


def test_dashboard_settings_rejects_invalid_live_values(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    result = dashboard_save_config_profile(
        config,
        config_path=config_path,
        request={
            "confirm": True,
            "changes": {
                "live.tick_seconds": 0,
                "live.collections.unsupported.enabled": True,
            },
        },
    )

    assert result["status"] == "failed"
    assert "live.tick_seconds: value must be a positive integer." in result["errors"]
    assert "live.collections.unsupported.enabled is not editable from the dashboard settings UI." in result["errors"]
    assert "live" not in load_config(config_path)
    assert str(tmp_path) not in str(result)


def test_dashboard_settings_live_run_trigger_requires_codex_confirmation(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    result = dashboard_save_config_profile(
        config,
        config_path=config_path,
        request={
            "confirm": True,
            "changes": {
                "live.enabled": True,
                "live.reports.triggers.market_breakout.enabled": True,
                "live.reports.triggers.market_breakout.cooldown_seconds": 600,
                "live.reports.triggers.market_breakout.job_intent": "run",
                "live.reports.triggers.market_breakout.window_seconds": 3600,
            },
        },
    )

    assert result["status"] == "failed"
    assert result["errors"] == [
        "live.reports.triggers.market_breakout.confirm_codex: "
        "confirm this trigger before saving unattended Codex-capable Live `run` behavior."
    ]
    assert "live" not in load_config(config_path)
    assert str(tmp_path) not in str(result)


def test_dashboard_settings_live_run_trigger_confirmation_persists_valid_authorization(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    result = dashboard_save_config_profile(
        config,
        config_path=config_path,
        request={
            "confirm": True,
            "changes": {
                "live.enabled": True,
                "live.reports.triggers.market_breakout.enabled": True,
                "live.reports.triggers.market_breakout.cooldown_seconds": 600,
                "live.reports.triggers.market_breakout.job_intent": "run",
                "live.reports.triggers.market_breakout.window_seconds": 3600,
                "live.reports.triggers.market_breakout.confirm_codex": True,
            },
        },
    )

    assert result["status"] == "succeeded"
    saved = load_config(config_path)
    authorization = saved["live"]["reports"]["triggers"]["market_breakout"]["codex_authorization"]
    assert authorization["authorized"] is True
    assert authorization["trigger_id"] == "market_breakout"
    assert authorization["job_intent"] == "run"
    assert authorization["authorization_scope"] == "unattended_live_trigger"
    assert "config_digest" in authorization

    trigger_model = LiveTriggerEvaluator(
        saved,
        config_path=config_path,
        job_manager=_NoopJobManager(),
    ).read_model()
    trigger_summary = {
        item["trigger_id"]: item
        for item in trigger_model["config"]["triggers"]
    }["market_breakout"]
    assert trigger_summary["codex_authorization"]["authorized"] is True
    assert trigger_summary["codex_authorization"]["valid"] is True
    assert str(tmp_path) not in str(result)


def test_dashboard_settings_live_run_trigger_authorization_invalidates_on_config_change(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    first = dashboard_save_config_profile(
        config,
        config_path=config_path,
        request={
            "confirm": True,
            "changes": {
                "live.enabled": True,
                "live.reports.triggers.market_breakout.enabled": True,
                "live.reports.triggers.market_breakout.cooldown_seconds": 600,
                "live.reports.triggers.market_breakout.job_intent": "run",
                "live.reports.triggers.market_breakout.window_seconds": 3600,
                "live.reports.triggers.market_breakout.confirm_codex": True,
            },
        },
    )
    assert first["status"] == "succeeded"
    original_text = config_path.read_text(encoding="utf-8")

    result = dashboard_save_config_profile(
        load_config(config_path),
        config_path=config_path,
        request={
            "confirm": True,
            "changes": {
                "live.reports.triggers.market_breakout.cooldown_seconds": 1200,
            },
        },
    )

    assert result["status"] == "failed"
    assert result["errors"] == [
        "live.reports.triggers.market_breakout.confirm_codex: "
        "confirm this trigger before saving unattended Codex-capable Live `run` behavior."
    ]
    assert config_path.read_text(encoding="utf-8") == original_text
    assert str(tmp_path) not in str(result)


class _NoopJobManager:
    def list_jobs(self, *, limit: int = 100) -> dict[str, Any]:
        return {"jobs": []}

    def create_job(self, request: dict[str, Any]) -> dict[str, Any]:
        raise AssertionError("settings authorization tests must not create jobs")


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


def _write_market_enabled_config(tmp_path: Path) -> Path:
    config_path = _write_config(tmp_path)
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            "market:\n  enabled: false",
            "market:\n  enabled: true\n  source: binance\n  symbols:\n    - BTCUSDT\n    - ETHUSDT",
            1,
        ),
        encoding="utf-8",
    )
    return config_path


def _write_market_enabled_ohlcv_config(tmp_path: Path) -> Path:
    config_path = _write_market_enabled_config(tmp_path)
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            "  symbols:\n    - BTCUSDT\n    - ETHUSDT",
            """
  symbols:
    - BTCUSDT
    - ETHUSDT
  ohlcv:
    storage_dir: data/market/ohlcv
    timeframes:
      - 1d
    lookback:
      1d: 500
""".rstrip(),
            1,
        ),
        encoding="utf-8",
    )
    return config_path


def _write_text_enabled_config(tmp_path: Path) -> Path:
    config_path = _write_config(tmp_path)
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            "text:\n  enabled: false\n  sources: []",
            """
text:
  enabled: true
  max_items: 30
  sources:
    - name: coindesk
      type: rss
      url: https://www.coindesk.com/arc/outboundfeeds/rss/
""".strip(),
            1,
        ),
        encoding="utf-8",
    )
    return config_path


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
