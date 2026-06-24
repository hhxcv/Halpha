from __future__ import annotations

import json
from datetime import datetime, timezone
from json import JSONDecodeError
from typing import Any

from halpha.runtime.pipeline_contracts import PipelineError, RunContext
from halpha.storage import resolve_runtime_path, write_json


STAGE_NAME = "build_user_state_context"
USER_STATE_CONTEXT_ARTIFACT = "analysis/user_state_context.json"
SCHEMA_VERSION = 1

ALLOWED_ROOT_FIELDS = {
    "schema_version",
    "watchlist",
    "disabled_assets",
    "risk",
    "preferred_timeframes",
    "strategy_preferences",
    "manual_exposure_notes",
}
WATCHLIST_FIELDS = {"symbol", "timeframes", "relevance"}
DISABLED_ASSET_FIELDS = {"symbol", "reason_code"}
RISK_FIELDS = {"preference", "max_risk_state", "max_action_level", "allow_new_exposure"}
STRATEGY_PREFERENCE_FIELDS = {"preferred", "disabled"}
MANUAL_EXPOSURE_FIELDS = {"symbol", "exposure_state", "private_note"}
RELEVANCE_VALUES = {"low", "medium", "high"}
RISK_PREFERENCES = {"conservative", "balanced", "aggressive"}
RISK_STATES = {"low", "medium", "high", "extreme"}
ACTION_LEVELS = {"NO_ACTION", "WATCH", "TRY_SMALL", "DO"}
EXPOSURE_STATES = {"none", "watch", "small", "material", "unknown"}


def build_user_state_context(
    config: dict[str, Any],
    run: RunContext,
    *,
    now: datetime | str | None = None,
) -> list[str]:
    created_at = _format_utc(now)
    user_config = config.get("user_state")
    if not isinstance(user_config, dict) or user_config.get("enabled") is not True:
        artifact = _skipped_artifact(run, created_at=created_at)
        _write_artifact(run, artifact)
        return [USER_STATE_CONTEXT_ARTIFACT]

    try:
        loaded = _load_user_state_file(user_config, run)
        artifact = _context_artifact(run, loaded, created_at=created_at)
    except _UserStateValidationError as exc:
        artifact = _failed_artifact(run, created_at=created_at, errors=exc.errors)
        _write_artifact(run, artifact)
        raise PipelineError(
            "configured user-state input is invalid; inspect analysis/user_state_context.json.",
            stage=STAGE_NAME,
            artifacts=[USER_STATE_CONTEXT_ARTIFACT],
            error_details={"errors": exc.errors},
        ) from exc

    _write_artifact(run, artifact)
    return [USER_STATE_CONTEXT_ARTIFACT]


class _UserStateValidationError(Exception):
    def __init__(self, errors: list[str]) -> None:
        super().__init__("configured user-state input is invalid")
        self.errors = errors


def _skipped_artifact(run: RunContext, *, created_at: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "user_state_context",
        "run_id": run.run_id,
        "created_at": created_at,
        "status": "skipped",
        "mode": "general",
        "source": _source(configured=False),
        "privacy": _privacy(omitted_private_values=0),
        "watchlist": [],
        "disabled_assets": [],
        "risk": {},
        "preferred_timeframes": [],
        "strategy_preferences": {"preferred": [], "disabled": []},
        "manual_exposure_summary": [],
        "counts": _counts([], [], [], {"preferred": [], "disabled": []}, [], 0, warnings=[], errors=[]),
        "warnings": [],
        "errors": [],
        "source_artifacts": [],
    }


def _failed_artifact(run: RunContext, *, created_at: str, errors: list[str]) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "user_state_context",
        "run_id": run.run_id,
        "created_at": created_at,
        "status": "failed",
        "mode": "invalid",
        "source": _source(configured=True),
        "privacy": _privacy(omitted_private_values=0),
        "watchlist": [],
        "disabled_assets": [],
        "risk": {},
        "preferred_timeframes": [],
        "strategy_preferences": {"preferred": [], "disabled": []},
        "manual_exposure_summary": [],
        "counts": _counts([], [], [], {"preferred": [], "disabled": []}, [], 0, warnings=[], errors=errors),
        "warnings": [],
        "errors": [{"message": error} for error in errors],
        "source_artifacts": [],
    }


def _context_artifact(run: RunContext, data: dict[str, Any], *, created_at: str) -> dict[str, Any]:
    errors = _schema_errors(data)
    if errors:
        raise _UserStateValidationError(errors)

    watchlist = _watchlist(data.get("watchlist"))
    disabled_assets = _disabled_assets(data.get("disabled_assets"))
    risk = _risk(data.get("risk"))
    preferred_timeframes = _string_list(data.get("preferred_timeframes"))
    strategy_preferences = _strategy_preferences(data.get("strategy_preferences"))
    manual_exposure_summary, omitted_private_values = _manual_exposure_summary(data.get("manual_exposure_notes"))

    warnings: list[str] = []
    artifact = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "user_state_context",
        "run_id": run.run_id,
        "created_at": created_at,
        "status": "ok",
        "mode": "personalized",
        "source": _source(configured=True),
        "privacy": _privacy(omitted_private_values=omitted_private_values),
        "watchlist": watchlist,
        "disabled_assets": disabled_assets,
        "risk": risk,
        "preferred_timeframes": preferred_timeframes,
        "strategy_preferences": strategy_preferences,
        "manual_exposure_summary": manual_exposure_summary,
        "counts": _counts(
            watchlist,
            disabled_assets,
            preferred_timeframes,
            strategy_preferences,
            manual_exposure_summary,
            omitted_private_values,
            warnings=warnings,
            errors=[],
        ),
        "warnings": warnings,
        "errors": [],
        "source_artifacts": [],
    }
    return artifact


def _load_user_state_file(config: dict[str, Any], run: RunContext) -> dict[str, Any]:
    path_value = config.get("path")
    if not isinstance(path_value, str) or not path_value.strip():
        raise _UserStateValidationError(["user_state.path must be configured when user_state.enabled is true."])
    path = resolve_runtime_path(path_value, config_path=run.config_path)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise _UserStateValidationError(["configured user-state file was not found."]) from exc
    except OSError as exc:
        raise _UserStateValidationError(["configured user-state file could not be read."]) from exc

    if path.suffix.lower() == ".json":
        try:
            loaded = json.loads(text)
        except JSONDecodeError as exc:
            raise _UserStateValidationError(["configured user-state file is not valid JSON."]) from exc
    else:
        try:
            import yaml
        except ModuleNotFoundError as exc:
            raise _UserStateValidationError(["PyYAML is required to read YAML user-state files."]) from exc
        try:
            loaded = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise _UserStateValidationError(["configured user-state file is not valid YAML."]) from exc
    if loaded is None:
        loaded = {}
    if not isinstance(loaded, dict):
        raise _UserStateValidationError(["user-state root must be a mapping."])
    return loaded


def _schema_errors(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    unsupported = sorted(set(data) - ALLOWED_ROOT_FIELDS)
    if unsupported:
        errors.append("unsupported user-state field(s): " + ", ".join(unsupported) + ".")
    if data.get("schema_version") != SCHEMA_VERSION:
        errors.append("schema_version must be 1.")
    _validate_list(data, "watchlist", errors)
    _validate_list(data, "disabled_assets", errors)
    _validate_mapping(data, "risk", errors)
    _validate_list(data, "preferred_timeframes", errors)
    _validate_mapping(data, "strategy_preferences", errors)
    _validate_list(data, "manual_exposure_notes", errors)
    if errors:
        return errors
    _validate_watchlist(data.get("watchlist"), errors)
    _validate_disabled_assets(data.get("disabled_assets"), errors)
    _validate_risk(data.get("risk"), errors)
    if "preferred_timeframes" in data:
        _validate_string_list(data.get("preferred_timeframes"), "preferred_timeframes", errors)
    _validate_strategy_preferences(data.get("strategy_preferences"), errors)
    _validate_manual_exposure_notes(data.get("manual_exposure_notes"), errors)
    return errors


def _validate_list(data: dict[str, Any], key: str, errors: list[str]) -> None:
    if key in data and not isinstance(data.get(key), list):
        errors.append(f"{key} must be a list.")


def _validate_mapping(data: dict[str, Any], key: str, errors: list[str]) -> None:
    if key in data and not isinstance(data.get(key), dict):
        errors.append(f"{key} must be a mapping.")


def _validate_watchlist(value: Any, errors: list[str]) -> None:
    for index, item in enumerate(_list(value)):
        path = f"watchlist[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{path} must be a mapping.")
            continue
        _validate_supported_fields(item, path, WATCHLIST_FIELDS, errors)
        _required_string(item, "symbol", f"{path}.symbol", errors)
        if "timeframes" in item:
            _validate_string_list(item.get("timeframes"), f"{path}.timeframes", errors)
        if "relevance" in item and item.get("relevance") not in RELEVANCE_VALUES:
            errors.append(f"{path}.relevance must be one of: high, low, medium.")


def _validate_disabled_assets(value: Any, errors: list[str]) -> None:
    for index, item in enumerate(_list(value)):
        path = f"disabled_assets[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{path} must be a mapping.")
            continue
        _validate_supported_fields(item, path, DISABLED_ASSET_FIELDS, errors)
        _required_string(item, "symbol", f"{path}.symbol", errors)
        if "reason_code" in item:
            _optional_string(item, "reason_code", f"{path}.reason_code", errors)


def _validate_risk(value: Any, errors: list[str]) -> None:
    risk = _dict(value)
    unsupported = sorted(set(risk) - RISK_FIELDS)
    if unsupported:
        errors.append("unsupported risk field(s): " + ", ".join(unsupported) + ".")
    if "preference" in risk and risk.get("preference") not in RISK_PREFERENCES:
        errors.append("risk.preference must be one of: aggressive, balanced, conservative.")
    if "max_risk_state" in risk and risk.get("max_risk_state") not in RISK_STATES:
        errors.append("risk.max_risk_state must be one of: extreme, high, low, medium.")
    if "max_action_level" in risk and risk.get("max_action_level") not in ACTION_LEVELS:
        errors.append("risk.max_action_level must be one of: DO, NO_ACTION, TRY_SMALL, WATCH.")
    if "allow_new_exposure" in risk and not isinstance(risk.get("allow_new_exposure"), bool):
        errors.append("risk.allow_new_exposure must be a boolean.")


def _validate_string_list(value: Any, path: str, errors: list[str]) -> None:
    if not isinstance(value, list):
        errors.append(f"{path} must be a list.")
        return
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            errors.append(f"{path}[{index}] must be a non-empty string.")


def _validate_strategy_preferences(value: Any, errors: list[str]) -> None:
    preferences = _dict(value)
    unsupported = sorted(set(preferences) - STRATEGY_PREFERENCE_FIELDS)
    if unsupported:
        errors.append("unsupported strategy_preferences field(s): " + ", ".join(unsupported) + ".")
    for key in sorted(STRATEGY_PREFERENCE_FIELDS):
        if key in preferences:
            _validate_string_list(preferences.get(key), f"strategy_preferences.{key}", errors)


def _validate_manual_exposure_notes(value: Any, errors: list[str]) -> None:
    for index, item in enumerate(_list(value)):
        path = f"manual_exposure_notes[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{path} must be a mapping.")
            continue
        _validate_supported_fields(item, path, MANUAL_EXPOSURE_FIELDS, errors)
        _required_string(item, "symbol", f"{path}.symbol", errors)
        if "exposure_state" in item and item.get("exposure_state") not in EXPOSURE_STATES:
            errors.append(f"{path}.exposure_state must be one of: material, none, small, unknown, watch.")
        if "private_note" in item:
            _optional_string(item, "private_note", f"{path}.private_note", errors)


def _required_string(item: dict[str, Any], key: str, path: str, errors: list[str]) -> None:
    if not isinstance(item.get(key), str) or not str(item.get(key)).strip():
        errors.append(f"{path} must be a non-empty string.")


def _optional_string(item: dict[str, Any], key: str, path: str, errors: list[str]) -> None:
    if not isinstance(item.get(key), str) or not str(item.get(key)).strip():
        errors.append(f"{path} must be a non-empty string when provided.")


def _validate_supported_fields(
    item: dict[str, Any],
    path: str,
    supported_fields: set[str],
    errors: list[str],
) -> None:
    unsupported = sorted(set(item) - supported_fields)
    if unsupported:
        errors.append(f"unsupported {path} field(s): " + ", ".join(unsupported) + ".")


def _watchlist(value: Any) -> list[dict[str, Any]]:
    records = []
    for item in _list(value):
        if not isinstance(item, dict):
            continue
        record = {"symbol": _symbol(item.get("symbol"))}
        timeframes = _string_list(item.get("timeframes"))
        if timeframes:
            record["timeframes"] = timeframes
        if isinstance(item.get("relevance"), str):
            record["relevance"] = item["relevance"]
        records.append(record)
    return sorted(records, key=lambda item: (item["symbol"], ",".join(item.get("timeframes", []))))


def _disabled_assets(value: Any) -> list[dict[str, Any]]:
    records = []
    for item in _list(value):
        if not isinstance(item, dict):
            continue
        record = {"symbol": _symbol(item.get("symbol"))}
        if isinstance(item.get("reason_code"), str):
            record["reason_code"] = item["reason_code"].strip()
        records.append(record)
    return sorted(records, key=lambda item: item["symbol"])


def _risk(value: Any) -> dict[str, Any]:
    risk = _dict(value)
    return {
        key: risk[key]
        for key in ("preference", "max_risk_state", "max_action_level", "allow_new_exposure")
        if key in risk
    }


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return sorted({item.strip() for item in value if isinstance(item, str) and item.strip()})


def _strategy_preferences(value: Any) -> dict[str, list[str]]:
    preferences = _dict(value)
    return {
        "preferred": _string_list(preferences.get("preferred")),
        "disabled": _string_list(preferences.get("disabled")),
    }


def _manual_exposure_summary(value: Any) -> tuple[list[dict[str, Any]], int]:
    records = []
    omitted_private_values = 0
    for item in _list(value):
        if not isinstance(item, dict):
            continue
        private_note = item.get("private_note")
        private_note_omitted = isinstance(private_note, str) and bool(private_note.strip())
        if private_note_omitted:
            omitted_private_values += 1
        record = {
            "symbol": _symbol(item.get("symbol")),
            "exposure_state": item.get("exposure_state") if isinstance(item.get("exposure_state"), str) else "unknown",
            "private_note_omitted": private_note_omitted,
        }
        records.append(record)
    return sorted(records, key=lambda item: item["symbol"]), omitted_private_values


def _source(*, configured: bool) -> dict[str, Any]:
    return {
        "configured": configured,
        "source_ref": "configured_user_state" if configured else "not_configured",
        "raw_path_embedded": False,
        "raw_file_embedded": False,
    }


def _privacy(*, omitted_private_values: int) -> dict[str, Any]:
    return {
        "private_notes_embedded": False,
        "machine_paths_embedded": False,
        "account_identifiers_embedded": False,
        "holdings_values_embedded": False,
        "omitted_private_values": omitted_private_values,
    }


def _counts(
    watchlist: list[dict[str, Any]],
    disabled_assets: list[dict[str, Any]],
    preferred_timeframes: list[str],
    strategy_preferences: dict[str, list[str]],
    manual_exposure_summary: list[dict[str, Any]],
    omitted_private_values: int,
    *,
    warnings: list[str],
    errors: list[str],
) -> dict[str, int]:
    return {
        "watchlist_records": len(watchlist),
        "disabled_assets": len(disabled_assets),
        "preferred_timeframes": len(preferred_timeframes),
        "strategy_preference_records": len(strategy_preferences.get("preferred", []))
        + len(strategy_preferences.get("disabled", [])),
        "manual_exposure_summary_records": len(manual_exposure_summary),
        "omitted_private_values": omitted_private_values,
        "warnings": len(warnings),
        "errors": len(errors),
    }


def _write_artifact(run: RunContext, artifact: dict[str, Any]) -> None:
    write_json(run.analysis_dir / "user_state_context.json", artifact)
    counts = _dict(artifact.get("counts"))
    run.manifest["artifacts"]["user_state_context"] = USER_STATE_CONTEXT_ARTIFACT
    run.manifest["user_state_context"] = {
        "status": artifact["status"],
        "mode": artifact["mode"],
        "artifact": USER_STATE_CONTEXT_ARTIFACT,
        "watchlist_records": _int(counts.get("watchlist_records")),
        "disabled_assets": _int(counts.get("disabled_assets")),
        "preferred_timeframes": _int(counts.get("preferred_timeframes")),
        "strategy_preference_records": _int(counts.get("strategy_preference_records")),
        "manual_exposure_summary_records": _int(counts.get("manual_exposure_summary_records")),
        "omitted_private_values": _int(counts.get("omitted_private_values")),
        "warnings": _int(counts.get("warnings")),
        "errors": _int(counts.get("errors")),
    }
    run.manifest["counts"]["user_state_watchlist_records"] = _int(counts.get("watchlist_records"))
    run.manifest["counts"]["user_state_disabled_assets"] = _int(counts.get("disabled_assets"))
    run.manifest["counts"]["user_state_preferred_timeframes"] = _int(counts.get("preferred_timeframes"))
    run.manifest["counts"]["user_state_strategy_preference_records"] = _int(
        counts.get("strategy_preference_records")
    )
    run.manifest["counts"]["user_state_manual_exposure_summary_records"] = _int(
        counts.get("manual_exposure_summary_records")
    )
    run.manifest["counts"]["user_state_omitted_private_values"] = _int(counts.get("omitted_private_values"))
    run.manifest["counts"]["user_state_warnings"] = _int(counts.get("warnings"))
    run.manifest["counts"]["user_state_errors"] = _int(counts.get("errors"))


def _format_utc(value: datetime | str | None) -> str:
    if isinstance(value, str):
        return value
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _symbol(value: Any) -> str:
    return str(value).strip().upper()


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    return value if isinstance(value, int) else 0
