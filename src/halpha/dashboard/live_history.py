from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


LIVE_HISTORY_ARTIFACT = "dashboard_live_history"
LIVE_HISTORY_TIMELINE_LIMIT = 200
LIVE_HISTORY_TRIGGER_LIMIT = 50
LIVE_HISTORY_ALERT_LIMIT = 50
ATTENTION_STATUSES = {
    "blocked",
    "cancelled",
    "degraded",
    "failed",
    "missing",
    "partial",
    "stale",
    "suppressed_cooldown",
    "suppressed_duplicate",
    "warning",
}


def dashboard_live_history(
    *,
    live_payload: dict[str, Any] | None,
    jobs_payload: dict[str, Any] | None,
    schedule_payload: dict[str, Any] | None,
    cycles_payload: dict[str, Any] | None,
    alerts_payload: dict[str, Any] | None,
    filters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    live = live_payload if isinstance(live_payload, dict) else {}
    jobs = _list(jobs_payload, "jobs")
    schedule = schedule_payload if isinstance(schedule_payload, dict) else {}
    cycles = _list(cycles_payload, "cycles")
    alerts = alerts_payload if isinstance(alerts_payload, dict) else {}
    trigger_read_model = _dict(live.get("triggers"))
    recent_decisions = _list(trigger_read_model, "recent_decisions")

    events: list[dict[str, Any]] = []
    events.extend(_source_state_events(live))
    events.extend(_collection_job_events(jobs))
    events.extend(_trigger_decision_events(recent_decisions))
    events.extend(_trigger_report_job_events(jobs))
    events.extend(_daily_dispatch_events(schedule))
    events.extend(_scheduled_report_job_events(jobs))
    events.extend(_monitor_cycle_events(cycles))
    events.extend(_alert_archive_events(alerts))

    ordered = _newest_first(events)
    filtered = filter_live_history_events(ordered, filters or {})
    timeline = filtered[:LIVE_HISTORY_TIMELINE_LIMIT]
    trigger_rows = _trigger_rows(recent_decisions, jobs=jobs)[:LIVE_HISTORY_TRIGGER_LIMIT]
    trigger_report_artifacts = [row for row in trigger_rows if row.get("linked_report_ref")]
    alert_rows = _alert_rows(alerts)[:LIVE_HISTORY_ALERT_LIMIT]
    warnings = _bounded_unique(
        [
            *_strings(live.get("warnings")),
            *_strings(trigger_read_model.get("warnings")),
            *_strings(schedule.get("warnings")),
            *_strings(cycles_payload.get("warnings") if isinstance(cycles_payload, dict) else []),
            *_strings(alerts.get("warnings")),
        ]
    )
    errors = _bounded_unique(
        [
            *_strings(live.get("errors")),
            *_strings(trigger_read_model.get("errors")),
            *_strings(schedule.get("errors")),
            *_strings(cycles_payload.get("errors") if isinstance(cycles_payload, dict) else []),
            *_strings(alerts.get("errors")),
        ]
    )
    live_enabled = _dict(live.get("scheduler")).get("enabled") is True
    trigger_config = _dict(trigger_read_model.get("config"))
    trigger_configs = _list(trigger_config, "triggers")
    triggers_enabled = any(item.get("enabled") is True for item in trigger_configs)
    alert_counts = _alert_counts(alerts)
    return {
        "schema_version": 1,
        "artifact_type": LIVE_HISTORY_ARTIFACT,
        "status": _payload_status(live, schedule, cycles_payload, alerts),
        "summary": {
            "timeline_events": len(ordered),
            "visible_timeline_events": len(filtered),
            "trigger_decisions": len(recent_decisions),
            "trigger_created_jobs": sum(1 for row in trigger_rows if row.get("linked_job_id")),
            "trigger_report_artifacts": len(trigger_report_artifacts),
            "alert_records": int(alert_counts.get("records") or len(alert_rows) or 0),
            "scheduled_dispatches": len(_list(schedule, "dispatches")),
        },
        "filter_options": _filter_options(ordered, recent_decisions),
        "filters": _normalized_filters(filters or {}),
        "timeline": timeline,
        "trigger_decisions": trigger_rows,
        "trigger_report_artifacts": trigger_report_artifacts,
        "alert_archive": {
            "counts": alert_counts,
            "records": alert_rows,
            "status": alerts.get("status") or "missing",
        },
        "empty_states": {
            "live_disabled": not live_enabled,
            "triggers_disabled": not triggers_enabled,
            "no_live_history_yet": not ordered,
            "no_trigger_decisions_yet": not trigger_rows,
            "no_trigger_report_artifacts_yet": not trigger_report_artifacts,
            "no_alert_archive_records_yet": not alert_rows,
        },
        "omitted": {
            "full_raw_stores_embedded": False,
            "full_command_logs_embedded": False,
            "timeline_limit": LIVE_HISTORY_TIMELINE_LIMIT,
            "trigger_limit": LIVE_HISTORY_TRIGGER_LIMIT,
            "alert_limit": LIVE_HISTORY_ALERT_LIMIT,
        },
        "warnings": warnings,
        "errors": errors,
    }


def filter_live_history_events(events: list[dict[str, Any]], filters: dict[str, Any]) -> list[dict[str, Any]]:
    normalized = _normalized_filters(filters)
    start = _parse_time(normalized.get("start"))
    end = _parse_time(normalized.get("end"))
    output: list[dict[str, Any]] = []
    for event in events:
        if start is not None or end is not None:
            timestamp = _parse_time(event.get("timestamp"))
            if timestamp is None:
                continue
            if start is not None and timestamp < start:
                continue
            if end is not None and timestamp > end:
                continue
        if normalized["data_type"] != "all" and event.get("data_type") != normalized["data_type"]:
            continue
        if normalized["trigger_id"] != "all" and event.get("trigger_id") != normalized["trigger_id"]:
            continue
        if normalized["event_kind"] != "all" and event.get("event_kind") != normalized["event_kind"]:
            continue
        if normalized["status"] != "all" and event.get("status") != normalized["status"]:
            continue
        if normalized["report_linked_only"] and not _event_has_report_link(event):
            continue
        if normalized["attention_only"] and str(event.get("status") or "") not in ATTENTION_STATUSES:
            continue
        output.append(event)
    return output


def _source_state_events(live: dict[str, Any]) -> list[dict[str, Any]]:
    events = []
    for item in _list(live, "collections"):
        status = _collection_status(item)
        target = _dict(item.get("target"))
        event = _event(
            event_id=f"source_state:{item.get('target_key') or item.get('data_type')}",
            timestamp=item.get("updated_at") or item.get("last_attempt_at") or item.get("last_success_at"),
            event_kind="source_state",
            status=status,
            title=f"Source state {item.get('target_key') or item.get('data_type') or 'target'}",
            summary=_first_text(item.get("errors")) or _first_text(item.get("warnings")) or "Latest collection target state.",
            data_type=item.get("data_type"),
            job_id=item.get("latest_job_id"),
            artifact_refs=_strings(item.get("source_refs")),
            warnings=_strings(item.get("warnings")),
            errors=_strings(item.get("errors")),
            metadata={
                "target": target,
                "enabled": item.get("enabled"),
                "last_attempt_at": item.get("last_attempt_at"),
                "last_success_at": item.get("last_success_at"),
                "next_attempt_at": item.get("next_attempt_at"),
                "latest_job_status": item.get("latest_job_status"),
                "latest_terminal_job_id": item.get("latest_terminal_job_id"),
                "latest_terminal_status": item.get("latest_terminal_status"),
                "consecutive_failures": item.get("consecutive_failures"),
            },
        )
        events.append(event)
    return events


def _collection_job_events(jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    events = []
    for job in jobs:
        requester = _dict(job.get("requester"))
        if requester.get("source") != "live_scheduler":
            continue
        refs = _job_refs(job)
        events.append(
            _event(
                event_id=f"collection_job:{job.get('job_id')}",
                timestamp=job.get("finished_at") or job.get("started_at") or job.get("created_at"),
                event_kind="collection_job",
                status=job.get("status"),
                title=f"Collection job {requester.get('target_key') or requester.get('data_type') or job.get('job_id')}",
                summary=_job_summary(job),
                data_type=requester.get("data_type"),
                job_id=job.get("job_id"),
                artifact_refs=refs,
                warnings=_strings(job.get("warnings")),
                errors=_strings(job.get("errors")),
                metadata={
                    "intent": job.get("intent"),
                    "requested_by": job.get("requested_by"),
                    "target_key": requester.get("target_key"),
                    "created_at": job.get("created_at"),
                    "started_at": job.get("started_at"),
                    "finished_at": job.get("finished_at"),
                    "params": _bounded_mapping(_dict(job.get("params"))),
                },
            )
        )
    return events


def _trigger_decision_events(decisions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    events = []
    for decision in decisions:
        events.append(
            _event(
                event_id=f"trigger_decision:{decision.get('decision_id')}",
                timestamp=decision.get("evaluated_at") or decision.get("updated_at"),
                event_kind="trigger_decision",
                status=decision.get("status"),
                title=f"Trigger decision {decision.get('trigger_id') or 'trigger'}",
                summary=_reason_summary(decision),
                data_type=_first_text(decision.get("source_data_types")),
                trigger_id=decision.get("trigger_id"),
                job_id=decision.get("linked_report_job_id"),
                run_id=decision.get("linked_run_id"),
                report_ref=decision.get("linked_report_ref"),
                artifact_refs=_strings(decision.get("source_refs")),
                warnings=_strings(decision.get("warnings")),
                errors=_strings(decision.get("errors")),
                metadata={
                    "decision_id": decision.get("decision_id"),
                    "reason_codes": _strings(decision.get("reason_codes")),
                    "threshold_params": _bounded_mapping(_dict(decision.get("threshold_params"))),
                    "matched_evidence": _bounded_mapping(_dict(decision.get("matched_evidence"))),
                    "cooldown_until": decision.get("cooldown_until"),
                    "linked_collection_job_ids": _strings(decision.get("linked_collection_job_ids")),
                    "linked_report_job_status": decision.get("linked_report_job_status"),
                },
            )
        )
    return events


def _trigger_report_job_events(jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    events = []
    for job in jobs:
        requester = _dict(job.get("requester"))
        if requester.get("source") != "live_trigger":
            continue
        refs = _job_refs(job)
        result_refs = _dict(job.get("result_refs"))
        report_ref = result_refs.get("report")
        has_report = isinstance(report_ref, str) and bool(report_ref)
        event_kind = "trigger_report_job" if has_report else "trigger_run_job"
        title = "Trigger-created report job" if has_report else "Trigger-created run job"
        events.append(
            _event(
                event_id=f"{event_kind}:{job.get('job_id')}",
                timestamp=job.get("finished_at") or job.get("started_at") or job.get("created_at"),
                event_kind=event_kind,
                status=job.get("status"),
                title=f"{title} {requester.get('trigger_id') or job.get('job_id')}",
                summary=_job_summary(job),
                trigger_id=requester.get("trigger_id"),
                job_id=job.get("job_id"),
                run_id=result_refs.get("run_id"),
                report_ref=report_ref,
                artifact_refs=refs,
                warnings=_strings(job.get("warnings")),
                errors=_strings(job.get("errors")),
                metadata={
                    "intent": job.get("intent"),
                    "decision_id": requester.get("decision_id"),
                    "trigger_revision": requester.get("trigger_revision"),
                    "created_at": job.get("created_at"),
                    "started_at": job.get("started_at"),
                    "finished_at": job.get("finished_at"),
                    "artifact_state": "available" if refs else "missing",
                },
            )
        )
    return events


def _daily_dispatch_events(schedule: dict[str, Any]) -> list[dict[str, Any]]:
    events = []
    for dispatch in _list(schedule, "dispatches"):
        refs = [value for value in (dispatch.get("run_ref"), dispatch.get("report_ref")) if isinstance(value, str) and value]
        events.append(
            _event(
                event_id=f"scheduled_dispatch:{dispatch.get('scheduled_for')}:{dispatch.get('job_id') or 'no-job'}",
                timestamp=dispatch.get("completed_at") or dispatch.get("claimed_at") or dispatch.get("scheduled_for"),
                event_kind="scheduled_report_dispatch",
                status=dispatch.get("terminal_status") or dispatch.get("status"),
                title=f"Scheduled daily report {dispatch.get('dispatch_kind') or 'dispatch'}",
                summary=_first_text(dispatch.get("errors")) or _first_text(dispatch.get("warnings")) or "Daily report schedule dispatch.",
                job_id=dispatch.get("job_id"),
                run_id=dispatch.get("run_ref"),
                report_ref=dispatch.get("report_ref"),
                artifact_refs=refs,
                warnings=_strings(dispatch.get("warnings")),
                errors=_strings(dispatch.get("errors")),
                metadata={
                    "report_kind": "scheduled_daily",
                    "scheduled_for": dispatch.get("scheduled_for"),
                    "dispatch_kind": dispatch.get("dispatch_kind"),
                    "claimed_at": dispatch.get("claimed_at"),
                    "completed_at": dispatch.get("completed_at"),
                },
            )
        )
    return events


def _scheduled_report_job_events(jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    events = []
    for job in jobs:
        requester = _dict(job.get("requester"))
        if requester.get("source") != "daily_report_schedule":
            continue
        result_refs = _dict(job.get("result_refs"))
        refs = _job_refs(job)
        events.append(
            _event(
                event_id=f"scheduled_report_job:{job.get('job_id')}",
                timestamp=job.get("finished_at") or job.get("started_at") or job.get("created_at"),
                event_kind="scheduled_report_job",
                status=job.get("status"),
                title=f"Scheduled daily report job {job.get('job_id')}",
                summary=_job_summary(job),
                job_id=job.get("job_id"),
                run_id=result_refs.get("run_id"),
                report_ref=result_refs.get("report"),
                artifact_refs=refs,
                warnings=_strings(job.get("warnings")),
                errors=_strings(job.get("errors")),
                metadata={
                    "report_kind": "scheduled_daily",
                    "dispatch_kind": requester.get("dispatch_kind"),
                    "schedule_id": requester.get("schedule_id"),
                    "intent": job.get("intent"),
                    "artifact_state": "available" if refs else "missing",
                },
            )
        )
    return events


def _monitor_cycle_events(cycles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    events = []
    for cycle in cycles:
        refs = [value for value in (cycle.get("run_manifest"), cycle.get("cycle_manifest")) if isinstance(value, str) and value]
        events.append(
            _event(
                event_id=f"monitor_cycle:{cycle.get('cycle_id')}",
                timestamp=cycle.get("finished_at") or cycle.get("started_at"),
                event_kind="monitor_cycle",
                status=cycle.get("status"),
                title=f"Historical monitor cycle {cycle.get('cycle_id') or ''}".strip(),
                summary=_first_text(cycle.get("errors"))
                or _first_text(cycle.get("warnings"))
                or f"Run {cycle.get('run_id') or 'n/a'}",
                run_id=cycle.get("run_id"),
                artifact_refs=refs,
                warnings=_strings(cycle.get("warnings")),
                errors=_strings(cycle.get("errors")),
                metadata={
                    "cycle_id": cycle.get("cycle_id"),
                    "cycle_mode": cycle.get("cycle_mode"),
                    "trigger_source": cycle.get("trigger_source"),
                    "alert_archive": _bounded_mapping(_dict(cycle.get("alert_archive"))),
                },
            )
        )
    return events


def _alert_archive_events(alerts: dict[str, Any]) -> list[dict[str, Any]]:
    events = []
    for record in _alert_records(alerts):
        source_run = _dict(record.get("source_run"))
        refs = _strings(record.get("source_artifacts"))
        run_id = source_run.get("run_id") if isinstance(source_run.get("run_id"), str) else record.get("source_run_id")
        report_ref = record.get("source_report_ref")
        events.append(
            _event(
                event_id=f"alert_record:{record.get('record_id')}",
                timestamp=record.get("created_at"),
                event_kind="alert_archive_record",
                status=record.get("status"),
                title=f"Alert archive {record.get('alert_key') or record.get('record_id') or 'record'}",
                summary=_suppression_summary(record) or record.get("attention_decision") or "Alert archive record.",
                data_type=record.get("data_type"),
                job_id=record.get("job_id"),
                run_id=run_id,
                report_ref=report_ref,
                artifact_refs=refs,
                warnings=_strings(record.get("warnings")),
                errors=_strings(record.get("errors")),
                metadata={
                    "record_id": record.get("record_id"),
                    "cycle_id": record.get("cycle_id"),
                    "decision_id": record.get("decision_id"),
                    "symbol": record.get("symbol"),
                    "timeframe": record.get("timeframe"),
                    "priority": record.get("priority"),
                    "attention_decision": record.get("attention_decision"),
                    "requires_user_attention": record.get("requires_user_attention"),
                    "suppression_reasons": _strings(record.get("suppression_reasons")),
                    "cooldown_until": record.get("cooldown_until"),
                },
            )
        )
    return events


def _trigger_rows(decisions: list[dict[str, Any]], *, jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for decision in decisions:
        job_id = decision.get("linked_report_job_id")
        job = _job_by_id(jobs, str(job_id)) if isinstance(job_id, str) else None
        result_refs = _dict(job.get("result_refs") if isinstance(job, dict) else {})
        report_ref = decision.get("linked_report_ref") or result_refs.get("report")
        run_id = decision.get("linked_run_id") or result_refs.get("run_id")
        rows.append(
            {
                "decision_id": decision.get("decision_id"),
                "trigger_id": decision.get("trigger_id"),
                "status": decision.get("status"),
                "evaluated_at": decision.get("evaluated_at"),
                "reason_codes": _strings(decision.get("reason_codes")),
                "reason_summary": _reason_summary(decision),
                "threshold_params": _bounded_mapping(_dict(decision.get("threshold_params"))),
                "matched_evidence": _bounded_mapping(_dict(decision.get("matched_evidence"))),
                "evidence_summary": _evidence_summary(decision.get("matched_evidence")),
                "cooldown_until": decision.get("cooldown_until"),
                "linked_collection_job_ids": _strings(decision.get("linked_collection_job_ids")),
                "linked_job_id": job_id,
                "job_intent": job.get("intent") if isinstance(job, dict) else None,
                "linked_run_id": run_id,
                "linked_report_ref": report_ref,
                "terminal_job_status": decision.get("linked_report_job_status") or (job.get("status") if isinstance(job, dict) else None),
                "artifact_state": "available" if report_ref else "missing",
                "warnings": _strings(decision.get("warnings")),
                "errors": _strings(decision.get("errors")),
            }
        )
    return _newest_first(rows, timestamp_key="evaluated_at")


def _alert_rows(alerts: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for record in _alert_records(alerts):
        source_run = _dict(record.get("source_run"))
        rows.append(
            {
                "record_id": record.get("record_id"),
                "created_at": record.get("created_at"),
                "status": record.get("status"),
                "alert_key": record.get("alert_key"),
                "decision_id": record.get("decision_id"),
                "symbol": record.get("symbol"),
                "timeframe": record.get("timeframe"),
                "priority": record.get("priority"),
                "attention_decision": record.get("attention_decision"),
                "requires_user_attention": record.get("requires_user_attention"),
                "suppression_reasons": _strings(record.get("suppression_reasons")),
                "cooldown_until": record.get("cooldown_until"),
                "source_run_id": source_run.get("run_id") or record.get("source_run_id"),
                "source_report_ref": record.get("source_report_ref"),
                "source_artifacts": _strings(record.get("source_artifacts")),
            }
        )
    return _newest_first(rows, timestamp_key="created_at")


def _event(
    *,
    event_id: str,
    timestamp: Any,
    event_kind: str,
    status: Any,
    title: str,
    summary: Any,
    data_type: Any = None,
    trigger_id: Any = None,
    job_id: Any = None,
    run_id: Any = None,
    report_ref: Any = None,
    artifact_refs: list[str] | None = None,
    warnings: list[str] | None = None,
    errors: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    refs = _bounded_unique([*list(artifact_refs or []), *_strings(report_ref), *_strings(run_id)])
    errors_list = list(errors or [])
    warnings_list = list(warnings or [])
    normalized_status = str(status or "unknown")
    degraded_ref = _reference_state(report_ref, refs)
    if degraded_ref == "missing" and event_kind in {"trigger_report_job", "scheduled_report_job"}:
        if normalized_status == "succeeded":
            warnings_list = _bounded_unique([*warnings_list, "linked report artifact ref is missing."])
            normalized_status = "degraded"
    return {
        "event_id": event_id,
        "timestamp": timestamp if isinstance(timestamp, str) and timestamp else None,
        "event_kind": event_kind,
        "status": normalized_status,
        "title": title,
        "summary": str(summary or "n/a"),
        "data_type": data_type if isinstance(data_type, str) and data_type else None,
        "trigger_id": trigger_id if isinstance(trigger_id, str) and trigger_id else None,
        "job_id": job_id if isinstance(job_id, str) and job_id else None,
        "run_id": run_id if isinstance(run_id, str) and run_id else None,
        "report_ref": report_ref if isinstance(report_ref, str) and report_ref else None,
        "artifact_refs": refs,
        "artifact_state": degraded_ref,
        "warnings": warnings_list[:10],
        "errors": errors_list[:10],
        "detail": {
            "metadata": _bounded_mapping(metadata or {}),
            "source_refs": refs[:12],
            "warnings": warnings_list[:10],
            "errors": errors_list[:10],
        },
    }


def _filter_options(events: list[dict[str, Any]], decisions: list[dict[str, Any]]) -> dict[str, list[str]]:
    return {
        "data_types": sorted({str(item.get("data_type")) for item in events if item.get("data_type")}),
        "trigger_ids": sorted(
            {
                *{str(item.get("trigger_id")) for item in events if item.get("trigger_id")},
                *{str(item.get("trigger_id")) for item in decisions if item.get("trigger_id")},
            }
        ),
        "event_kinds": sorted({str(item.get("event_kind")) for item in events if item.get("event_kind")}),
        "statuses": sorted({str(item.get("status")) for item in events if item.get("status")}),
    }


def _normalized_filters(filters: dict[str, Any]) -> dict[str, Any]:
    return {
        "start": filters.get("start") if isinstance(filters.get("start"), str) else "",
        "end": filters.get("end") if isinstance(filters.get("end"), str) else "",
        "data_type": str(filters.get("data_type") or "all"),
        "trigger_id": str(filters.get("trigger_id") or "all"),
        "event_kind": str(filters.get("event_kind") or "all"),
        "status": str(filters.get("status") or "all"),
        "report_linked_only": filters.get("report_linked_only") is True,
        "attention_only": filters.get("attention_only") is True,
    }


def _payload_status(*payloads: dict[str, Any] | None) -> str:
    statuses = [str(payload.get("status") or "") for payload in payloads if isinstance(payload, dict)]
    if any(status == "failed" for status in statuses):
        return "failed"
    if any(status in {"degraded", "partial"} for status in statuses):
        return "degraded"
    if any(status == "available" for status in statuses):
        return "available"
    if any(status == "disabled" for status in statuses):
        return "disabled"
    return "missing"


def _collection_status(item: dict[str, Any]) -> str:
    if item.get("enabled") is not True:
        return "disabled"
    terminal_status = str(item.get("latest_terminal_status") or "")
    latest_status = str(item.get("latest_job_status") or "")
    if _strings(item.get("errors")) or terminal_status in {"failed", "blocked"}:
        return "failed"
    if latest_status in {"queued", "running", "cancel_requested"}:
        return latest_status
    if terminal_status in {"cancelled", "unsupported", "not_started"}:
        return terminal_status
    if _strings(item.get("warnings")):
        return "warning"
    if item.get("last_success_at"):
        return "available"
    if item.get("latest_job_id"):
        return "pending"
    return "missing"


def _reason_summary(decision: dict[str, Any]) -> str:
    reasons = _strings(decision.get("reason_codes"))
    if reasons:
        return ", ".join(reasons[:4])
    return _evidence_summary(decision.get("matched_evidence")) or "No reason recorded."


def _evidence_summary(value: Any) -> str:
    data = _dict(value)
    if not data:
        return "No matched evidence."
    candidates = []
    for key in ("record_count", "matched_count", "failed_target_count", "symbol", "timeframe", "data_type", "latest_close"):
        item = data.get(key)
        if item is not None:
            candidates.append(f"{key}: {item}")
    if not candidates and isinstance(data.get("records"), list):
        candidates.append(f"records: {len(data['records'])}")
    return ", ".join(candidates[:5]) or "Matched evidence recorded."


def _suppression_summary(record: dict[str, Any]) -> str:
    reasons = _strings(record.get("suppression_reasons"))
    if reasons:
        return ", ".join(reasons[:4])
    status = str(record.get("status") or "")
    if status.startswith("suppressed"):
        return status
    return ""


def _job_summary(job: dict[str, Any]) -> str:
    return _first_text(job.get("errors")) or _first_text(job.get("warnings")) or str(job.get("intent") or "job")


def _job_refs(job: dict[str, Any]) -> list[str]:
    refs = []
    result_refs = _dict(job.get("result_refs"))
    refs.extend(str(value) for value in result_refs.values() if isinstance(value, str) and value)
    refs.extend(_strings(job.get("source_artifacts")))
    return _bounded_unique(refs)


def _alert_records(alerts: dict[str, Any]) -> list[dict[str, Any]]:
    archive = _dict(alerts.get("alert_archive"))
    fields = _dict(archive.get("fields"))
    records = fields.get("sample_records")
    return [item for item in records if isinstance(item, dict)] if isinstance(records, list) else []


def _alert_counts(alerts: dict[str, Any]) -> dict[str, Any]:
    archive = _dict(alerts.get("alert_archive"))
    fields = _dict(archive.get("fields"))
    counts = fields.get("counts") or archive.get("counts")
    return dict(counts) if isinstance(counts, dict) else {}


def _event_has_report_link(event: dict[str, Any]) -> bool:
    return isinstance(event.get("report_ref"), str) and bool(event.get("report_ref"))


def _reference_state(report_ref: Any, refs: list[str]) -> str:
    if isinstance(report_ref, str) and report_ref:
        return "available"
    return "available" if refs else "missing"


def _job_by_id(jobs: list[dict[str, Any]], job_id: str) -> dict[str, Any] | None:
    for job in jobs:
        if job.get("job_id") == job_id:
            return job
    return None


def _list(value: Any, key: str) -> list[Any]:
    if isinstance(value, dict) and isinstance(value.get(key), list):
        return [item for item in value[key] if isinstance(item, dict)]
    return []


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _strings(value: Any) -> list[str]:
    if isinstance(value, str) and value:
        return [value]
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, (str, int, float)) and str(item)]


def _first_text(value: Any) -> str | None:
    values = _strings(value)
    return values[0] if values else None


def _newest_first(items: list[dict[str, Any]], *, timestamp_key: str = "timestamp") -> list[dict[str, Any]]:
    return sorted(
        items,
        key=lambda item: (_timestamp_seconds(item.get(timestamp_key)), str(item.get("event_id") or item.get("decision_id") or item.get("record_id") or "")),
        reverse=True,
    )


def _timestamp_seconds(value: Any) -> float:
    parsed = _parse_time(value)
    return parsed.timestamp() if parsed is not None else 0.0


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _bounded_mapping(value: dict[str, Any], *, limit: int = 24) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key in sorted(value):
        item = value[key]
        if isinstance(item, dict):
            output[str(key)] = _bounded_mapping(item, limit=limit)
        elif isinstance(item, list):
            output[str(key)] = [
                _bounded_mapping(entry, limit=limit) if isinstance(entry, dict) else entry
                for entry in item[:12]
                if isinstance(entry, (str, int, float, bool, dict)) or entry is None
            ]
        elif isinstance(item, (str, int, float, bool)) or item is None:
            output[str(key)] = item
        if len(output) >= limit:
            break
    return output


def _bounded_unique(values: list[str], *, limit: int = 40) -> list[str]:
    output: list[str] = []
    seen = set()
    for value in values:
        if not isinstance(value, str) or not value or value in seen:
            continue
        seen.add(value)
        output.append(value)
        if len(output) >= limit:
            break
    return output
