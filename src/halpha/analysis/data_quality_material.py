from __future__ import annotations

import json
from json import JSONDecodeError
from typing import Any

from halpha.pipeline import PipelineError, RunContext


STAGE_NAME = "build_analysis_materials"
DATA_QUALITY_SUMMARY_ARTIFACT = "analysis/data_quality_summary.json"
DATA_QUALITY_MATERIAL_ARTIFACT = "analysis/data_quality_material.md"
MAX_CHECKS = 12
MAX_MESSAGES = 8
MAX_SOURCE_ARTIFACTS = 20
MAX_MESSAGE_CHARS = 240


def build_data_quality_material(config: dict[str, Any], run: RunContext) -> list[str]:
    summary = _read_summary(run)
    material = render_data_quality_material(
        summary,
        manifest_artifacts=run.manifest.get("artifacts", {}),
    )
    output_path = run.analysis_dir / "data_quality_material.md"
    output_path.write_text(material, encoding="utf-8")
    run.manifest["artifacts"]["data_quality_material"] = DATA_QUALITY_MATERIAL_ARTIFACT
    run.manifest["counts"]["data_quality_material_checks"] = min(
        len(_list(summary.get("checks"))),
        MAX_CHECKS,
    )
    run.manifest["data_quality_material"] = {
        "status": summary.get("status") or "unknown",
        "artifact": DATA_QUALITY_MATERIAL_ARTIFACT,
        "source_artifact": DATA_QUALITY_SUMMARY_ARTIFACT,
        "checks": run.manifest["counts"]["data_quality_material_checks"],
    }
    return [DATA_QUALITY_MATERIAL_ARTIFACT]


def render_data_quality_material(
    summary: dict[str, Any],
    *,
    manifest_artifacts: dict[str, Any] | None = None,
) -> str:
    _validate_summary(summary)
    record = _record_from_summary(summary, manifest_artifacts=manifest_artifacts or {})
    lines = [
        "---",
        "artifact_type: analysis_data_quality_material",
        "schema_version: 1",
        "audience: ai",
        "source_artifacts:",
        f"  - {DATA_QUALITY_SUMMARY_ARTIFACT}",
        "---",
        "",
        "# data_quality_material",
        "",
        "```yaml",
        _yaml_block(record).rstrip(),
        "```",
        "",
    ]
    return "\n".join(lines)


def _read_summary(run: RunContext) -> dict[str, Any]:
    try:
        loaded = json.loads((run.analysis_dir / "data_quality_summary.json").read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PipelineError(
            f"{DATA_QUALITY_SUMMARY_ARTIFACT} was not found; build_data_quality_summary must run first.",
            stage=STAGE_NAME,
            exit_code=3,
        ) from exc
    except JSONDecodeError as exc:
        raise PipelineError(
            f"{DATA_QUALITY_SUMMARY_ARTIFACT} is not valid JSON: {exc.msg}.",
            stage=STAGE_NAME,
            exit_code=3,
        ) from exc
    if not isinstance(loaded, dict):
        raise PipelineError(
            f"{DATA_QUALITY_SUMMARY_ARTIFACT} must be a JSON object.",
            stage=STAGE_NAME,
            exit_code=3,
        )
    _validate_summary(loaded)
    return loaded


def _validate_summary(summary: dict[str, Any]) -> None:
    if summary.get("artifact_type") != "data_quality_summary":
        raise PipelineError(
            f"{DATA_QUALITY_SUMMARY_ARTIFACT} must have artifact_type data_quality_summary.",
            stage=STAGE_NAME,
            exit_code=3,
        )
    if not isinstance(summary.get("checks"), list):
        raise PipelineError(
            f"{DATA_QUALITY_SUMMARY_ARTIFACT} must contain checks as a list.",
            stage=STAGE_NAME,
            exit_code=3,
        )


def _record_from_summary(
    summary: dict[str, Any],
    *,
    manifest_artifacts: dict[str, Any],
) -> dict[str, Any]:
    checks = [_check_record(check) for check in _list(summary.get("checks"))[:MAX_CHECKS]]
    total_checks = len(_list(summary.get("checks")))
    return {
        "record_type": "data_quality_context",
        "run_id": summary.get("run_id"),
        "created_at": summary.get("created_at"),
        "status": summary.get("status") or "unknown",
        "counts": _dict(summary.get("counts")),
        "quality_status_is_halpha_generated": True,
        "data_quality_scope": "current_run_inputs_and_shared_store_metadata",
        "codex_may_explain_data_quality_status": True,
        "codex_may_generate_quality_checks": False,
        "codex_may_generate_validation_results": False,
        "codex_may_inspect_omitted_tables": False,
        "full_data_quality_json_embedded": False,
        "full_reusable_history_embedded": False,
        "full_raw_archives_embedded": False,
        "full_catalog_embedded": False,
        "full_run_index_embedded": False,
        "source_artifacts": [DATA_QUALITY_SUMMARY_ARTIFACT],
        "referenced_evidence_artifacts": _bounded_artifacts(_list(summary.get("source_artifacts"))),
        "store_references": _store_references(summary, manifest_artifacts),
        "checks": checks,
        "omitted_check_count": max(0, total_checks - len(checks)),
        "warnings": _bounded_messages(_list(summary.get("warnings"))),
        "errors": _bounded_errors(_list(summary.get("errors"))),
    }


def _check_record(check: Any) -> dict[str, Any]:
    if not isinstance(check, dict):
        return {
            "name": "invalid_check",
            "scope": "unknown",
            "status": "failed",
            "summary": "data quality check record is not an object.",
            "warning_count": 0,
            "error_count": 1,
            "source_artifacts": [],
            "details": {},
            "warnings": [],
            "errors": ["data quality check record is not an object."],
        }
    details = _dict(check.get("details"))
    return {
        "name": check.get("name") or "unknown",
        "scope": check.get("scope") or "unknown",
        "status": check.get("status") or "unknown",
        "summary": _bounded_text(check.get("summary")),
        "warning_count": _int(check.get("warning_count")),
        "error_count": _int(check.get("error_count")),
        "source_artifacts": _bounded_artifacts(_list(check.get("source_artifacts"))),
        "details": _detail_counts(details),
        "warnings": _bounded_messages(_list(details.get("warnings"))),
        "errors": _bounded_messages(_list(details.get("errors"))),
    }


def _detail_counts(details: dict[str, Any]) -> dict[str, Any]:
    selected: dict[str, Any] = {}
    for key in sorted(details):
        value = details[key]
        if key in {"warnings", "errors"}:
            continue
        if isinstance(value, bool | int | float | str) or value is None:
            selected[key] = value
    return selected


def _store_references(summary: dict[str, Any], manifest_artifacts: dict[str, Any]) -> list[str]:
    values = [
        artifact
        for artifact in _list(summary.get("source_artifacts"))
        if isinstance(artifact, str) and artifact.startswith("data/")
    ]
    for artifact in _artifact_values(manifest_artifacts):
        if artifact.startswith("data/"):
            values.append(artifact)
    return _bounded_artifacts(values)


def _artifact_values(value: Any) -> list[str]:
    if isinstance(value, str) and value:
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value if isinstance(item, str) and item]
    if isinstance(value, dict):
        values: list[str] = []
        for item in value.values():
            values.extend(_artifact_values(item))
        return values
    return []


def _bounded_artifacts(values: list[Any]) -> list[str]:
    artifacts = sorted({str(value) for value in values if isinstance(value, str) and value})
    return artifacts[:MAX_SOURCE_ARTIFACTS]


def _bounded_messages(values: list[Any]) -> list[str]:
    messages = [_bounded_text(value) for value in values if isinstance(value, str) and value]
    return messages[:MAX_MESSAGES]


def _bounded_errors(values: list[Any]) -> list[dict[str, Any] | str]:
    errors: list[dict[str, Any] | str] = []
    for value in values[:MAX_MESSAGES]:
        if isinstance(value, dict):
            check = value.get("check")
            message = value.get("message")
            errors.append(
                {
                    "check": _bounded_text(check),
                    "message": _bounded_text(message),
                }
            )
        elif isinstance(value, str):
            errors.append(_bounded_text(value))
    return errors


def _bounded_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    if len(text) <= MAX_MESSAGE_CHARS:
        return text
    return f"{text[: MAX_MESSAGE_CHARS - 3].rstrip()}..."


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    return value if isinstance(value, int) else 0


def _yaml_block(record: dict[str, Any]) -> str:
    try:
        import yaml
    except ModuleNotFoundError as exc:
        raise PipelineError(
            "PyYAML is required to write YAML data quality material.",
            stage=STAGE_NAME,
            exit_code=1,
        ) from exc

    return yaml.safe_dump(record, allow_unicode=True, sort_keys=False)
