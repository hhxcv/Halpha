from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlparse


CONFIG_SECTIONS = {"codex", "market", "quant", "report", "run", "text"}
SUPPORTED_MARKET_SOURCES = {"binance"}
SUPPORTED_OHLCV_TIMEFRAMES = {"1d", "1h"}
SUPPORTED_QUANT_SIGNALS = {"trend", "momentum", "volatility", "volume_anomaly"}


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

    validate_config(loaded)
    return loaded


def validate_config(config: dict[str, Any]) -> None:
    _validate_config_sections(config)

    run = _require_mapping(config, "run")
    _require_non_empty_string(run, "output_dir", "run.output_dir")
    if "timezone" in run:
        _require_non_empty_string(run, "timezone", "run.timezone")

    market = _require_mapping(config, "market")
    market_enabled = _require_bool(market, "enabled", "market.enabled")
    if market_enabled:
        market_source = _require_non_empty_string(market, "source", "market.source")
        _require_supported_value(market_source, "market.source", SUPPORTED_MARKET_SOURCES)
        _require_non_empty_string_list(market, "symbols", "market.symbols")

    quant = _optional_mapping(config, "quant")
    quant_enabled = False
    if quant is not None:
        quant_enabled = _require_bool(quant, "enabled", "quant.enabled")
        if quant_enabled:
            _require_non_empty_string_list(quant, "signals", "quant.signals")
            for index, signal in enumerate(quant["signals"]):
                _require_supported_value(signal, f"quant.signals[{index}]", SUPPORTED_QUANT_SIGNALS)

    if quant_enabled and not market_enabled:
        raise ConfigError("quant.enabled requires market.enabled to be true.")
    if quant_enabled or "ohlcv" in market:
        _validate_ohlcv_config(config, market, quant_enabled=quant_enabled)

    text = _require_mapping(config, "text")
    text_enabled = _require_bool(text, "enabled", "text.enabled")
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


def _validate_ohlcv_config(config: dict[str, Any], market: dict[str, Any], *, quant_enabled: bool) -> None:
    if quant_enabled and not isinstance(market.get("ohlcv"), dict):
        raise ConfigError("market.ohlcv must be a mapping when quant.enabled is true.")
    ohlcv = market.get("ohlcv")
    if not isinstance(ohlcv, dict):
        raise ConfigError("market.ohlcv must be a mapping.")
    storage_dir = _require_non_empty_string(ohlcv, "storage_dir", "market.ohlcv.storage_dir")
    _require_outside_run_output_dir(storage_dir, config)

    timeframes = _require_non_empty_string_list(ohlcv, "timeframes", "market.ohlcv.timeframes")
    for index, timeframe in enumerate(timeframes):
        _require_supported_value(timeframe, f"market.ohlcv.timeframes[{index}]", SUPPORTED_OHLCV_TIMEFRAMES)

    lookback = ohlcv.get("lookback")
    if not isinstance(lookback, dict):
        raise ConfigError("market.ohlcv.lookback must be a mapping.")
    for timeframe in timeframes:
        _require_positive_int(lookback, timeframe, f"market.ohlcv.lookback.{timeframe}")


def _require_outside_run_output_dir(storage_dir: str, config: dict[str, Any]) -> None:
    run_output_dir = config.get("run", {}).get("output_dir")
    if not isinstance(run_output_dir, str) or not run_output_dir.strip():
        return

    storage_path = Path(storage_dir)
    run_path = Path(run_output_dir)
    if storage_path == run_path or run_path in storage_path.parents:
        raise ConfigError("market.ohlcv.storage_dir must be outside run.output_dir.")


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
