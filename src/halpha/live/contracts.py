from __future__ import annotations

DEFAULT_LIVE_TICK_SECONDS = 30

LIVE_DATA_TYPES = (
    "ohlcv",
    "text_event",
    "macro_calendar",
    "onchain_flow",
    "derivatives_market",
    "market_anomaly",
)

LIVE_CONFIG_FIELDS = {"enabled", "tick_seconds", "collections", "streams", "reports"}
LIVE_COLLECTION_FIELDS = {"enabled", "cadence_seconds", "lookback_seconds", "lookahead_seconds"}
LIVE_STREAM_FIELDS = {"ohlcv"}
LIVE_OHLCV_STREAM_FIELDS = {
    "enabled",
    "stale_after_seconds",
    "reconnect_initial_seconds",
    "reconnect_max_seconds",
}
LIVE_REPORTS_FIELDS = {"daily", "triggers"}
LIVE_DAILY_REPORT_FIELDS = {"enabled"}
LIVE_REPORT_TRIGGER_FIELDS = {
    "enabled",
    "cooldown_seconds",
    "job_intent",
    "min_priority",
    "window_seconds",
    "price_change_pct",
    "volume_change_pct",
    "lookahead_seconds",
    "min_failed_targets",
    "min_stale_targets",
    "codex_authorization",
}
LIVE_REPORT_TRIGGER_JOB_INTENTS = ("run_no_codex", "run")
LIVE_TRIGGER_PRIORITY_LEVELS = ("low", "medium", "high", "critical")
LIVE_TRIGGER_DECISION_STATUSES = (
    "triggered",
    "suppressed_cooldown",
    "skipped_disabled",
    "skipped_no_match",
    "skipped_insufficient_evidence",
    "blocked_authorization",
    "failed",
)
LIVE_TRIGGER_REVISION = 1

LIVE_TRIGGER_IDS = (
    "market_breakout",
    "major_market_move",
    "critical_news",
    "scheduled_catalyst",
    "derivatives_stress",
    "data_quality_degraded",
)
