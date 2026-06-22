from __future__ import annotations

import json
from json import JSONDecodeError
from typing import Any

from halpha.runtime.pipeline_contracts import PipelineError, RunContext


STAGE_NAME = "build_analysis_materials"
FEATURE_SNAPSHOTS_ARTIFACT = "analysis/feature_snapshots.json"
FACTOR_STATES_ARTIFACT = "analysis/factor_states.json"
MULTI_SOURCE_SIGNALS_ARTIFACT = "analysis/multi_source_signals.json"
FACTOR_SIGNAL_MATERIAL_ARTIFACT = "analysis/factor_signal_material.md"

MAX_FEATURE_RECORDS = 2
MAX_FACTOR_RECORDS = 4
MAX_SIGNAL_RECORDS = 3
MAX_MESSAGES = 2
MAX_ARTIFACTS = 10
MAX_VALUE_FIELDS = 4
MAX_MESSAGE_CHARS = 160


def build_factor_signal_material(config: dict[str, Any], run: RunContext) -> list[str]:
    feature_snapshots = _read_artifact(
        run.analysis_dir / "feature_snapshots.json",
        FEATURE_SNAPSHOTS_ARTIFACT,
        expected_type="feature_snapshots",
        producer_stage="build_feature_snapshots",
    )
    factor_states = _read_artifact(
        run.analysis_dir / "factor_states.json",
        FACTOR_STATES_ARTIFACT,
        expected_type="factor_states",
        producer_stage="build_factor_states",
    )
    multi_source_signals = _read_artifact(
        run.analysis_dir / "multi_source_signals.json",
        MULTI_SOURCE_SIGNALS_ARTIFACT,
        expected_type="multi_source_signals",
        producer_stage="build_multi_source_signals",
    )

    material_record = _material_record(
        feature_snapshots=feature_snapshots,
        factor_states=factor_states,
        multi_source_signals=multi_source_signals,
    )
    material = render_factor_signal_material(material_record)
    (run.analysis_dir / "factor_signal_material.md").write_text(material, encoding="utf-8")

    run.manifest["artifacts"]["factor_signal_material"] = FACTOR_SIGNAL_MATERIAL_ARTIFACT
    run.manifest["counts"]["factor_signal_material_records"] = material_record["selected_record_count"]
    run.manifest["counts"]["factor_signal_material_omitted_records"] = material_record["omitted_record_count"]
    run.manifest["factor_signal_material"] = {
        "status": material_record["factor_signal_overview"]["status"],
        "artifact": FACTOR_SIGNAL_MATERIAL_ARTIFACT,
        "source_artifacts": material_record["source_policy"]["source_artifacts"],
        "selected_feature_records": material_record["selected_feature_snapshots"]["selected_record_count"],
        "selected_factor_records": material_record["selected_factor_states"]["selected_record_count"],
        "selected_multi_source_signal_records": material_record["selected_multi_source_signals"][
            "selected_record_count"
        ],
        "omitted_feature_records": material_record["selected_feature_snapshots"]["omitted_record_count"],
        "omitted_factor_records": material_record["selected_factor_states"]["omitted_record_count"],
        "omitted_multi_source_signal_records": material_record["selected_multi_source_signals"][
            "omitted_record_count"
        ],
    }
    return [FACTOR_SIGNAL_MATERIAL_ARTIFACT]


def render_factor_signal_material(material_record: dict[str, Any]) -> str:
    lines = [
        "---",
        "artifact_type: analysis_factor_signal_material",
        "schema_version: 1",
        "audience: ai",
        "source_artifacts:",
        f"  - {FEATURE_SNAPSHOTS_ARTIFACT}",
        f"  - {FACTOR_STATES_ARTIFACT}",
        f"  - {MULTI_SOURCE_SIGNALS_ARTIFACT}",
        "---",
        "",
        "# factor_signal_material",
        "",
    ]
    for section in (
        "source_policy",
        "factor_signal_overview",
        "taxonomy",
        "selected_multi_source_signals",
        "selected_factor_states",
        "selected_feature_snapshots",
        "data_quality",
        "omissions",
        "report_usage_rules",
    ):
        lines.extend(
            [
                f"## {section}",
                "",
                "```yaml",
                _yaml_block(material_record[section]).rstrip(),
                "```",
                "",
            ]
        )
    return "\n".join(lines)


def _read_artifact(
    path: Any,
    artifact: str,
    *,
    expected_type: str,
    producer_stage: str,
) -> dict[str, Any]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PipelineError(
            f"{artifact} was not found; {producer_stage} must run first.",
            stage=STAGE_NAME,
            exit_code=3,
        ) from exc
    except JSONDecodeError as exc:
        raise PipelineError(
            f"{artifact} is not valid JSON: {exc.msg}.",
            stage=STAGE_NAME,
            exit_code=3,
        ) from exc
    if not isinstance(loaded, dict):
        raise PipelineError(
            f"{artifact} must contain a JSON object.",
            stage=STAGE_NAME,
            exit_code=3,
        )
    if loaded.get("artifact_type") != expected_type:
        raise PipelineError(
            f"{artifact} must have artifact_type {expected_type}.",
            stage=STAGE_NAME,
            exit_code=3,
        )
    if not isinstance(loaded.get("records"), list):
        raise PipelineError(
            f"{artifact} must contain a records list.",
            stage=STAGE_NAME,
            exit_code=3,
        )
    return loaded


def _material_record(
    *,
    feature_snapshots: dict[str, Any],
    factor_states: dict[str, Any],
    multi_source_signals: dict[str, Any],
) -> dict[str, Any]:
    feature_records = _dict_records(feature_snapshots)
    factor_records = _dict_records(factor_states)
    signal_records = _dict_records(multi_source_signals)

    selected_features = _select_records(feature_records, _feature_sort_key, limit=MAX_FEATURE_RECORDS)
    selected_factors = _select_records(factor_records, _factor_sort_key, limit=MAX_FACTOR_RECORDS)
    selected_signals = _select_records(signal_records, _signal_sort_key, limit=MAX_SIGNAL_RECORDS)
    selected_count = len(selected_features) + len(selected_factors) + len(selected_signals)
    total_count = len(feature_records) + len(factor_records) + len(signal_records)

    return {
        "source_policy": _source_policy(feature_snapshots, factor_states, multi_source_signals),
        "factor_signal_overview": {
            "record_type": "factor_signal_overview",
            "run_id": multi_source_signals.get("run_id")
            or factor_states.get("run_id")
            or feature_snapshots.get("run_id"),
            "created_at": multi_source_signals.get("created_at")
            or factor_states.get("created_at")
            or feature_snapshots.get("created_at"),
            "status": _material_status(feature_snapshots, factor_states, multi_source_signals),
            "feature_record_count": len(feature_records),
            "factor_record_count": len(factor_records),
            "multi_source_signal_record_count": len(signal_records),
            "selected_record_count": selected_count,
            "omitted_record_count": max(0, total_count - selected_count),
            "feature_status_counts": _counts_by(feature_records, "status"),
            "factor_state_counts": _counts_by(factor_records, "state"),
            "factor_direction_counts": _counts_by(factor_records, "direction"),
            "multi_source_signal_state_counts": _counts_by(signal_records, "state"),
            "multi_source_signal_direction_counts": _counts_by(signal_records, "direction"),
            "source_status_counts": _coverage_status_counts(feature_snapshots),
            "warnings": _bounded_messages(
                [
                    *_string_list(feature_snapshots.get("warnings")),
                    *_string_list(factor_states.get("warnings")),
                    *_string_list(multi_source_signals.get("warnings")),
                ]
            ),
            "errors": _bounded_errors(
                [
                    *_list(feature_snapshots.get("errors")),
                    *_list(factor_states.get("errors")),
                    *_list(multi_source_signals.get("errors")),
                ]
            ),
        },
        "taxonomy": {
            "record_type": "factor_signal_taxonomy",
            "factor_types": sorted(_counts_by(factor_records, "factor_type")),
            "factor_states": [
                "supportive",
                "cautionary",
                "neutral",
                "conflicting",
                "insufficient_evidence",
                "degraded",
                "stale",
                "failed",
            ],
            "multi_source_signal_states": [
                "supportive",
                "cautionary",
                "neutral",
                "conflicting",
                "insufficient_evidence",
                "degraded",
                "failed",
            ],
            "score_unit": "bounded_-1_to_1",
            "source_layers": sorted(_counts_by(feature_records, "source_layer")),
        },
        "selected_multi_source_signals": {
            "record_type": "selected_multi_source_signals",
            "selection_policy": "conflict_degraded_insufficient_then_directional_high_signal",
            "record_limit": MAX_SIGNAL_RECORDS,
            "total_record_count": len(signal_records),
            "selected_record_count": len(selected_signals),
            "omitted_record_count": max(0, len(signal_records) - len(selected_signals)),
            "records": [_signal_summary(record) for record in selected_signals],
        },
        "selected_factor_states": {
            "record_type": "selected_factor_states",
            "selection_policy": "failed_conflicting_stale_degraded_insufficient_then_directional",
            "record_limit": MAX_FACTOR_RECORDS,
            "total_record_count": len(factor_records),
            "selected_record_count": len(selected_factors),
            "omitted_record_count": max(0, len(factor_records) - len(selected_factors)),
            "records": [_factor_summary(record) for record in selected_factors],
        },
        "selected_feature_snapshots": {
            "record_type": "selected_feature_snapshots",
            "selection_policy": "source_gap_or_non_available_then_directional_high_signal",
            "record_limit": MAX_FEATURE_RECORDS,
            "total_record_count": len(feature_records),
            "selected_record_count": len(selected_features),
            "omitted_record_count": max(0, len(feature_records) - len(selected_features)),
            "coverage": _coverage_summary(feature_snapshots),
            "records": [_feature_summary(record) for record in selected_features],
        },
        "omissions": {
            "record_type": "factor_signal_material_omissions",
            "feature_records_omitted": max(0, len(feature_records) - len(selected_features)),
            "factor_records_omitted": max(0, len(factor_records) - len(selected_factors)),
            "multi_source_signal_records_omitted": max(0, len(signal_records) - len(selected_signals)),
            "omitted_feature_status_counts": _omitted_counts(feature_records, selected_features, "status", "feature_id"),
            "omitted_factor_state_counts": _omitted_counts(factor_records, selected_factors, "state", "factor_id"),
            "omitted_multi_source_signal_state_counts": _omitted_counts(
                signal_records,
                selected_signals,
                "state",
                "signal_id",
            ),
            "full_feature_snapshots_json_embedded": False,
            "full_factor_states_json_embedded": False,
            "full_multi_source_signals_json_embedded": False,
        },
        "data_quality": {
            "record_type": "factor_signal_data_quality",
            "feature_snapshot_status": feature_snapshots.get("status") or "unknown",
            "factor_states_status": factor_states.get("status") or "unknown",
            "multi_source_signals_status": multi_source_signals.get("status") or "unknown",
            "source_status_counts": _coverage_status_counts(feature_snapshots),
            "warnings": _bounded_messages(
                [
                    *_string_list(feature_snapshots.get("warnings")),
                    *_string_list(factor_states.get("warnings")),
                    *_string_list(multi_source_signals.get("warnings")),
                ]
            ),
            "errors": _bounded_errors(
                [
                    *_list(feature_snapshots.get("errors")),
                    *_list(factor_states.get("errors")),
                    *_list(multi_source_signals.get("errors")),
                ]
            ),
        },
        "report_usage_rules": _report_usage_rules(),
        "selected_record_count": selected_count,
        "omitted_record_count": max(0, total_count - selected_count),
    }


def _source_policy(
    feature_snapshots: dict[str, Any],
    factor_states: dict[str, Any],
    multi_source_signals: dict[str, Any],
) -> dict[str, Any]:
    return {
        "record_type": "factor_signal_source_policy",
        "research_material_only": True,
        "codex_may_explain_factor_signal_material": True,
        "codex_may_generate_feature_records": False,
        "codex_may_generate_factor_scores": False,
        "codex_may_generate_factor_states": False,
        "codex_may_generate_signal_states": False,
        "codex_may_generate_action_levels": False,
        "codex_may_generate_price_forecasts": False,
        "codex_may_create_trading_instructions": False,
        "full_feature_snapshots_json_embedded": False,
        "full_factor_states_json_embedded": False,
        "full_multi_source_signals_json_embedded": False,
        "full_raw_streams_embedded": False,
        "full_reusable_histories_embedded": False,
        "selected_records_only": True,
        "source_artifacts": _bounded_source_artifacts(
            [
                FEATURE_SNAPSHOTS_ARTIFACT,
                FACTOR_STATES_ARTIFACT,
                MULTI_SOURCE_SIGNALS_ARTIFACT,
            ],
            [
                *_string_list(feature_snapshots.get("source_artifacts")),
                *_string_list(factor_states.get("source_artifacts")),
                *_string_list(multi_source_signals.get("source_artifacts")),
            ],
        ),
    }


def _report_usage_rules() -> dict[str, Any]:
    return {
        "record_type": "factor_signal_report_usage_rules",
        "explain_agreement_conflict_missing_stale_degraded_and_uncertainty": True,
        "use_halpha_factor_states_only": True,
        "use_halpha_multi_source_signal_states_only": True,
        "use_halpha_feature_records_only": True,
        "do_not_generate_feature_records": True,
        "do_not_generate_factor_scores": True,
        "do_not_generate_factor_states": True,
        "do_not_generate_signal_states": True,
        "do_not_generate_action_levels": True,
        "do_not_generate_price_forecasts": True,
        "do_not_create_trading_instructions": True,
    }


def _signal_summary(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "record_type": "multi_source_signal",
        "signal_id": record.get("signal_id"),
        "signal_type": record.get("signal_type"),
        "scope": _compact_scope(record.get("scope")),
        "state": record.get("state"),
        "direction": record.get("direction"),
        "score": _bounded_score(record.get("score")),
        "confidence": record.get("confidence"),
        "factor_score_summary": _bounded_mapping(_dict(record.get("factor_score_summary"))),
        "factor_link_counts": {
            "conflicting": len(_string_list(record.get("conflicting_factor_ids"))),
            "insufficient": len(_string_list(record.get("insufficient_factor_ids"))),
            "degraded": len(_string_list(record.get("degraded_factor_ids"))),
            "failed": len(_string_list(record.get("failed_factor_ids"))),
        },
        "evidence": _bounded_messages(_string_list(record.get("evidence"))),
        "uncertainty": _bounded_messages(_string_list(record.get("uncertainty"))),
        "warnings": _bounded_messages(_string_list(record.get("warnings"))),
        "errors": _bounded_errors(_list(record.get("errors"))),
    }


def _factor_summary(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "record_type": "factor_state",
        "factor_id": record.get("factor_id"),
        "factor_type": record.get("factor_type"),
        "scope": _compact_scope(record.get("scope")),
        "state": record.get("state"),
        "direction": record.get("direction"),
        "score": _bounded_score(record.get("score")),
        "score_unit": record.get("score_unit"),
        "confidence": record.get("confidence"),
        "input_feature_count": len(_string_list(record.get("input_feature_ids"))),
        "evidence": _bounded_messages(_string_list(record.get("evidence"))),
        "uncertainty": _bounded_messages(_string_list(record.get("uncertainty"))),
        "warnings": _bounded_messages(_string_list(record.get("warnings"))),
        "errors": _bounded_errors(_list(record.get("errors"))),
    }


def _feature_summary(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "record_type": "feature_snapshot",
        "feature_id": record.get("feature_id"),
        "feature_type": record.get("feature_type"),
        "factor_family": record.get("factor_family"),
        "source_layer": record.get("source_layer"),
        "source_artifact": record.get("source_artifact"),
        "scope": _compact_scope(record.get("scope")),
        "observed_at": record.get("observed_at"),
        "value": _bounded_value(record.get("value")),
        "value_unit": record.get("value_unit"),
        "direction_hint": record.get("direction_hint"),
        "status": record.get("status"),
        "confidence": record.get("confidence"),
        "evidence": _bounded_messages(_string_list(record.get("evidence"))),
        "uncertainty": _bounded_messages(_string_list(record.get("uncertainty"))),
        "warnings": _bounded_messages(_string_list(record.get("warnings"))),
        "errors": _bounded_errors(_list(record.get("errors"))),
    }


def _coverage_summary(feature_snapshots: dict[str, Any]) -> list[dict[str, Any]]:
    records = [item for item in _list(feature_snapshots.get("coverage")) if isinstance(item, dict)]
    return [
        {
            "source_layer": record.get("source_layer"),
            "source_artifact": record.get("source_artifact"),
            "status": record.get("status"),
            "record_count": record.get("record_count"),
            "reason": record.get("reason"),
            "error": record.get("error"),
        }
        for record in sorted(records, key=lambda item: (str(item.get("source_layer")), str(item.get("source_artifact"))))[
            :MAX_FEATURE_RECORDS
        ]
    ]


def _select_records(
    records: list[dict[str, Any]],
    key_func: Any,
    *,
    limit: int,
) -> list[dict[str, Any]]:
    return sorted(records, key=key_func)[:limit]


def _signal_sort_key(record: dict[str, Any]) -> tuple[int, int, str, str]:
    return (
        _state_priority(record.get("state")),
        _direction_priority(record.get("direction")),
        _scope_key(record.get("scope")),
        str(record.get("signal_id") or ""),
    )


def _factor_sort_key(record: dict[str, Any]) -> tuple[int, int, str, str, str]:
    return (
        _state_priority(record.get("state")),
        _direction_priority(record.get("direction")),
        str(record.get("factor_type") or ""),
        _scope_key(record.get("scope")),
        str(record.get("factor_id") or ""),
    )


def _feature_sort_key(record: dict[str, Any]) -> tuple[int, int, str, str, str]:
    return (
        _feature_status_priority(record.get("status")),
        _direction_priority(record.get("direction_hint")),
        str(record.get("source_layer") or ""),
        _scope_key(record.get("scope")),
        str(record.get("feature_id") or ""),
    )


def _state_priority(value: Any) -> int:
    state = str(value or "unknown").lower()
    order = {
        "failed": 0,
        "conflicting": 1,
        "stale": 2,
        "degraded": 3,
        "insufficient_evidence": 4,
        "cautionary": 5,
        "supportive": 6,
        "neutral": 7,
        "unknown": 8,
    }
    return order.get(state, 8)


def _feature_status_priority(value: Any) -> int:
    status = str(value or "unknown").lower()
    order = {
        "failed": 0,
        "missing": 1,
        "unavailable": 2,
        "stale": 3,
        "degraded": 4,
        "partial": 5,
        "insufficient_evidence": 6,
        "available": 7,
        "skipped": 8,
        "unknown": 9,
    }
    return order.get(status, 9)


def _direction_priority(value: Any) -> int:
    direction = str(value or "unknown").lower()
    order = {
        "conflicting": 0,
        "cautionary": 1,
        "supportive": 2,
        "neutral": 3,
        "unknown": 4,
    }
    return order.get(direction, 4)


def _material_status(
    feature_snapshots: dict[str, Any],
    factor_states: dict[str, Any],
    multi_source_signals: dict[str, Any],
) -> str:
    statuses = [
        str(feature_snapshots.get("status") or "unknown").lower(),
        str(factor_states.get("status") or "unknown").lower(),
        str(multi_source_signals.get("status") or "unknown").lower(),
    ]
    if "failed" in statuses:
        return "failed"
    if any(status in {"warning", "degraded", "partial"} for status in statuses):
        return "warning"
    if all(status in {"ok", "succeeded"} for status in statuses):
        return "ok"
    return "unknown"


def _coverage_status_counts(feature_snapshots: dict[str, Any]) -> dict[str, int]:
    return _counts_by(
        [item for item in _list(feature_snapshots.get("coverage")) if isinstance(item, dict)],
        "status",
    )


def _omitted_counts(
    all_records: list[dict[str, Any]],
    selected_records: list[dict[str, Any]],
    count_key: str,
    identity_key: str,
) -> dict[str, int]:
    selected_ids = {str(record.get(identity_key)) for record in selected_records if record.get(identity_key)}
    omitted = [
        record
        for record in all_records
        if str(record.get(identity_key)) not in selected_ids
    ]
    return _counts_by(omitted, count_key)


def _dict_records(artifact: dict[str, Any]) -> list[dict[str, Any]]:
    return [record for record in _list(artifact.get("records")) if isinstance(record, dict)]


def _counts_by(records: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        value = str(record.get(key) or "unknown")
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _scope_key(value: Any) -> str:
    scope = value if isinstance(value, dict) else {}
    values = [scope.get(key) for key in ("symbol", "timeframe", "asset", "chain", "region") if scope.get(key)]
    return ":".join(str(item).lower().replace(" ", "_") for item in values) or "global"


def _bounded_mapping(value: dict[str, Any]) -> dict[str, Any]:
    selected: dict[str, Any] = {}
    for key in sorted(value)[:MAX_VALUE_FIELDS]:
        item = value[key]
        if isinstance(item, dict):
            selected[key] = _bounded_mapping(item)
        elif isinstance(item, list):
            selected[key] = _bounded_messages(_string_list(item))
        elif isinstance(item, bool | int | float | str) or item is None:
            selected[key] = item
    return selected


def _bounded_score(value: Any) -> float | None:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return None
    return round(max(-1.0, min(1.0, score)), 4)


def _bounded_value(value: Any) -> Any:
    if isinstance(value, bool | int | float | str) or value is None:
        return value
    if isinstance(value, dict):
        return _bounded_mapping(value)
    if isinstance(value, list):
        return _bounded_messages(_string_list(value))
    return str(value)


def _bounded_messages(values: list[Any]) -> list[str]:
    messages = []
    for value in values:
        if value is None:
            continue
        text = str(value)
        if not text:
            continue
        messages.append(text if len(text) <= MAX_MESSAGE_CHARS else f"{text[: MAX_MESSAGE_CHARS - 3].rstrip()}...")
        if len(messages) >= MAX_MESSAGES:
            break
    return messages


def _bounded_errors(values: list[Any]) -> list[dict[str, Any] | str]:
    errors: list[dict[str, Any] | str] = []
    for value in values[:MAX_MESSAGES]:
        if isinstance(value, dict):
            message = _bounded_messages([value.get("message") or value.get("error") or value])
            errors.append(
                {
                    "code": value.get("code"),
                    "message": message[0] if message else None,
                }
            )
        elif isinstance(value, str):
            errors.append(value)
    return errors


def _bounded_artifacts(values: list[Any]) -> list[str]:
    return sorted({str(value) for value in values if isinstance(value, str) and value})[:MAX_ARTIFACTS]


def _bounded_source_artifacts(core: list[str], extras: list[str]) -> list[str]:
    values: list[str] = []
    seen = set()
    for value in [*core, *sorted(extras)]:
        if not isinstance(value, str) or not value or value in seen:
            continue
        seen.add(value)
        values.append(value)
        if len(values) >= MAX_ARTIFACTS:
            break
    return values


def _compact_scope(value: Any) -> dict[str, Any]:
    scope = _dict(value)
    return {
        key: scope[key]
        for key in ("symbol", "timeframe", "asset", "chain", "region")
        if scope.get(key) is not None
    }


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, list):
        strings = []
        for item in value:
            if isinstance(item, dict):
                strings.append(json.dumps(item, ensure_ascii=False, sort_keys=True))
            elif isinstance(item, str | int | float) and str(item):
                strings.append(str(item))
        return strings
    if isinstance(value, dict):
        return [json.dumps(value, ensure_ascii=False, sort_keys=True)]
    return [str(value)] if str(value) else []


def _yaml_block(data: dict[str, Any]) -> str:
    try:
        import yaml
    except ModuleNotFoundError as exc:
        raise PipelineError(
            "PyYAML is required to write YAML factor signal material records.",
            stage=STAGE_NAME,
            exit_code=1,
        ) from exc

    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
