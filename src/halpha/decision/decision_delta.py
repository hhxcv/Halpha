from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from halpha.pipeline import PipelineError, RunContext
from halpha.storage import write_json


BUILD_MARKET_REGIME_ASSESSMENT_STAGE = "build_market_regime_assessment"
BUILD_RISK_ASSESSMENT_STAGE = "build_risk_assessment"
BUILD_DECISION_RECOMMENDATIONS_STAGE = "build_decision_recommendations"
BUILD_WATCH_TRIGGERS_STAGE = "build_watch_triggers"
BUILD_DECISION_INTELLIGENCE_DELTA_STAGE = "build_decision_intelligence_delta"
MARKET_REGIME_ASSESSMENT_ARTIFACT = "analysis/market_regime_assessment.json"
RISK_ASSESSMENT_ARTIFACT = "analysis/risk_assessment.json"
DECISION_RECOMMENDATIONS_ARTIFACT = "analysis/decision_recommendations.json"
WATCH_TRIGGERS_ARTIFACT = "analysis/watch_triggers.json"
DECISION_INTELLIGENCE_DELTA_ARTIFACT = "analysis/decision_intelligence_delta.json"
SCHEMA_VERSION = 1
NO_PREVIOUS_RUN_WARNING = "No previous successful decision-intelligence run found."
DECISION_DELTA_INPUT_ARTIFACTS = {
    "market_regime_assessment": MARKET_REGIME_ASSESSMENT_ARTIFACT,
    "risk_assessment": RISK_ASSESSMENT_ARTIFACT,
    "decision_recommendations": DECISION_RECOMMENDATIONS_ARTIFACT,
    "watch_triggers": WATCH_TRIGGERS_ARTIFACT,
}


@dataclass(frozen=True)
class DecisionDeltaBuildResult:
    artifacts: list[str]
    enabled: bool
    status: str
    previous_run: dict[str, Any]
    warnings: list[str]
    errors: list[str]
    reason: str | None = None


def build_decision_intelligence_delta_artifact(
    config: dict[str, Any],
    run: RunContext,
    *,
    now: datetime | str | None = None,
) -> DecisionDeltaBuildResult:
    if not _quant_enabled(config):
        _record_zero_decision_delta_counts(run)
        return DecisionDeltaBuildResult(
            artifacts=[],
            enabled=False,
            status="skipped",
            reason="quant_disabled",
            previous_run=_previous_run_summary("not_checked"),
            warnings=[],
            errors=[],
        )

    current_artifacts = _read_current_decision_delta_inputs(run)
    previous_run, scan_warnings = _find_previous_decision_intelligence_run(run)
    created_at = _created_at(current_artifacts["watch_triggers"], now)

    if previous_run is None:
        changes: list[dict[str, Any]] = []
        warnings = _unique_ordered([NO_PREVIOUS_RUN_WARNING, *scan_warnings])
        previous_summary = _previous_run_summary("no_previous_run")
        status = "no_previous_run"
        previous_artifacts = {}
    else:
        changes = _decision_delta_changes(current_artifacts, previous_run["artifacts"])
        warnings = _unique_ordered(scan_warnings)
        previous_summary = _previous_run_summary(
            "compared",
            run_id=previous_run["run_id"],
            path=previous_run["path"],
        )
        status = "compared"
        previous_artifacts = DECISION_DELTA_INPUT_ARTIFACTS

    artifact = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "decision_intelligence_delta",
        "run_id": run.run_id,
        "created_at": created_at,
        "status": status,
        "previous_run_id": previous_summary["run_id"],
        "previous_run_path": previous_summary["path"],
        "compared_artifacts": {
            "current": DECISION_DELTA_INPUT_ARTIFACTS,
            "previous": previous_artifacts,
        },
        "changes": changes,
        "warnings": warnings,
        "errors": [],
        "source_artifacts": _decision_delta_source_artifacts(current_artifacts),
    }
    write_json(run.analysis_dir / "decision_intelligence_delta.json", artifact)
    run.manifest["artifacts"]["decision_intelligence_delta"] = DECISION_INTELLIGENCE_DELTA_ARTIFACT
    run.manifest["counts"]["decision_delta_changed_records"] = len(changes)
    return DecisionDeltaBuildResult(
        artifacts=[DECISION_INTELLIGENCE_DELTA_ARTIFACT],
        enabled=True,
        status="succeeded",
        previous_run=previous_summary,
        warnings=warnings,
        errors=[],
    )


def _read_current_decision_delta_inputs(run: RunContext) -> dict[str, dict[str, Any]]:
    artifacts = {
        "market_regime_assessment": _read_json_artifact(
            run.analysis_dir / "market_regime_assessment.json",
            MARKET_REGIME_ASSESSMENT_ARTIFACT,
            producer_stage=BUILD_MARKET_REGIME_ASSESSMENT_STAGE,
            stage=BUILD_DECISION_INTELLIGENCE_DELTA_STAGE,
        ),
        "risk_assessment": _read_json_artifact(
            run.analysis_dir / "risk_assessment.json",
            RISK_ASSESSMENT_ARTIFACT,
            producer_stage=BUILD_RISK_ASSESSMENT_STAGE,
            stage=BUILD_DECISION_INTELLIGENCE_DELTA_STAGE,
        ),
        "decision_recommendations": _read_json_artifact(
            run.analysis_dir / "decision_recommendations.json",
            DECISION_RECOMMENDATIONS_ARTIFACT,
            producer_stage=BUILD_DECISION_RECOMMENDATIONS_STAGE,
            stage=BUILD_DECISION_INTELLIGENCE_DELTA_STAGE,
        ),
        "watch_triggers": _read_json_artifact(
            run.analysis_dir / "watch_triggers.json",
            WATCH_TRIGGERS_ARTIFACT,
            producer_stage=BUILD_WATCH_TRIGGERS_STAGE,
            stage=BUILD_DECISION_INTELLIGENCE_DELTA_STAGE,
        ),
    }
    for artifact_key, artifact_name in DECISION_DELTA_INPUT_ARTIFACTS.items():
        _records_from_artifact(
            artifacts[artifact_key],
            artifact_name,
            stage=BUILD_DECISION_INTELLIGENCE_DELTA_STAGE,
        )
    return artifacts


def _find_previous_decision_intelligence_run(run: RunContext) -> tuple[dict[str, Any] | None, list[str]]:
    output_dir = run.run_dir.parent
    if not output_dir.exists():
        return None, []

    current_key = _previous_run_sort_key(run.run_dir, run.manifest)
    candidates = []
    for candidate_dir in output_dir.iterdir():
        if not candidate_dir.is_dir() or candidate_dir == run.run_dir:
            continue
        manifest, manifest_warning = _read_previous_manifest(candidate_dir)
        if manifest_warning is not None or manifest is None:
            continue
        if manifest.get("status") != "succeeded":
            continue
        candidate_key = _previous_run_sort_key(candidate_dir, manifest)
        if candidate_key >= current_key:
            continue
        candidates.append((candidate_key, candidate_dir.name, candidate_dir, manifest))

    warnings: list[str] = []
    for _candidate_key, _candidate_name, candidate_dir, manifest in sorted(candidates, reverse=True):
        artifacts, artifact_warnings = _read_previous_decision_delta_inputs(candidate_dir, manifest)
        if artifacts is None:
            warnings = _append_previous_scan_warnings(warnings, candidate_dir.name, artifact_warnings)
            continue
        return {
            "run_id": _clean_text(manifest.get("run_id"), fallback=candidate_dir.name),
            "path": _previous_run_path_reference(run, candidate_dir),
            "artifacts": artifacts,
        }, warnings
    return None, warnings


def _read_previous_manifest(run_dir: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        loaded = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, "run_manifest.json was not found."
    except JSONDecodeError as exc:
        return None, f"run_manifest.json is not valid JSON: {exc.msg}."
    if not isinstance(loaded, dict):
        return None, "run_manifest.json must be a JSON object."
    return loaded, None


def _read_previous_decision_delta_inputs(
    run_dir: Path,
    manifest: dict[str, Any],
) -> tuple[dict[str, dict[str, Any]] | None, list[str]]:
    artifacts: dict[str, dict[str, Any]] = {}
    warnings: list[str] = []
    for artifact_key, artifact_name in DECISION_DELTA_INPUT_ARTIFACTS.items():
        artifact_path = run_dir / _previous_artifact_path(manifest, artifact_key, artifact_name)
        loaded, warning = _read_previous_json_object(artifact_path, artifact_name)
        if warning is not None or loaded is None:
            warnings.append(warning or f"{artifact_name} could not be read.")
            return None, warnings
        records_warning = _previous_records_warning(loaded, artifact_name)
        if records_warning is not None:
            warnings.append(records_warning)
            return None, warnings
        artifacts[artifact_key] = loaded
    return artifacts, warnings


def _previous_artifact_path(manifest: dict[str, Any], artifact_key: str, artifact_name: str) -> Path:
    manifest_artifacts = _mapping(manifest.get("artifacts"))
    configured = manifest_artifacts.get(artifact_key)
    if isinstance(configured, str) and configured.strip():
        path = Path(configured)
        if not path.is_absolute():
            return path
    return Path(artifact_name)


def _read_previous_json_object(path: Path, artifact_name: str) -> tuple[dict[str, Any] | None, str | None]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, f"{artifact_name} was not found."
    except JSONDecodeError as exc:
        return None, f"{artifact_name} is not valid JSON: {exc.msg}."
    if not isinstance(loaded, dict):
        return None, f"{artifact_name} must be a JSON object."
    return loaded, None


def _previous_records_warning(artifact: dict[str, Any], artifact_name: str) -> str | None:
    records = artifact.get("records")
    if not isinstance(records, list):
        return f"{artifact_name} must contain a records list."
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            return f"records[{index}] in {artifact_name} must be a mapping."
    return None


def _append_previous_scan_warnings(
    warnings: list[str],
    run_id: str,
    artifact_warnings: list[str],
) -> list[str]:
    result = list(warnings)
    for warning in artifact_warnings:
        if len(result) >= 5:
            if "Additional previous-run candidates were skipped." not in result:
                result.append("Additional previous-run candidates were skipped.")
            break
        result.append(f"Skipped previous run {run_id}: {warning}")
    return result


def _previous_run_sort_key(run_dir: Path, manifest: dict[str, Any]) -> tuple[datetime, str, str]:
    timestamp = _sort_timestamp(manifest.get("started_at")) or _sort_timestamp(run_dir.name)
    return (
        timestamp or datetime.min.replace(tzinfo=timezone.utc),
        _clean_text(manifest.get("run_id"), fallback=run_dir.name),
        run_dir.name,
    )


def _sort_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    clean = value.strip()
    try:
        parsed = datetime.fromisoformat(clean.replace("Z", "+00:00"))
    except ValueError:
        run_id_part = clean.split("-", 1)[0]
        try:
            parsed = datetime.strptime(run_id_part, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _previous_run_path_reference(run: RunContext, previous_run_dir: Path) -> str:
    return f"{run.run_dir.parent.name}/{previous_run_dir.name}"


def _previous_run_summary(status: str, *, run_id: str | None = None, path: str | None = None) -> dict[str, Any]:
    return {
        "status": status,
        "run_id": run_id,
        "path": path,
    }


def _decision_delta_changes(
    current_artifacts: dict[str, dict[str, Any]],
    previous_artifacts: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    changes = []
    changes.extend(
        _field_delta_changes(
            current_artifacts["market_regime_assessment"],
            previous_artifacts["market_regime_assessment"],
            field="regime",
            artifact_name=MARKET_REGIME_ASSESSMENT_ARTIFACT,
        )
    )
    changes.extend(
        _field_delta_changes(
            current_artifacts["risk_assessment"],
            previous_artifacts["risk_assessment"],
            field="risk_level",
            artifact_name=RISK_ASSESSMENT_ARTIFACT,
        )
    )
    changes.extend(
        _field_delta_changes(
            current_artifacts["decision_recommendations"],
            previous_artifacts["decision_recommendations"],
            field="action_level",
            artifact_name=DECISION_RECOMMENDATIONS_ARTIFACT,
        )
    )
    changes.extend(
        _field_delta_changes(
            current_artifacts["decision_recommendations"],
            previous_artifacts["decision_recommendations"],
            field="decision_bias",
            artifact_name=DECISION_RECOMMENDATIONS_ARTIFACT,
        )
    )
    changes.extend(
        _invalidation_delta_changes(
            current_artifacts["decision_recommendations"],
            previous_artifacts["decision_recommendations"],
        )
    )
    changes.extend(
        _watch_trigger_delta_changes(
            current_artifacts["watch_triggers"],
            previous_artifacts["watch_triggers"],
        )
    )
    return changes


def _field_delta_changes(
    current_artifact: dict[str, Any],
    previous_artifact: dict[str, Any],
    *,
    field: str,
    artifact_name: str,
) -> list[dict[str, Any]]:
    current_records = _records_by_tuple(
        _records_from_artifact(current_artifact, artifact_name, stage=BUILD_DECISION_INTELLIGENCE_DELTA_STAGE)
    )
    previous_records = _records_by_tuple(
        _records_from_artifact(previous_artifact, artifact_name, stage=BUILD_DECISION_INTELLIGENCE_DELTA_STAGE)
    )
    changes = []
    for key in sorted({*previous_records.keys(), *current_records.keys()}):
        previous_record = previous_records.get(key)
        current_record = current_records.get(key)
        previous_value = _delta_field_value(previous_record, field)
        current_value = _delta_field_value(current_record, field)
        if previous_value == current_value:
            continue
        if previous_value is None and current_value is None:
            continue
        changes.append(
            _decision_delta_change(
                key,
                field=field,
                previous_value=previous_value,
                current_value=current_value,
                source_artifacts=_field_delta_source_artifacts(artifact_name, current_record, previous_record),
            )
        )
    return changes


def _invalidation_delta_changes(
    current_artifact: dict[str, Any],
    previous_artifact: dict[str, Any],
) -> list[dict[str, Any]]:
    current_records = _records_by_tuple(
        _records_from_artifact(
            current_artifact,
            DECISION_RECOMMENDATIONS_ARTIFACT,
            stage=BUILD_DECISION_INTELLIGENCE_DELTA_STAGE,
        )
    )
    previous_records = _records_by_tuple(
        _records_from_artifact(
            previous_artifact,
            DECISION_RECOMMENDATIONS_ARTIFACT,
            stage=BUILD_DECISION_INTELLIGENCE_DELTA_STAGE,
        )
    )
    changes = []
    for key in sorted({*previous_records.keys(), *current_records.keys()}):
        previous_record = previous_records.get(key)
        current_record = current_records.get(key)
        previous_value = _invalidation_status(previous_record)
        current_value = _invalidation_status(current_record)
        if previous_value == current_value:
            continue
        if previous_value is None and current_value is None:
            continue
        changes.append(
            _decision_delta_change(
                key,
                field="invalidation_status",
                previous_value=previous_value,
                current_value=current_value,
                source_artifacts=_field_delta_source_artifacts(
                    DECISION_RECOMMENDATIONS_ARTIFACT,
                    current_record,
                    previous_record,
                ),
            )
        )
    return changes


def _watch_trigger_delta_changes(
    current_artifact: dict[str, Any],
    previous_artifact: dict[str, Any],
) -> list[dict[str, Any]]:
    current_records = _records_from_artifact(
        current_artifact,
        WATCH_TRIGGERS_ARTIFACT,
        stage=BUILD_DECISION_INTELLIGENCE_DELTA_STAGE,
    )
    previous_records = _records_from_artifact(
        previous_artifact,
        WATCH_TRIGGERS_ARTIFACT,
        stage=BUILD_DECISION_INTELLIGENCE_DELTA_STAGE,
    )
    current_groups = _watch_trigger_conditions_by_tuple(current_records)
    previous_groups = _watch_trigger_conditions_by_tuple(previous_records)
    changes = []
    for key in sorted({*previous_groups.keys(), *current_groups.keys()}):
        previous_value = previous_groups.get(key, [])
        current_value = current_groups.get(key, [])
        if previous_value == current_value:
            continue
        changes.append(
            _decision_delta_change(
                key,
                field="major_watch_triggers",
                previous_value=previous_value,
                current_value=current_value,
                source_artifacts=_watch_delta_source_artifacts(
                    key,
                    current_records=current_records,
                    previous_records=previous_records,
                ),
            )
        )
    return changes


def _records_by_tuple(records: list[dict[str, Any]]) -> dict[tuple[str, str, str], dict[str, Any]]:
    return {_tuple_key(record): record for record in records}


def _delta_field_value(record: dict[str, Any] | None, field: str) -> str | None:
    if record is None or field not in record:
        return None
    value = record.get(field)
    if not isinstance(value, str):
        return None
    return value.strip() or None


def _invalidation_status(record: dict[str, Any] | None) -> str | None:
    if record is None or "invalidation_conditions" not in record:
        return None
    if _string_list(record.get("invalidation_conditions")):
        return "has_invalidation_conditions"
    return "no_invalidation_conditions"


def _watch_trigger_conditions_by_tuple(records: list[dict[str, Any]]) -> dict[tuple[str, str, str], list[str]]:
    groups: dict[tuple[str, str, str], list[str]] = {}
    for record in records:
        condition = _clean_text(record.get("condition"), fallback="")
        if not condition:
            continue
        groups.setdefault(_tuple_key(record), []).append(condition)
    return {key: sorted(_unique_ordered(values)) for key, values in groups.items()}


def _decision_delta_change(
    key: tuple[str, str, str],
    *,
    field: str,
    previous_value: Any,
    current_value: Any,
    source_artifacts: list[str],
) -> dict[str, Any]:
    source, symbol, timeframe = key
    return {
        "change_id": f"decision_delta:{source}:{symbol}:{timeframe}:{field}",
        "scope": {
            "source": source,
            "symbol": symbol,
            "timeframe": timeframe,
        },
        "field": field,
        "from": previous_value,
        "to": current_value,
        "source_artifacts": source_artifacts,
    }


def _field_delta_source_artifacts(
    artifact_name: str,
    current_record: dict[str, Any] | None,
    previous_record: dict[str, Any] | None,
) -> list[str]:
    return _unique_ordered(
        [
            artifact_name,
            *_string_list(current_record.get("source_artifacts") if current_record else None),
            *_string_list(previous_record.get("source_artifacts") if previous_record else None),
        ]
    )


def _watch_delta_source_artifacts(
    key: tuple[str, str, str],
    *,
    current_records: list[dict[str, Any]],
    previous_records: list[dict[str, Any]],
) -> list[str]:
    return _unique_ordered(
        [
            WATCH_TRIGGERS_ARTIFACT,
            *[
                artifact
                for record in [*current_records, *previous_records]
                if _tuple_key(record) == key
                for artifact in _string_list(record.get("source_artifacts"))
            ],
        ]
    )


def _decision_delta_source_artifacts(current_artifacts: dict[str, dict[str, Any]]) -> list[str]:
    return _unique_ordered(
        [
            *DECISION_DELTA_INPUT_ARTIFACTS.values(),
            *[
                artifact
                for current_artifact in current_artifacts.values()
                for artifact in _string_list(current_artifact.get("source_artifacts"))
            ],
        ]
    )


def _read_json_artifact(path: Path, artifact: str, *, producer_stage: str, stage: str) -> dict[str, Any]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PipelineError(
            f"{artifact} was not found; {producer_stage} must run first.",
            stage=stage,
            exit_code=3,
        ) from exc
    except JSONDecodeError as exc:
        raise PipelineError(
            f"{artifact} is not valid JSON: {exc.msg}.",
            stage=stage,
            exit_code=3,
        ) from exc
    if not isinstance(loaded, dict):
        raise PipelineError(
            f"{artifact} must be a JSON object.",
            stage=stage,
            exit_code=3,
        )
    return loaded


def _records_from_artifact(artifact: dict[str, Any], artifact_name: str, *, stage: str) -> list[dict[str, Any]]:
    records = artifact.get("records")
    if not isinstance(records, list):
        raise PipelineError(
            f"{artifact_name} must contain a records list.",
            stage=stage,
            exit_code=3,
        )
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise PipelineError(
                f"records[{index}] must be a mapping.",
                stage=stage,
                exit_code=3,
            )
    return records


def _created_at(artifact: dict[str, Any], now: datetime | str | None) -> str:
    if now is not None:
        return _format_utc(now)
    created_at = artifact.get("created_at")
    if isinstance(created_at, str) and created_at.strip():
        return _format_utc(created_at)
    return _format_utc(None)


def _format_utc(value: datetime | str | None) -> str:
    if value is None:
        timestamp = datetime.now(timezone.utc).replace(microsecond=0)
    elif isinstance(value, datetime):
        if value.tzinfo is None:
            raise PipelineError(
                "created_at must include a UTC offset.",
                stage=BUILD_DECISION_INTELLIGENCE_DELTA_STAGE,
                exit_code=3,
            )
        timestamp = value.astimezone(timezone.utc).replace(microsecond=0)
    elif isinstance(value, str):
        try:
            timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise PipelineError(
                "created_at must be an ISO 8601 timestamp.",
                stage=BUILD_DECISION_INTELLIGENCE_DELTA_STAGE,
                exit_code=3,
            ) from exc
        if timestamp.tzinfo is None:
            raise PipelineError(
                "created_at must include a UTC offset.",
                stage=BUILD_DECISION_INTELLIGENCE_DELTA_STAGE,
                exit_code=3,
            )
        timestamp = timestamp.astimezone(timezone.utc).replace(microsecond=0)
    else:
        raise PipelineError(
            "created_at must be an ISO 8601 timestamp.",
            stage=BUILD_DECISION_INTELLIGENCE_DELTA_STAGE,
            exit_code=3,
        )
    return timestamp.isoformat().replace("+00:00", "Z")


def _tuple_key(item: dict[str, Any]) -> tuple[str, str, str]:
    return (
        _clean_text(item.get("source"), fallback="missing"),
        _clean_text(item.get("symbol"), fallback="missing"),
        _clean_text(item.get("timeframe"), fallback="missing"),
    )


def _record_zero_decision_delta_counts(run: RunContext) -> None:
    run.manifest["counts"]["decision_delta_changed_records"] = 0


def _quant_enabled(config: dict[str, Any]) -> bool:
    quant = config.get("quant")
    return isinstance(quant, dict) and quant.get("enabled") is True


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def _clean_text(value: Any, *, fallback: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return fallback


def _unique_ordered(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
