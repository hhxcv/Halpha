from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Protocol

from halpha.live.config import LiveCollectionConfig, LiveSettings, load_live_settings
from halpha.live.contracts import LIVE_DATA_TYPES
from halpha.live.state_store import LiveCollectionStateRepository
from halpha.live.triggers import LiveTriggerEvaluator
from halpha.runtime.command_job_store import JOB_TERMINAL_STATUSES, JOB_TRANSIENT_STATUSES


LIVE_SCHEDULER_ARTIFACT = "live_scheduler_tick"
LIVE_READ_MODEL_ARTIFACT = "dashboard_live"
LIVE_SCHEDULER_SOURCE = "live_scheduler"
LIVE_COLLECTION_JOB_INTENT = "data_collect"
LIVE_RECENT_JOB_LIMIT = 20


class _JobManager(Protocol):
    def create_job(self, request: dict[str, Any]) -> dict[str, Any]:
        ...

    def list_jobs(self, *, limit: int = 100) -> dict[str, Any]:
        ...


@dataclass(frozen=True)
class LiveCollectionTarget:
    data_type: str
    target_key: str
    enabled: bool
    cadence_seconds: int | None
    lookback_seconds: int | None
    lookahead_seconds: int | None
    params: dict[str, Any]
    target: dict[str, Any]
    warnings: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()


class LiveScheduler:
    def __init__(
        self,
        config: dict[str, Any],
        *,
        config_path: Path,
        job_manager: _JobManager,
        state_repository: LiveCollectionStateRepository | None = None,
        now: datetime | None = None,
    ) -> None:
        self.config = config
        self.config_path = Path(config_path)
        self.job_manager = job_manager
        self.state_repository = state_repository or LiveCollectionStateRepository(self.config_path)
        self.now = _utc_datetime(now)

    def tick(self, *, tick_id: str | None = None) -> dict[str, Any]:
        settings = load_live_settings(self.config)
        now_text = _format_utc(self.now)
        if not settings.enabled:
            return {
                "schema_version": 1,
                "artifact_type": LIVE_SCHEDULER_ARTIFACT,
                "status": "skipped",
                "tick_id": tick_id,
                "enabled": False,
                "reason": "live.enabled is false.",
                "created_jobs": [],
                "collections": self._disabled_collections(settings, now_text=now_text),
                "trigger_evaluation": None,
                "warnings": [],
                "errors": [],
            }

        created_jobs: list[dict[str, Any]] = []
        updated_states: list[dict[str, Any]] = []
        warnings: list[str] = []
        errors: list[str] = []
        targets = build_live_collection_targets(self.config, settings)
        jobs = self._live_jobs(limit=200)
        existing_states = {
            str(state.get("target_key")): state
            for state in self.state_repository.list_states()
            if isinstance(state, dict) and state.get("target_key")
        }
        state_error = existing_states.get("__live_state_error__")
        if state_error:
            errors.extend(_strings(state_error.get("errors")))
            updated_states.append(state_error)
        for target in targets:
            state = existing_states.get(target.target_key)
            state = self._base_state(target, previous=state, now_text=now_text)
            state = self._reconcile_state(state, jobs=jobs, now_text=now_text)
            if not target.enabled:
                updated_states.append(self.state_repository.upsert_state(state))
                continue
            if target.errors:
                state["errors"] = sorted(set([*_strings(state.get("errors")), *target.errors]))
                updated_states.append(self.state_repository.upsert_state(state))
                errors.extend(target.errors)
                continue
            duplicate = _transient_live_job(jobs, target_key=target.target_key)
            if duplicate is not None:
                state["latest_job_id"] = duplicate.get("job_id")
                state["latest_job_status"] = duplicate.get("status")
                state["next_attempt_at"] = state.get("next_attempt_at") or _format_utc(
                    self.now + timedelta(seconds=target.cadence_seconds or 1)
                )
                updated_states.append(self.state_repository.upsert_state(state))
                continue
            if not _state_due(state, now=self.now):
                updated_states.append(self.state_repository.upsert_state(state))
                continue
            job = self._create_collection_job(target, tick_id=tick_id)
            created_jobs.append(job)
            state.update(
                {
                    "last_attempt_at": now_text,
                    "next_attempt_at": _format_utc(self.now + timedelta(seconds=target.cadence_seconds or 1)),
                    "latest_job_id": job.get("job_id"),
                    "latest_job_status": job.get("status"),
                    "warnings": sorted(set([*_strings(state.get("warnings")), *_strings(job.get("warnings"))])),
                    "errors": sorted(set([*_strings(state.get("errors")), *_strings(job.get("errors"))])),
                }
            )
            if isinstance(job.get("job_id"), str) and job.get("job_id"):
                state = self._reconcile_state(state, jobs=[job, *jobs], now_text=now_text)
            elif str(job.get("status") or "") in JOB_TERMINAL_STATUSES:
                state["latest_terminal_status"] = str(job.get("status") or "")
                state["consecutive_failures"] = int(state.get("consecutive_failures") or 0) + 1
            updated_states.append(self.state_repository.upsert_state(state))
        errors.extend(_collection_errors(updated_states))
        warnings.extend(_collection_warnings(updated_states))
        trigger_evaluation = LiveTriggerEvaluator(
            self.config,
            config_path=self.config_path,
            job_manager=self.job_manager,
            now=self.now,
        ).evaluate(
            tick_id=tick_id,
            live_read_model={
                "status": "available" if not errors else "degraded",
                "collections": updated_states,
            },
        )
        errors.extend(_strings(trigger_evaluation.get("errors")))
        warnings.extend(_strings(trigger_evaluation.get("warnings")))
        return {
            "schema_version": 1,
            "artifact_type": LIVE_SCHEDULER_ARTIFACT,
            "status": "available" if not errors else "degraded",
            "tick_id": tick_id,
            "enabled": True,
            "reason": None,
            "created_jobs": created_jobs,
            "collections": sorted(updated_states, key=lambda item: str(item.get("target_key") or "")),
            "trigger_evaluation": trigger_evaluation,
            "warnings": _bounded_unique(warnings),
            "errors": _bounded_unique(errors),
        }

    def read_model(self) -> dict[str, Any]:
        settings = load_live_settings(self.config)
        targets = build_live_collection_targets(self.config, settings)
        target_keys = {target.target_key for target in targets}
        now_text = _format_utc(self.now)
        states = {
            str(state.get("target_key")): state
            for state in self.state_repository.list_states()
            if isinstance(state, dict) and state.get("target_key")
        }
        collections: list[dict[str, Any]] = []
        for target in targets:
            state = self._base_state(target, previous=states.get(target.target_key), now_text=now_text)
            collections.append(state)
        for target_key, state in states.items():
            if target_key not in target_keys:
                data_type = str(state.get("data_type") or "")
                collection = settings.collections.get(data_type)
                if collection is not None and not collection.enabled:
                    state = {
                        **state,
                        "enabled": False,
                        "next_attempt_at": None,
                        "updated_at": now_text,
                    }
                collections.append(state)
        jobs = self._live_jobs(limit=200)
        active_jobs = [job for job in jobs if str(job.get("status") or "") in JOB_TRANSIENT_STATUSES]
        recent_jobs = [job for job in jobs if str(job.get("status") or "") in JOB_TERMINAL_STATUSES][:LIVE_RECENT_JOB_LIMIT]
        errors = _collection_errors(collections)
        warnings = _collection_warnings(collections)
        payload = {
            "schema_version": 1,
            "artifact_type": LIVE_READ_MODEL_ARTIFACT,
            "status": "disabled" if not settings.enabled else "available" if not errors else "degraded",
            "scheduler": {
                "enabled": settings.enabled,
                "tick_seconds": settings.tick_seconds,
                "source": "core",
            },
            "collections": sorted(collections, key=lambda item: str(item.get("target_key") or "")),
            "active_jobs": active_jobs,
            "recent_jobs": recent_jobs,
            "warnings": _bounded_unique(warnings),
            "errors": _bounded_unique(errors),
        }
        triggers = LiveTriggerEvaluator(
            self.config,
            config_path=self.config_path,
            job_manager=self.job_manager,
            now=self.now,
        ).read_model(live_read_model=payload)
        payload["triggers"] = triggers
        payload["warnings"] = _bounded_unique([*payload["warnings"], *_strings(triggers.get("warnings"))])
        payload["errors"] = _bounded_unique([*payload["errors"], *_strings(triggers.get("errors"))])
        if payload["errors"] and payload["status"] != "disabled":
            payload["status"] = "degraded"
        return payload

    def _disabled_collections(self, settings: LiveSettings, *, now_text: str) -> list[dict[str, Any]]:
        return [
            {
                "target_key": data_type,
                "data_type": data_type,
                "target": {"data_type": data_type},
                "enabled": settings.collections[data_type].enabled,
                "cadence_seconds": settings.collections[data_type].cadence_seconds,
                "lookback_seconds": settings.collections[data_type].lookback_seconds,
                "lookahead_seconds": settings.collections[data_type].lookahead_seconds,
                "last_attempt_at": None,
                "last_success_at": None,
                "next_attempt_at": None,
                "latest_job_id": None,
                "latest_job_status": None,
                "latest_terminal_job_id": None,
                "latest_terminal_status": None,
                "consecutive_failures": 0,
                "source_refs": [],
                "warnings": [],
                "errors": [],
                "updated_at": now_text,
            }
            for data_type in LIVE_DATA_TYPES
        ]

    def _base_state(
        self,
        target: LiveCollectionTarget,
        *,
        previous: dict[str, Any] | None,
        now_text: str,
    ) -> dict[str, Any]:
        state = dict(previous or {})
        state.update(
            {
                "target_key": target.target_key,
                "data_type": target.data_type,
                "target": target.target,
                "enabled": target.enabled,
                "cadence_seconds": target.cadence_seconds,
                "lookback_seconds": target.lookback_seconds,
                "lookahead_seconds": target.lookahead_seconds,
                "warnings": sorted(set([*_strings(state.get("warnings")), *target.warnings])),
                "errors": sorted(set([*_strings(state.get("errors")), *target.errors])),
                "updated_at": now_text,
            }
        )
        state.setdefault("last_attempt_at", None)
        state.setdefault("last_success_at", None)
        state.setdefault("next_attempt_at", None)
        state.setdefault("latest_job_id", None)
        state.setdefault("latest_job_status", None)
        state.setdefault("latest_terminal_job_id", None)
        state.setdefault("latest_terminal_status", None)
        state.setdefault("consecutive_failures", 0)
        state.setdefault("source_refs", [])
        return state

    def _reconcile_state(self, state: dict[str, Any], *, jobs: list[dict[str, Any]], now_text: str) -> dict[str, Any]:
        job_id = state.get("latest_job_id")
        if not isinstance(job_id, str) or not job_id:
            return state
        job = _job_by_id(jobs, job_id)
        if job is None:
            job = self._get_job(job_id)
        if job is None:
            return state
        status = str(job.get("status") or "unknown")
        state["latest_job_status"] = status
        if status not in JOB_TERMINAL_STATUSES:
            return state
        if state.get("latest_terminal_job_id") == job_id:
            return state
        state["latest_terminal_job_id"] = job_id
        state["latest_terminal_status"] = status
        state["source_refs"] = _source_refs(job)
        state["warnings"] = sorted(set([*_strings(state.get("warnings")), *_strings(job.get("warnings"))]))
        state["errors"] = sorted(set([*_strings(state.get("errors")), *_strings(job.get("errors"))]))
        if status == "succeeded":
            state["last_success_at"] = _job_time(job) or now_text
            state["consecutive_failures"] = 0
            state["errors"] = _strings(job.get("errors"))
            state["warnings"] = _strings(job.get("warnings"))
        else:
            state["consecutive_failures"] = int(state.get("consecutive_failures") or 0) + 1
        return state

    def _create_collection_job(self, target: LiveCollectionTarget, *, tick_id: str | None) -> dict[str, Any]:
        params = self._job_params(target)
        request = {
            "intent": LIVE_COLLECTION_JOB_INTENT,
            "params": params,
            "requested_by": "Core",
            "requester": {
                "source": LIVE_SCHEDULER_SOURCE,
                "tick_id": tick_id,
                "data_type": target.data_type,
                "target_key": target.target_key,
            },
        }
        try:
            return self.job_manager.create_job(request)
        except Exception as exc:
            return {
                "schema_version": 1,
                "artifact_type": "command_job",
                "job_id": None,
                "intent": LIVE_COLLECTION_JOB_INTENT,
                "kind": "data_collection",
                "requested_by": "Core",
                "requester": request["requester"],
                "params": params,
                "status": "failed",
                "warnings": [],
                "errors": [str(exc) or "Live collection job could not be created."],
            }

    def _job_params(self, target: LiveCollectionTarget) -> dict[str, Any]:
        params = dict(target.params)
        lookback_seconds = target.lookback_seconds or 1
        start = self.now - timedelta(seconds=lookback_seconds)
        end = self.now
        if target.data_type == "macro_calendar" and target.lookahead_seconds:
            end = self.now + timedelta(seconds=target.lookahead_seconds)
        params["start"] = _format_utc(start)
        params["end"] = _format_utc(end)
        return params

    def _live_jobs(self, *, limit: int) -> list[dict[str, Any]]:
        try:
            payload = self.job_manager.list_jobs(limit=limit)
        except Exception:
            return []
        jobs = payload.get("jobs") if isinstance(payload, dict) else []
        return [job for job in jobs if _is_live_collection_job(job)]

    def _get_job(self, job_id: str) -> dict[str, Any] | None:
        get_job = getattr(self.job_manager, "get_job", None)
        if not callable(get_job):
            return None
        try:
            job = get_job(job_id)
        except Exception:
            return None
        return job if isinstance(job, dict) else None


def build_live_collection_targets(config: dict[str, Any], settings: LiveSettings) -> list[LiveCollectionTarget]:
    targets: list[LiveCollectionTarget] = []
    for data_type in LIVE_DATA_TYPES:
        collection = settings.collections[data_type]
        if data_type == "ohlcv" and collection.enabled:
            targets.extend(_ohlcv_targets(config, collection))
        else:
            targets.append(_configured_scope_target(data_type, collection))
    return targets


def _ohlcv_targets(config: dict[str, Any], collection: LiveCollectionConfig) -> list[LiveCollectionTarget]:
    market = config.get("market") if isinstance(config.get("market"), dict) else {}
    ohlcv = market.get("ohlcv") if isinstance(market.get("ohlcv"), dict) else {}
    symbols = _strings(market.get("symbols"))
    timeframes = _strings(ohlcv.get("timeframes"))
    sources = _strings(ohlcv.get("sources"))
    if not sources and isinstance(market.get("source"), str) and market.get("source"):
        sources = [str(market["source"])]
    missing = []
    if not sources:
        missing.append("market.ohlcv.sources")
    if not symbols:
        missing.append("market.symbols")
    if not timeframes:
        missing.append("market.ohlcv.timeframes")
    if missing:
        return [
            LiveCollectionTarget(
                data_type="ohlcv",
                target_key="ohlcv",
                enabled=True,
                cadence_seconds=collection.cadence_seconds,
                lookback_seconds=collection.lookback_seconds,
                lookahead_seconds=collection.lookahead_seconds,
                params={},
                target={"data_type": "ohlcv"},
                errors=(f"Live ohlcv collection requires configured {', '.join(missing)}.",),
            )
        ]
    targets = []
    for source in sources:
        for symbol in symbols:
            for timeframe in timeframes:
                target_key = f"ohlcv:{source}:{symbol}:{timeframe}"
                targets.append(
                    LiveCollectionTarget(
                        data_type="ohlcv",
                        target_key=target_key,
                        enabled=True,
                        cadence_seconds=collection.cadence_seconds,
                        lookback_seconds=collection.lookback_seconds,
                        lookahead_seconds=collection.lookahead_seconds,
                        params={
                            "data_type": "ohlcv",
                            "source": source,
                            "symbol": symbol,
                            "timeframe": timeframe,
                        },
                        target={
                            "data_type": "ohlcv",
                            "source": source,
                            "symbol": symbol,
                            "timeframe": timeframe,
                        },
                    )
                )
    return targets


def _configured_scope_target(data_type: str, collection: LiveCollectionConfig) -> LiveCollectionTarget:
    target_key = "text_event:all" if data_type == "text_event" else f"{data_type}:configured"
    params: dict[str, Any] = {"data_type": data_type}
    if data_type == "text_event":
        params["source"] = "all"
    return LiveCollectionTarget(
        data_type=data_type,
        target_key=target_key,
        enabled=collection.enabled,
        cadence_seconds=collection.cadence_seconds,
        lookback_seconds=collection.lookback_seconds,
        lookahead_seconds=collection.lookahead_seconds,
        params=params,
        target={
            "data_type": data_type,
            **({"source": "all"} if data_type == "text_event" else {"source_scope": "configured"}),
        },
    )


def _is_live_collection_job(job: Any) -> bool:
    if not isinstance(job, dict):
        return False
    if job.get("intent") != LIVE_COLLECTION_JOB_INTENT:
        return False
    requester = job.get("requester") if isinstance(job.get("requester"), dict) else {}
    return requester.get("source") == LIVE_SCHEDULER_SOURCE


def _transient_live_job(jobs: list[dict[str, Any]], *, target_key: str) -> dict[str, Any] | None:
    for job in jobs:
        requester = job.get("requester") if isinstance(job.get("requester"), dict) else {}
        if requester.get("target_key") != target_key:
            continue
        if str(job.get("status") or "") in JOB_TRANSIENT_STATUSES:
            return job
    return None


def _state_due(state: dict[str, Any], *, now: datetime) -> bool:
    next_attempt = _parse_utc(state.get("next_attempt_at"))
    if next_attempt is None:
        return True
    return next_attempt <= now


def _job_by_id(jobs: list[dict[str, Any]], job_id: str) -> dict[str, Any] | None:
    for job in jobs:
        if job.get("job_id") == job_id:
            return job
    return None


def _source_refs(job: dict[str, Any]) -> list[str]:
    refs: list[str] = []
    result_refs = job.get("result_refs") if isinstance(job.get("result_refs"), dict) else {}
    for value in result_refs.values():
        if isinstance(value, str) and value and value not in refs:
            refs.append(value)
    for value in _strings(job.get("source_artifacts")):
        if value not in refs:
            refs.append(value)
    return refs[:20]


def _job_time(job: dict[str, Any]) -> str | None:
    for key in ("finished_at", "updated_at", "created_at"):
        value = job.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _collection_errors(collections: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    for state in collections:
        errors.extend(_strings(state.get("errors")))
    return _bounded_unique(errors)


def _collection_warnings(collections: list[dict[str, Any]]) -> list[str]:
    warnings: list[str] = []
    for state in collections:
        warnings.extend(_strings(state.get("warnings")))
    return _bounded_unique(warnings)


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


def _strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _utc_datetime(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc).replace(microsecond=0)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc).replace(microsecond=0)
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
