from __future__ import annotations

from datetime import datetime
import math
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from halpha.data.public_capabilities import (
    SUPPORTED_DERIVATIVES_DATA_CLASSES,
    SUPPORTED_DERIVATIVES_MARKET_SOURCES,
    SUPPORTED_DERIVATIVES_PERIODS,
    SUPPORTED_MACRO_CALENDAR_DATA_CLASSES,
    SUPPORTED_MACRO_CALENDAR_REGIONS,
    SUPPORTED_MACRO_CALENDAR_SOURCES,
    SUPPORTED_ONCHAIN_FLOW_ASSETS,
    SUPPORTED_ONCHAIN_FLOW_CHAINS,
    SUPPORTED_ONCHAIN_FLOW_DATA_CLASSES,
    SUPPORTED_ONCHAIN_FLOW_SOURCES,
)
from halpha.live.contracts import (
    LIVE_COLLECTION_FIELDS,
    LIVE_CONFIG_FIELDS,
    LIVE_DAILY_REPORT_FIELDS,
    LIVE_DATA_TYPES,
    LIVE_REPORT_TRIGGER_FIELDS,
    LIVE_REPORTS_FIELDS,
    LIVE_TRIGGER_IDS,
)
from halpha.market.ohlcv_quality import OHLCV_TIMEFRAME_DURATIONS
from halpha.market.ohlcv_source import SUPPORTED_OHLCV_SOURCES
from halpha.monitor.monitoring import MONITOR_SOURCE_KEYS, SUPPORTED_MONITOR_FIELDS
from halpha.quant.registry import SUPPORTED_STRATEGY_NAMES
from halpha.storage import resolve_runtime_path


CONFIG_SECTIONS = {
    "codex",
    "dashboard",
    "logging",
    "live",
    "macro_calendar",
    "market",
    "monitor",
    "onchain_flow",
    "quant",
    "report",
    "run",
    "text",
    "user_state",
}
SUPPORTED_LOGGING_FIELDS = {"output_dir"}
SUPPORTED_USER_STATE_FIELDS = {"enabled", "path"}
SUPPORTED_OHLCV_MARKET_SOURCES = {"binance", "binance_spot", "binance_usdm"}
SUPPORTED_OHLCV_DATA_SOURCES = set(SUPPORTED_OHLCV_SOURCES)
SUPPORTED_OHLCV_TIMEFRAMES = set(OHLCV_TIMEFRAME_DURATIONS)
SUPPORTED_DERIVATIVES_FIELDS = {"data_classes", "enabled", "lookback", "periods", "source", "symbols"}
SUPPORTED_MARKET_ANOMALY_FIELDS = {
    "enabled",
    "external_json_path",
    "lookback_days",
    "ohlcv_source",
    "price_move_threshold_pct",
    "source_kinds",
    "symbols",
    "timeframes",
    "volume_spike_multiplier",
    "window_end",
    "window_start",
}
SUPPORTED_MARKET_ANOMALY_SOURCE_KINDS = {"external_intel", "halpha_rule"}
SUPPORTED_MACRO_CALENDAR_FIELDS = {
    "data_classes",
    "enabled",
    "lookahead_days",
    "lookback_days",
    "regions",
    "source",
    "source_url",
}
SUPPORTED_ONCHAIN_FLOW_FIELDS = {
    "assets",
    "chain_activity_source_url",
    "chains",
    "data_classes",
    "enabled",
    "lookback_days",
    "network_congestion_source_url",
    "source",
    "stablecoin_source_url",
}
SUPPORTED_QUANT_ENGINES = {"vectorbt"}
SUPPORTED_QUANT_STRATEGIES = SUPPORTED_STRATEGY_NAMES
SUPPORTED_BACKTEST_MODES = {"long_flat", "long_only"}
SUPPORTED_BENCHMARK_WINDOW_SELECTIONS = {"configured_lookback", "latest_lookback", "date_window"}
SUPPORTED_TEXT_INTELLIGENCE_FIELDS = {
    "allow_model_download",
    "enabled",
    "model_cache_dir",
    "models",
    "thresholds",
}
SUPPORTED_TEXT_INTELLIGENCE_MODEL_FIELDS = {"name", "provider", "revision"}
SUPPORTED_TEXT_INTELLIGENCE_MODEL_PROVIDERS = {
    "classifier": "transformers_zero_shot",
    "embedding": "sentence_transformers",
    "ner": "gliner",
    "sentiment": "transformers_text_classification",
}
SUPPORTED_TEXT_INTELLIGENCE_THRESHOLD_FIELDS = {
    "classifier_accept_score",
    "classifier_top_margin",
    "duplicate_similarity",
    "entity_accept_score",
    "max_topic_window_hours",
    "same_topic_similarity",
}
SUPPORTED_DASHBOARD_FIELDS = {"display_timezone", "timestamp_date_order", "timestamp_hour_cycle"}
SUPPORTED_EFFECTIVENESS_GATE_FIELDS = {
    "elevated_overfitting_blocks_effective",
    "max_abs_drawdown_pct",
    "max_abs_funding_drag_pct",
    "max_average_gross_exposure_pct",
    "max_cost_drag_pct",
    "max_turnover",
    "min_benchmark_success_rate_pct",
    "min_mean_excess_return_vs_buy_and_hold_pct",
    "min_mean_net_return_pct",
    "min_min_sample_rows",
    "min_positive_excess_return_benchmark_pct",
    "min_positive_net_return_benchmark_pct",
    "min_succeeded_benchmarks",
    "min_total_trade_count",
    "min_walk_forward_positive_net_return_window_pct",
    "min_walk_forward_succeeded_windows",
    "require_parameter_stability",
    "require_walk_forward_stable",
}
SUPPORTED_LIFECYCLE_POLICY_FIELDS = {"records"}
SUPPORTED_LIFECYCLE_POLICY_RECORD_FIELDS = {
    "action",
    "created_at",
    "effective_at",
    "parameter_digest",
    "reason",
    "scope",
    "strategy_contract_version",
    "strategy_name",
}
SUPPORTED_LIFECYCLE_POLICY_ACTIONS = {"promote", "reject", "retire", "watchlist"}
SUPPORTED_LIFECYCLE_POLICY_SCOPE_FIELDS = {"symbol", "timeframe"}
SUPPORTED_QUANT_STRATEGY_PARAM_NAMES = {
    "sma_cross_trend": {"short_window", "long_window"},
    "sma_cross_long_short": {"short_window", "long_window", "neutral_band_pct"},
    "pair_zscore_reversion": {"lookback_window", "entry_zscore", "exit_zscore", "hedge_ratio"},
    "cross_sectional_momentum": {"lookback_window", "long_count", "short_count", "min_instrument_count"},
    "signed_tsmom_trend": {
        "return_window",
        "deadband_pct",
        "volatility_filter_enabled",
        "volatility_filter_window",
        "max_realized_volatility_pct",
        "funding_rate_filter_enabled",
        "max_abs_funding_rate",
        "market_anomaly_filter_enabled",
        "market_anomaly_filter_lookback_hours",
        "market_anomaly_filter_min_count",
    },
    "tsmom_vol_scaled": {"return_window", "volatility_window", "target_volatility"},
    "breakout_atr_trend": {"breakout_window", "exit_window", "atr_window"},
    "bollinger_rsi_reversion": {
        "bollinger_window",
        "band_std",
        "rsi_window",
        "rsi_oversold",
        "rsi_overbought",
        "trend_window",
        "trend_filter_pct",
    },
    "bollinger_rsi_long_short": {
        "bollinger_window",
        "band_std",
        "rsi_window",
        "rsi_oversold",
        "rsi_overbought",
        "trend_window",
        "trend_filter_pct",
    },
}


class ConfigError(Exception):
    """Raised when the run configuration violates the config contract."""


def load_config(path: Path | str) -> dict[str, Any]:
    config_path = Path(path)

    try:
        text = config_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ConfigError(f"config file not found: {config_path}") from exc

    try:
        import yaml
    except ModuleNotFoundError as exc:
        raise ConfigError("PyYAML is required to read YAML config files.") from exc

    try:
        loaded = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigError(f"config file is not valid YAML: {exc}") from exc

    if loaded is None:
        loaded = {}
    if not isinstance(loaded, dict):
        raise ConfigError("config root must be a mapping.")

    validate_config(loaded, config_path=config_path)
    return loaded


def validate_config(config: dict[str, Any], *, config_path: Path | str | None = None) -> None:
    path_context = Path(config_path) if config_path is not None else None
    _validate_config_sections(config)

    run = _require_mapping(config, "run")
    _require_non_empty_string(run, "output_dir", "run.output_dir")
    if "timezone" in run:
        timezone_name = _require_non_empty_string(run, "timezone", "run.timezone")
        try:
            ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError as exc:
            raise ConfigError(f"run.timezone is not an available IANA timezone: {timezone_name}.") from exc

    market = _require_mapping(config, "market")
    market_enabled = _require_bool(market, "enabled", "market.enabled")
    if market_enabled:
        _require_non_empty_string(market, "source", "market.source")
        _require_non_empty_string_list(market, "symbols", "market.symbols")
        if "proxy" in market:
            _validate_market_proxy_config(market)
    if "derivatives" in market:
        _validate_derivatives_config(market, market_enabled=market_enabled)
    if "anomalies" in market:
        _validate_market_anomalies_config(market, market_enabled=market_enabled)

    if "macro_calendar" in config:
        _validate_macro_calendar_config(config["macro_calendar"])
    if "onchain_flow" in config:
        _validate_onchain_flow_config(config["onchain_flow"])
    if "user_state" in config:
        _validate_user_state_config(config["user_state"])
    if "monitor" in config:
        _validate_monitor_config(config["monitor"])
    if "dashboard" in config:
        _validate_dashboard_config(config["dashboard"])
    if "live" in config:
        _validate_live_config(config["live"])
    if "logging" in config:
        _validate_logging_config(config["logging"])

    quant = _optional_mapping(config, "quant")
    quant_enabled = False
    if quant is not None:
        quant_enabled = _require_bool(quant, "enabled", "quant.enabled")
        if quant_enabled:
            _validate_quant_config(quant)

    if quant_enabled and not market_enabled:
        raise ConfigError("quant.enabled requires market.enabled to be true.")
    if quant_enabled or "ohlcv" in market:
        if not market_enabled:
            raise ConfigError("market.ohlcv requires market.enabled to be true.")
        market_source = _require_non_empty_string(market, "source", "market.source")
        _require_supported_value(market_source, "market.source", SUPPORTED_OHLCV_MARKET_SOURCES)
        _validate_ohlcv_config(config, market, quant_enabled=quant_enabled, config_path=path_context)

    text = _require_mapping(config, "text")
    text_enabled = _require_bool(text, "enabled", "text.enabled")
    if "intelligence" in text:
        _validate_text_intelligence_config(text, text_enabled=text_enabled)
    if text_enabled:
        if "max_items" in text:
            _require_positive_int(text, "max_items", "text.max_items")
        sources = _require_non_empty_list(text, "sources", "text.sources")
        for index, source in enumerate(sources):
            path = f"text.sources[{index}]"
            if not isinstance(source, dict):
                raise ConfigError(f"{path} must be a mapping.")
            _require_non_empty_string(source, "name", f"{path}.name")
            _require_non_empty_string(source, "type", f"{path}.type")
            _require_http_url(source, "url", f"{path}.url")

    report = _require_mapping(config, "report")
    if "title" in report:
        _require_non_empty_string(report, "title", "report.title")
    language = _require_non_empty_string(report, "language", "report.language")
    if language != "zh-CN":
        raise ConfigError("report.language must be zh-CN.")

    codex = _require_mapping(config, "codex")
    codex_enabled = _require_bool(codex, "enabled", "codex.enabled")
    if codex_enabled:
        _require_non_empty_string(codex, "command", "codex.command")
        _require_non_empty_string_list(codex, "args", "codex.args")
        _require_positive_int(codex, "timeout_seconds", "codex.timeout_seconds")


def _validate_config_sections(config: dict[str, Any]) -> None:
    unsupported = sorted(set(config) - CONFIG_SECTIONS)
    if unsupported:
        supported = ", ".join(sorted(CONFIG_SECTIONS))
        names = ", ".join(unsupported)
        raise ConfigError(f"unsupported top-level config section(s): {names}. Supported sections: {supported}.")


def _validate_text_intelligence_config(text: dict[str, Any], *, text_enabled: bool) -> None:
    intelligence = text.get("intelligence")
    if not isinstance(intelligence, dict):
        raise ConfigError("text.intelligence must be a mapping.")

    _reject_unsupported_fields(
        intelligence,
        path="text.intelligence",
        supported_fields=SUPPORTED_TEXT_INTELLIGENCE_FIELDS,
    )
    enabled = _require_bool(intelligence, "enabled", "text.intelligence.enabled")
    if enabled and not text_enabled:
        raise ConfigError("text.intelligence.enabled requires text.enabled to be true.")

    if "model_cache_dir" in intelligence or enabled:
        _require_non_empty_string(intelligence, "model_cache_dir", "text.intelligence.model_cache_dir")
    if "allow_model_download" in intelligence or enabled:
        _require_bool(intelligence, "allow_model_download", "text.intelligence.allow_model_download")
    if "models" in intelligence or enabled:
        _validate_text_intelligence_models(intelligence, required=enabled)
    if "thresholds" in intelligence or enabled:
        _validate_text_intelligence_thresholds(intelligence, required=enabled)


def _validate_user_state_config(user_state: dict[str, Any]) -> None:
    if not isinstance(user_state, dict):
        raise ConfigError("user_state must be a mapping.")
    _reject_unsupported_fields(
        user_state,
        path="user_state",
        supported_fields=SUPPORTED_USER_STATE_FIELDS,
    )
    enabled = _require_bool(user_state, "enabled", "user_state.enabled")
    if enabled or "path" in user_state:
        _require_non_empty_string(user_state, "path", "user_state.path")


def _validate_monitor_config(monitor: dict[str, Any]) -> None:
    if not isinstance(monitor, dict):
        raise ConfigError("monitor must be a mapping.")
    _reject_unsupported_fields(
        monitor,
        path="monitor",
        supported_fields=SUPPORTED_MONITOR_FIELDS,
    )
    if "enabled" in monitor:
        _require_bool(monitor, "enabled", "monitor.enabled")
    if "interval_seconds" in monitor:
        _require_positive_int(monitor, "interval_seconds", "monitor.interval_seconds")
    if "failure_backoff_max_seconds" in monitor:
        _require_positive_int(
            monitor,
            "failure_backoff_max_seconds",
            "monitor.failure_backoff_max_seconds",
        )
    if "max_cycles" in monitor:
        _require_positive_int(monitor, "max_cycles", "monitor.max_cycles")
    if "cooldown_seconds" in monitor:
        _require_positive_int(monitor, "cooldown_seconds", "monitor.cooldown_seconds")
    if "output_dir" in monitor:
        _require_non_empty_string(monitor, "output_dir", "monitor.output_dir")
    if "target_stage" in monitor:
        _require_non_empty_string(monitor, "target_stage", "monitor.target_stage")
    if "no_codex" in monitor:
        _require_bool(monitor, "no_codex", "monitor.no_codex")
    if "source_cadence_seconds" in monitor:
        _validate_monitor_source_cadence_config(monitor["source_cadence_seconds"])


def _validate_monitor_source_cadence_config(value: Any) -> None:
    if not isinstance(value, dict) or not value:
        raise ConfigError("monitor.source_cadence_seconds must be a non-empty mapping.")
    unsupported = sorted(set(value) - set(MONITOR_SOURCE_KEYS))
    if unsupported:
        supported = ", ".join(MONITOR_SOURCE_KEYS)
        names = ", ".join(str(item) for item in unsupported)
        raise ConfigError(
            "unsupported monitor.source_cadence_seconds source(s): "
            f"{names}. Supported sources: {supported}."
        )
    for source_key in sorted(value):
        item = value[source_key]
        if not isinstance(item, int) or isinstance(item, bool) or item <= 0:
            raise ConfigError(f"monitor.source_cadence_seconds.{source_key} must be a positive integer.")


def _validate_dashboard_config(dashboard: Any) -> None:
    if not isinstance(dashboard, dict):
        raise ConfigError("dashboard must be a mapping.")
    _reject_unsupported_fields(
        dashboard,
        path="dashboard",
        supported_fields=SUPPORTED_DASHBOARD_FIELDS,
    )
    if "display_timezone" in dashboard:
        timezone_name = _require_non_empty_string(
            dashboard,
            "display_timezone",
            "dashboard.display_timezone",
        )
        try:
            ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError as exc:
            raise ConfigError(
                f"dashboard.display_timezone is not an available IANA timezone: {timezone_name}."
            ) from exc
    if "timestamp_hour_cycle" in dashboard:
        value = _require_non_empty_string(
            dashboard,
            "timestamp_hour_cycle",
            "dashboard.timestamp_hour_cycle",
        )
        if value not in {"24h", "12h"}:
            raise ConfigError("dashboard.timestamp_hour_cycle must be one of: 24h, 12h.")
    if "timestamp_date_order" in dashboard:
        value = _require_non_empty_string(
            dashboard,
            "timestamp_date_order",
            "dashboard.timestamp_date_order",
        )
        if value not in {"year_first", "year_last"}:
            raise ConfigError("dashboard.timestamp_date_order must be one of: year_first, year_last.")


def _validate_logging_config(logging_config: Any) -> None:
    if not isinstance(logging_config, dict):
        raise ConfigError("logging must be a mapping.")
    _reject_unsupported_fields(
        logging_config,
        path="logging",
        supported_fields=SUPPORTED_LOGGING_FIELDS,
    )
    if "output_dir" in logging_config:
        _require_non_empty_string(logging_config, "output_dir", "logging.output_dir")


def _validate_live_config(live: Any) -> None:
    if not isinstance(live, dict):
        raise ConfigError("live must be a mapping.")
    _reject_unsupported_fields(live, path="live", supported_fields=LIVE_CONFIG_FIELDS)
    if "enabled" in live:
        _require_bool(live, "enabled", "live.enabled")
    if "tick_seconds" in live:
        _require_positive_int(live, "tick_seconds", "live.tick_seconds")
    if "collections" in live:
        _validate_live_collections_config(live["collections"])
    if "reports" in live:
        _validate_live_reports_config(live["reports"])


def _validate_live_collections_config(collections: Any) -> None:
    if not isinstance(collections, dict):
        raise ConfigError("live.collections must be a mapping.")
    unsupported = sorted(set(collections) - set(LIVE_DATA_TYPES))
    if unsupported:
        supported = ", ".join(LIVE_DATA_TYPES)
        names = ", ".join(str(item) for item in unsupported)
        raise ConfigError(f"unsupported live.collections data type(s): {names}. Supported data types: {supported}.")
    for data_type in sorted(collections):
        path = f"live.collections.{data_type}"
        collection = collections[data_type]
        if not isinstance(collection, dict):
            raise ConfigError(f"{path} must be a mapping.")
        _reject_unsupported_fields(collection, path=path, supported_fields=LIVE_COLLECTION_FIELDS)
        enabled = collection.get("enabled") is True
        if "enabled" in collection:
            _require_bool(collection, "enabled", f"{path}.enabled")
        if enabled or "cadence_seconds" in collection:
            _require_positive_int(collection, "cadence_seconds", f"{path}.cadence_seconds")
        if enabled or "lookback_seconds" in collection:
            _require_positive_int(collection, "lookback_seconds", f"{path}.lookback_seconds")
        if data_type == "macro_calendar":
            if enabled or "lookahead_seconds" in collection:
                _require_positive_int(collection, "lookahead_seconds", f"{path}.lookahead_seconds")
        elif "lookahead_seconds" in collection:
            raise ConfigError(f"{path}.lookahead_seconds is only supported for macro_calendar.")


def _validate_live_reports_config(reports: Any) -> None:
    if not isinstance(reports, dict):
        raise ConfigError("live.reports must be a mapping.")
    _reject_unsupported_fields(reports, path="live.reports", supported_fields=LIVE_REPORTS_FIELDS)
    if "daily" in reports:
        daily = reports["daily"]
        if not isinstance(daily, dict):
            raise ConfigError("live.reports.daily must be a mapping.")
        _reject_unsupported_fields(daily, path="live.reports.daily", supported_fields=LIVE_DAILY_REPORT_FIELDS)
        if "enabled" in daily:
            _require_bool(daily, "enabled", "live.reports.daily.enabled")
    if "triggers" in reports:
        triggers = reports["triggers"]
        if not isinstance(triggers, dict):
            raise ConfigError("live.reports.triggers must be a mapping.")
        unsupported = sorted(set(triggers) - set(LIVE_TRIGGER_IDS))
        if unsupported:
            supported = ", ".join(LIVE_TRIGGER_IDS)
            names = ", ".join(str(item) for item in unsupported)
            raise ConfigError(f"unsupported live.reports.triggers id(s): {names}. Supported trigger ids: {supported}.")
        for trigger_id in sorted(triggers):
            path = f"live.reports.triggers.{trigger_id}"
            trigger = triggers[trigger_id]
            if not isinstance(trigger, dict):
                raise ConfigError(f"{path} must be a mapping.")
            _reject_unsupported_fields(trigger, path=path, supported_fields=LIVE_REPORT_TRIGGER_FIELDS)
            enabled = trigger.get("enabled") is True
            if "enabled" in trigger:
                _require_bool(trigger, "enabled", f"{path}.enabled")
            if enabled or "cooldown_seconds" in trigger:
                _require_positive_int(trigger, "cooldown_seconds", f"{path}.cooldown_seconds")


def _validate_text_intelligence_models(intelligence: dict[str, Any], *, required: bool) -> None:
    models = intelligence.get("models")
    if not isinstance(models, dict) or (required and not models):
        raise ConfigError("text.intelligence.models must be a non-empty mapping.")

    unsupported = sorted(set(models) - set(SUPPORTED_TEXT_INTELLIGENCE_MODEL_PROVIDERS))
    if unsupported:
        supported = ", ".join(sorted(SUPPORTED_TEXT_INTELLIGENCE_MODEL_PROVIDERS))
        names = ", ".join(unsupported)
        raise ConfigError(
            f"unsupported text.intelligence.models role(s): {names}. Supported roles: {supported}."
        )

    if required:
        missing = sorted(set(SUPPORTED_TEXT_INTELLIGENCE_MODEL_PROVIDERS) - set(models))
        if missing:
            names = ", ".join(missing)
            raise ConfigError(f"text.intelligence.models missing required role(s): {names}.")

    for role, model in sorted(models.items()):
        path = f"text.intelligence.models.{role}"
        if not isinstance(model, dict):
            raise ConfigError(f"{path} must be a mapping.")
        _reject_unsupported_fields(
            model,
            path=path,
            supported_fields=SUPPORTED_TEXT_INTELLIGENCE_MODEL_FIELDS,
        )
        provider = _require_non_empty_string(model, "provider", f"{path}.provider")
        expected_provider = SUPPORTED_TEXT_INTELLIGENCE_MODEL_PROVIDERS[role]
        if provider != expected_provider:
            raise ConfigError(f"{path}.provider must be {expected_provider}.")
        _require_non_empty_string(model, "name", f"{path}.name")
        _require_non_empty_string(model, "revision", f"{path}.revision")


def _validate_text_intelligence_thresholds(intelligence: dict[str, Any], *, required: bool) -> None:
    thresholds = intelligence.get("thresholds")
    if not isinstance(thresholds, dict) or (required and not thresholds):
        raise ConfigError("text.intelligence.thresholds must be a non-empty mapping.")

    _reject_unsupported_fields(
        thresholds,
        path="text.intelligence.thresholds",
        supported_fields=SUPPORTED_TEXT_INTELLIGENCE_THRESHOLD_FIELDS,
    )
    if required:
        missing = sorted(SUPPORTED_TEXT_INTELLIGENCE_THRESHOLD_FIELDS - set(thresholds))
        if missing:
            names = ", ".join(missing)
            raise ConfigError(f"text.intelligence.thresholds missing required field(s): {names}.")

    for key in sorted(SUPPORTED_TEXT_INTELLIGENCE_THRESHOLD_FIELDS - {"max_topic_window_hours"}):
        if key in thresholds:
            _require_unit_interval_number(thresholds, key, f"text.intelligence.thresholds.{key}")
    if "max_topic_window_hours" in thresholds:
        _require_positive_int(
            thresholds,
            "max_topic_window_hours",
            "text.intelligence.thresholds.max_topic_window_hours",
        )


def _require_mapping(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key)
    if not isinstance(value, dict):
        raise ConfigError(f"{key} must be a mapping.")
    return value


def _optional_mapping(data: dict[str, Any], key: str) -> dict[str, Any] | None:
    if key not in data:
        return None
    return _require_mapping(data, key)


def _require_bool(data: dict[str, Any], key: str, path: str) -> bool:
    value = data.get(key)
    if not isinstance(value, bool):
        raise ConfigError(f"{path} must be a boolean.")
    return value


def _require_non_empty_string(data: dict[str, Any], key: str, path: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{path} must be a non-empty string.")
    return value


def _require_utc_timestamp(data: dict[str, Any], key: str, path: str) -> datetime:
    value = _require_non_empty_string(data, key, path)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ConfigError(f"{path} must be an ISO 8601 timestamp.") from exc
    if parsed.tzinfo is None:
        raise ConfigError(f"{path} must include a UTC offset.")
    return parsed


def _require_http_url(data: dict[str, Any], key: str, path: str) -> str:
    value = _require_non_empty_string(data, key, path)
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ConfigError(f"{path} must be an http or https URL.")
    return value


def _require_positive_int(data: dict[str, Any], key: str, path: str) -> int:
    value = data.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ConfigError(f"{path} must be a positive integer.")
    return value


def _require_positive_number(data: dict[str, Any], key: str, path: str) -> float:
    value = data.get(key)
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(float(value))
        or float(value) <= 0
    ):
        raise ConfigError(f"{path} must be a positive number.")
    return float(value)


def _require_unit_interval_number(data: dict[str, Any], key: str, path: str) -> float:
    value = data.get(key)
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(float(value))
        or float(value) < 0
        or float(value) > 1
    ):
        raise ConfigError(f"{path} must be a number between 0 and 1.")
    return float(value)


def _require_bounded_number(
    data: dict[str, Any],
    key: str,
    path: str,
    *,
    minimum: float,
    maximum: float,
) -> float:
    return _require_bounded_number_value(data.get(key), path, minimum=minimum, maximum=maximum)


def _require_non_negative_number(data: dict[str, Any], key: str, path: str) -> float:
    value = data.get(key)
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(float(value))
        or float(value) < 0
    ):
        raise ConfigError(f"{path} must be a non-negative number.")
    return float(value)


def _reject_unsupported_fields(
    data: dict[str, Any],
    *,
    path: str,
    supported_fields: set[str],
) -> None:
    unsupported = sorted(set(data) - supported_fields)
    if unsupported:
        supported = ", ".join(sorted(supported_fields))
        names = ", ".join(unsupported)
        raise ConfigError(f"unsupported {path} field(s): {names}. Supported fields: {supported}.")


def _validate_ohlcv_config(
    config: dict[str, Any],
    market: dict[str, Any],
    *,
    quant_enabled: bool,
    config_path: Path | None,
) -> None:
    if quant_enabled and not isinstance(market.get("ohlcv"), dict):
        raise ConfigError("market.ohlcv must be a mapping when quant.enabled is true.")
    ohlcv = market.get("ohlcv")
    if not isinstance(ohlcv, dict):
        raise ConfigError("market.ohlcv must be a mapping.")
    storage_dir = _require_non_empty_string(ohlcv, "storage_dir", "market.ohlcv.storage_dir")
    _require_outside_run_output_dir(storage_dir, config, config_path=config_path)

    timeframes = _require_non_empty_string_list(ohlcv, "timeframes", "market.ohlcv.timeframes")
    for index, timeframe in enumerate(timeframes):
        _require_supported_value(timeframe, f"market.ohlcv.timeframes[{index}]", SUPPORTED_OHLCV_TIMEFRAMES)

    if "sources" in ohlcv:
        sources = _require_non_empty_string_list(ohlcv, "sources", "market.ohlcv.sources")
        for index, source in enumerate(sources):
            _require_supported_value(source, f"market.ohlcv.sources[{index}]", SUPPORTED_OHLCV_DATA_SOURCES)

    lookback = ohlcv.get("lookback")
    if not isinstance(lookback, dict):
        raise ConfigError("market.ohlcv.lookback must be a mapping.")
    for timeframe in timeframes:
        _require_positive_int(lookback, timeframe, f"market.ohlcv.lookback.{timeframe}")


def _validate_derivatives_config(market: dict[str, Any], *, market_enabled: bool) -> None:
    derivatives = market.get("derivatives")
    if not isinstance(derivatives, dict):
        raise ConfigError("market.derivatives must be a mapping.")
    _reject_unsupported_fields(
        derivatives,
        path="market.derivatives",
        supported_fields=SUPPORTED_DERIVATIVES_FIELDS,
    )

    derivatives_enabled = _require_bool(derivatives, "enabled", "market.derivatives.enabled")
    if not derivatives_enabled:
        return
    if not market_enabled:
        raise ConfigError("market.derivatives.enabled requires market.enabled to be true.")

    source = _require_non_empty_string(derivatives, "source", "market.derivatives.source")
    _require_supported_value(source, "market.derivatives.source", SUPPORTED_DERIVATIVES_MARKET_SOURCES)

    _require_non_empty_string_list(derivatives, "symbols", "market.derivatives.symbols")

    data_classes = _require_non_empty_string_list(
        derivatives,
        "data_classes",
        "market.derivatives.data_classes",
    )
    for index, data_class in enumerate(data_classes):
        _require_supported_value(
            data_class,
            f"market.derivatives.data_classes[{index}]",
            SUPPORTED_DERIVATIVES_DATA_CLASSES,
        )

    periods = _require_non_empty_string_list(derivatives, "periods", "market.derivatives.periods")
    for index, period in enumerate(periods):
        _require_supported_value(period, f"market.derivatives.periods[{index}]", SUPPORTED_DERIVATIVES_PERIODS)

    lookback = derivatives.get("lookback")
    if not isinstance(lookback, dict):
        raise ConfigError("market.derivatives.lookback must be a mapping.")
    unsupported_lookback_periods = sorted(set(lookback) - set(periods))
    if unsupported_lookback_periods:
        configured = ", ".join(periods)
        names = ", ".join(str(period) for period in unsupported_lookback_periods)
        raise ConfigError(
            "unsupported market.derivatives.lookback period(s): "
            f"{names}. Configured periods: {configured}."
        )
    for period in periods:
        _require_positive_int(lookback, period, f"market.derivatives.lookback.{period}")


def _validate_market_anomalies_config(market: dict[str, Any], *, market_enabled: bool) -> None:
    anomalies = market.get("anomalies")
    if not isinstance(anomalies, dict):
        raise ConfigError("market.anomalies must be a mapping.")
    _reject_unsupported_fields(
        anomalies,
        path="market.anomalies",
        supported_fields=SUPPORTED_MARKET_ANOMALY_FIELDS,
    )

    enabled = _require_bool(anomalies, "enabled", "market.anomalies.enabled")
    if not enabled:
        return
    if not market_enabled:
        raise ConfigError("market.anomalies.enabled requires market.enabled to be true.")

    source_kinds = ["halpha_rule"]
    if "source_kinds" in anomalies:
        source_kinds = _require_non_empty_string_list(anomalies, "source_kinds", "market.anomalies.source_kinds")
        for index, source_kind in enumerate(source_kinds):
            _require_supported_value(
                source_kind,
                f"market.anomalies.source_kinds[{index}]",
                SUPPORTED_MARKET_ANOMALY_SOURCE_KINDS,
            )

    if "external_intel" in source_kinds or "external_json_path" in anomalies:
        _require_non_empty_string(anomalies, "external_json_path", "market.anomalies.external_json_path")

    if "halpha_rule" in source_kinds and not isinstance(market.get("ohlcv"), dict):
        raise ConfigError("market.anomalies halpha_rule source requires market.ohlcv.")

    if "ohlcv_source" in anomalies:
        source = _require_non_empty_string(anomalies, "ohlcv_source", "market.anomalies.ohlcv_source")
        _require_supported_value(source, "market.anomalies.ohlcv_source", SUPPORTED_OHLCV_DATA_SOURCES)
    if "symbols" in anomalies:
        _require_non_empty_string_list(anomalies, "symbols", "market.anomalies.symbols")
    if "timeframes" in anomalies:
        timeframes = _require_non_empty_string_list(anomalies, "timeframes", "market.anomalies.timeframes")
        for index, timeframe in enumerate(timeframes):
            _require_supported_value(timeframe, f"market.anomalies.timeframes[{index}]", SUPPORTED_OHLCV_TIMEFRAMES)
    if "lookback_days" in anomalies:
        _require_positive_int(anomalies, "lookback_days", "market.anomalies.lookback_days")
    if "price_move_threshold_pct" in anomalies:
        _require_positive_number(
            anomalies,
            "price_move_threshold_pct",
            "market.anomalies.price_move_threshold_pct",
        )
    if "volume_spike_multiplier" in anomalies:
        _require_positive_number(
            anomalies,
            "volume_spike_multiplier",
            "market.anomalies.volume_spike_multiplier",
        )
    for key in ("window_start", "window_end"):
        if key in anomalies:
            _require_utc_timestamp(anomalies, key, f"market.anomalies.{key}")


def _validate_macro_calendar_config(macro_calendar: Any) -> None:
    if not isinstance(macro_calendar, dict):
        raise ConfigError("macro_calendar must be a mapping.")
    _reject_unsupported_fields(
        macro_calendar,
        path="macro_calendar",
        supported_fields=SUPPORTED_MACRO_CALENDAR_FIELDS,
    )

    enabled = _require_bool(macro_calendar, "enabled", "macro_calendar.enabled")
    if not enabled:
        return

    source = _require_non_empty_string(macro_calendar, "source", "macro_calendar.source")
    _require_supported_value(source, "macro_calendar.source", SUPPORTED_MACRO_CALENDAR_SOURCES)

    data_classes = _require_non_empty_string_list(
        macro_calendar,
        "data_classes",
        "macro_calendar.data_classes",
    )
    for index, data_class in enumerate(data_classes):
        _require_supported_value(
            data_class,
            f"macro_calendar.data_classes[{index}]",
            SUPPORTED_MACRO_CALENDAR_DATA_CLASSES,
        )

    regions = _require_non_empty_string_list(macro_calendar, "regions", "macro_calendar.regions")
    for index, region in enumerate(regions):
        _require_supported_value(region, f"macro_calendar.regions[{index}]", SUPPORTED_MACRO_CALENDAR_REGIONS)
    _require_positive_int(macro_calendar, "lookback_days", "macro_calendar.lookback_days")
    _require_positive_int(macro_calendar, "lookahead_days", "macro_calendar.lookahead_days")
    if "source_url" in macro_calendar:
        _require_proxy_url(macro_calendar, "source_url", "macro_calendar.source_url")


def _validate_onchain_flow_config(onchain_flow: Any) -> None:
    if not isinstance(onchain_flow, dict):
        raise ConfigError("onchain_flow must be a mapping.")
    _reject_unsupported_fields(
        onchain_flow,
        path="onchain_flow",
        supported_fields=SUPPORTED_ONCHAIN_FLOW_FIELDS,
    )

    enabled = _require_bool(onchain_flow, "enabled", "onchain_flow.enabled")
    if not enabled:
        return

    source = _require_non_empty_string(onchain_flow, "source", "onchain_flow.source")
    _require_supported_value(source, "onchain_flow.source", SUPPORTED_ONCHAIN_FLOW_SOURCES)

    data_classes = _require_non_empty_string_list(
        onchain_flow,
        "data_classes",
        "onchain_flow.data_classes",
    )
    for index, data_class in enumerate(data_classes):
        _require_supported_value(
            data_class,
            f"onchain_flow.data_classes[{index}]",
            SUPPORTED_ONCHAIN_FLOW_DATA_CLASSES,
        )

    assets = _require_non_empty_string_list(onchain_flow, "assets", "onchain_flow.assets")
    for index, asset in enumerate(assets):
        _require_supported_value(asset, f"onchain_flow.assets[{index}]", SUPPORTED_ONCHAIN_FLOW_ASSETS)

    chains = _require_non_empty_string_list(onchain_flow, "chains", "onchain_flow.chains")
    for index, chain in enumerate(chains):
        _require_supported_value(chain, f"onchain_flow.chains[{index}]", SUPPORTED_ONCHAIN_FLOW_CHAINS)

    _require_positive_int(onchain_flow, "lookback_days", "onchain_flow.lookback_days")
    for key in ("stablecoin_source_url", "chain_activity_source_url", "network_congestion_source_url"):
        if key in onchain_flow:
            _require_proxy_url(onchain_flow, key, f"onchain_flow.{key}")


def _validate_quant_config(quant: dict[str, Any]) -> None:
    has_strategies = "strategies" in quant
    if "signals" in quant:
        supported = ", ".join(sorted(SUPPORTED_QUANT_STRATEGIES))
        raise ConfigError(f"quant.signals is retired; use quant.strategies with: {supported}.")
    if not has_strategies:
        raise ConfigError("quant.enabled requires quant.strategies.")

    if "engine" in quant:
        engine = _require_non_empty_string(quant, "engine", "quant.engine")
        _require_supported_value(engine, "quant.engine", SUPPORTED_QUANT_ENGINES)

    if has_strategies:
        strategies = _require_non_empty_list(quant, "strategies", "quant.strategies")
        for index, strategy in enumerate(strategies):
            path = f"quant.strategies[{index}]"
            if not isinstance(strategy, dict):
                raise ConfigError(f"{path} must be a mapping.")
            name = _require_non_empty_string(strategy, "name", f"{path}.name")
            _require_supported_value(name, f"{path}.name", SUPPORTED_QUANT_STRATEGIES)
            if "enabled" in strategy:
                _require_bool(strategy, "enabled", f"{path}.enabled")
            if "params" in strategy and not isinstance(strategy["params"], dict):
                raise ConfigError(f"{path}.params must be a mapping.")
            if isinstance(strategy.get("params"), dict):
                _validate_quant_strategy_params(name, strategy["params"], f"{path}.params")
            if "targeted_params" in strategy:
                _validate_quant_strategy_targeted_params(name, strategy["targeted_params"], f"{path}.targeted_params")
            if "backtest" in strategy:
                backtest = strategy["backtest"]
                if not isinstance(backtest, dict):
                    raise ConfigError(f"{path}.backtest must be a mapping.")
                _validate_quant_strategy_backtest(backtest, f"{path}.backtest")
    if "parameter_diagnostics" in quant:
        diagnostics = quant["parameter_diagnostics"]
        if not isinstance(diagnostics, dict):
            raise ConfigError("quant.parameter_diagnostics must be a mapping.")
        _validate_quant_parameter_diagnostics(diagnostics, "quant.parameter_diagnostics")
    if "benchmark_suite" in quant:
        suite = quant["benchmark_suite"]
        if not isinstance(suite, dict):
            raise ConfigError("quant.benchmark_suite must be a mapping.")
        _validate_quant_benchmark_suite(suite, "quant.benchmark_suite")
    if "effectiveness_gates" in quant:
        gates = quant["effectiveness_gates"]
        if not isinstance(gates, dict):
            raise ConfigError("quant.effectiveness_gates must be a mapping.")
        _validate_quant_effectiveness_gates(gates, "quant.effectiveness_gates")
    if "lifecycle_policy" in quant:
        policy = quant["lifecycle_policy"]
        if not isinstance(policy, dict):
            raise ConfigError("quant.lifecycle_policy must be a mapping.")
        _validate_quant_lifecycle_policy(policy, "quant.lifecycle_policy")


def _validate_quant_strategy_params(name: str, params: dict[str, Any], path: str) -> None:
    if name == "signed_tsmom_trend":
        if "return_window" in params:
            _require_positive_int(params, "return_window", f"{path}.return_window")
        if "deadband_pct" in params:
            _require_bounded_number(params, "deadband_pct", f"{path}.deadband_pct", minimum=0.0, maximum=100.0)
        if "volatility_filter_enabled" in params:
            _require_bool(params, "volatility_filter_enabled", f"{path}.volatility_filter_enabled")
        if "volatility_filter_window" in params:
            _require_positive_int(params, "volatility_filter_window", f"{path}.volatility_filter_window")
        if "max_realized_volatility_pct" in params:
            _require_positive_number(params, "max_realized_volatility_pct", f"{path}.max_realized_volatility_pct")
        if "funding_rate_filter_enabled" in params:
            _require_bool(params, "funding_rate_filter_enabled", f"{path}.funding_rate_filter_enabled")
        if "max_abs_funding_rate" in params:
            _require_positive_number(params, "max_abs_funding_rate", f"{path}.max_abs_funding_rate")
        if "market_anomaly_filter_enabled" in params:
            _require_bool(params, "market_anomaly_filter_enabled", f"{path}.market_anomaly_filter_enabled")
        if "market_anomaly_filter_lookback_hours" in params:
            _require_positive_number(
                params,
                "market_anomaly_filter_lookback_hours",
                f"{path}.market_anomaly_filter_lookback_hours",
            )
        if "market_anomaly_filter_min_count" in params:
            _require_positive_int(params, "market_anomaly_filter_min_count", f"{path}.market_anomaly_filter_min_count")
    if name == "tsmom_vol_scaled":
        if "return_window" in params:
            _require_positive_int(params, "return_window", f"{path}.return_window")
        if "volatility_window" in params:
            _require_positive_int(params, "volatility_window", f"{path}.volatility_window")
        if "target_volatility" in params:
            _require_positive_number(params, "target_volatility", f"{path}.target_volatility")
    if name == "breakout_atr_trend":
        if "breakout_window" in params:
            _require_positive_int(params, "breakout_window", f"{path}.breakout_window")
        if "exit_window" in params:
            _require_positive_int(params, "exit_window", f"{path}.exit_window")
        if "atr_window" in params:
            _require_positive_int(params, "atr_window", f"{path}.atr_window")
    if name in {"bollinger_rsi_reversion", "bollinger_rsi_long_short"}:
        if "bollinger_window" in params:
            _require_positive_int(params, "bollinger_window", f"{path}.bollinger_window")
        if "band_std" in params:
            _require_positive_number(params, "band_std", f"{path}.band_std")
        if "rsi_window" in params:
            _require_positive_int(params, "rsi_window", f"{path}.rsi_window")
        if "trend_window" in params:
            _require_positive_int(params, "trend_window", f"{path}.trend_window")
        if "trend_filter_pct" in params:
            _require_positive_number(params, "trend_filter_pct", f"{path}.trend_filter_pct")
        _validate_bollinger_rsi_thresholds(params, path)
    if name == "sma_cross_trend":
        if "short_window" in params:
            _require_positive_int(params, "short_window", f"{path}.short_window")
        if "long_window" in params:
            _require_positive_int(params, "long_window", f"{path}.long_window")
        _validate_sma_cross_windows(params, path)
    if name == "sma_cross_long_short":
        if "short_window" in params:
            _require_positive_int(params, "short_window", f"{path}.short_window")
        if "long_window" in params:
            _require_positive_int(params, "long_window", f"{path}.long_window")
        if "neutral_band_pct" in params:
            _require_bounded_number(params, "neutral_band_pct", f"{path}.neutral_band_pct", minimum=0.0, maximum=100.0)
        _validate_sma_cross_windows(params, path)
    if name == "pair_zscore_reversion":
        if "lookback_window" in params:
            _require_positive_int(params, "lookback_window", f"{path}.lookback_window")
        if "entry_zscore" in params:
            _require_positive_number(params, "entry_zscore", f"{path}.entry_zscore")
        if "exit_zscore" in params:
            _require_non_negative_number(params, "exit_zscore", f"{path}.exit_zscore")
        if "hedge_ratio" in params:
            _require_positive_number(params, "hedge_ratio", f"{path}.hedge_ratio")
        _validate_pair_zscore_thresholds(params, path)
    if name == "cross_sectional_momentum":
        if "lookback_window" in params:
            _require_positive_int(params, "lookback_window", f"{path}.lookback_window")
        if "long_count" in params:
            _require_positive_int(params, "long_count", f"{path}.long_count")
        if "short_count" in params:
            _require_positive_int(params, "short_count", f"{path}.short_count")
        if "min_instrument_count" in params:
            _require_positive_int(params, "min_instrument_count", f"{path}.min_instrument_count")
        _validate_cross_sectional_counts(params, path)


def _validate_quant_strategy_targeted_params(name: str, profiles: Any, path: str) -> None:
    if not isinstance(profiles, list):
        raise ConfigError(f"{path} must be a list.")
    seen: set[tuple[str, str, str]] = set()
    for index, profile in enumerate(profiles):
        profile_path = f"{path}[{index}]"
        if not isinstance(profile, dict):
            raise ConfigError(f"{profile_path} must be a mapping.")
        source = _require_non_empty_string(profile, "source", f"{profile_path}.source")
        symbol = _require_non_empty_string(profile, "symbol", f"{profile_path}.symbol")
        timeframe = _require_non_empty_string(profile, "timeframe", f"{profile_path}.timeframe")
        identity = (source, symbol, timeframe)
        if identity in seen:
            raise ConfigError(
                f"{profile_path} duplicates targeted params for source={source}, symbol={symbol}, timeframe={timeframe}."
            )
        seen.add(identity)
        params = profile.get("params")
        if not isinstance(params, dict):
            raise ConfigError(f"{profile_path}.params must be a mapping.")
        _validate_quant_strategy_params(name, params, f"{profile_path}.params")


def _validate_bollinger_rsi_thresholds(params: dict[str, Any], path: str) -> None:
    effective = {
        "rsi_oversold": 30.0,
        "rsi_overbought": 70.0,
    }
    effective.update(params)
    if "rsi_oversold" in params:
        _require_rsi_threshold(effective, "rsi_oversold", f"{path}.rsi_oversold")
    if "rsi_overbought" in params:
        _require_rsi_threshold(effective, "rsi_overbought", f"{path}.rsi_overbought")
    if "rsi_oversold" in params or "rsi_overbought" in params:
        oversold = _require_rsi_threshold(effective, "rsi_oversold", f"{path}.rsi_oversold")
        overbought = _require_rsi_threshold(effective, "rsi_overbought", f"{path}.rsi_overbought")
        if oversold >= overbought:
            raise ConfigError(f"{path}.rsi_oversold must be lower than {path}.rsi_overbought.")


def _require_rsi_threshold(data: dict[str, Any], key: str, path: str) -> float:
    value = data.get(key)
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(float(value))
        or float(value) <= 0
        or float(value) >= 100
    ):
        raise ConfigError(f"{path} must be a number greater than 0 and lower than 100.")
    return float(value)


def _validate_sma_cross_windows(params: dict[str, Any], path: str) -> None:
    effective = {
        "short_window": 20,
        "long_window": 50,
    }
    effective.update(params)
    short_window = _require_positive_int(effective, "short_window", f"{path}.short_window")
    long_window = _require_positive_int(effective, "long_window", f"{path}.long_window")
    if short_window >= long_window:
        raise ConfigError(f"{path}.short_window must be lower than {path}.long_window.")


def _validate_pair_zscore_thresholds(params: dict[str, Any], path: str) -> None:
    effective = {
        "entry_zscore": 2.0,
        "exit_zscore": 0.5,
    }
    effective.update(params)
    entry_zscore = _require_positive_number(effective, "entry_zscore", f"{path}.entry_zscore")
    exit_zscore = _require_non_negative_number(effective, "exit_zscore", f"{path}.exit_zscore")
    if exit_zscore >= entry_zscore:
        raise ConfigError(f"{path}.exit_zscore must be lower than {path}.entry_zscore.")


def _validate_cross_sectional_counts(params: dict[str, Any], path: str) -> None:
    effective = {
        "long_count": 1,
        "short_count": 1,
        "min_instrument_count": 3,
    }
    effective.update(params)
    long_count = _require_positive_int(effective, "long_count", f"{path}.long_count")
    short_count = _require_positive_int(effective, "short_count", f"{path}.short_count")
    min_instrument_count = _require_positive_int(
        effective,
        "min_instrument_count",
        f"{path}.min_instrument_count",
    )
    if min_instrument_count < long_count + short_count:
        raise ConfigError(f"{path}.min_instrument_count must be at least {path}.long_count + {path}.short_count.")


def _validate_quant_strategy_backtest(backtest: dict[str, Any], path: str) -> None:
    if "enabled" in backtest:
        _require_bool(backtest, "enabled", f"{path}.enabled")
    if "initial_cash" in backtest:
        _require_positive_number(backtest, "initial_cash", f"{path}.initial_cash")
    if "fees_bps" in backtest:
        _require_non_negative_number(backtest, "fees_bps", f"{path}.fees_bps")
    if "slippage_bps" in backtest:
        _require_non_negative_number(backtest, "slippage_bps", f"{path}.slippage_bps")
    if "mode" in backtest:
        mode = _require_non_empty_string(backtest, "mode", f"{path}.mode")
        _require_supported_value(mode, f"{path}.mode", SUPPORTED_BACKTEST_MODES)


def _validate_quant_parameter_diagnostics(diagnostics: dict[str, Any], path: str) -> None:
    enabled = _require_bool(diagnostics, "enabled", f"{path}.enabled")
    max_combinations = None
    if "max_combinations" in diagnostics:
        max_combinations = _require_positive_int(diagnostics, "max_combinations", f"{path}.max_combinations")
    elif enabled:
        raise ConfigError(f"{path}.max_combinations must be a positive integer.")

    if not enabled:
        return

    grids = diagnostics.get("grids")
    if not isinstance(grids, dict) or not grids:
        raise ConfigError(f"{path}.grids must be a non-empty mapping when parameter diagnostics are enabled.")
    for name, grid in grids.items():
        strategy_path = f"{path}.grids.{name}"
        if not isinstance(name, str) or not name.strip():
            raise ConfigError(f"{path}.grids keys must be strategy names.")
        _require_supported_value(name, strategy_path, SUPPORTED_QUANT_STRATEGIES)
        if not isinstance(grid, dict) or not grid:
            raise ConfigError(f"{strategy_path} must be a non-empty mapping.")
        _validate_quant_parameter_grid(name, grid, strategy_path, max_combinations=max_combinations)


def _validate_quant_parameter_grid(
    name: str,
    grid: dict[str, Any],
    path: str,
    *,
    max_combinations: int | None,
) -> None:
    combination_count = 1
    for param_name, values in grid.items():
        param_path = f"{path}.{param_name}"
        if not isinstance(param_name, str) or param_name not in SUPPORTED_QUANT_STRATEGY_PARAM_NAMES[name]:
            supported = ", ".join(sorted(SUPPORTED_QUANT_STRATEGY_PARAM_NAMES[name]))
            raise ConfigError(f"{param_path} is not supported for {name}. Supported params: {supported}.")
        if not isinstance(values, list) or not values:
            raise ConfigError(f"{param_path} must be a non-empty list.")
        combination_count *= len(values)
        for index, value in enumerate(values):
            _validate_quant_parameter_grid_value(name, param_name, value, f"{param_path}[{index}]")
    if max_combinations is not None and combination_count > max_combinations:
        raise ConfigError(f"{path} has {combination_count} combinations; max_combinations is {max_combinations}.")


def _validate_quant_parameter_grid_value(name: str, param_name: str, value: Any, path: str) -> None:
    if name == "signed_tsmom_trend":
        if param_name == "return_window":
            _require_positive_int_value(value, path)
        if param_name == "deadband_pct":
            _require_bounded_number_value(value, path, minimum=0.0, maximum=100.0)
        if param_name == "volatility_filter_enabled":
            if not isinstance(value, bool):
                raise ConfigError(f"{path} must be a boolean.")
        if param_name == "volatility_filter_window":
            _require_positive_int_value(value, path)
        if param_name == "max_realized_volatility_pct":
            _require_positive_number_value(value, path)
        if param_name == "funding_rate_filter_enabled":
            if not isinstance(value, bool):
                raise ConfigError(f"{path} must be a boolean.")
        if param_name == "max_abs_funding_rate":
            _require_positive_number_value(value, path)
        if param_name == "market_anomaly_filter_enabled":
            if not isinstance(value, bool):
                raise ConfigError(f"{path} must be a boolean.")
        if param_name == "market_anomaly_filter_lookback_hours":
            _require_positive_number_value(value, path)
        if param_name == "market_anomaly_filter_min_count":
            _require_positive_int_value(value, path)
    if name == "tsmom_vol_scaled":
        if param_name in {"return_window", "volatility_window"}:
            _require_positive_int_value(value, path)
        if param_name == "target_volatility":
            _require_positive_number_value(value, path)
    if name == "breakout_atr_trend":
        _require_positive_int_value(value, path)
    if name in {"bollinger_rsi_reversion", "bollinger_rsi_long_short"}:
        if param_name in {"bollinger_window", "rsi_window", "trend_window"}:
            _require_positive_int_value(value, path)
        if param_name in {"band_std", "trend_filter_pct"}:
            _require_positive_number_value(value, path)
        if param_name in {"rsi_oversold", "rsi_overbought"}:
            _require_rsi_threshold_value(value, path)
    if name == "sma_cross_trend":
        if param_name in {"short_window", "long_window"}:
            _require_positive_int_value(value, path)
    if name == "sma_cross_long_short":
        if param_name in {"short_window", "long_window"}:
            _require_positive_int_value(value, path)
        if param_name == "neutral_band_pct":
            _require_bounded_number_value(value, path, minimum=0.0, maximum=100.0)
    if name == "pair_zscore_reversion":
        if param_name == "lookback_window":
            _require_positive_int_value(value, path)
        if param_name in {"entry_zscore", "hedge_ratio"}:
            _require_positive_number_value(value, path)
        if param_name == "exit_zscore":
            _require_bounded_number_value(value, path, minimum=0.0, maximum=100.0)
    if name == "cross_sectional_momentum":
        _require_positive_int_value(value, path)


def _validate_quant_benchmark_suite(suite: dict[str, Any], path: str) -> None:
    if "enabled" in suite:
        _require_bool(suite, "enabled", f"{path}.enabled")
    if "windows" not in suite:
        return

    windows = _require_non_empty_list(suite, "windows", f"{path}.windows")
    names = set()
    for index, window in enumerate(windows):
        window_path = f"{path}.windows[{index}]"
        if not isinstance(window, dict):
            raise ConfigError(f"{window_path} must be a mapping.")
        name = _require_non_empty_string(window, "name", f"{window_path}.name")
        if name in names:
            raise ConfigError(f"{window_path}.name must be unique.")
        names.add(name)
        selection = str(window.get("selection") or "configured_lookback")
        _require_supported_value(selection, f"{window_path}.selection", SUPPORTED_BENCHMARK_WINDOW_SELECTIONS)
        if selection == "latest_lookback":
            _require_positive_int(window, "lookback", f"{window_path}.lookback")
        if selection == "date_window":
            _require_iso8601_utc_value(window, "start", f"{window_path}.start")
            _require_iso8601_utc_value(window, "end", f"{window_path}.end")
            if "minimum_rows" in window:
                _require_positive_int(window, "minimum_rows", f"{window_path}.minimum_rows")


def _require_positive_int_value(value: Any, path: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ConfigError(f"{path} must be a positive integer.")
    return value


def _require_positive_number_value(value: Any, path: str) -> float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(float(value))
        or float(value) <= 0
    ):
        raise ConfigError(f"{path} must be a positive number.")
    return float(value)


def _require_bounded_number_value(value: Any, path: str, *, minimum: float, maximum: float) -> float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(float(value))
        or float(value) < minimum
        or float(value) > maximum
    ):
        raise ConfigError(f"{path} must be a number between {minimum} and {maximum}.")
    return float(value)


def _require_rsi_threshold_value(value: Any, path: str) -> float:
    number = _require_positive_number_value(value, path)
    if number >= 100:
        raise ConfigError(f"{path} must be a number greater than 0 and lower than 100.")
    return number


def _require_iso8601_utc_value(data: dict[str, Any], key: str, path: str) -> None:
    value = data.get(key)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ConfigError(f"{path} must include a UTC offset.")
        return
    if isinstance(value, str) and value.strip():
        return
    raise ConfigError(f"{path} must be an ISO 8601 UTC string.")


def _validate_quant_effectiveness_gates(gates: dict[str, Any], path: str) -> None:
    unsupported = sorted(set(gates) - SUPPORTED_EFFECTIVENESS_GATE_FIELDS)
    if unsupported:
        supported = ", ".join(sorted(SUPPORTED_EFFECTIVENESS_GATE_FIELDS))
        names = ", ".join(unsupported)
        raise ConfigError(f"unsupported {path} field(s): {names}. Supported fields: {supported}.")

    positive_int_fields = {
        "min_min_sample_rows",
        "min_succeeded_benchmarks",
        "min_total_trade_count",
        "min_walk_forward_succeeded_windows",
    }
    non_negative_number_fields = {
        "max_abs_drawdown_pct",
        "max_abs_funding_drag_pct",
        "max_average_gross_exposure_pct",
        "max_cost_drag_pct",
        "max_turnover",
        "min_benchmark_success_rate_pct",
        "min_mean_excess_return_vs_buy_and_hold_pct",
        "min_mean_net_return_pct",
        "min_positive_excess_return_benchmark_pct",
        "min_positive_net_return_benchmark_pct",
        "min_walk_forward_positive_net_return_window_pct",
    }
    bool_fields = {
        "elevated_overfitting_blocks_effective",
        "require_parameter_stability",
        "require_walk_forward_stable",
    }
    for key in sorted(positive_int_fields & set(gates)):
        _require_positive_int(gates, key, f"{path}.{key}")
    for key in sorted(non_negative_number_fields & set(gates)):
        _require_non_negative_number(gates, key, f"{path}.{key}")
    for key in sorted(bool_fields & set(gates)):
        _require_bool(gates, key, f"{path}.{key}")


def _validate_quant_lifecycle_policy(policy: dict[str, Any], path: str) -> None:
    _reject_unsupported_fields(
        policy,
        path=path,
        supported_fields=SUPPORTED_LIFECYCLE_POLICY_FIELDS,
    )
    if "records" not in policy:
        return
    records = policy["records"]
    if not isinstance(records, list):
        raise ConfigError(f"{path}.records must be a list.")
    for index, record in enumerate(records):
        record_path = f"{path}.records[{index}]"
        if not isinstance(record, dict):
            raise ConfigError(f"{record_path} must be a mapping.")
        _reject_unsupported_fields(
            record,
            path=record_path,
            supported_fields=SUPPORTED_LIFECYCLE_POLICY_RECORD_FIELDS,
        )
        action = _require_non_empty_string(record, "action", f"{record_path}.action")
        _require_supported_value(action, f"{record_path}.action", SUPPORTED_LIFECYCLE_POLICY_ACTIONS)
        strategy_name = _require_non_empty_string(record, "strategy_name", f"{record_path}.strategy_name")
        _require_supported_value(
            strategy_name,
            f"{record_path}.strategy_name",
            SUPPORTED_QUANT_STRATEGIES,
        )
        _require_non_empty_string(record, "reason", f"{record_path}.reason")
        if "strategy_contract_version" in record:
            _require_non_empty_string(
                record,
                "strategy_contract_version",
                f"{record_path}.strategy_contract_version",
            )
        if "parameter_digest" in record:
            _require_non_empty_string(record, "parameter_digest", f"{record_path}.parameter_digest")
        if "created_at" in record:
            _require_iso8601_utc_value(record, "created_at", f"{record_path}.created_at")
        if "effective_at" in record and record["effective_at"] is not None:
            _require_iso8601_utc_value(record, "effective_at", f"{record_path}.effective_at")
        if "scope" in record:
            scope = record["scope"]
            if not isinstance(scope, dict):
                raise ConfigError(f"{record_path}.scope must be a mapping.")
            _reject_unsupported_fields(
                scope,
                path=f"{record_path}.scope",
                supported_fields=SUPPORTED_LIFECYCLE_POLICY_SCOPE_FIELDS,
            )
            if "symbol" in scope:
                _require_non_empty_string(scope, "symbol", f"{record_path}.scope.symbol")
            if "timeframe" in scope:
                _require_non_empty_string(scope, "timeframe", f"{record_path}.scope.timeframe")


def _validate_market_proxy_config(market: dict[str, Any]) -> None:
    proxy = market.get("proxy")
    if not isinstance(proxy, dict):
        raise ConfigError("market.proxy must be a mapping.")
    proxy_enabled = _require_bool(proxy, "enabled", "market.proxy.enabled")
    if proxy_enabled:
        _require_proxy_url(proxy, "url", "market.proxy.url")
    elif "url" in proxy:
        _require_proxy_url(proxy, "url", "market.proxy.url")


def _require_proxy_url(data: dict[str, Any], key: str, path: str) -> str:
    value = _require_http_url(data, key, path)
    parsed = urlparse(value)
    if parsed.username or parsed.password:
        raise ConfigError(f"{path} must not include credentials.")
    return value


def _require_outside_run_output_dir(
    storage_dir: str,
    config: dict[str, Any],
    *,
    config_path: Path | None,
) -> None:
    run_output_dir = config.get("run", {}).get("output_dir")
    if not isinstance(run_output_dir, str) or not run_output_dir.strip():
        return

    storage_path = _resolve_runtime_config_path(storage_dir, config_path)
    run_path = _resolve_runtime_config_path(run_output_dir, config_path)
    if storage_path == run_path or run_path in storage_path.parents:
        raise ConfigError("market.ohlcv.storage_dir must be outside run.output_dir.")


def _resolve_runtime_config_path(value: str, config_path: Path | None) -> Path:
    return resolve_runtime_path(value, config_path=config_path).resolve()


def _require_supported_value(value: str, path: str, supported_values: set[str]) -> None:
    if value not in supported_values:
        supported = ", ".join(sorted(supported_values))
        raise ConfigError(f"{path} must be one of: {supported}.")


def _require_non_empty_list(data: dict[str, Any], key: str, path: str) -> list[Any]:
    value = data.get(key)
    if not isinstance(value, list) or not value:
        raise ConfigError(f"{path} must be a non-empty list.")
    return value


def _require_non_empty_string_list(data: dict[str, Any], key: str, path: str) -> list[str]:
    values = _require_non_empty_list(data, key, path)
    for index, value in enumerate(values):
        if not isinstance(value, str) or not value.strip():
            raise ConfigError(f"{path}[{index}] must be a non-empty string.")
    return values
