from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from halpha.collectors.text import TEXT_ARTIFACT, collect_text_events_raw
from halpha.analysis.event_intelligence_material import build_event_intelligence_material
from halpha.runtime.pipeline_contracts import PipelineError, RunContext
from halpha.data.raw_artifacts import RawArtifactError, validate_text_events_raw_artifact
from halpha.storage import display_path, ensure_directory, write_json
from halpha.text.text_entity_evidence import build_text_entity_evidence
from halpha.text.text_event_classification import build_text_event_classification_evidence
from halpha.text.text_event_records import TEXT_EVENT_RECORDS_ARTIFACT, build_text_event_records
from halpha.text.text_event_signals import build_text_event_signals
from halpha.text.text_event_topics import build_text_event_topics


TEXT_INTELLIGENCE_MANIFEST = "manifest.json"
TEXT_INTELLIGENCE_DEFAULT_DIR = "text_intelligence"
SKIPPED_PROCESSORS = (
    "build_event_market_confluence",
)


@dataclass(frozen=True)
class StandaloneTextIntelligenceResult:
    succeeded: bool
    exit_code: int
    status: str
    reason: str | None
    output_dir: Path
    manifest_path: Path


class StandaloneTextIntelligenceError(Exception):
    def __init__(self, message: str, *, stage: str, exit_code: int = 1) -> None:
        super().__init__(message)
        self.stage = stage
        self.exit_code = exit_code


def run_standalone_text_intelligence(
    config: dict[str, Any],
    *,
    config_path: Path,
    input_path: Path | None = None,
    output_dir: Path | None = None,
    now: datetime | None = None,
) -> StandaloneTextIntelligenceResult:
    clock_value = _utc_now(now)
    base_output_dir = _base_output_dir(config, config_path=config_path, output_dir=output_dir)
    target_dir = _unique_output_dir(base_output_dir, _run_id(clock_value))
    raw_dir = target_dir / "raw"
    analysis_dir = target_dir / "analysis"
    ensure_directory(raw_dir)
    ensure_directory(analysis_dir)

    manifest_path = target_dir / TEXT_INTELLIGENCE_MANIFEST
    manifest = _initial_manifest(
        config_path=config_path,
        input_path=input_path,
        manifest_path=manifest_path,
        created_at=_format_utc(clock_value),
    )
    run = RunContext(
        run_id=target_dir.name,
        run_dir=target_dir,
        raw_dir=raw_dir,
        analysis_dir=analysis_dir,
        codex_context_dir=target_dir / "codex_context",
        report_dir=target_dir / "report",
        manifest_path=manifest_path,
        config_path=config_path,
        manifest=manifest,
    )

    try:
        _write_raw_text_events(config, run, input_path=input_path)
        _run_text_event_records(config, run)
        _run_text_entity_evidence(config, run)
        _run_text_event_classification_evidence(config, run)
        _run_text_event_topics(config, run)
        _run_text_event_signals(config, run)
        _run_event_intelligence_material(config, run)
        _record_skipped_processors(run)
        _finish_manifest(run, status="succeeded")
        return StandaloneTextIntelligenceResult(
            succeeded=True,
            exit_code=0,
            status="succeeded",
            reason=None,
            output_dir=target_dir,
            manifest_path=manifest_path,
        )
    except StandaloneTextIntelligenceError as exc:
        _record_error(run, stage=exc.stage, message=str(exc))
        _record_skipped_processors(run)
        _finish_manifest(run, status="failed")
        return StandaloneTextIntelligenceResult(
            succeeded=False,
            exit_code=exc.exit_code,
            status="failed",
            reason=str(exc),
            output_dir=target_dir,
            manifest_path=manifest_path,
        )
    except PipelineError as exc:
        stage = exc.stage or "text_intelligence"
        _record_error(run, stage=stage, message=str(exc))
        _record_skipped_processors(run)
        _finish_manifest(run, status="failed")
        return StandaloneTextIntelligenceResult(
            succeeded=False,
            exit_code=exc.exit_code,
            status="failed",
            reason=str(exc),
            output_dir=target_dir,
            manifest_path=manifest_path,
        )


def _write_raw_text_events(config: dict[str, Any], run: RunContext, *, input_path: Path | None) -> None:
    _require_text_enabled(config)
    if input_path is None:
        raw = _collect_configured_text(config)
        processor_name = "collect_text_events"
        input_mode = "configured_sources"
    else:
        raw = _read_input_raw_text_events(input_path)
        processor_name = "load_raw_text_events"
        input_mode = "existing_raw_artifact"

    raw_path = run.raw_dir / "text_events.json"
    write_json(raw_path, raw)
    run.manifest["inputs"]["mode"] = input_mode
    run.manifest["artifacts"]["raw_text_events"] = TEXT_ARTIFACT
    run.manifest["counts"]["text_event_items"] = len(raw["items"])
    run.manifest["processors"].append(
        {
            "name": processor_name,
            "status": "succeeded",
            "artifacts": [TEXT_ARTIFACT],
            "counts": {
                "text_event_items": len(raw["items"]),
            },
        }
    )

    if not raw["items"] and raw.get("errors"):
        raise StandaloneTextIntelligenceError(
            _collector_failure_message(raw["errors"]),
            stage=processor_name,
            exit_code=3,
        )


def _collect_configured_text(config: dict[str, Any]) -> dict[str, Any]:
    text = _require_text_enabled(config)
    return collect_text_events_raw(text)


def _require_text_enabled(config: dict[str, Any]) -> dict[str, Any]:
    text = config.get("text")
    if not isinstance(text, dict) or text.get("enabled") is not True:
        raise StandaloneTextIntelligenceError(
            "text.enabled must be true for text-intel.",
            stage="collect_text_events",
            exit_code=2,
        )
    return text


def _read_input_raw_text_events(input_path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(input_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise StandaloneTextIntelligenceError(
            "input raw text artifact was not found.",
            stage="load_raw_text_events",
            exit_code=2,
        ) from exc
    except JSONDecodeError as exc:
        raise StandaloneTextIntelligenceError(
            f"input raw text artifact is not valid JSON: {exc.msg}.",
            stage="load_raw_text_events",
            exit_code=2,
        ) from exc

    try:
        validate_text_events_raw_artifact(raw, _safe_path(input_path))
    except RawArtifactError as exc:
        raise StandaloneTextIntelligenceError(
            str(exc),
            stage="load_raw_text_events",
            exit_code=3,
        ) from exc
    return raw


def _run_text_event_records(config: dict[str, Any], run: RunContext) -> None:
    artifacts = build_text_event_records(config, run)
    artifact = _read_json(run.analysis_dir / "text_event_records.json")
    run.manifest["processors"].append(
        {
            "name": "build_text_event_records",
            "status": "succeeded",
            "artifacts": artifacts,
            "counts": dict(artifact.get("coverage") or {}),
            "warnings": list(artifact.get("warnings") or []),
            "errors": list(artifact.get("errors") or []),
        }
    )


def _run_text_entity_evidence(config: dict[str, Any], run: RunContext) -> None:
    artifacts = build_text_entity_evidence(config, run)
    artifact = _read_json(run.analysis_dir / "text_entity_evidence.json")
    run.manifest["processors"].append(
        {
            "name": "build_text_entity_evidence",
            "status": "succeeded",
            "artifacts": artifacts,
            "counts": dict(artifact.get("coverage") or {}),
            "model_states": list(artifact.get("model_states") or []),
            "warnings": list(artifact.get("warnings") or []),
            "errors": list(artifact.get("errors") or []),
        }
    )


def _run_text_event_classification_evidence(config: dict[str, Any], run: RunContext) -> None:
    artifacts = build_text_event_classification_evidence(config, run)
    artifact = _read_json(run.analysis_dir / "text_event_classification_evidence.json")
    run.manifest["processors"].append(
        {
            "name": "build_text_event_classification_evidence",
            "status": "succeeded",
            "artifacts": artifacts,
            "counts": dict(artifact.get("coverage") or {}),
            "model_states": list(artifact.get("model_states") or []),
            "warnings": list(artifact.get("warnings") or []),
            "errors": list(artifact.get("errors") or []),
        }
    )


def _run_text_event_topics(config: dict[str, Any], run: RunContext) -> None:
    artifacts = build_text_event_topics(config, run)
    artifact = _read_json(run.analysis_dir / "text_event_topics.json")
    run.manifest["processors"].append(
        {
            "name": "build_text_event_topics",
            "status": "succeeded",
            "artifacts": artifacts,
            "counts": dict(artifact.get("coverage") or {}),
            "model_states": list(artifact.get("model_states") or []),
            "warnings": list(artifact.get("warnings") or []),
            "errors": list(artifact.get("errors") or []),
        }
    )


def _run_text_event_signals(config: dict[str, Any], run: RunContext) -> None:
    artifacts = build_text_event_signals(config, run)
    artifact = _read_json(run.analysis_dir / "text_event_signals.json")
    run.manifest["processors"].append(
        {
            "name": "build_text_event_signals",
            "status": "succeeded",
            "artifacts": artifacts,
            "counts": dict(artifact.get("coverage") or {}),
            "model_states": list(artifact.get("model_states") or []),
            "warnings": list(artifact.get("warnings") or []),
            "errors": list(artifact.get("errors") or []),
        }
    )


def _run_event_intelligence_material(config: dict[str, Any], run: RunContext) -> None:
    artifacts = build_event_intelligence_material(config, run)
    material_path = run.analysis_dir / "event_intelligence_material.md"
    run.manifest["processors"].append(
        {
            "name": "build_event_intelligence_material",
            "status": "succeeded" if material_path.exists() else "skipped",
            "artifacts": artifacts,
            "counts": {
                "records": run.manifest.get("counts", {}).get("event_intelligence_material_records", 0),
            },
            "warning_count": run.manifest.get("event_intelligence_material", {}).get("warnings", 0)
            if isinstance(run.manifest.get("event_intelligence_material"), dict)
            else 0,
            "errors": [],
        }
    )


def _record_skipped_processors(run: RunContext) -> None:
    existing = {str(processor.get("name")) for processor in run.manifest["processors"]}
    for name in SKIPPED_PROCESSORS:
        if name in existing:
            continue
        run.manifest["processors"].append(
            {
                "name": name,
                "status": "skipped",
                "reason": "not_implemented",
                "artifacts": [],
            }
        )


def _finish_manifest(run: RunContext, *, status: str) -> None:
    run.manifest["status"] = status
    run.manifest["artifacts"]["manifest"] = TEXT_INTELLIGENCE_MANIFEST
    run.manifest["counts"]["processors"] = len(run.manifest["processors"])
    run.manifest["counts"]["processors_succeeded"] = sum(
        1 for processor in run.manifest["processors"] if processor.get("status") == "succeeded"
    )
    run.manifest["counts"]["processors_skipped"] = sum(
        1 for processor in run.manifest["processors"] if processor.get("status") == "skipped"
    )
    run.manifest["warnings"] = _unique_warnings(run.manifest["processors"])
    run.manifest.setdefault("errors", [])
    write_json(run.manifest_path, run.manifest)


def _record_error(run: RunContext, *, stage: str, message: str) -> None:
    run.manifest.setdefault("errors", []).append(
        {
            "stage": stage,
            "message": message,
        }
    )


def _initial_manifest(
    *,
    config_path: Path,
    input_path: Path | None,
    manifest_path: Path,
    created_at: str,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "artifact_type": "text_intelligence_manifest",
        "created_at": created_at,
        "status": "running",
        "config_path": _safe_path(config_path),
        "inputs": {
            "mode": "existing_raw_artifact" if input_path is not None else "configured_sources",
            "input": _safe_path(input_path) if input_path is not None else None,
        },
        "artifacts": {},
        "counts": {},
        "model_states": [],
        "processors": [],
        "warnings": [],
        "errors": [],
        "manifest_path": display_path(manifest_path, base=manifest_path.parent),
    }


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _unique_warnings(processors: list[dict[str, Any]]) -> list[str]:
    warnings = []
    for processor in processors:
        for warning in processor.get("warnings") or []:
            if warning not in warnings:
                warnings.append(str(warning))
    return warnings


def _collector_failure_message(errors: list[dict[str, Any]]) -> str:
    summaries = [f"{error.get('source')}: {error.get('message')}" for error in errors]
    return f"text collection failed for {len(errors)} source(s): {'; '.join(summaries)}"


def _base_output_dir(config: dict[str, Any], *, config_path: Path, output_dir: Path | None) -> Path:
    if output_dir is not None:
        return output_dir
    run = config.get("run") if isinstance(config.get("run"), dict) else {}
    root = Path(str(run.get("output_dir") or "runs"))
    if not root.is_absolute():
        root = config_path.parent / root
    return root / TEXT_INTELLIGENCE_DEFAULT_DIR


def _unique_output_dir(output_dir: Path, run_id: str) -> Path:
    ensure_directory(output_dir)
    candidate = output_dir / run_id
    if not candidate.exists():
        candidate.mkdir()
        return candidate
    for index in range(1, 100):
        candidate = output_dir / f"{run_id}-{index:02d}"
        if not candidate.exists():
            candidate.mkdir()
            return candidate
    raise StandaloneTextIntelligenceError(
        f"could not create a unique text-intelligence output directory for {run_id}.",
        stage="text_intelligence",
        exit_code=1,
    )


def _safe_path(path: Path | None) -> str | None:
    if path is None:
        return None
    if not path.is_absolute():
        return path.as_posix()
    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return path.name


def _run_id(value: datetime) -> str:
    timestamp = value.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{timestamp}_text_intelligence"


def _utc_now(value: datetime | None = None) -> datetime:
    return value.astimezone(UTC) if value is not None else datetime.now(UTC)


def _format_utc(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
