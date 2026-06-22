from __future__ import annotations

from contextlib import suppress
from copy import deepcopy
from datetime import datetime, timezone
import os
from pathlib import Path
import shutil
from typing import Any
from uuid import uuid4

from halpha.config import ConfigError, load_config
from halpha.storage import config_base, safe_local_ref


CONFIG_BACKUP_DIR = "runs/dashboard/config_backups"
CONFIG_PROFILE_SECTIONS = (
    "General",
    "Market data",
    "Strategy",
    "Reports",
    "Monitor",
    "Intelligence sources",
    "Storage",
    "Dashboard",
)
CONFIG_PROFILE_FIELDS = (
    {
        "section": "General",
        "label": "Run timezone",
        "path": "run.timezone",
        "control": "select",
        "value_type": "string",
        "options": ("Asia/Shanghai", "UTC"),
        "description": "Default timezone used by local run artifacts.",
    },
    {
        "section": "Dashboard",
        "label": "Display timezone",
        "path": "dashboard.display_timezone",
        "control": "select",
        "value_type": "string",
        "options": ("Asia/Shanghai", "UTC"),
        "description": "Timezone used for timestamps displayed in dashboard pages.",
    },
    {
        "section": "Market data",
        "label": "Enable market data",
        "path": "market.enabled",
        "control": "toggle",
        "value_type": "bool",
        "description": "Collect market data for research runs.",
    },
    {
        "section": "Market data",
        "label": "Source",
        "path": "market.source",
        "control": "select",
        "value_type": "string",
        "options": ("binance",),
        "description": "Configured public market data source.",
    },
    {
        "section": "Market data",
        "label": "Symbols",
        "path": "market.symbols",
        "control": "tags",
        "value_type": "string_list",
        "description": "Comma-separated market symbols used by the local research pipeline.",
    },
    {
        "section": "Market data",
        "label": "OHLCV timeframes",
        "path": "market.ohlcv.timeframes",
        "control": "multi_select",
        "value_type": "string_list",
        "options": ("1d", "1h"),
        "description": "Reusable OHLCV windows maintained outside single-run artifacts.",
    },
    {
        "section": "Market data",
        "label": "Daily lookback",
        "path": "market.ohlcv.lookback.1d",
        "control": "number",
        "value_type": "positive_int",
        "description": "Number of daily candles to collect.",
    },
    {
        "section": "Market data",
        "label": "Hourly lookback",
        "path": "market.ohlcv.lookback.1h",
        "control": "number",
        "value_type": "positive_int",
        "description": "Number of hourly candles to collect.",
    },
    {
        "section": "Market data",
        "label": "Use proxy",
        "path": "market.proxy.enabled",
        "control": "toggle",
        "value_type": "bool",
        "description": "Enable a configured proxy without exposing proxy URL values in the dashboard.",
    },
    {
        "section": "Market data",
        "label": "Enable derivatives",
        "path": "market.derivatives.enabled",
        "control": "toggle",
        "value_type": "bool",
        "description": "Collect public derivatives market evidence when the derivatives source is configured.",
    },
    {
        "section": "Strategy",
        "label": "Enable quant research",
        "path": "quant.enabled",
        "control": "toggle",
        "value_type": "bool",
        "description": "Enable configured strategy evaluation and backtest evidence.",
    },
    {
        "section": "Reports",
        "label": "Report title",
        "path": "report.title",
        "control": "text",
        "value_type": "string",
        "description": "Human-readable report title used by generated Markdown reports.",
    },
    {
        "section": "Reports",
        "label": "Report language",
        "path": "report.language",
        "control": "select",
        "value_type": "string",
        "options": ("zh-CN",),
        "description": "Final reports are Simplified Chinese unless requested otherwise.",
    },
    {
        "section": "Reports",
        "label": "Enable Codex report",
        "path": "codex.enabled",
        "control": "toggle",
        "value_type": "bool",
        "description": "Allow report generation through the configured local Codex command.",
    },
    {
        "section": "Monitor",
        "label": "Interval seconds",
        "path": "monitor.interval_seconds",
        "control": "number",
        "value_type": "positive_int",
        "description": "Delay between monitor loop cycles.",
    },
    {
        "section": "Monitor",
        "label": "Max cycles",
        "path": "monitor.max_cycles",
        "control": "number",
        "value_type": "positive_int",
        "description": "Maximum monitor cycles for a bounded local loop.",
    },
    {
        "section": "Monitor",
        "label": "Cooldown seconds",
        "path": "monitor.cooldown_seconds",
        "control": "number",
        "value_type": "positive_int",
        "description": "Alert cooldown window.",
    },
    {
        "section": "Monitor",
        "label": "No Codex in monitor",
        "path": "monitor.no_codex",
        "control": "toggle",
        "value_type": "bool",
        "description": "Keep monitor cycles deterministic unless explicit report generation is requested.",
    },
    {
        "section": "Intelligence sources",
        "label": "Enable text collection",
        "path": "text.enabled",
        "control": "toggle",
        "value_type": "bool",
        "description": "Collect configured public text sources.",
    },
    {
        "section": "Intelligence sources",
        "label": "Max text items",
        "path": "text.max_items",
        "control": "number",
        "value_type": "positive_int",
        "description": "Maximum collected text items per run.",
    },
    {
        "section": "Intelligence sources",
        "label": "Enable text intelligence",
        "path": "text.intelligence.enabled",
        "control": "toggle",
        "value_type": "bool",
        "description": "Enable local text intelligence evidence generation.",
    },
    {
        "section": "Intelligence sources",
        "label": "Allow model download",
        "path": "text.intelligence.allow_model_download",
        "control": "toggle",
        "value_type": "bool",
        "description": "Permit configured model download when local models are missing.",
    },
    {
        "section": "Intelligence sources",
        "label": "Enable macro calendar",
        "path": "macro_calendar.enabled",
        "control": "toggle",
        "value_type": "bool",
        "description": "Collect configured public scheduled-event evidence.",
    },
    {
        "section": "Intelligence sources",
        "label": "Enable on-chain flow",
        "path": "onchain_flow.enabled",
        "control": "toggle",
        "value_type": "bool",
        "description": "Collect configured public on-chain and exchange-flow evidence.",
    },
)


def dashboard_config_profile(config: dict[str, Any], *, config_path: Path) -> dict[str, Any]:
    fields = [_config_profile_field(config, field) for field in CONFIG_PROFILE_FIELDS]
    return {
        "schema_version": 1,
        "artifact_type": "dashboard_config_profile",
        "status": "available",
        "config": {
            "ref": dashboard_config_ref(config_path),
            "editable": True,
            "requires_confirmation": True,
        },
        "sections": list(CONFIG_PROFILE_SECTIONS),
        "fields": fields,
        "warnings": [],
        "errors": [],
        "omitted": {
            "absolute_local_paths_embedded": False,
            "proxy_urls_embedded": False,
            "credentials_embedded": False,
            "raw_config_text_embedded": False,
        },
    }


def dashboard_backup_config(*, config_path: Path) -> dict[str, Any]:
    backup, error = _backup_dashboard_config(config_path)
    if error:
        return {
            "schema_version": 1,
            "artifact_type": "dashboard_config_backup",
            "status": "failed",
            "config": {"ref": dashboard_config_ref(config_path)},
            "backup_ref": None,
            "warnings": [],
            "errors": [error],
            "omitted": {"absolute_local_paths_embedded": False},
        }
    base = config_base(config_path)
    return {
        "schema_version": 1,
        "artifact_type": "dashboard_config_backup",
        "status": "succeeded",
        "config": {"ref": dashboard_config_ref(config_path)},
        "backup_ref": safe_local_ref(backup, base=base) if backup else None,
        "warnings": [],
        "errors": [],
        "omitted": {"absolute_local_paths_embedded": False},
    }


def dashboard_save_config_profile(
    config: dict[str, Any],
    *,
    config_path: Path,
    request: dict[str, Any],
) -> dict[str, Any]:
    if request.get("confirm") is not True:
        return _config_save_result(
            config,
            config_path=config_path,
            status="blocked",
            errors=["confirm must be true to save dashboard settings."],
        )

    changes = request.get("changes")
    if not isinstance(changes, dict) or not changes:
        return _config_save_result(
            config,
            config_path=config_path,
            status="skipped",
            warnings=["no config changes were submitted."],
        )

    next_config = deepcopy(config)
    changed_paths: list[str] = []
    errors: list[str] = []
    for path, raw_value in sorted(changes.items()):
        if not isinstance(path, str):
            errors.append("config change path must be a string.")
            continue
        field = _config_profile_field_definition(path)
        if field is None:
            errors.append(f"{path} is not editable from the dashboard settings UI.")
            continue
        value, error = _coerce_config_profile_value(raw_value, field)
        if error:
            errors.append(f"{path}: {error}")
            continue
        _set_config_value(next_config, path, value)
        changed_paths.append(path)
    if errors:
        return _config_save_result(config, config_path=config_path, status="failed", errors=errors)

    serialized, error = _serialize_config_yaml(next_config)
    if error:
        return _config_save_result(config, config_path=config_path, status="failed", errors=[error])

    temp_path = _dashboard_config_temp_path(config_path)
    backup_path: Path | None = None
    try:
        _write_text_for_validation(temp_path, serialized)
        try:
            validated = load_config(temp_path)
        except ConfigError as exc:
            return _config_save_result(
                config,
                config_path=config_path,
                status="failed",
                errors=[sanitize_dashboard_message(str(exc), config_path=temp_path)],
            )
        backup_path, backup_error = _backup_dashboard_config(config_path)
        if backup_error:
            return _config_save_result(config, config_path=config_path, status="failed", errors=[backup_error])
        os.replace(temp_path, config_path)
    except OSError as exc:
        return _config_save_result(
            config,
            config_path=config_path,
            status="failed",
            errors=[sanitize_dashboard_message(f"config file could not be saved: {exc}", config_path=config_path)],
        )
    finally:
        with suppress(OSError):
            if temp_path.exists():
                temp_path.unlink()

    config.clear()
    config.update(validated)
    base = config_base(config_path)
    return _config_save_result(
        config,
        config_path=config_path,
        status="succeeded",
        changed_paths=changed_paths,
        backup_ref=safe_local_ref(backup_path, base=base) if backup_path else None,
    )


def dashboard_config_ref(config_path: Path) -> str:
    path = Path(config_path)
    if not path.is_absolute():
        return path.as_posix()
    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return "<external-config>"


def _dashboard_config_temp_path(config_path: Path) -> Path:
    return config_path.with_name(f".{config_path.name}.{uuid4().hex}.dashboard-save.tmp")


def _write_text_for_validation(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())


def sanitize_dashboard_message(message: str, *, config_path: Path) -> str:
    safe_ref = dashboard_config_ref(config_path)
    variants = {str(config_path), config_path.as_posix()}
    try:
        variants.add(str(config_path.resolve()))
        variants.add(config_path.resolve().as_posix())
    except OSError:
        pass

    sanitized = message
    for value in sorted(variants, key=len, reverse=True):
        if value:
            sanitized = sanitized.replace(value, safe_ref)
    return sanitized


def _config_profile_field(config: dict[str, Any], field: dict[str, Any]) -> dict[str, Any]:
    path = str(field["path"])
    value = _get_config_value(config, path)
    if value is None:
        value = _config_profile_default(field)
    result = {
        "section": field["section"],
        "label": field["label"],
        "path": path,
        "control": field["control"],
        "value_type": field["value_type"],
        "value": value,
        "description": field.get("description") or "",
    }
    options = field.get("options")
    if isinstance(options, tuple):
        result["options"] = list(options)
    return result


def _config_profile_field_definition(path: str) -> dict[str, Any] | None:
    for field in CONFIG_PROFILE_FIELDS:
        if field.get("path") == path:
            return field
    return None


def _config_profile_default(field: dict[str, Any]) -> Any:
    value_type = field.get("value_type")
    if value_type == "bool":
        return False
    if value_type == "positive_int":
        return 1
    if value_type == "string_list":
        options = field.get("options")
        return [options[0]] if isinstance(options, tuple) and options else []
    options = field.get("options")
    if isinstance(options, tuple) and options:
        return options[0]
    return ""


def _get_config_value(config: dict[str, Any], path: str) -> Any:
    current: Any = config
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _set_config_value(config: dict[str, Any], path: str, value: Any) -> None:
    current: dict[str, Any] = config
    parts = path.split(".")
    for part in parts[:-1]:
        child = current.get(part)
        if not isinstance(child, dict):
            child = {}
            current[part] = child
        current = child
    current[parts[-1]] = value


def _coerce_config_profile_value(raw_value: Any, field: dict[str, Any]) -> tuple[Any, str | None]:
    value_type = field.get("value_type")
    options = field.get("options")
    if value_type == "bool":
        if isinstance(raw_value, bool):
            return raw_value, None
        return None, "value must be true or false."
    if value_type == "positive_int":
        if isinstance(raw_value, bool):
            return None, "value must be a positive integer."
        try:
            value = int(raw_value)
        except (TypeError, ValueError):
            return None, "value must be a positive integer."
        if value <= 0:
            return None, "value must be a positive integer."
        return value, None
    if value_type == "string_list":
        if not isinstance(raw_value, list):
            return None, "value must be a list of strings."
        values = [str(value).strip() for value in raw_value if str(value).strip()]
        if not values:
            return None, "value must include at least one string."
        if isinstance(options, tuple):
            unsupported = sorted(set(values) - set(str(option) for option in options))
            if unsupported:
                return None, f"unsupported value(s): {', '.join(unsupported)}."
        return values, None
    if not isinstance(raw_value, str) or not raw_value.strip():
        return None, "value must be a non-empty string."
    value = raw_value.strip()
    if isinstance(options, tuple) and value not in options:
        return None, f"value must be one of: {', '.join(str(option) for option in options)}."
    return value, None


def _serialize_config_yaml(config: dict[str, Any]) -> tuple[str, str | None]:
    try:
        import yaml
    except ModuleNotFoundError:
        return "", "PyYAML is required to save YAML config files."
    try:
        return yaml.safe_dump(config, allow_unicode=True, sort_keys=False), None
    except yaml.YAMLError as exc:
        return "", f"config could not be serialized as YAML: {exc}"


def _backup_dashboard_config(config_path: Path) -> tuple[Path | None, str | None]:
    base = config_base(config_path)
    source = config_path if config_path.is_absolute() else base / config_path.name
    if not source.exists():
        return None, f"{dashboard_config_ref(config_path)} was not found."
    safe_stem = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in source.stem) or "config"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup_dir = base / CONFIG_BACKUP_DIR
    backup_path = backup_dir / f"{safe_stem}-{stamp}.yaml.bak"
    try:
        backup_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, backup_path)
    except OSError as exc:
        return None, sanitize_dashboard_message(f"config backup could not be created: {exc}", config_path=config_path)
    return backup_path, None


def _config_save_result(
    config: dict[str, Any],
    *,
    config_path: Path,
    status: str,
    changed_paths: list[str] | None = None,
    backup_ref: str | None = None,
    warnings: list[str] | None = None,
    errors: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "artifact_type": "dashboard_config_save_result",
        "status": status,
        "config": {"ref": dashboard_config_ref(config_path)},
        "changed_paths": changed_paths or [],
        "backup_ref": backup_ref,
        "profile": dashboard_config_profile(config, config_path=config_path),
        "warnings": warnings or [],
        "errors": errors or [],
        "omitted": {
            "absolute_local_paths_embedded": False,
            "raw_config_text_embedded": False,
            "credentials_embedded": False,
        },
    }
