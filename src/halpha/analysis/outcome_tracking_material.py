from __future__ import annotations

import json
from json import JSONDecodeError
from typing import Any

from halpha.pipeline import PipelineError, RunContext


STAGE_NAME = "build_analysis_materials"
OUTCOME_TARGETS_ARTIFACT = "analysis/outcome_targets.json"
OUTCOME_EVALUATIONS_ARTIFACT = "analysis/outcome_evaluations.json"
OUTCOME_TRACKING_MATERIAL_ARTIFACT = "analysis/outcome_tracking_material.md"
OUTCOME_HISTORY_STATE_ARTIFACT = "data/research/metadata/outcome_history_state.json"
MAX_EVALUATIONS = 10
MAX_WARNINGS = 6
MAX_ERRORS = 6
MAX_SOURCE_ARTIFACTS = 16
MAX_EVIDENCE = 2
MAX_TEXT_CHARS = 180


def build_outcome_tracking_material(config: dict[str, Any], run: RunContext) -> list[str]:
    del config
    targets = _read_optional_run_artifact(run, "outcome_targets.json", OUTCOME_TARGETS_ARTIFACT)
    evaluations = _read_optional_run_artifact(run, "outcome_evaluations.json", OUTCOME_EVALUATIONS_ARTIFACT)
    history_state = _read_optional_shared_artifact(run, OUTCOME_HISTORY_STATE_ARTIFACT)
    if not _has_outcome_evidence(targets, evaluations, history_state):
        run.manifest["outcome_tracking_material"] = {
            "status": "not_generated",
            "artifact": OUTCOME_TRACKING_MATERIAL_ARTIFACT,
            "reason": "no outcome targets, evaluations, or reusable history records were available",
        }
        run.manifest["counts"]["outcome_tracking_material_evaluations"] = 0
        return []

    material = render_outcome_tracking_material(
        targets=targets or {},
        evaluations=evaluations or {},
        history_state=history_state,
    )
    output_path = run.analysis_dir / "outcome_tracking_material.md"
    output_path.write_text(material, encoding="utf-8")
    selected_count = min(len(_evaluation_records(evaluations or {})), MAX_EVALUATIONS)
    run.manifest["artifacts"]["outcome_tracking_material"] = OUTCOME_TRACKING_MATERIAL_ARTIFACT
    run.manifest["counts"]["outcome_tracking_material_evaluations"] = selected_count
    run.manifest["outcome_tracking_material"] = {
        "status": _material_status(evaluations or {}, history_state),
        "artifact": OUTCOME_TRACKING_MATERIAL_ARTIFACT,
        "source_artifacts": _source_artifacts(targets or {}, evaluations or {}, history_state),
        "selected_evaluation_count": selected_count,
        "omitted_evaluation_count": max(0, len(_evaluation_records(evaluations or {})) - selected_count),
    }
    return [OUTCOME_TRACKING_MATERIAL_ARTIFACT]


def render_outcome_tracking_material(
    *,
    targets: dict[str, Any],
    evaluations: dict[str, Any],
    history_state: dict[str, Any] | None,
) -> str:
    record = _material_record(targets=targets, evaluations=evaluations, history_state=history_state)
    lines = [
        "---",
        "artifact_type: analysis_outcome_tracking_material",
        "schema_version: 1",
        "audience: ai",
        "source_artifacts:",
        *_yaml_list(record["source_artifacts"]),
        "---",
        "",
        "# outcome_tracking_material",
        "",
        "```yaml",
        _yaml_block(record).rstrip(),
        "```",
        "",
    ]
    return "\n".join(lines)


def _material_record(
    *,
    targets: dict[str, Any],
    evaluations: dict[str, Any],
    history_state: dict[str, Any] | None,
) -> dict[str, Any]:
    evaluation_records = _selected_evaluations(_evaluation_records(evaluations))
    all_evaluations = _evaluation_records(evaluations)
    return {
        "record_type": "outcome_tracking_context",
        "run_id": evaluations.get("run_id") or targets.get("run_id"),
        "created_at": evaluations.get("created_at") or targets.get("created_at"),
        "status": _material_status(evaluations, history_state),
        "outcome_states_are_halpha_generated": True,
        "codex_may_explain_outcome_states": True,
        "codex_may_generate_outcome_labels": False,
        "codex_may_validate_missing_histories": False,
        "codex_may_infer_omitted_store_contents": False,
        "codex_may_score_prior_recommendations": False,
        "codex_may_rank_strategies_from_outcomes": False,
        "full_outcome_targets_embedded": False,
        "full_outcome_evaluations_embedded": False,
        "full_outcome_history_embedded": False,
        "raw_store_tables_embedded": False,
        "source_artifacts": _source_artifacts(targets, evaluations, history_state),
        "counts": _counts(targets, evaluations, history_state),
        "evaluation_summary": _evaluation_summary(evaluations),
        "history_summary": _history_summary(history_state),
        "notable_evaluations": [_evaluation_record(record) for record in evaluation_records],
        "omitted_evaluation_count": max(0, len(all_evaluations) - len(evaluation_records)),
        "warnings": _bounded_messages(
            [
                *_string_list(targets.get("warnings")),
                *_string_list(evaluations.get("warnings")),
                *(_string_list(history_state.get("warnings")) if isinstance(history_state, dict) else []),
            ]
        ),
        "errors": _bounded_errors(
            [
                *_list(targets.get("errors")),
                *_list(evaluations.get("errors")),
                *(_list(history_state.get("errors")) if isinstance(history_state, dict) else []),
            ]
        ),
    }


def _read_optional_run_artifact(run: RunContext, file_name: str, artifact: str) -> dict[str, Any] | None:
    path = run.analysis_dir / file_name
    loaded = _read_optional_json(path, artifact)
    if loaded is None:
        return None
    if not isinstance(loaded, dict):
        raise PipelineError(f"{artifact} must be a JSON object.", stage=STAGE_NAME, exit_code=3)
    return loaded


def _read_optional_shared_artifact(run: RunContext, artifact: str) -> dict[str, Any] | None:
    loaded = _read_optional_json(run.config_path.parent / artifact, artifact)
    if loaded is None:
        return None
    if not isinstance(loaded, dict):
        raise PipelineError(f"{artifact} must be a JSON object.", stage=STAGE_NAME, exit_code=3)
    return loaded


def _read_optional_json(path, artifact: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except JSONDecodeError as exc:
        raise PipelineError(f"{artifact} is not valid JSON: {exc.msg}.", stage=STAGE_NAME, exit_code=3) from exc


def _has_outcome_evidence(
    targets: dict[str, Any] | None,
    evaluations: dict[str, Any] | None,
    history_state: dict[str, Any] | None,
) -> bool:
    if targets is not None and (_target_records(targets) or _list(targets.get("skipped_records"))):
        return True
    if evaluations is not None and _evaluation_records(evaluations):
        return True
    totals = history_state.get("totals") if isinstance(history_state, dict) else {}
    return _int(totals.get("records")) > 0 if isinstance(totals, dict) else False


def _counts(
    targets: dict[str, Any],
    evaluations: dict[str, Any],
    history_state: dict[str, Any] | None,
) -> dict[str, Any]:
    evaluation_counts = _dict(evaluations.get("counts"))
    target_counts = _dict(targets.get("counts"))
    history_totals = _dict(history_state.get("totals")) if isinstance(history_state, dict) else {}
    return {
        "targets": _int(target_counts.get("targets")),
        "skipped_target_records": _int(target_counts.get("skipped_records")),
        "evaluations": _int(evaluation_counts.get("evaluations")),
        "evaluated": _int(evaluation_counts.get("evaluated")),
        "pending": _int(evaluation_counts.get("pending")),
        "skipped": _int(evaluation_counts.get("skipped")),
        "stale": _int(evaluation_counts.get("stale")),
        "insufficient_data": _int(evaluation_counts.get("insufficient_data")),
        "outcome_history_records": _int(history_totals.get("records")),
        "outcome_history_warnings": _int(history_totals.get("warning_count")),
        "outcome_history_errors": _int(history_totals.get("error_count")),
    }


def _evaluation_summary(evaluations: dict[str, Any]) -> dict[str, Any]:
    counts = _dict(evaluations.get("counts"))
    return {
        "status": evaluations.get("status") or "unknown",
        "by_target_kind": _dict(counts.get("by_target_kind")),
        "by_evaluation_status": _dict(counts.get("by_evaluation_status")),
        "by_outcome_state": _dict(counts.get("by_outcome_state")),
    }


def _history_summary(history_state: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(history_state, dict):
        return {
            "status": "not_available",
            "full_outcome_history_embedded": False,
        }
    return {
        "status": history_state.get("status") or "unknown",
        "storage_path": history_state.get("storage_path"),
        "history_path": history_state.get("history_path"),
        "state_path": history_state.get("state_path"),
        "full_outcome_history_embedded": False,
        "totals": _dict(history_state.get("totals")),
        "sources": _list(history_state.get("sources"))[:MAX_EVIDENCE],
        "target_kinds": _list(history_state.get("target_kinds"))[:MAX_EVIDENCE],
        "outcome_states": _list(history_state.get("outcome_states"))[:MAX_EVIDENCE],
        "evaluation_statuses": _list(history_state.get("evaluation_statuses"))[:MAX_EVIDENCE],
    }


def _selected_evaluations(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    priority = {
        "contradicted": 0,
        "stale": 1,
        "not_aligned": 2,
        "insufficient_data": 3,
        "unresolved": 4,
        "skipped": 5,
        "failed": 6,
        "confirmed": 7,
        "aligned": 8,
        "no_change": 9,
    }
    return sorted(
        records,
        key=lambda item: (
            priority.get(str(item.get("outcome_state") or "unknown"), 20),
            str(item.get("target_kind") or ""),
            str(item.get("target_id") or ""),
        ),
    )[:MAX_EVALUATIONS]


def _evaluation_record(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "target_id": record.get("target_id"),
        "target_kind": record.get("target_kind"),
        "source_run_id": record.get("source_run_id"),
        "evaluation_run_id": record.get("evaluation_run_id"),
        "evaluation_status": record.get("evaluation_status"),
        "outcome_state": record.get("outcome_state"),
        "observation_window": _bounded_window(_dict(record.get("observation_window"))),
        "metrics": _bounded_metrics(_dict(record.get("metrics"))),
        "evidence": _bounded_messages(_list(record.get("evidence"))),
        "uncertainty": _bounded_messages(_list(record.get("uncertainty"))),
        "warnings": _bounded_messages(_list(record.get("warnings"))),
        "errors": _bounded_errors(_list(record.get("errors"))),
        "source_artifacts": _bounded_artifacts(_list(record.get("source_artifacts"))),
    }


def _bounded_window(window: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_as_of": window.get("source_as_of"),
        "start": window.get("start"),
        "end": window.get("end"),
        "horizon_end": window.get("horizon_end"),
        "sample_rows": window.get("sample_rows"),
        "no_lookahead": window.get("no_lookahead"),
    }


def _bounded_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    selected: dict[str, Any] = {}
    for key in (
        "return_pct",
        "max_favorable_excursion_pct",
        "max_adverse_excursion_pct",
        "threshold_hit",
        "current_record_count",
        "confirming_evidence_count",
        "contradicting_evidence_count",
        "text_event_history_records",
    ):
        if key in metrics:
            selected[key] = metrics[key]
    return selected


def _material_status(evaluations: dict[str, Any], history_state: dict[str, Any] | None) -> str:
    statuses = [str(evaluations.get("status") or "unknown")]
    if isinstance(history_state, dict):
        statuses.append(str(history_state.get("status") or "unknown"))
    if "failed" in statuses:
        return "failed"
    if "degraded" in statuses:
        return "degraded"
    if "warning" in statuses:
        return "warning"
    if statuses == ["unknown"]:
        return "unknown"
    return "ok"


def _source_artifacts(
    targets: dict[str, Any],
    evaluations: dict[str, Any],
    history_state: dict[str, Any] | None,
) -> list[str]:
    artifacts = [
        OUTCOME_TARGETS_ARTIFACT,
        OUTCOME_EVALUATIONS_ARTIFACT,
        *_string_list(targets.get("source_artifacts")),
        *_string_list(evaluations.get("source_artifacts")),
    ]
    if isinstance(history_state, dict):
        artifacts.append(OUTCOME_HISTORY_STATE_ARTIFACT)
        artifacts.extend(_string_list(history_state.get("source_artifacts")))
    return _bounded_artifacts(artifacts)


def _target_records(targets: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in _list(targets.get("targets")) if isinstance(item, dict)]


def _evaluation_records(evaluations: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in _list(evaluations.get("evaluations")) if isinstance(item, dict)]


def _bounded_artifacts(values: list[Any]) -> list[str]:
    artifacts = sorted({str(value) for value in values if isinstance(value, str) and value})
    return artifacts[:MAX_SOURCE_ARTIFACTS]


def _bounded_messages(values: list[Any]) -> list[str]:
    messages = [_bounded_text(value) for value in values if value is not None]
    return messages[:MAX_WARNINGS]


def _bounded_errors(values: list[Any]) -> list[dict[str, Any] | str]:
    errors: list[dict[str, Any] | str] = []
    for value in values[:MAX_ERRORS]:
        if isinstance(value, dict):
            errors.append({key: _bounded_text(item) for key, item in sorted(value.items())})
        elif value is not None:
            errors.append(_bounded_text(value))
    return errors


def _bounded_text(value: Any) -> str:
    text = str(value)
    if len(text) <= MAX_TEXT_CHARS:
        return text
    return f"{text[: MAX_TEXT_CHARS - 3].rstrip()}..."


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str) and item]


def _int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    return value if isinstance(value, int) else 0


def _yaml_list(values: list[str]) -> list[str]:
    if not values:
        return ["  []"]
    return [f"  - {value}" for value in values]


def _yaml_block(data: dict[str, Any]) -> str:
    try:
        import yaml
    except ModuleNotFoundError as exc:
        raise PipelineError(
            "PyYAML is required to write YAML outcome tracking material.",
            stage=STAGE_NAME,
            exit_code=1,
        ) from exc

    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
