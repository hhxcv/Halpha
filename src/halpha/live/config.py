from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from halpha.live.contracts import (
    DEFAULT_LIVE_TICK_SECONDS,
    LIVE_DATA_TYPES,
    LIVE_REPORT_TRIGGER_JOB_INTENTS,
    LIVE_TRIGGER_IDS,
)


@dataclass(frozen=True)
class LiveCollectionConfig:
    data_type: str
    enabled: bool
    cadence_seconds: int | None
    lookback_seconds: int | None
    lookahead_seconds: int | None


@dataclass(frozen=True)
class LiveTriggerConfig:
    trigger_id: str
    enabled: bool
    cooldown_seconds: int | None
    job_intent: str
    min_priority: str | None
    window_seconds: int | None
    price_change_pct: float | None
    volume_change_pct: float | None
    lookahead_seconds: int | None
    min_failed_targets: int | None
    min_stale_targets: int | None
    codex_authorization: dict[str, Any]


@dataclass(frozen=True)
class LiveReportsConfig:
    daily_enabled: bool
    triggers: dict[str, LiveTriggerConfig]


@dataclass(frozen=True)
class LiveSettings:
    enabled: bool
    tick_seconds: int
    collections: dict[str, LiveCollectionConfig]
    reports: LiveReportsConfig


def load_live_settings(config: dict[str, Any]) -> LiveSettings:
    live = config.get("live") if isinstance(config.get("live"), dict) else {}
    collections_config = live.get("collections") if isinstance(live.get("collections"), dict) else {}
    collections: dict[str, LiveCollectionConfig] = {}
    for data_type in LIVE_DATA_TYPES:
        item = collections_config.get(data_type) if isinstance(collections_config.get(data_type), dict) else {}
        collections[data_type] = LiveCollectionConfig(
            data_type=data_type,
            enabled=item.get("enabled") is True,
            cadence_seconds=_optional_positive_int(item.get("cadence_seconds")),
            lookback_seconds=_optional_positive_int(item.get("lookback_seconds")),
            lookahead_seconds=_optional_positive_int(item.get("lookahead_seconds")),
        )
    reports_config = live.get("reports") if isinstance(live.get("reports"), dict) else {}
    daily = reports_config.get("daily") if isinstance(reports_config.get("daily"), dict) else {}
    triggers_config = reports_config.get("triggers") if isinstance(reports_config.get("triggers"), dict) else {}
    triggers: dict[str, LiveTriggerConfig] = {}
    for trigger_id in LIVE_TRIGGER_IDS:
        item = triggers_config.get(trigger_id) if isinstance(triggers_config.get(trigger_id), dict) else {}
        job_intent = str(item.get("job_intent") or "run_no_codex").strip()
        if job_intent not in LIVE_REPORT_TRIGGER_JOB_INTENTS:
            job_intent = "run_no_codex"
        authorization = item.get("codex_authorization") if isinstance(item.get("codex_authorization"), dict) else {}
        triggers[trigger_id] = LiveTriggerConfig(
            trigger_id=trigger_id,
            enabled=item.get("enabled") is True,
            cooldown_seconds=_optional_positive_int(item.get("cooldown_seconds")),
            job_intent=job_intent,
            min_priority=_optional_text(item.get("min_priority")),
            window_seconds=_optional_positive_int(item.get("window_seconds")),
            price_change_pct=_optional_positive_number(item.get("price_change_pct")),
            volume_change_pct=_optional_positive_number(item.get("volume_change_pct")),
            lookahead_seconds=_optional_positive_int(item.get("lookahead_seconds")),
            min_failed_targets=_optional_positive_int(item.get("min_failed_targets")),
            min_stale_targets=_optional_positive_int(item.get("min_stale_targets")),
            codex_authorization=dict(authorization),
        )
    return LiveSettings(
        enabled=live.get("enabled") is True,
        tick_seconds=_optional_positive_int(live.get("tick_seconds")) or DEFAULT_LIVE_TICK_SECONDS,
        collections=collections,
        reports=LiveReportsConfig(
            daily_enabled=daily.get("enabled") is True,
            triggers=triggers,
        ),
    )


def _optional_positive_int(value: Any) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    return None


def _optional_positive_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    parsed = float(value)
    if parsed > 0:
        return parsed
    return None


def _optional_text(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None
