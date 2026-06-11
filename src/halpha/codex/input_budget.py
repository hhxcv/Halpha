from __future__ import annotations

from copy import deepcopy
from typing import Any


SCHEMA_VERSION = 1
DEFAULT_MATERIAL_MAX_CHARS = 16_000
RESEARCH_CONTEXT_MAX_CHARS = 140_000
CODEX_CONTEXT_MAX_CHARS = 150_000
CODEX_PROMPT_MAX_CHARS = 170_000

CODEX_INPUT_POLICY = {
    "bounded_report_facing_material_only": True,
    "complete_evidence_artifacts_preserved_outside_codex_input": True,
    "full_raw_streams_embedded": False,
    "full_intermediate_json_embedded": False,
    "full_shared_ohlcv_history_embedded": False,
    "full_run_manifest_embedded": False,
    "prefer_high_signal_decision_risk_alert_event_strategy_material": True,
    "summarize_or_omit_low_priority_records_with_counts": True,
}


def text_budget_record(
    artifact: str,
    content: str | None,
    *,
    status: str,
    max_chars: int,
    role: str,
) -> dict[str, Any]:
    text = content or ""
    chars = len(text)
    record = {
        "artifact": artifact,
        "role": role,
        "status": status,
        "chars": chars,
        "lines": _line_count(text),
        "max_chars": max_chars,
        "over_budget": chars > max_chars,
        "warnings": [],
    }
    if chars > max_chars:
        record["warnings"].append("codex_input_over_budget")
    return record


def update_codex_input_manifest(
    manifest: dict[str, Any],
    *,
    materials: list[dict[str, Any]] | None = None,
    research_context: dict[str, Any] | None = None,
    codex_context: dict[str, Any] | None = None,
    codex_prompt: dict[str, Any] | None = None,
) -> None:
    section = manifest.setdefault(
        "codex_input",
        {
            "schema_version": SCHEMA_VERSION,
            "policy": deepcopy(CODEX_INPUT_POLICY),
            "materials": [],
            "warnings": [],
        },
    )
    section.setdefault("schema_version", SCHEMA_VERSION)
    section.setdefault("policy", deepcopy(CODEX_INPUT_POLICY))
    section.setdefault("materials", [])
    section.setdefault("warnings", [])

    if materials is not None:
        for record in materials:
            _upsert_by_artifact(section["materials"], record)
    if research_context is not None:
        section["research_context"] = research_context
    if codex_context is not None:
        section["codex_context"] = codex_context
    if codex_prompt is not None:
        section["codex_prompt"] = codex_prompt

    warnings: list[str] = []
    for record in section.get("materials", []):
        warnings.extend(record.get("warnings") or [])
    for key in ("research_context", "codex_context", "codex_prompt"):
        record = section.get(key)
        if isinstance(record, dict):
            warnings.extend(record.get("warnings") or [])
    section["warnings"] = _unique([str(warning) for warning in warnings if warning])


def _upsert_by_artifact(records: list[dict[str, Any]], record: dict[str, Any]) -> None:
    artifact = record.get("artifact")
    for index, existing in enumerate(records):
        if existing.get("artifact") == artifact:
            records[index] = record
            return
    records.append(record)


def _line_count(text: str) -> int:
    if not text:
        return 0
    return text.count("\n") + 1


def _unique(values: list[str]) -> list[str]:
    unique: list[str] = []
    for value in values:
        if value not in unique:
            unique.append(value)
    return unique
