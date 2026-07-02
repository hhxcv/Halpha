from __future__ import annotations

from contextlib import suppress
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
from typing import Any
from uuid import uuid4

from halpha.config import ConfigError, load_config
from halpha.dashboard.constants import (
    DASHBOARD_PNL_COLOR_SCHEME_OPTIONS,
    DASHBOARD_TIMESTAMP_DATE_ORDER_OPTIONS,
    DASHBOARD_TIMESTAMP_HOUR_CYCLE_OPTIONS,
    DEFAULT_DASHBOARD_PNL_COLOR_SCHEME,
    DEFAULT_DASHBOARD_TIMESTAMP_DATE_ORDER,
    DEFAULT_DASHBOARD_TIMESTAMP_HOUR_CYCLE,
)
from halpha.data.public_capabilities import (
    SUPPORTED_DERIVATIVES_DATA_CLASSES,
    SUPPORTED_DERIVATIVES_MARKET_SOURCES,
    SUPPORTED_DERIVATIVES_PERIODS,
    SUPPORTED_MACRO_CALENDAR_DATA_CLASSES,
    SUPPORTED_MACRO_CALENDAR_REGIONS,
    SUPPORTED_MACRO_CALENDAR_SOURCES,
    SUPPORTED_ONCHAIN_FLOW_ASSETS,
    SUPPORTED_ONCHAIN_FLOW_CHAINS,
    SUPPORTED_ONCHAIN_FLOW_DATA_CLASSES,
    SUPPORTED_ONCHAIN_FLOW_SOURCES,
)
from halpha.dashboard.paths import dashboard_control_path
from halpha.live.contracts import (
    DEFAULT_LIVE_TICK_SECONDS,
    LIVE_DATA_TYPES,
    LIVE_REPORT_TRIGGER_JOB_INTENTS,
    LIVE_TRIGGER_IDS,
    LIVE_TRIGGER_PRIORITY_LEVELS,
    LIVE_TRIGGER_REVISION,
)
from halpha.market.ohlcv_quality import OHLCV_TIMEFRAME_ORDER
from halpha.market.ohlcv_source import OHLCV_SOURCE_ORDER
from halpha.storage import config_base, display_path, safe_local_ref


OHLCV_LOOKBACK_DEFAULTS = {
    "1m": 1440,
    "5m": 2016,
    "15m": 2016,
    "1h": 720,
    "4h": 720,
    "1d": 500,
    "1w": 260,
    "1M": 120,
}
DERIVATIVES_PERIOD_OPTIONS = tuple(
    period
    for period in ("5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d")
    if period in SUPPORTED_DERIVATIVES_PERIODS
)
DERIVATIVES_LOOKBACK_DEFAULTS = {
    "5m": 720,
    "15m": 720,
    "30m": 720,
    "1h": 720,
    "2h": 360,
    "4h": 180,
    "6h": 120,
    "8h": 90,
    "12h": 90,
    "1d": 90,
}
DERIVATIVES_DATA_CLASS_OPTIONS = tuple(
    data_class
    for data_class in ("funding_rate", "open_interest", "premium_index", "basis", "spread_depth", "liquidation_summary")
    if data_class in SUPPORTED_DERIVATIVES_DATA_CLASSES
)
MACRO_CALENDAR_DATA_CLASS_OPTIONS = tuple(sorted(SUPPORTED_MACRO_CALENDAR_DATA_CLASSES))
ONCHAIN_FLOW_DATA_CLASS_OPTIONS = tuple(
    data_class
    for data_class in ("stablecoin_supply", "chain_activity", "network_congestion", "exchange_flow_availability")
    if data_class in SUPPORTED_ONCHAIN_FLOW_DATA_CLASSES
)
ONCHAIN_FLOW_ASSET_OPTIONS = tuple(asset for asset in ("ALL_STABLECOINS", "BTC") if asset in SUPPORTED_ONCHAIN_FLOW_ASSETS)
ONCHAIN_FLOW_CHAIN_OPTIONS = tuple(chain for chain in ("all", "bitcoin") if chain in SUPPORTED_ONCHAIN_FLOW_CHAINS)
TEXT_INTELLIGENCE_MODEL_DEFAULTS = {
    "embedding": {
        "provider": "sentence_transformers",
        "name": "sentence-transformers/all-MiniLM-L6-v2",
        "revision": "pinned",
    },
    "classifier": {
        "provider": "transformers_zero_shot",
        "name": "facebook/bart-large-mnli",
        "revision": "pinned",
    },
    "sentiment": {
        "provider": "transformers_text_classification",
        "name": "ProsusAI/finbert",
        "revision": "pinned",
    },
    "ner": {
        "provider": "gliner",
        "name": "urchade/gliner_medium-v2.1",
        "revision": "pinned",
    },
}
TEXT_INTELLIGENCE_THRESHOLD_DEFAULTS = {
    "duplicate_similarity": 0.92,
    "same_topic_similarity": 0.82,
    "classifier_accept_score": 0.65,
    "classifier_top_margin": 0.10,
    "entity_accept_score": 0.50,
    "max_topic_window_hours": 48,
}
DEFAULT_CONFIG_STORAGE_DIR = Path(".halpha") / "configs"
CONFIG_IMPORT_MAX_BYTES = 512 * 1024
LIVE_COLLECTION_DEFAULTS = {
    "ohlcv": {"cadence_seconds": 300, "lookback_seconds": 24 * 3600},
    "text_event": {"cadence_seconds": 600, "lookback_seconds": 6 * 3600},
    "macro_calendar": {
        "cadence_seconds": 6 * 3600,
        "lookback_seconds": 7 * 24 * 3600,
        "lookahead_seconds": 45 * 24 * 3600,
    },
    "onchain_flow": {"cadence_seconds": 3600, "lookback_seconds": 24 * 3600},
    "derivatives_market": {"cadence_seconds": 900, "lookback_seconds": 6 * 3600},
    "market_anomaly": {"cadence_seconds": 300, "lookback_seconds": 6 * 3600},
}
LIVE_TRIGGER_DEFAULTS = {
    "market_breakout": {
        "cooldown_seconds": 1800,
        "job_intent": "run_no_codex",
        "window_seconds": 3600,
    },
    "major_market_move": {
        "cooldown_seconds": 1800,
        "job_intent": "run_no_codex",
        "window_seconds": 3600,
        "price_change_pct": 3.0,
        "volume_change_pct": 2.0,
    },
    "critical_news": {
        "cooldown_seconds": 3600,
        "job_intent": "run_no_codex",
        "min_priority": "high",
        "window_seconds": 3600,
    },
    "scheduled_catalyst": {
        "cooldown_seconds": 3600,
        "job_intent": "run_no_codex",
        "min_priority": "high",
        "lookahead_seconds": 24 * 3600,
    },
    "derivatives_stress": {
        "cooldown_seconds": 1800,
        "job_intent": "run_no_codex",
        "window_seconds": 3600,
    },
    "data_quality_degraded": {
        "cooldown_seconds": 3600,
        "job_intent": "run_no_codex",
        "min_failed_targets": 1,
        "min_stale_targets": 1,
    },
}
LIVE_TRIGGER_THRESHOLD_FIELDS = {
    "market_breakout": (
        ("window_seconds", "Evidence window seconds", "positive_int", "Recent anomaly evidence window."),
    ),
    "major_market_move": (
        ("window_seconds", "Evidence window seconds", "positive_int", "Recent OHLCV evidence window."),
        ("price_change_pct", "Price change pct", "positive_number", "Minimum absolute price move percentage."),
        ("volume_change_pct", "Volume change multiplier", "positive_number", "Minimum volume change multiplier."),
    ),
    "critical_news": (
        ("min_priority", "Minimum priority", "select", "Minimum text-event priority accepted as trigger evidence."),
        ("window_seconds", "Evidence window seconds", "positive_int", "Recent text-event evidence window."),
    ),
    "scheduled_catalyst": (
        ("min_priority", "Minimum priority", "select", "Minimum macro event priority accepted as trigger evidence."),
        ("lookahead_seconds", "Lookahead seconds", "positive_int", "Future scheduled-event evidence window."),
    ),
    "derivatives_stress": (
        ("window_seconds", "Evidence window seconds", "positive_int", "Recent derivatives stress evidence window."),
    ),
    "data_quality_degraded": (
        ("min_failed_targets", "Failed targets threshold", "positive_int", "Minimum failed Live collection targets."),
        ("min_stale_targets", "Stale targets threshold", "positive_int", "Minimum stale Live collection targets."),
    ),
}
CONFIG_PROFILE_SECTIONS = (
    "General",
    "Market data",
    "Strategy",
    "Reports",
    "Monitor",
    "Live",
    "Intelligence sources",
    "Storage",
    "Dashboard",
)
CONFIG_PROFILE_FIELDS = (
    {
        "section": "General",
        "label": "Run timezone",
        "path": "run.timezone",
        "control": "select",
        "value_type": "string",
        "options": ("Asia/Shanghai", "UTC"),
        "description": "Default timezone used by local run artifacts.",
    },
    {
        "section": "Dashboard",
        "label": "Display timezone",
        "path": "dashboard.display_timezone",
        "control": "select",
        "value_type": "string",
        "options": ("Asia/Shanghai", "UTC"),
        "description": "Timezone used for timestamps displayed in dashboard pages.",
    },
    {
        "section": "Dashboard",
        "label": "Time clock",
        "path": "dashboard.timestamp_hour_cycle",
        "control": "select",
        "value_type": "string",
        "options": DASHBOARD_TIMESTAMP_HOUR_CYCLE_OPTIONS,
        "default": DEFAULT_DASHBOARD_TIMESTAMP_HOUR_CYCLE,
        "description": "Default clock style used by dashboard timestamps.",
    },
    {
        "section": "Dashboard",
        "label": "Date order",
        "path": "dashboard.timestamp_date_order",
        "control": "select",
        "value_type": "string",
        "options": DASHBOARD_TIMESTAMP_DATE_ORDER_OPTIONS,
        "default": DEFAULT_DASHBOARD_TIMESTAMP_DATE_ORDER,
        "description": "Default date order used by dashboard timestamps.",
    },
    {
        "section": "Dashboard",
        "label": "PnL colors",
        "path": "dashboard.pnl_color_scheme",
        "control": "select",
        "value_type": "string",
        "options": DASHBOARD_PNL_COLOR_SCHEME_OPTIONS,
        "default": DEFAULT_DASHBOARD_PNL_COLOR_SCHEME,
        "description": "Color convention for profit/loss values and candle up/down moves.",
    },
    {
        "section": "Market data",
        "label": "Enable market data",
        "path": "market.enabled",
        "control": "toggle",
        "value_type": "bool",
        "description": "Collect market data for research runs.",
    },
    {
        "section": "Market data",
        "label": "Source",
        "path": "market.source",
        "control": "select",
        "value_type": "string",
        "options": ("binance",),
        "description": "Configured public market data source.",
    },
    {
        "section": "Market data",
        "label": "OHLCV sources",
        "path": "market.ohlcv.sources",
        "control": "multi_select",
        "value_type": "string_list",
        "options": OHLCV_SOURCE_ORDER,
        "default": OHLCV_SOURCE_ORDER,
        "description": "Public OHLCV sources available to CLI and dashboard collection.",
    },
    {
        "section": "Market data",
        "label": "Symbols",
        "path": "market.symbols",
        "control": "tags",
        "value_type": "string_list",
        "description": "Comma-separated market symbols used by the local research pipeline.",
    },
    {
        "section": "Market data",
        "label": "OHLCV timeframes",
        "path": "market.ohlcv.timeframes",
        "control": "multi_select",
        "value_type": "string_list",
        "options": OHLCV_TIMEFRAME_ORDER,
        "description": "Reusable OHLCV windows maintained outside single-run artifacts.",
    },
    *(
        {
            "section": "Market data",
            "label": f"OHLCV lookback {timeframe}",
            "path": f"market.ohlcv.lookback.{timeframe}",
            "control": "number",
            "value_type": "positive_int",
            "default": OHLCV_LOOKBACK_DEFAULTS[timeframe],
            "description": f"Number of {timeframe} candles to collect during automatic OHLCV sync.",
        }
        for timeframe in OHLCV_TIMEFRAME_ORDER
    ),
    {
        "section": "Market data",
        "label": "Use proxy",
        "path": "market.proxy.enabled",
        "control": "toggle",
        "value_type": "bool",
        "description": "Enable a configured proxy without exposing proxy URL values in the dashboard.",
    },
    {
        "section": "Market data",
        "label": "Enable derivatives",
        "path": "market.derivatives.enabled",
        "control": "toggle",
        "value_type": "bool",
        "description": "Collect public derivatives market evidence.",
    },
    {
        "section": "Market data",
        "label": "Derivatives source",
        "path": "market.derivatives.source",
        "control": "select",
        "value_type": "string",
        "options": tuple(sorted(SUPPORTED_DERIVATIVES_MARKET_SOURCES)),
        "description": "Public derivatives market data source.",
    },
    {
        "section": "Market data",
        "label": "Derivatives symbols",
        "path": "market.derivatives.symbols",
        "control": "tags",
        "value_type": "string_list",
        "default_from": "market.symbols",
        "description": "Comma-separated symbols used for derivatives evidence.",
    },
    {
        "section": "Market data",
        "label": "Derivatives data classes",
        "path": "market.derivatives.data_classes",
        "control": "multi_select",
        "value_type": "string_list",
        "options": DERIVATIVES_DATA_CLASS_OPTIONS,
        "default": ("funding_rate", "open_interest", "premium_index"),
        "description": "Derivatives evidence classes to collect and summarize.",
    },
    {
        "section": "Market data",
        "label": "Derivatives periods",
        "path": "market.derivatives.periods",
        "control": "multi_select",
        "value_type": "string_list",
        "options": DERIVATIVES_PERIOD_OPTIONS,
        "default": ("1h", "4h", "1d"),
        "description": "Aggregation periods for derivatives history windows.",
    },
    *(
        {
            "section": "Market data",
            "label": f"Derivatives lookback {period}",
            "path": f"market.derivatives.lookback.{period}",
            "control": "number",
            "value_type": "positive_int",
            "default": DERIVATIVES_LOOKBACK_DEFAULTS[period],
            "description": f"History rows to retain for the {period} derivatives period.",
        }
        for period in DERIVATIVES_PERIOD_OPTIONS
    ),
    {
        "section": "Market data",
        "label": "Enable market anomalies",
        "path": "market.anomalies.enabled",
        "control": "toggle",
        "value_type": "bool",
        "description": "Collect external or Halpha rule-detected market anomaly records.",
    },
    {
        "section": "Strategy",
        "label": "Enable quant research",
        "path": "quant.enabled",
        "control": "toggle",
        "value_type": "bool",
        "description": "Enable configured strategy evaluation and backtest evidence.",
    },
    {
        "section": "Reports",
        "label": "Report title",
        "path": "report.title",
        "control": "text",
        "value_type": "string",
        "description": "Human-readable report title used by generated Markdown reports.",
    },
    {
        "section": "Reports",
        "label": "Report language",
        "path": "report.language",
        "control": "select",
        "value_type": "string",
        "options": ("zh-CN",),
        "description": "Final reports are Simplified Chinese unless requested otherwise.",
    },
    {
        "section": "Reports",
        "label": "Enable Codex report",
        "path": "codex.enabled",
        "control": "toggle",
        "value_type": "bool",
        "description": "Allow report generation through the configured local Codex command.",
    },
    {
        "section": "Monitor",
        "label": "Interval seconds",
        "path": "monitor.interval_seconds",
        "control": "number",
        "value_type": "positive_int",
        "description": "Delay between local Monitor health checks.",
    },
    {
        "section": "Monitor",
        "label": "Failure backoff cap",
        "path": "monitor.failure_backoff_max_seconds",
        "control": "number",
        "value_type": "positive_int",
        "description": "Maximum retry delay after recoverable Core health-check failures.",
    },
    {
        "section": "Live",
        "label": "Enable Live",
        "path": "live.enabled",
        "control": "toggle",
        "value_type": "bool",
        "description": "Enable Core-owned Live scheduling for continuous market intelligence.",
    },
    {
        "section": "Live",
        "label": "Scheduler tick seconds",
        "path": "live.tick_seconds",
        "control": "number",
        "value_type": "positive_int",
        "default": DEFAULT_LIVE_TICK_SECONDS,
        "description": "How often Core evaluates Live collection and trigger work.",
    },
    {
        "section": "Live",
        "label": "Daily report in Live",
        "path": "live.reports.daily.enabled",
        "control": "toggle",
        "value_type": "bool",
        "description": "Show the existing daily report schedule in Live without creating a second scheduler authority.",
    },
    {
        "section": "Live",
        "label": "Stream OHLCV",
        "path": "live.streams.ohlcv.enabled",
        "control": "toggle",
        "value_type": "bool",
        "default": True,
        "description": "Use public WebSocket kline streams for Live OHLCV targets when an implemented source supports it.",
    },
    {
        "section": "Live",
        "label": "OHLCV stream stale seconds",
        "path": "live.streams.ohlcv.stale_after_seconds",
        "control": "number",
        "value_type": "positive_int",
        "default": 180,
        "description": "Seconds without stream events before Live schedules REST backfill.",
    },
    {
        "section": "Live",
        "label": "OHLCV stream reconnect start",
        "path": "live.streams.ohlcv.reconnect_initial_seconds",
        "control": "number",
        "value_type": "positive_int",
        "default": 5,
        "description": "Initial reconnect delay after a Live OHLCV WebSocket disconnect.",
    },
    {
        "section": "Live",
        "label": "OHLCV stream reconnect cap",
        "path": "live.streams.ohlcv.reconnect_max_seconds",
        "control": "number",
        "value_type": "positive_int",
        "default": 300,
        "description": "Maximum reconnect delay for Live OHLCV WebSocket streams.",
    },
    *(
        {
            "section": "Live",
            "label": f"Collect {data_type}",
            "path": f"live.collections.{data_type}.enabled",
            "control": "toggle",
            "value_type": "bool",
            "description": f"Allow Live to create visible collection jobs for {data_type}.",
        }
        for data_type in LIVE_DATA_TYPES
    ),
    *(
        {
            "section": "Live",
            "label": f"{data_type} cadence seconds",
            "path": f"live.collections.{data_type}.cadence_seconds",
            "control": "number",
            "value_type": "positive_int",
            "default": LIVE_COLLECTION_DEFAULTS[data_type]["cadence_seconds"],
            "description": f"Minimum seconds between Live {data_type} collection attempts.",
        }
        for data_type in LIVE_DATA_TYPES
    ),
    *(
        {
            "section": "Live",
            "label": f"{data_type} lookback seconds",
            "path": f"live.collections.{data_type}.lookback_seconds",
            "control": "number",
            "value_type": "positive_int",
            "default": LIVE_COLLECTION_DEFAULTS[data_type]["lookback_seconds"],
            "description": f"Backward collection window for Live {data_type} jobs.",
        }
        for data_type in LIVE_DATA_TYPES
    ),
    {
        "section": "Live",
        "label": "Macro calendar lookahead seconds",
        "path": "live.collections.macro_calendar.lookahead_seconds",
        "control": "number",
        "value_type": "positive_int",
        "default": LIVE_COLLECTION_DEFAULTS["macro_calendar"]["lookahead_seconds"],
        "description": "Forward collection window for scheduled macro events.",
    },
    *(
        {
            "section": "Live",
            "label": f"{trigger_id} trigger",
            "path": f"live.reports.triggers.{trigger_id}.enabled",
            "control": "toggle",
            "value_type": "bool",
            "description": f"Enable deterministic Live trigger evaluation for {trigger_id}.",
        }
        for trigger_id in LIVE_TRIGGER_IDS
    ),
    *(
        {
            "section": "Live",
            "label": f"{trigger_id} cooldown seconds",
            "path": f"live.reports.triggers.{trigger_id}.cooldown_seconds",
            "control": "number",
            "value_type": "positive_int",
            "default": LIVE_TRIGGER_DEFAULTS[trigger_id]["cooldown_seconds"],
            "description": f"Minimum seconds before {trigger_id} can create another equivalent report job.",
        }
        for trigger_id in LIVE_TRIGGER_IDS
    ),
    *(
        {
            "section": "Live",
            "label": f"{trigger_id} job intent",
            "path": f"live.reports.triggers.{trigger_id}.job_intent",
            "control": "select",
            "value_type": "string",
            "options": LIVE_REPORT_TRIGGER_JOB_INTENTS,
            "default": LIVE_TRIGGER_DEFAULTS[trigger_id]["job_intent"],
            "description": "`run_no_codex` creates deterministic jobs. `run` requires explicit unattended Codex authorization.",
        }
        for trigger_id in LIVE_TRIGGER_IDS
    ),
    *(
        {
            "section": "Live",
            "label": f"{trigger_id} {label}",
            "path": f"live.reports.triggers.{trigger_id}.{field_name}",
            "control": "select" if value_type == "select" else "number",
            "value_type": "string" if value_type == "select" else value_type,
            "options": LIVE_TRIGGER_PRIORITY_LEVELS if value_type == "select" else None,
            "default": LIVE_TRIGGER_DEFAULTS[trigger_id][field_name],
            "description": description,
        }
        for trigger_id, field_specs in LIVE_TRIGGER_THRESHOLD_FIELDS.items()
        for field_name, label, value_type, description in field_specs
    ),
    *(
        {
            "section": "Live",
            "label": f"Authorize {trigger_id} Codex run",
            "path": f"live.reports.triggers.{trigger_id}.confirm_codex",
            "control": "toggle",
            "value_type": "bool",
            "virtual": True,
            "description": "Explicitly authorize this enabled trigger to create unattended Codex-capable `run` jobs for the current config digest.",
        }
        for trigger_id in LIVE_TRIGGER_IDS
    ),
    {
        "section": "Intelligence sources",
        "label": "Enable text collection",
        "path": "text.enabled",
        "control": "toggle",
        "value_type": "bool",
        "description": "Collect configured public text sources.",
    },
    {
        "section": "Intelligence sources",
        "label": "Max text items",
        "path": "text.max_items",
        "control": "number",
        "value_type": "positive_int",
        "description": "Maximum collected text items per run.",
    },
    {
        "section": "Intelligence sources",
        "label": "Enable text intelligence",
        "path": "text.intelligence.enabled",
        "control": "toggle",
        "value_type": "bool",
        "description": "Enable local text intelligence evidence generation.",
    },
    {
        "section": "Intelligence sources",
        "label": "Allow model download",
        "path": "text.intelligence.allow_model_download",
        "control": "toggle",
        "value_type": "bool",
        "description": "Permit configured model download when local models are missing.",
    },
    {
        "section": "Intelligence sources",
        "label": "Model cache directory",
        "path": "text.intelligence.model_cache_dir",
        "control": "text",
        "value_type": "string",
        "default": "data/models/text",
        "description": "Relative directory for local text intelligence model files.",
    },
    *(
        {
            "section": "Intelligence sources",
            "label": f"{role.title()} model provider",
            "path": f"text.intelligence.models.{role}.provider",
            "control": "select",
            "value_type": "string",
            "options": (model["provider"],),
            "default": model["provider"],
            "description": f"Provider used for the {role} text intelligence model.",
        }
        for role, model in TEXT_INTELLIGENCE_MODEL_DEFAULTS.items()
    ),
    *(
        {
            "section": "Intelligence sources",
            "label": f"{role.title()} model name",
            "path": f"text.intelligence.models.{role}.name",
            "control": "text",
            "value_type": "string",
            "default": model["name"],
            "description": f"Model identifier used for the {role} text intelligence model.",
        }
        for role, model in TEXT_INTELLIGENCE_MODEL_DEFAULTS.items()
    ),
    *(
        {
            "section": "Intelligence sources",
            "label": f"{role.title()} model revision",
            "path": f"text.intelligence.models.{role}.revision",
            "control": "text",
            "value_type": "string",
            "default": model["revision"],
            "description": f"Revision pin used for the {role} text intelligence model.",
        }
        for role, model in TEXT_INTELLIGENCE_MODEL_DEFAULTS.items()
    ),
    *(
        {
            "section": "Intelligence sources",
            "label": label,
            "path": f"text.intelligence.thresholds.{path}",
            "control": "number",
            "value_type": value_type,
            "default": TEXT_INTELLIGENCE_THRESHOLD_DEFAULTS[path],
            "description": description,
        }
        for path, label, value_type, description in (
            (
                "duplicate_similarity",
                "Duplicate similarity",
                "unit_interval_number",
                "Similarity threshold used to mark duplicate text events.",
            ),
            (
                "same_topic_similarity",
                "Same-topic similarity",
                "unit_interval_number",
                "Similarity threshold used to group related text events.",
            ),
            (
                "classifier_accept_score",
                "Classifier accept score",
                "unit_interval_number",
                "Minimum zero-shot classifier score accepted as evidence.",
            ),
            (
                "classifier_top_margin",
                "Classifier top margin",
                "unit_interval_number",
                "Minimum margin between the top classifier label and runner-up.",
            ),
            (
                "entity_accept_score",
                "Entity accept score",
                "unit_interval_number",
                "Minimum entity extraction confidence accepted as evidence.",
            ),
            (
                "max_topic_window_hours",
                "Max topic window hours",
                "positive_int",
                "Maximum time window for text events to be grouped as one topic.",
            ),
        )
    ),
    {
        "section": "Intelligence sources",
        "label": "Enable macro calendar",
        "path": "macro_calendar.enabled",
        "control": "toggle",
        "value_type": "bool",
        "description": "Collect configured public scheduled-event evidence.",
    },
    {
        "section": "Intelligence sources",
        "label": "Macro calendar source",
        "path": "macro_calendar.source",
        "control": "select",
        "value_type": "string",
        "options": tuple(sorted(SUPPORTED_MACRO_CALENDAR_SOURCES)),
        "description": "Public scheduled-event source.",
    },
    {
        "section": "Intelligence sources",
        "label": "Macro calendar data classes",
        "path": "macro_calendar.data_classes",
        "control": "multi_select",
        "value_type": "string_list",
        "options": MACRO_CALENDAR_DATA_CLASS_OPTIONS,
        "default": MACRO_CALENDAR_DATA_CLASS_OPTIONS,
        "description": "Scheduled-event evidence classes to collect.",
    },
    {
        "section": "Intelligence sources",
        "label": "Macro calendar regions",
        "path": "macro_calendar.regions",
        "control": "multi_select",
        "value_type": "string_list",
        "options": tuple(sorted(SUPPORTED_MACRO_CALENDAR_REGIONS)),
        "default": ("US",),
        "description": "Regions included in scheduled-event evidence.",
    },
    {
        "section": "Intelligence sources",
        "label": "Macro lookback days",
        "path": "macro_calendar.lookback_days",
        "control": "number",
        "value_type": "positive_int",
        "default": 7,
        "description": "Past scheduled-event window in days.",
    },
    {
        "section": "Intelligence sources",
        "label": "Macro lookahead days",
        "path": "macro_calendar.lookahead_days",
        "control": "number",
        "value_type": "positive_int",
        "default": 45,
        "description": "Future scheduled-event window in days.",
    },
    {
        "section": "Intelligence sources",
        "label": "Enable on-chain flow",
        "path": "onchain_flow.enabled",
        "control": "toggle",
        "value_type": "bool",
        "description": "Collect configured public on-chain and exchange-flow evidence.",
    },
    {
        "section": "Intelligence sources",
        "label": "On-chain source",
        "path": "onchain_flow.source",
        "control": "select",
        "value_type": "string",
        "options": tuple(sorted(SUPPORTED_ONCHAIN_FLOW_SOURCES)),
        "description": "Public aggregate on-chain evidence source.",
    },
    {
        "section": "Intelligence sources",
        "label": "On-chain data classes",
        "path": "onchain_flow.data_classes",
        "control": "multi_select",
        "value_type": "string_list",
        "options": ONCHAIN_FLOW_DATA_CLASS_OPTIONS,
        "default": ONCHAIN_FLOW_DATA_CLASS_OPTIONS,
        "description": "On-chain and exchange-flow evidence classes to collect.",
    },
    {
        "section": "Intelligence sources",
        "label": "On-chain assets",
        "path": "onchain_flow.assets",
        "control": "multi_select",
        "value_type": "string_list",
        "options": ONCHAIN_FLOW_ASSET_OPTIONS,
        "default": ONCHAIN_FLOW_ASSET_OPTIONS,
        "description": "Assets included in on-chain evidence.",
    },
    {
        "section": "Intelligence sources",
        "label": "On-chain chains",
        "path": "onchain_flow.chains",
        "control": "multi_select",
        "value_type": "string_list",
        "options": ONCHAIN_FLOW_CHAIN_OPTIONS,
        "default": ONCHAIN_FLOW_CHAIN_OPTIONS,
        "description": "Chains included in on-chain evidence.",
    },
    {
        "section": "Intelligence sources",
        "label": "On-chain lookback days",
        "path": "onchain_flow.lookback_days",
        "control": "number",
        "value_type": "positive_int",
        "default": 7,
        "description": "Past on-chain evidence window in days.",
    },
)


def dashboard_config_profile(
    config: dict[str, Any],
    *,
    config_path: Path,
    config_history: list[str] | None = None,
) -> dict[str, Any]:
    fields = [_config_profile_field(config, field, config_path=config_path) for field in CONFIG_PROFILE_FIELDS]
    return {
        "schema_version": 1,
        "artifact_type": "dashboard_config_profile",
        "status": "available",
        "config": {
            "ref": dashboard_config_ref(config_path),
            "editable": True,
            "requires_confirmation": True,
        },
        "config_selection": dashboard_config_selection(config_path, config_history=config_history),
        "sections": list(CONFIG_PROFILE_SECTIONS),
        "fields": fields,
        "warnings": [],
        "errors": [],
        "omitted": {
            "absolute_local_paths_embedded": False,
            "proxy_urls_embedded": False,
            "credentials_embedded": False,
            "raw_config_text_embedded": False,
        },
    }


def dashboard_config_selection(config_path: Path | None, *, config_history: list[str] | None = None) -> dict[str, Any]:
    records = _dashboard_config_candidate_records(config_path, config_history=config_history)
    return {
        "active_id": _config_candidate_id(config_path) if config_path is not None else None,
        "default_storage_ref": DEFAULT_CONFIG_STORAGE_DIR.as_posix(),
        "import_supported": True,
        "candidates": [_public_config_candidate(record) for record in records],
    }


def resolve_dashboard_config_candidate(
    candidate_id: str,
    *,
    active_config_path: Path | None,
    config_history: list[str] | None = None,
) -> Path | None:
    wanted = str(candidate_id or "").strip()
    if not wanted:
        return None
    for record in _dashboard_config_candidate_records(active_config_path, config_history=config_history):
        if record["id"] == wanted:
            return Path(str(record["_path"]))
    return None


def dashboard_import_config_file(request: dict[str, Any]) -> dict[str, Any]:
    name = str(request.get("name") or "").strip()
    content = request.get("content")
    if not name:
        return _config_import_result(status="failed", errors=["config file name is required."])
    if not isinstance(content, str) or not content.strip():
        return _config_import_result(status="failed", errors=["config file content is required."])
    if len(content.encode("utf-8")) > CONFIG_IMPORT_MAX_BYTES:
        return _config_import_result(status="failed", errors=["config file is larger than the dashboard import limit."])
    safe_name = _safe_config_file_name(name)
    if not safe_name:
        return _config_import_result(status="failed", errors=["config file must be a YAML file."])

    target_dir = Path.cwd() / DEFAULT_CONFIG_STORAGE_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = _unique_config_import_path(target_dir, safe_name)
    temp_path = target_path.with_name(f".{target_path.name}.{uuid4().hex}.tmp")
    try:
        _write_text_for_validation(temp_path, content if content.endswith("\n") else f"{content}\n")
        try:
            load_config(temp_path)
        except ConfigError as exc:
            return _config_import_result(
                status="failed",
                errors=[sanitize_dashboard_message(str(exc), config_path=temp_path)],
            )
        os.replace(temp_path, target_path)
    except OSError as exc:
        return _config_import_result(
            status="failed",
            errors=[sanitize_dashboard_message(f"config file could not be imported: {exc}", config_path=temp_path)],
        )
    finally:
        with suppress(OSError):
            if temp_path.exists():
                temp_path.unlink()

    return _config_import_result(
        status="succeeded",
        config_path=safe_local_ref(target_path, base=Path.cwd()),
        config={"loaded": True, "ref": safe_local_ref(target_path, base=Path.cwd())},
    )


def dashboard_backup_config(*, config_path: Path) -> dict[str, Any]:
    backup, error = _backup_dashboard_config(config_path)
    if error:
        return {
            "schema_version": 1,
            "artifact_type": "dashboard_config_backup",
            "status": "failed",
            "config": {"ref": dashboard_config_ref(config_path)},
            "backup_ref": None,
            "warnings": [],
            "errors": [error],
            "omitted": {"absolute_local_paths_embedded": False},
        }
    base = Path.cwd()
    return {
        "schema_version": 1,
        "artifact_type": "dashboard_config_backup",
        "status": "succeeded",
        "config": {"ref": dashboard_config_ref(config_path)},
        "backup_ref": safe_local_ref(backup, base=base) if backup else None,
        "warnings": [],
        "errors": [],
        "omitted": {"absolute_local_paths_embedded": False},
    }


def dashboard_save_config_profile(
    config: dict[str, Any],
    *,
    config_path: Path,
    request: dict[str, Any],
) -> dict[str, Any]:
    if request.get("confirm") is not True:
        return _config_save_result(
            config,
            config_path=config_path,
            status="blocked",
            errors=["confirm must be true to save dashboard settings."],
        )

    changes = request.get("changes")
    if not isinstance(changes, dict) or not changes:
        return _config_save_result(
            config,
            config_path=config_path,
            status="skipped",
            warnings=["no config changes were submitted."],
        )

    next_config = deepcopy(config)
    changed_paths: list[str] = []
    virtual_changes: dict[str, Any] = {}
    errors: list[str] = []
    for path, raw_value in sorted(changes.items()):
        if not isinstance(path, str):
            errors.append("config change path must be a string.")
            continue
        field = _config_profile_field_definition(path)
        if field is None:
            errors.append(f"{path} is not editable from the dashboard settings UI.")
            continue
        value, error = _coerce_config_profile_value(raw_value, field)
        if error:
            errors.append(f"{path}: {error}")
            continue
        if field.get("virtual") is True:
            virtual_changes[path] = value
        else:
            _set_config_value(next_config, path, value)
        changed_paths.append(path)
    if errors:
        return _config_save_result(config, config_path=config_path, status="failed", errors=errors)
    _materialize_enabled_capability_defaults(next_config)
    authorization_errors = _materialize_live_trigger_authorizations(
        next_config,
        config_path=config_path,
        virtual_changes=virtual_changes,
    )
    if authorization_errors:
        return _config_save_result(config, config_path=config_path, status="failed", errors=authorization_errors)

    serialized, error = _serialize_config_yaml(next_config)
    if error:
        return _config_save_result(config, config_path=config_path, status="failed", errors=[error])

    temp_path = _dashboard_config_temp_path(config_path)
    backup_path: Path | None = None
    try:
        _write_text_for_validation(temp_path, serialized)
        try:
            validated = load_config(temp_path)
        except ConfigError as exc:
            return _config_save_result(
                config,
                config_path=config_path,
                status="failed",
                errors=[sanitize_dashboard_message(str(exc), config_path=temp_path)],
            )
        backup_path, backup_error = _backup_dashboard_config(config_path)
        if backup_error:
            return _config_save_result(config, config_path=config_path, status="failed", errors=[backup_error])
        os.replace(temp_path, config_path)
    except OSError as exc:
        return _config_save_result(
            config,
            config_path=config_path,
            status="failed",
            errors=[sanitize_dashboard_message(f"config file could not be saved: {exc}", config_path=config_path)],
        )
    finally:
        with suppress(OSError):
            if temp_path.exists():
                temp_path.unlink()

    config.clear()
    config.update(validated)
    base = Path.cwd()
    return _config_save_result(
        config,
        config_path=config_path,
        status="succeeded",
        changed_paths=changed_paths,
        backup_ref=safe_local_ref(backup_path, base=base) if backup_path else None,
    )


def dashboard_config_ref(config_path: Path) -> str:
    path = Path(config_path)
    if not path.is_absolute():
        return display_path(path, external_ref="<external-config>")
    return "<external-config>"


def _dashboard_config_temp_path(config_path: Path) -> Path:
    return config_path.with_name(f".{config_path.name}.{uuid4().hex}.dashboard-save.tmp")


def _write_text_for_validation(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())


def sanitize_dashboard_message(message: str, *, config_path: Path) -> str:
    safe_ref = dashboard_config_ref(config_path)
    variants = {str(config_path), config_path.as_posix()}
    try:
        variants.add(str(config_path.resolve()))
        variants.add(config_path.resolve().as_posix())
    except OSError:
        pass

    sanitized = message
    for value in sorted(variants, key=len, reverse=True):
        if value:
            sanitized = sanitized.replace(value, safe_ref)
    return sanitized


def _config_profile_field(config: dict[str, Any], field: dict[str, Any], *, config_path: Path | None = None) -> dict[str, Any]:
    path = str(field["path"])
    value = _get_config_value(config, path)
    if value is None:
        value = _config_profile_default(config, field, config_path=config_path)
    result = {
        "section": field["section"],
        "label": field["label"],
        "path": path,
        "control": field["control"],
        "value_type": field["value_type"],
        "value": value,
        "description": field.get("description") or "",
    }
    options = field.get("options")
    if isinstance(options, tuple):
        result["options"] = list(options)
    if field.get("virtual") is True:
        result["virtual"] = True
    return result


def _config_profile_field_definition(path: str) -> dict[str, Any] | None:
    for field in CONFIG_PROFILE_FIELDS:
        if field.get("path") == path:
            return field
    return None


def _config_profile_default(config: dict[str, Any], field: dict[str, Any], *, config_path: Path | None = None) -> Any:
    path = str(field.get("path") or "")
    trigger_id = _live_confirm_trigger_id(path)
    if trigger_id and config_path is not None:
        return _live_trigger_codex_authorization_valid(config, config_path=config_path, trigger_id=trigger_id)
    default_from = field.get("default_from")
    if isinstance(default_from, str):
        value = _get_config_value(config, default_from)
        if value is not None:
            return deepcopy(value)
    if "default" in field:
        value = deepcopy(field["default"])
        if field.get("value_type") == "string_list" and isinstance(value, tuple):
            return list(value)
        return value
    value_type = field.get("value_type")
    if value_type == "bool":
        return False
    if value_type == "positive_int":
        return 1
    if value_type == "positive_number":
        return 1.0
    if value_type == "string_list":
        options = field.get("options")
        return [options[0]] if isinstance(options, tuple) and options else []
    options = field.get("options")
    if isinstance(options, tuple) and options:
        return options[0]
    return ""


def _materialize_enabled_capability_defaults(config: dict[str, Any]) -> None:
    for prefix in ("market.derivatives", "text.intelligence", "macro_calendar", "onchain_flow"):
        if _get_config_value(config, f"{prefix}.enabled") is not True:
            continue
        for field in CONFIG_PROFILE_FIELDS:
            path = str(field.get("path") or "")
            if not path.startswith(f"{prefix}.") or path == f"{prefix}.enabled":
                continue
            if _get_config_value(config, path) is None:
                _set_config_value(config, path, _config_profile_default(config, field))
    _materialize_live_defaults(config)
    _normalize_ohlcv_lookback(config)
    _normalize_derivatives_lookback(config)


def _materialize_live_defaults(config: dict[str, Any]) -> None:
    if _get_config_value(config, "live.enabled") is not True:
        return
    if _get_config_value(config, "live.tick_seconds") is None:
        _set_config_value(config, "live.tick_seconds", DEFAULT_LIVE_TICK_SECONDS)
    for data_type in LIVE_DATA_TYPES:
        prefix = f"live.collections.{data_type}"
        if _get_config_value(config, f"{prefix}.enabled") is not True:
            continue
        defaults = LIVE_COLLECTION_DEFAULTS[data_type]
        for key, value in defaults.items():
            path = f"{prefix}.{key}"
            if _get_config_value(config, path) is None:
                _set_config_value(config, path, value)
    for trigger_id in LIVE_TRIGGER_IDS:
        prefix = f"live.reports.triggers.{trigger_id}"
        if _get_config_value(config, f"{prefix}.enabled") is not True:
            continue
        defaults = LIVE_TRIGGER_DEFAULTS[trigger_id]
        for key, value in defaults.items():
            path = f"{prefix}.{key}"
            if _get_config_value(config, path) is None:
                _set_config_value(config, path, value)


def _materialize_live_trigger_authorizations(
    config: dict[str, Any],
    *,
    config_path: Path,
    virtual_changes: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    if _get_config_value(config, "live.enabled") is not True:
        return errors
    for trigger_id in LIVE_TRIGGER_IDS:
        prefix = f"live.reports.triggers.{trigger_id}"
        if _get_config_value(config, f"{prefix}.enabled") is not True:
            continue
        if _get_config_value(config, f"{prefix}.job_intent") != "run":
            continue
        if _live_trigger_codex_authorization_valid(config, config_path=config_path, trigger_id=trigger_id):
            continue
        confirm_path = f"{prefix}.confirm_codex"
        if virtual_changes.get(confirm_path) is True:
            _set_config_value(
                config,
                f"{prefix}.codex_authorization",
                _live_trigger_codex_authorization(config, config_path=config_path, trigger_id=trigger_id),
            )
            continue
        errors.append(
            f"{confirm_path}: confirm this trigger before saving unattended Codex-capable Live `run` behavior."
        )
    return errors


def _live_confirm_trigger_id(path: str) -> str | None:
    parts = path.split(".")
    if len(parts) != 5:
        return None
    if parts[:3] != ["live", "reports", "triggers"] or parts[4] != "confirm_codex":
        return None
    trigger_id = parts[3]
    return trigger_id if trigger_id in LIVE_TRIGGER_IDS else None


def _live_trigger_codex_authorization(config: dict[str, Any], *, config_path: Path, trigger_id: str) -> dict[str, Any]:
    return {
        "authorized": True,
        "valid": True,
        "authorized_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "trigger_id": trigger_id,
        "trigger_revision": LIVE_TRIGGER_REVISION,
        "config_ref": _live_config_ref(config_path),
        "config_digest": _live_trigger_config_digest(config, config_path=config_path, trigger_id=trigger_id),
        "job_intent": "run",
        "authorization_scope": "unattended_live_trigger",
    }


def _live_trigger_codex_authorization_valid(config: dict[str, Any], *, config_path: Path, trigger_id: str) -> bool:
    data = _get_config_value(config, f"live.reports.triggers.{trigger_id}.codex_authorization")
    if not isinstance(data, dict):
        return False
    return (
        data.get("authorized") is True
        and data.get("job_intent") == "run"
        and data.get("authorization_scope") == "unattended_live_trigger"
        and data.get("trigger_id") == trigger_id
        and data.get("trigger_revision") == LIVE_TRIGGER_REVISION
        and data.get("config_digest") == _live_trigger_config_digest(config, config_path=config_path, trigger_id=trigger_id)
        and data.get("config_ref") == _live_config_ref(config_path)
    )


def _live_trigger_config_digest(config: dict[str, Any], *, config_path: Path, trigger_id: str) -> str:
    live = _as_mapping(config.get("live"))
    reports = _as_mapping(live.get("reports"))
    triggers = _as_mapping(reports.get("triggers"))
    trigger_config = _as_mapping(triggers.get(trigger_id))
    material = {
        "config_ref": _live_config_ref(config_path),
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
    return sha256(payload.encode("utf-8")).hexdigest()


def _live_config_ref(config_path: Path) -> str:
    path = Path(config_path)
    return display_path(path, external_ref="<external-config>") if not path.is_absolute() else "<external-config>"


def _as_mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _normalize_ohlcv_lookback(config: dict[str, Any]) -> None:
    market = _get_config_value(config, "market")
    if not isinstance(market, dict) or market.get("enabled") is not True:
        return
    ohlcv = market.get("ohlcv")
    if not isinstance(ohlcv, dict):
        return
    timeframes = ohlcv.get("timeframes")
    if not isinstance(timeframes, list):
        return
    lookback = ohlcv.get("lookback")
    if not isinstance(lookback, dict):
        lookback = {}
    normalized = {}
    for timeframe in [str(item) for item in timeframes]:
        normalized[timeframe] = lookback.get(timeframe, OHLCV_LOOKBACK_DEFAULTS.get(timeframe, 1))
    ohlcv["lookback"] = normalized


def _normalize_derivatives_lookback(config: dict[str, Any]) -> None:
    derivatives = _get_config_value(config, "market.derivatives")
    if not isinstance(derivatives, dict) or derivatives.get("enabled") is not True:
        return
    periods = derivatives.get("periods")
    if not isinstance(periods, list):
        return
    lookback = derivatives.get("lookback")
    if not isinstance(lookback, dict):
        lookback = {}
    normalized = {}
    for period in [str(item) for item in periods]:
        normalized[period] = lookback.get(period, DERIVATIVES_LOOKBACK_DEFAULTS.get(period, 1))
    derivatives["lookback"] = normalized


def _get_config_value(config: dict[str, Any], path: str) -> Any:
    current: Any = config
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _set_config_value(config: dict[str, Any], path: str, value: Any) -> None:
    current: dict[str, Any] = config
    parts = path.split(".")
    for part in parts[:-1]:
        child = current.get(part)
        if not isinstance(child, dict):
            child = {}
            current[part] = child
        current = child
    current[parts[-1]] = value


def _coerce_config_profile_value(raw_value: Any, field: dict[str, Any]) -> tuple[Any, str | None]:
    value_type = field.get("value_type")
    options = field.get("options")
    if value_type == "bool":
        if isinstance(raw_value, bool):
            return raw_value, None
        return None, "value must be true or false."
    if value_type == "positive_int":
        if isinstance(raw_value, bool):
            return None, "value must be a positive integer."
        try:
            value = int(raw_value)
        except (TypeError, ValueError):
            return None, "value must be a positive integer."
        if value <= 0:
            return None, "value must be a positive integer."
        return value, None
    if value_type == "positive_number":
        if isinstance(raw_value, bool):
            return None, "value must be a positive number."
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            return None, "value must be a positive number."
        if value <= 0:
            return None, "value must be a positive number."
        return value, None
    if value_type == "unit_interval_number":
        if isinstance(raw_value, bool):
            return None, "value must be a number between 0 and 1."
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            return None, "value must be a number between 0 and 1."
        if value < 0 or value > 1:
            return None, "value must be a number between 0 and 1."
        return value, None
    if value_type == "string_list":
        if not isinstance(raw_value, list):
            return None, "value must be a list of strings."
        values = [str(value).strip() for value in raw_value if str(value).strip()]
        if not values:
            return None, "value must include at least one string."
        if isinstance(options, tuple):
            unsupported = sorted(set(values) - set(str(option) for option in options))
            if unsupported:
                return None, f"unsupported value(s): {', '.join(unsupported)}."
        return values, None
    if not isinstance(raw_value, str) or not raw_value.strip():
        return None, "value must be a non-empty string."
    value = raw_value.strip()
    if isinstance(options, tuple) and value not in options:
        return None, f"value must be one of: {', '.join(str(option) for option in options)}."
    return value, None


def _serialize_config_yaml(config: dict[str, Any]) -> tuple[str, str | None]:
    try:
        import yaml
    except ModuleNotFoundError:
        return "", "PyYAML is required to save YAML config files."
    try:
        return yaml.safe_dump(config, allow_unicode=True, sort_keys=False), None
    except yaml.YAMLError as exc:
        return "", f"config could not be serialized as YAML: {exc}"


def _backup_dashboard_config(config_path: Path) -> tuple[Path | None, str | None]:
    config_dir = config_base(config_path)
    source = config_path if config_path.is_absolute() else config_dir / config_path.name
    if not source.exists():
        return None, f"{dashboard_config_ref(config_path)} was not found."
    safe_stem = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in source.stem) or "config"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup_dir = dashboard_control_path("config_backups")
    backup_path = backup_dir / f"{safe_stem}-{stamp}.yaml.bak"
    try:
        backup_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, backup_path)
    except OSError as exc:
        return None, sanitize_dashboard_message(f"config backup could not be created: {exc}", config_path=config_path)
    return backup_path, None


def _config_save_result(
    config: dict[str, Any],
    *,
    config_path: Path,
    status: str,
    changed_paths: list[str] | None = None,
    backup_ref: str | None = None,
    warnings: list[str] | None = None,
    errors: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "artifact_type": "dashboard_config_save_result",
        "status": status,
        "config": {"ref": dashboard_config_ref(config_path)},
        "changed_paths": changed_paths or [],
        "backup_ref": backup_ref,
        "profile": dashboard_config_profile(config, config_path=config_path),
        "warnings": warnings or [],
        "errors": errors or [],
        "omitted": {
            "absolute_local_paths_embedded": False,
            "raw_config_text_embedded": False,
            "credentials_embedded": False,
        },
    }


def _dashboard_config_candidate_records(config_path: Path | None, *, config_history: list[str] | None) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []

    def add(path: Path, *, source: str, label: str | None = None) -> None:
        candidate_id = _config_candidate_id(path)
        if any(record["id"] == candidate_id for record in records):
            return
        ref = display_path(path, base=Path.cwd(), external_ref="<external-config>")
        records.append(
            {
                "id": candidate_id,
                "_path": str(path),
                "label": label or _config_candidate_label(ref, source),
                "ref": ref,
                "source": source,
                "active": config_path is not None and Path(path).resolve() == Path(config_path).resolve(),
            }
        )

    if config_path is not None:
        add(Path(config_path), source="current", label="Current config" if dashboard_config_ref(config_path) == "<external-config>" else None)

    for path in _workspace_config_files():
        add(path, source="workspace")

    for item in config_history or []:
        if not item:
            continue
        add(Path(item), source="history")

    return records


def _workspace_config_files() -> list[Path]:
    root = Path.cwd()
    candidates: list[Path] = []
    for pattern in ("config*.yaml", "config*.yml"):
        candidates.extend(path for path in root.glob(pattern) if path.is_file())
    storage_dir = root / DEFAULT_CONFIG_STORAGE_DIR
    for pattern in ("*.yaml", "*.yml"):
        candidates.extend(path for path in storage_dir.glob(pattern) if path.is_file())
    return sorted(set(candidates), key=lambda path: display_path(path, base=root, external_ref="<external-config>"))


def _public_config_candidate(record: dict[str, Any]) -> dict[str, Any]:
    return {key: record[key] for key in ("id", "label", "ref", "source", "active") if key in record}


def _config_candidate_id(path: Path | None) -> str:
    if path is None:
        return ""
    return sha256(str(Path(path).resolve()).encode("utf-8")).hexdigest()[:20]


def _config_candidate_label(ref: str, source: str) -> str:
    if ref == "<external-config>":
        return "External config" if source != "current" else "Current external config"
    return ref


def _safe_config_file_name(name: str) -> str:
    raw_name = Path(name.replace("\\", "/")).name.strip()
    suffix = Path(raw_name).suffix.lower()
    if suffix not in {".yaml", ".yml"}:
        return ""
    safe = "".join(char if char.isalnum() or char in {"-", "_", "."} else "-" for char in raw_name)
    safe = safe.strip(".-")
    return safe if safe.lower().endswith((".yaml", ".yml")) else ""


def _unique_config_import_path(directory: Path, name: str) -> Path:
    candidate = directory / name
    if not candidate.exists():
        return candidate
    stem = candidate.stem
    suffix = candidate.suffix
    for index in range(2, 100):
        next_candidate = directory / f"{stem}-{index}{suffix}"
        if not next_candidate.exists():
            return next_candidate
    return directory / f"{stem}-{uuid4().hex[:8]}{suffix}"


def _config_import_result(
    *,
    status: str,
    config_path: str | None = None,
    config: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
    errors: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "artifact_type": "dashboard_config_import",
        "status": status,
        "config_path": config_path,
        "config": config or {"loaded": False, "ref": None},
        "warnings": warnings or [],
        "errors": errors or [],
        "omitted": {
            "absolute_local_paths_embedded": False,
            "raw_config_text_embedded": True,
            "credentials_embedded": False,
        },
    }
