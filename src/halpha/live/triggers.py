from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Protocol

from halpha.data.event_like_query import EventLikeQueryError, query_event_like_records
from halpha.live.config import LiveTriggerConfig, load_live_settings
from halpha.live.contracts import (
    LIVE_REPORT_TRIGGER_JOB_INTENTS,
    LIVE_TRIGGER_IDS,
    LIVE_TRIGGER_PRIORITY_LEVELS,
    LIVE_TRIGGER_REVISION,
)
from halpha.live.state_store import LiveTriggerStateRepository
from halpha.market.ohlcv_query import OHLCVQueryError, query_latest_ohlcv_records
from halpha.runtime.command_job_store import JOB_TERMINAL_STATUSES, JOB_TRANSIENT_STATUSES
from halpha.storage import display_path, resolve_runtime_path


LIVE_TRIGGER_SOURCE = "live_trigger"
LIVE_TRIGGER_EVALUATION_ARTIFACT = "live_trigger_evaluation"
LIVE_TRIGGER_READ_MODEL_ARTIFACT = "dashboard_live_triggers"
LIVE_TRIGGER_RECENT_LIMIT = 50
LIVE_TRIGGER_WINDOW_SECONDS = 3600
LIVE_TRIGGER_QUERY_LIMIT = 50


class _JobManager(Protocol):
    def create_job(self, request: dict[str, Any]) -> dict[str, Any]:
        ...

    def list_jobs(self, *, limit: int = 100) -> dict[str, Any]:
        ...


@dataclass(frozen=True)
class _EvidenceResult:
    status: str
    source_data_types: list[str]
    source_refs: list[str]
    reason_codes: list[str]
    matched_evidence: dict[str, Any]
    warnings: list[str]
    errors: list[str]


class LiveTriggerEvaluator:
    def __init__(
        self,
        config: dict[str, Any],
        *,
        config_path: Path,
        job_manager: _JobManager,
        state_repository: LiveTriggerStateRepository | None = None,
        now: datetime | None = None,
    ) -> None:
        self.config = config
        self.config_path = Path(config_path)
        self.job_manager = job_manager
        self.state_repository = state_repository or LiveTriggerStateRepository(self.config_path)
        self.now = _utc_datetime(now)

    def evaluate(self, *, tick_id: str | None = None, live_read_model: dict[str, Any] | None = None) -> dict[str, Any]:
        settings = load_live_settings(self.config)
        now_text = _format_utc(self.now)
        jobs = self._all_jobs(limit=250)
        self._reconcile_recent_decisions(jobs=jobs, updated_at=now_text)
        decisions: list[dict[str, Any]] = []
        warnings: list[str] = []
        errors: list[str] = []
        for trigger_id in LIVE_TRIGGER_IDS:
            trigger = settings.reports.triggers[trigger_id]
            decision = self._evaluate_one(
                trigger,
                tick_id=tick_id,
                live_read_model=live_read_model or {},
                jobs=jobs,
                now_text=now_text,
            )
            persisted = self.state_repository.upsert_decision(decision)
            decisions.append(persisted)
            warnings.extend(_strings(persisted.get("warnings")))
            errors.extend(_strings(persisted.get("errors")))
        return {
            "schema_version": 1,
            "artifact_type": LIVE_TRIGGER_EVALUATION_ARTIFACT,
            "status": "available" if not errors else "degraded",
            "evaluated_at": now_text,
            "trigger_revision": LIVE_TRIGGER_REVISION,
            "decisions": decisions,
            "warnings": _bounded_unique(warnings),
            "errors": _bounded_unique(errors),
        }

    def read_model(self, *, live_read_model: dict[str, Any] | None = None) -> dict[str, Any]:
        settings = load_live_settings(self.config)
        jobs = self._all_jobs(limit=250)
        now_text = _format_utc(self.now)
        self._reconcile_recent_decisions(jobs=jobs, updated_at=now_text)
        recent_decisions = self.state_repository.list_decisions(limit=LIVE_TRIGGER_RECENT_LIMIT)
        latest = self.state_repository.latest_decisions()
        cooldowns = self.state_repository.list_cooldowns()
        active_jobs = [job for job in jobs if _is_active_trigger_job(job)]
        errors: list[str] = []
        warnings: list[str] = []
        for decision in recent_decisions:
            errors.extend(_strings(decision.get("errors")))
            warnings.extend(_strings(decision.get("warnings")))
        config_summary = [
            {
                "trigger_id": trigger_id,
                "enabled": trigger.enabled,
                "job_intent": trigger.job_intent,
                "cooldown_seconds": trigger.cooldown_seconds,
                "threshold_params": _threshold_params(trigger),
                "codex_authorization": _authorization_summary(
                    trigger,
                    config=self.config,
                    config_path=self.config_path,
                ),
            }
            for trigger_id, trigger in settings.reports.triggers.items()
        ]
        return {
            "schema_version": 1,
            "artifact_type": LIVE_TRIGGER_READ_MODEL_ARTIFACT,
            "status": "available" if not errors else "degraded",
            "trigger_revision": LIVE_TRIGGER_REVISION,
            "config": {
                "enabled": settings.enabled,
                "triggers": config_summary,
            },
            "latest_decisions": latest,
            "recent_decisions": recent_decisions,
            "active_trigger_report_jobs": active_jobs,
            "cooldowns": cooldowns,
            "warnings": _bounded_unique(warnings),
            "errors": _bounded_unique(errors),
            "omitted": {
                "full_live_history_embedded": False,
                "full_source_records_embedded": False,
                "recent_decision_limit": LIVE_TRIGGER_RECENT_LIMIT,
            },
            **({"live_summary": _bounded_live_summary(live_read_model)} if live_read_model else {}),
        }

    def _evaluate_one(
        self,
        trigger: LiveTriggerConfig,
        *,
        tick_id: str | None,
        live_read_model: dict[str, Any],
        jobs: list[dict[str, Any]],
        now_text: str,
    ) -> dict[str, Any]:
        decision = _base_decision(trigger, evaluated_at=now_text)
        if not trigger.enabled:
            return {
                **decision,
                "status": "skipped_disabled",
                "reason_codes": ["trigger_disabled"],
            }
        if trigger.job_intent not in LIVE_REPORT_TRIGGER_JOB_INTENTS:
            return {
                **decision,
                "status": "failed",
                "reason_codes": ["invalid_job_intent"],
                "errors": [f"{trigger.trigger_id}.job_intent is not supported."],
            }
        evidence = self._evidence(trigger, live_read_model=live_read_model)
        decision.update(
            {
                "source_data_types": evidence.source_data_types,
                "source_refs": evidence.source_refs,
                "reason_codes": evidence.reason_codes,
                "matched_evidence": evidence.matched_evidence,
                "linked_collection_job_ids": _strings(evidence.matched_evidence.get("linked_collection_job_ids")),
                "warnings": evidence.warnings,
                "errors": evidence.errors,
            }
        )
        if evidence.status != "matched":
            return {**decision, "status": evidence.status}
        cooldown = self.state_repository.get_cooldown(trigger.trigger_id)
        cooldown_until = _parse_utc(_dict(cooldown).get("cooldown_until"))
        if cooldown_until is not None and cooldown_until > self.now:
            return {
                **decision,
                "status": "suppressed_cooldown",
                "cooldown_until": _format_utc(cooldown_until),
                "reason_codes": _bounded_unique([*evidence.reason_codes, "cooldown_active"]),
            }
        duplicate = _active_trigger_job(jobs, trigger_id=trigger.trigger_id)
        if duplicate is not None:
            return {
                **decision,
                "status": "suppressed_cooldown",
                "linked_report_job_id": duplicate.get("job_id"),
                "linked_report_job_status": duplicate.get("status"),
                "reason_codes": _bounded_unique([*evidence.reason_codes, "equivalent_active_report_job"]),
            }
        if trigger.job_intent == "run" and not _trigger_codex_authorization_valid(
            trigger,
            config=self.config,
            config_path=self.config_path,
        ):
            return {
                **decision,
                "status": "blocked_authorization",
                "reason_codes": _bounded_unique([*evidence.reason_codes, "missing_live_trigger_codex_authorization"]),
                "errors": ["Codex-capable Live trigger report dispatch requires valid persisted authorization."],
            }
        return self._create_report_job(decision, trigger, tick_id=tick_id, now_text=now_text)

    def _create_report_job(
        self,
        decision: dict[str, Any],
        trigger: LiveTriggerConfig,
        *,
        tick_id: str | None,
        now_text: str,
    ) -> dict[str, Any]:
        params = {"confirm_codex": True} if trigger.job_intent == "run" else {}
        request = {
            "intent": trigger.job_intent,
            "params": params,
            "requested_by": "Core",
            "requester": {
                "source": LIVE_TRIGGER_SOURCE,
                "tick_id": tick_id,
                "trigger_id": trigger.trigger_id,
                "trigger_revision": LIVE_TRIGGER_REVISION,
                "decision_id": decision["decision_id"],
            },
        }
        try:
            job = self.job_manager.create_job(request)
        except Exception as exc:
            return {
                **decision,
                "status": "failed",
                "reason_codes": _bounded_unique([*_strings(decision.get("reason_codes")), "report_job_creation_failed"]),
                "errors": [str(exc) or "Live trigger report job could not be created."],
            }
        job_status = str(job.get("status") or "unknown")
        updated = {
            **decision,
            "status": "triggered" if job_status not in {"failed", "blocked", "unsupported"} else "failed",
            "linked_report_job_id": job.get("job_id") if isinstance(job.get("job_id"), str) else None,
            "linked_report_job_status": job_status,
            "linked_run_id": _dict(job.get("result_refs")).get("run_id"),
            "linked_report_ref": _dict(job.get("result_refs")).get("report"),
            "warnings": _bounded_unique([*_strings(decision.get("warnings")), *_strings(job.get("warnings"))]),
            "errors": _bounded_unique([*_strings(decision.get("errors")), *_strings(job.get("errors"))]),
        }
        if updated["status"] == "triggered":
            cooldown_until = self.now + timedelta(seconds=trigger.cooldown_seconds or 1)
            updated["cooldown_until"] = _format_utc(cooldown_until)
            self.state_repository.upsert_cooldown(
                trigger_id=trigger.trigger_id,
                cooldown_until=updated["cooldown_until"],
                decision_id=updated["decision_id"],
                updated_at=now_text,
            )
        return updated

    def _evidence(self, trigger: LiveTriggerConfig, *, live_read_model: dict[str, Any]) -> _EvidenceResult:
        if trigger.trigger_id == "data_quality_degraded":
            return _data_quality_evidence(trigger, live_read_model=live_read_model, now=self.now)
        if trigger.trigger_id == "market_breakout":
            return self._event_evidence(
                trigger,
                data_type="market_anomaly",
                match=lambda record: _text_contains(record, ("breakout", "突破")) or _record_data_class(record)
                in {"market_breakout", "price_breakout", "breakout"},
            )
        if trigger.trigger_id == "major_market_move":
            return self._major_market_move_evidence(trigger)
        if trigger.trigger_id == "critical_news":
            return self._priority_event_evidence(trigger, data_type="text_event")
        if trigger.trigger_id == "scheduled_catalyst":
            return self._priority_event_evidence(
                trigger,
                data_type="macro_calendar",
                future=True,
                lookahead_seconds=trigger.lookahead_seconds or 7 * 24 * 3600,
            )
        if trigger.trigger_id == "derivatives_stress":
            return self._event_evidence(
                trigger,
                data_type="derivatives_market",
                match=_derivatives_stress_record,
            )
        return _insufficient(["unsupported_trigger"], source_data_types=[])

    def _event_evidence(
        self,
        trigger: LiveTriggerConfig,
        *,
        data_type: str,
        match: Any,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> _EvidenceResult:
        start = start or (self.now - timedelta(seconds=trigger.window_seconds or LIVE_TRIGGER_WINDOW_SECONDS))
        end = end or self.now
        try:
            result = query_event_like_records(
                self.config_path,
                data_type=data_type,
                start=start,
                end=end,
                as_of=self.now,
                limit=LIVE_TRIGGER_QUERY_LIMIT,
                sort_order="desc",
            )
        except EventLikeQueryError as exc:
            return _insufficient([f"{data_type}_query_failed"], source_data_types=[data_type], errors=[str(exc)])
        records = [record for record in _records(result) if match(record)]
        source_refs = _bounded_unique(_strings(result.get("source_artifacts")))
        warnings = _strings(result.get("warnings"))
        if records:
            return _matched(
                source_data_types=[data_type],
                source_refs=source_refs,
                reason_codes=[f"{trigger.trigger_id}_matched"],
                matched_evidence=_records_summary(records, data_type=data_type),
                warnings=warnings,
            )
        if int(result.get("history_row_count") or 0) <= 0 and not result.get("records"):
            return _insufficient([f"{data_type}_history_empty"], source_data_types=[data_type], source_refs=source_refs, warnings=warnings)
        return _no_match(
            [f"{trigger.trigger_id}_no_matching_records"],
            source_data_types=[data_type],
            source_refs=source_refs,
            warnings=warnings,
        )

    def _priority_event_evidence(
        self,
        trigger: LiveTriggerConfig,
        *,
        data_type: str,
        future: bool = False,
        lookahead_seconds: int | None = None,
    ) -> _EvidenceResult:
        start = self.now if future else self.now - timedelta(seconds=trigger.window_seconds or LIVE_TRIGGER_WINDOW_SECONDS)
        end = self.now + timedelta(seconds=lookahead_seconds or LIVE_TRIGGER_WINDOW_SECONDS) if future else self.now
        min_priority = trigger.min_priority or "high"
        try:
            result = query_event_like_records(
                self.config_path,
                data_type=data_type,
                start=start,
                end=end,
                as_of=self.now,
                limit=LIVE_TRIGGER_QUERY_LIMIT,
                sort_order="asc" if future else "desc",
            )
        except EventLikeQueryError as exc:
            return _insufficient([f"{data_type}_query_failed"], source_data_types=[data_type], errors=[str(exc)])
        records = _records(result)
        with_priority = [record for record in records if _record_priority(record) is not None]
        matches = [record for record in with_priority if _priority_at_least(_record_priority(record), min_priority)]
        source_refs = _bounded_unique(_strings(result.get("source_artifacts")))
        warnings = _strings(result.get("warnings"))
        if matches:
            return _matched(
                source_data_types=[data_type],
                source_refs=source_refs,
                reason_codes=[f"{trigger.trigger_id}_priority_matched"],
                matched_evidence=_records_summary(matches, data_type=data_type),
                warnings=warnings,
            )
        if records and not with_priority:
            return _insufficient(
                [f"{data_type}_priority_fields_missing"],
                source_data_types=[data_type],
                source_refs=source_refs,
                warnings=warnings,
            )
        if int(result.get("history_row_count") or 0) <= 0 and not records:
            return _insufficient([f"{data_type}_history_empty"], source_data_types=[data_type], source_refs=source_refs, warnings=warnings)
        return _no_match(
            [f"{trigger.trigger_id}_below_min_priority"],
            source_data_types=[data_type],
            source_refs=source_refs,
            warnings=warnings,
        )

    def _major_market_move_evidence(self, trigger: LiveTriggerConfig) -> _EvidenceResult:
        market = _dict(self.config.get("market"))
        ohlcv = _dict(market.get("ohlcv"))
        source = _first_text(ohlcv.get("sources")) or _optional_text(market.get("source"))
        symbol = _first_text(market.get("symbols"))
        timeframe = _first_text(ohlcv.get("timeframes"))
        if not source or not symbol or not timeframe:
            return _insufficient(["ohlcv_scope_not_configured"], source_data_types=["ohlcv"])
        storage_dir = resolve_runtime_path(str(ohlcv.get("storage_dir") or "data/market/ohlcv"), config_path=self.config_path)
        try:
            result = query_latest_ohlcv_records(
                storage_dir,
                source=source,
                symbol=symbol,
                timeframe=timeframe,
                lookback=2,
                as_of=self.now,
                config_path=self.config_path,
                limit=2,
            )
        except OHLCVQueryError as exc:
            return _insufficient(["ohlcv_query_failed"], source_data_types=["ohlcv"], errors=[str(exc)])
        records = _records(result)
        if len(records) < 2:
            return _insufficient(["ohlcv_requires_two_closed_candles"], source_data_types=["ohlcv"], source_refs=_strings(result.get("source_artifacts")))
        previous, latest = records[-2], records[-1]
        previous_close = _number(previous.get("close"))
        latest_close = _number(latest.get("close"))
        previous_volume = _number(previous.get("volume"))
        latest_volume = _number(latest.get("volume"))
        if previous_close is None or latest_close is None or previous_close == 0:
            return _insufficient(["ohlcv_close_fields_missing"], source_data_types=["ohlcv"])
        price_change_pct = ((latest_close - previous_close) / previous_close) * 100.0
        volume_change_pct = None
        if previous_volume is not None and latest_volume is not None and previous_volume > 0:
            volume_change_pct = ((latest_volume - previous_volume) / previous_volume) * 100.0
        price_threshold = trigger.price_change_pct or 5.0
        volume_threshold = trigger.volume_change_pct
        price_matched = abs(price_change_pct) >= price_threshold
        volume_matched = volume_threshold is not None and volume_change_pct is not None and abs(volume_change_pct) >= volume_threshold
        evidence = {
            "symbol": symbol,
            "timeframe": timeframe,
            "source": source,
            "latest_open_time": latest.get("open_time"),
            "previous_close": previous_close,
            "latest_close": latest_close,
            "price_change_pct": round(price_change_pct, 6),
            "volume_change_pct": round(volume_change_pct, 6) if volume_change_pct is not None else None,
        }
        if price_matched or volume_matched:
            reasons = ["major_market_move_price_change"] if price_matched else []
            if volume_matched:
                reasons.append("major_market_move_volume_change")
            return _matched(
                source_data_types=["ohlcv"],
                source_refs=_strings(result.get("source_artifacts")),
                reason_codes=reasons,
                matched_evidence=evidence,
                warnings=_strings(result.get("warnings")),
            )
        return _no_match(
            ["major_market_move_below_threshold"],
            source_data_types=["ohlcv"],
            source_refs=_strings(result.get("source_artifacts")),
            matched_evidence=evidence,
            warnings=_strings(result.get("warnings")),
        )

    def _all_jobs(self, *, limit: int) -> list[dict[str, Any]]:
        try:
            payload = self.job_manager.list_jobs(limit=limit)
        except Exception:
            return []
        jobs = payload.get("jobs") if isinstance(payload, dict) else []
        return [job for job in jobs if isinstance(job, dict)]

    def _reconcile_recent_decisions(self, *, jobs: list[dict[str, Any]], updated_at: str) -> None:
        for decision in self.state_repository.list_decisions(limit=LIVE_TRIGGER_RECENT_LIMIT):
            job_id = decision.get("linked_report_job_id")
            if not isinstance(job_id, str) or not job_id:
                continue
            job = _job_by_id(jobs, job_id) or self._get_job(job_id)
            if not isinstance(job, dict):
                continue
            status = str(job.get("status") or "unknown")
            refs = _dict(job.get("result_refs"))
            updated = {
                **decision,
                "linked_report_job_status": status,
                "linked_run_id": refs.get("run_id") if isinstance(refs.get("run_id"), str) else decision.get("linked_run_id"),
                "linked_report_ref": refs.get("report") if isinstance(refs.get("report"), str) else decision.get("linked_report_ref"),
                "warnings": _bounded_unique([*_strings(decision.get("warnings")), *_strings(job.get("warnings"))]),
                "errors": _bounded_unique([*_strings(decision.get("errors")), *_strings(job.get("errors"))]),
                "updated_at": updated_at,
            }
            if status in JOB_TERMINAL_STATUSES:
                self.state_repository.upsert_decision(updated)

    def _get_job(self, job_id: str) -> dict[str, Any] | None:
        get_job = getattr(self.job_manager, "get_job", None)
        if not callable(get_job):
            return None
        try:
            job = get_job(job_id)
        except Exception:
            return None
        return job if isinstance(job, dict) else None


def _base_decision(trigger: LiveTriggerConfig, *, evaluated_at: str) -> dict[str, Any]:
    decision_id = _decision_id(trigger.trigger_id, evaluated_at=evaluated_at)
    return {
        "schema_version": 1,
        "artifact_type": "live_trigger_decision",
        "decision_id": decision_id,
        "trigger_id": trigger.trigger_id,
        "trigger_revision": LIVE_TRIGGER_REVISION,
        "status": "skipped_no_match",
        "evaluated_at": evaluated_at,
        "source_data_types": [],
        "source_refs": [],
        "reason_codes": [],
        "threshold_params": _threshold_params(trigger),
        "matched_evidence": {},
        "cooldown_until": None,
        "linked_collection_job_ids": [],
        "linked_report_job_id": None,
        "linked_report_job_status": None,
        "linked_run_id": None,
        "linked_report_ref": None,
        "warnings": [],
        "errors": [],
        "updated_at": evaluated_at,
    }


def _data_quality_evidence(
    trigger: LiveTriggerConfig,
    *,
    live_read_model: dict[str, Any],
    now: datetime,
) -> _EvidenceResult:
    collections = [
        item
        for item in live_read_model.get("collections", [])
        if isinstance(item, dict) and item.get("enabled") is True
    ]
    if not collections:
        return _insufficient(["live_collection_state_missing"], source_data_types=["live"])
    failed_targets = [
        item
        for item in collections
        if _strings(item.get("errors")) or str(item.get("latest_terminal_status") or "") in {"failed", "unsupported", "blocked", "not_started"}
    ]
    stale_targets = []
    for item in collections:
        next_attempt = _parse_utc(item.get("next_attempt_at"))
        if next_attempt is None or next_attempt > now:
            continue
        if str(item.get("latest_job_status") or "") in JOB_TRANSIENT_STATUSES:
            continue
        stale_targets.append(item)
    min_failed = trigger.min_failed_targets or 1
    min_stale = trigger.min_stale_targets or 1
    matched = len(failed_targets) >= min_failed or len(stale_targets) >= min_stale
    evidence = {
        "failed_targets": [_collection_target_summary(item) for item in failed_targets[:10]],
        "stale_targets": [_collection_target_summary(item) for item in stale_targets[:10]],
        "failed_target_count": len(failed_targets),
        "stale_target_count": len(stale_targets),
    }
    linked_job_ids = _bounded_unique(
        [
            str(item.get("latest_job_id"))
            for item in [*failed_targets, *stale_targets]
            if isinstance(item.get("latest_job_id"), str) and item.get("latest_job_id")
        ]
    )
    if matched:
        reasons = []
        if len(failed_targets) >= min_failed:
            reasons.append("data_quality_failed_targets")
        if len(stale_targets) >= min_stale:
            reasons.append("data_quality_stale_targets")
        matched_result = _matched(
            source_data_types=["live"],
            source_refs=[],
            reason_codes=reasons,
            matched_evidence=evidence,
        )
        matched_result.matched_evidence["linked_collection_job_ids"] = linked_job_ids
        return matched_result
    return _no_match(
        ["data_quality_within_thresholds"],
        source_data_types=["live"],
        matched_evidence=evidence,
    )


def _matched(
    *,
    source_data_types: list[str],
    source_refs: list[str],
    reason_codes: list[str],
    matched_evidence: dict[str, Any],
    warnings: list[str] | None = None,
) -> _EvidenceResult:
    return _EvidenceResult(
        status="matched",
        source_data_types=source_data_types,
        source_refs=_bounded_unique(source_refs),
        reason_codes=_bounded_unique(reason_codes),
        matched_evidence=matched_evidence,
        warnings=_bounded_unique(warnings or []),
        errors=[],
    )


def _no_match(
    reason_codes: list[str],
    *,
    source_data_types: list[str],
    source_refs: list[str] | None = None,
    matched_evidence: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
) -> _EvidenceResult:
    return _EvidenceResult(
        status="skipped_no_match",
        source_data_types=source_data_types,
        source_refs=_bounded_unique(source_refs or []),
        reason_codes=_bounded_unique(reason_codes),
        matched_evidence=matched_evidence or {},
        warnings=_bounded_unique(warnings or []),
        errors=[],
    )


def _insufficient(
    reason_codes: list[str],
    *,
    source_data_types: list[str],
    source_refs: list[str] | None = None,
    warnings: list[str] | None = None,
    errors: list[str] | None = None,
) -> _EvidenceResult:
    return _EvidenceResult(
        status="skipped_insufficient_evidence",
        source_data_types=source_data_types,
        source_refs=_bounded_unique(source_refs or []),
        reason_codes=_bounded_unique(reason_codes),
        matched_evidence={},
        warnings=_bounded_unique(warnings or []),
        errors=_bounded_unique(errors or []),
    )


def _threshold_params(trigger: LiveTriggerConfig) -> dict[str, Any]:
    return {
        "cooldown_seconds": trigger.cooldown_seconds,
        "job_intent": trigger.job_intent,
        "min_priority": trigger.min_priority,
        "window_seconds": trigger.window_seconds,
        "price_change_pct": trigger.price_change_pct,
        "volume_change_pct": trigger.volume_change_pct,
        "lookahead_seconds": trigger.lookahead_seconds,
        "min_failed_targets": trigger.min_failed_targets,
        "min_stale_targets": trigger.min_stale_targets,
    }


def _trigger_codex_authorization_valid(
    trigger: LiveTriggerConfig,
    *,
    config: dict[str, Any],
    config_path: Path,
) -> bool:
    data = trigger.codex_authorization if isinstance(trigger.codex_authorization, dict) else {}
    return (
        data.get("authorized") is True
        and data.get("job_intent") == "run"
        and data.get("authorization_scope") == "unattended_live_trigger"
        and data.get("trigger_id") == trigger.trigger_id
        and data.get("trigger_revision") == LIVE_TRIGGER_REVISION
        and data.get("config_digest") == _config_digest(config, config_path=config_path, trigger_id=trigger.trigger_id)
        and data.get("config_ref") == _config_ref(config_path)
    )


def _authorization_summary(
    trigger: LiveTriggerConfig,
    *,
    config: dict[str, Any],
    config_path: Path,
) -> dict[str, Any]:
    data = trigger.codex_authorization if isinstance(trigger.codex_authorization, dict) else {}
    valid = _trigger_codex_authorization_valid(trigger, config=config, config_path=config_path)
    return {
        "authorized": data.get("authorized") is True,
        "valid": valid,
        "authorization_scope": data.get("authorization_scope") if isinstance(data.get("authorization_scope"), str) else None,
        "invalid_reason": None if valid else "authorization is missing or does not match the current Live trigger config.",
    }


def _config_digest(config: dict[str, Any], *, config_path: Path, trigger_id: str) -> str:
    live = _dict(config.get("live"))
    reports = _dict(live.get("reports"))
    triggers = _dict(reports.get("triggers"))
    trigger_config = _dict(triggers.get(trigger_id))
    material = {
        "config_ref": _config_ref(config_path),
        "trigger_id": trigger_id,
        "trigger_revision": LIVE_TRIGGER_REVISION,
        "trigger_config": {
            key: value
            for key, value in trigger_config.items()
            if key != "codex_authorization"
        },
        "contract": "live_trigger_v1",
    }
    payload = json.dumps(material, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _config_ref(config_path: Path) -> str:
    path = Path(config_path)
    return display_path(path, external_ref="<external-config>") if not path.is_absolute() else "<external-config>"


def _decision_id(trigger_id: str, *, evaluated_at: str) -> str:
    digest = hashlib.sha256(f"{trigger_id}|{evaluated_at}".encode("utf-8")).hexdigest()[:16]
    return f"live_trigger:{trigger_id}:{digest}"


def _records_summary(records: list[dict[str, Any]], *, data_type: str) -> dict[str, Any]:
    return {
        "data_type": data_type,
        "record_count": len(records),
        "records": [_record_summary(record) for record in records[:5]],
        "omitted_records": max(0, len(records) - 5),
    }


def _record_summary(record: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "history_key",
        "stable_event_key",
        "title",
        "summary",
        "source",
        "source_name",
        "data_class",
        "symbol",
        "timeframe",
        "period",
        "published_at",
        "scheduled_at",
        "observed_at",
        "as_of",
        "importance",
        "priority",
        "severity",
        "status",
    )
    result = {key: record.get(key) for key in keys if record.get(key) is not None}
    metrics = record.get("metrics") if isinstance(record.get("metrics"), dict) else {}
    if metrics:
        result["metrics"] = {key: metrics[key] for key in sorted(metrics)[:8]}
    return result


def _collection_target_summary(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "target_key": item.get("target_key"),
        "data_type": item.get("data_type"),
        "latest_job_id": item.get("latest_job_id"),
        "latest_job_status": item.get("latest_job_status"),
        "latest_terminal_status": item.get("latest_terminal_status"),
        "next_attempt_at": item.get("next_attempt_at"),
        "errors": _strings(item.get("errors"))[:3],
    }


def _derivatives_stress_record(record: dict[str, Any]) -> bool:
    data_class = _record_data_class(record)
    if data_class in {"liquidation_summary", "spread_depth"}:
        return True
    metrics = record.get("metrics") if isinstance(record.get("metrics"), dict) else {}
    for key, value in metrics.items():
        parsed = _number(value)
        if parsed is None:
            continue
        key_text = str(key).lower()
        if ("funding" in key_text or "basis" in key_text or "premium" in key_text) and abs(parsed) >= 0.05:
            return True
        if ("imbalance" in key_text or "depth" in key_text) and abs(parsed) >= 0.5:
            return True
    return bool(_strings(record.get("errors")) or _strings(record.get("warnings")))


def _record_priority(record: dict[str, Any]) -> str | None:
    for key in ("priority", "severity", "importance", "impact"):
        value = record.get(key)
        if isinstance(value, str) and value.lower() in LIVE_TRIGGER_PRIORITY_LEVELS:
            return value.lower()
    status = record.get("status")
    if isinstance(status, str) and status.lower() in {"critical", "high", "medium", "low"}:
        return status.lower()
    return None


def _priority_at_least(priority: str | None, minimum: str) -> bool:
    if priority not in LIVE_TRIGGER_PRIORITY_LEVELS or minimum not in LIVE_TRIGGER_PRIORITY_LEVELS:
        return False
    return LIVE_TRIGGER_PRIORITY_LEVELS.index(priority) >= LIVE_TRIGGER_PRIORITY_LEVELS.index(minimum)


def _record_data_class(record: dict[str, Any]) -> str:
    value = record.get("data_class")
    return str(value).strip().lower() if isinstance(value, str) else ""


def _text_contains(record: dict[str, Any], needles: tuple[str, ...]) -> bool:
    haystack = " ".join(
        str(record.get(key) or "")
        for key in ("title", "summary", "description", "metric", "data_class", "direction")
    ).lower()
    return any(needle.lower() in haystack for needle in needles)


def _active_trigger_job(jobs: list[dict[str, Any]], *, trigger_id: str) -> dict[str, Any] | None:
    for job in jobs:
        requester = _dict(job.get("requester"))
        if requester.get("source") != LIVE_TRIGGER_SOURCE:
            continue
        if requester.get("trigger_id") != trigger_id:
            continue
        if str(job.get("status") or "") in JOB_TRANSIENT_STATUSES:
            return job
    return None


def _is_active_trigger_job(job: dict[str, Any]) -> bool:
    requester = _dict(job.get("requester"))
    return requester.get("source") == LIVE_TRIGGER_SOURCE and str(job.get("status") or "") in JOB_TRANSIENT_STATUSES


def _job_by_id(jobs: list[dict[str, Any]], job_id: str) -> dict[str, Any] | None:
    for job in jobs:
        if job.get("job_id") == job_id:
            return job
    return None


def _bounded_live_summary(value: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    collections = value.get("collections") if isinstance(value.get("collections"), list) else []
    return {
        "collection_count": len(collections),
        "status": value.get("status"),
    }


def _records(result: dict[str, Any]) -> list[dict[str, Any]]:
    records = result.get("records") if isinstance(result.get("records"), list) else []
    return [record for record in records if isinstance(record, dict)]


def _first_text(value: Any) -> str | None:
    if isinstance(value, list):
        for item in value:
            if isinstance(item, str) and item.strip():
                return item.strip()
    return None


def _optional_text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _bounded_unique(values: list[str], *, limit: int = 20) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
        if len(result) >= limit:
            break
    return result


def _utc_datetime(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc).replace(microsecond=0)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).replace(microsecond=0)


def _parse_utc(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _format_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
