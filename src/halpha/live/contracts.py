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

LIVE_CONFIG_FIELDS = {"enabled", "tick_seconds", "collections", "reports"}
LIVE_COLLECTION_FIELDS = {"enabled", "cadence_seconds", "lookback_seconds", "lookahead_seconds"}
LIVE_REPORTS_FIELDS = {"daily", "triggers"}
LIVE_DAILY_REPORT_FIELDS = {"enabled"}
LIVE_REPORT_TRIGGER_FIELDS = {"enabled", "cooldown_seconds"}

LIVE_TRIGGER_IDS = (
    "market_breakout",
    "major_market_move",
    "critical_news",
    "scheduled_catalyst",
    "derivatives_stress",
    "data_quality_degraded",
)
