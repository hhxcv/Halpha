from __future__ import annotations

import math
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .quant.registry import SUPPORTED_STRATEGY_NAMES


CONFIG_SECTIONS = {"codex", "market", "quant", "report", "run", "text"}
SUPPORTED_OHLCV_MARKET_SOURCES = {"binance"}
SUPPORTED_OHLCV_TIMEFRAMES = {"1d", "1h"}
SUPPORTED_QUANT_ENGINES = {"vectorbt"}
SUPPORTED_QUANT_STRATEGIES = SUPPORTED_STRATEGY_NAMES
SUPPORTED_BACKTEST_MODES = {"long_flat", "long_only"}
SUPPORTED_QUANT_STRATEGY_PARAM_NAMES = {
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
        _require_non_empty_string(market, "source", "market.source")
        _require_non_empty_string_list(market, "symbols", "market.symbols")
        if "proxy" in market:
            _validate_market_proxy_config(market)

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


def _validate_quant_strategy_params(name: str, params: dict[str, Any], path: str) -> None:
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
    if name == "bollinger_rsi_reversion":
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
    if name == "tsmom_vol_scaled":
        if param_name in {"return_window", "volatility_window"}:
            _require_positive_int_value(value, path)
        if param_name == "target_volatility":
            _require_positive_number_value(value, path)
    if name == "breakout_atr_trend":
        _require_positive_int_value(value, path)
    if name == "bollinger_rsi_reversion":
        if param_name in {"bollinger_window", "rsi_window", "trend_window"}:
            _require_positive_int_value(value, path)
        if param_name in {"band_std", "trend_filter_pct"}:
            _require_positive_number_value(value, path)
        if param_name in {"rsi_oversold", "rsi_overbought"}:
            _require_rsi_threshold_value(value, path)


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


def _require_rsi_threshold_value(value: Any, path: str) -> float:
    number = _require_positive_number_value(value, path)
    if number >= 100:
        raise ConfigError(f"{path} must be a number greater than 0 and lower than 100.")
    return number


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
