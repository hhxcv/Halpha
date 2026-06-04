from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlparse


CONFIG_SECTIONS = {"codex", "market", "report", "run", "text"}


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
