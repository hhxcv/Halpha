from __future__ import annotations

import os
from typing import Any, Mapping


RUN_TRIGGER_SOURCE_ENV = "HALPHA_RUN_TRIGGER_SOURCE"
RUN_TRIGGER_INTENT_ENV = "HALPHA_RUN_TRIGGER_INTENT"
RUN_TRIGGER_JOB_ID_ENV = "HALPHA_RUN_TRIGGER_JOB_ID"
RUN_TRIGGER_SCHEDULE_ID_ENV = "HALPHA_RUN_TRIGGER_SCHEDULE_ID"
RUN_TRIGGER_MONITOR_CYCLE_ID_ENV = "HALPHA_RUN_TRIGGER_MONITOR_CYCLE_ID"
RUN_TRIGGER_SOURCE_KEYS_ENV = "HALPHA_RUN_TRIGGER_SOURCE_KEYS"
RUN_TRIGGER_PARENT_RUN_ID_ENV = "HALPHA_RUN_TRIGGER_PARENT_RUN_ID"
RUN_TRIGGER_REQUESTED_STAGE_ENV = "HALPHA_RUN_TRIGGER_REQUESTED_STAGE"
RUN_TRIGGER_DISPATCH_KIND_ENV = "HALPHA_RUN_TRIGGER_DISPATCH_KIND"

RUN_TRIGGER_ENV_FIELDS = {
    RUN_TRIGGER_SOURCE_ENV: "source",
    RUN_TRIGGER_INTENT_ENV: "intent",
    RUN_TRIGGER_JOB_ID_ENV: "job_id",
    RUN_TRIGGER_SCHEDULE_ID_ENV: "schedule_id",
    RUN_TRIGGER_MONITOR_CYCLE_ID_ENV: "monitor_cycle_id",
    RUN_TRIGGER_PARENT_RUN_ID_ENV: "parent_run_id",
    RUN_TRIGGER_REQUESTED_STAGE_ENV: "requested_stage",
    RUN_TRIGGER_DISPATCH_KIND_ENV: "dispatch_kind",
}
RUN_TRIGGER_ENV_VARS = tuple(RUN_TRIGGER_ENV_FIELDS) + (RUN_TRIGGER_SOURCE_KEYS_ENV,)

RUN_TRIGGER_SOURCES = {"CLI", "Dashboard", "Monitor", "Schedule", "unknown"}
RUN_KIND_PRODUCT_REPORT = "product_report"
RUN_KIND_SCHEDULED_REPORT = "scheduled_report"
RUN_KIND_MONITOR_REASSESSMENT = "monitor_reassessment"
RUN_KIND_STAGE_RERUN = "stage_rerun"
RUN_KIND_VALIDATION = "validation_run"
RUN_KIND_UNKNOWN = "unknown"
DISPOSAL_REPORT_ARCHIVE = "report_archive"
DISPOSAL_MONITOR_REASSESSMENT_ARCHIVE = "monitor_reassessment_archive"
DISPOSAL_DERIVED_ARCHIVE = "derived_archive"
DISPOSAL_VALIDATION_ARCHIVE = "validation_archive"
DISPOSAL_LEGACY_ARCHIVE = "legacy_archive"

_LABEL_MAX_CHARS = 160
_PRIVATE_MARKERS = ("\\", "/", "://", "@", "token", "secret", "credential", "proxy", "password", "cookie")
_SOURCE_BY_LOWER = {source.lower(): source for source in RUN_TRIGGER_SOURCES}


def run_trigger_from_env(
    *,
    default_source: str,
    default_intent: str,
    extra: Mapping[str, Any] | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    values = env or os.environ
    raw: dict[str, Any] = {
        field: values.get(env_key)
        for env_key, field in RUN_TRIGGER_ENV_FIELDS.items()
        if values.get(env_key)
    }
    source_keys = values.get(RUN_TRIGGER_SOURCE_KEYS_ENV)
    if source_keys:
        raw["source_keys"] = source_keys.split(",")
    if extra:
        raw.update(dict(extra))
    return normalize_run_trigger(raw, default_source=default_source, default_intent=default_intent)


def run_trigger_env(env: Mapping[str, str] | None, trigger: Mapping[str, Any]) -> dict[str, str]:
    values = dict(env or os.environ)
    for key in RUN_TRIGGER_ENV_VARS:
        values.pop(key, None)
    normalized = normalize_run_trigger(trigger, default_source="CLI", default_intent="run")
    values[RUN_TRIGGER_SOURCE_ENV] = normalized["source"]
    values[RUN_TRIGGER_INTENT_ENV] = normalized["intent"]
    optional_fields = {
        "job_id": RUN_TRIGGER_JOB_ID_ENV,
        "schedule_id": RUN_TRIGGER_SCHEDULE_ID_ENV,
        "monitor_cycle_id": RUN_TRIGGER_MONITOR_CYCLE_ID_ENV,
        "parent_run_id": RUN_TRIGGER_PARENT_RUN_ID_ENV,
        "requested_stage": RUN_TRIGGER_REQUESTED_STAGE_ENV,
        "dispatch_kind": RUN_TRIGGER_DISPATCH_KIND_ENV,
    }
    for field, env_key in optional_fields.items():
        value = normalized.get(field)
        if isinstance(value, str) and value:
            values[env_key] = value
    source_keys = normalized.get("source_keys")
    if isinstance(source_keys, list) and source_keys:
        values[RUN_TRIGGER_SOURCE_KEYS_ENV] = ",".join(source_keys)
    return values


def normalize_run_trigger(
    value: Mapping[str, Any] | None,
    *,
    default_source: str,
    default_intent: str,
) -> dict[str, Any]:
    raw = dict(value or {})
    trigger = {
        "source": _safe_source(raw.get("source"), default=default_source),
        "intent": _safe_label(raw.get("intent"), fallback=default_intent),
    }
    for field in (
        "job_id",
        "schedule_id",
        "monitor_cycle_id",
        "parent_run_id",
        "requested_stage",
        "dispatch_kind",
    ):
        label = _safe_label(raw.get(field), fallback=None)
        if label:
            trigger[field] = label
    source_keys = _safe_source_keys(raw.get("source_keys"))
    if source_keys:
        trigger["source_keys"] = source_keys
    return trigger


def product_run_classification(
    *,
    trigger: Mapping[str, Any] | None,
    until_stage: str | None,
    skip_codex: bool,
) -> dict[str, Any]:
    normalized = normalize_run_trigger(trigger, default_source="CLI", default_intent=_default_run_intent(until_stage, skip_codex))
    validation_run = until_stage is not None or skip_codex or normalized["intent"] in {"run_no_codex", "run_until"}
    if normalized["source"] == "Monitor" or normalized.get("monitor_cycle_id"):
        run_kind = RUN_KIND_MONITOR_REASSESSMENT
        disposal_class = DISPOSAL_MONITOR_REASSESSMENT_ARCHIVE
    elif normalized["source"] == "Schedule" or normalized.get("schedule_id"):
        run_kind = RUN_KIND_SCHEDULED_REPORT
        disposal_class = DISPOSAL_VALIDATION_ARCHIVE if validation_run else DISPOSAL_REPORT_ARCHIVE
    elif validation_run:
        run_kind = RUN_KIND_VALIDATION
        disposal_class = DISPOSAL_VALIDATION_ARCHIVE
    else:
        run_kind = RUN_KIND_PRODUCT_REPORT
        disposal_class = DISPOSAL_REPORT_ARCHIVE
    return {"run_kind": run_kind, "trigger": normalized, "disposal_class": disposal_class}


def stage_rerun_classification(
    *,
    trigger: Mapping[str, Any] | None,
    parent_run_id: str,
    requested_stage: str,
) -> dict[str, Any]:
    normalized = normalize_run_trigger(
        {**dict(trigger or {}), "parent_run_id": parent_run_id, "requested_stage": requested_stage},
        default_source="CLI",
        default_intent="stage_rerun",
    )
    return {
        "run_kind": RUN_KIND_STAGE_RERUN,
        "trigger": normalized,
        "disposal_class": DISPOSAL_DERIVED_ARCHIVE,
    }


def stage_resume_trigger(
    *,
    trigger: Mapping[str, Any] | None,
    run_id: str,
    requested_stage: str,
) -> dict[str, Any]:
    return normalize_run_trigger(
        {**dict(trigger or {}), "parent_run_id": run_id, "requested_stage": requested_stage},
        default_source="CLI",
        default_intent="stage_resume",
    )


def classification_from_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    trigger_value = manifest.get("trigger")
    default_source = "unknown" if not isinstance(trigger_value, Mapping) else "unknown"
    trigger = normalize_run_trigger(
        trigger_value if isinstance(trigger_value, Mapping) else None,
        default_source=default_source,
        default_intent="unknown",
    )
    return {
        "run_kind": _safe_label(manifest.get("run_kind"), fallback=RUN_KIND_UNKNOWN),
        "trigger": trigger,
        "disposal_class": _safe_label(manifest.get("disposal_class"), fallback=DISPOSAL_LEGACY_ARCHIVE),
    }


def run_trigger_requested_by(trigger: Mapping[str, Any] | None, *, default: str = "CLI") -> str:
    source = normalize_run_trigger(trigger, default_source=default, default_intent="run")["source"]
    return source if source in {"CLI", "Dashboard", "Monitor", "Schedule"} else default


def _default_run_intent(until_stage: str | None, skip_codex: bool) -> str:
    if until_stage is not None:
        return "run_until"
    if skip_codex:
        return "run_no_codex"
    return "run"


def _safe_source(value: Any, *, default: str) -> str:
    fallback = _SOURCE_BY_LOWER.get(str(default or "").strip().lower(), "CLI")
    if not isinstance(value, str):
        return fallback
    label = _safe_label(value, fallback=None)
    if not label:
        return fallback
    return _SOURCE_BY_LOWER.get(label.lower(), fallback)


def _safe_label(value: Any, *, fallback: str | None) -> str | None:
    if not isinstance(value, str):
        return fallback
    text = value.strip()
    if not text:
        return fallback
    lowered = text.lower()
    if any(marker in lowered for marker in _PRIVATE_MARKERS):
        return fallback
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-+")
    if any(char not in allowed for char in text):
        return fallback
    return text[:_LABEL_MAX_CHARS]


def _safe_source_keys(value: Any) -> list[str]:
    if not isinstance(value, list | tuple):
        return []
    output: list[str] = []
    for item in value:
        label = _safe_label(item, fallback=None)
        if label and label not in output:
            output.append(label)
    return output
