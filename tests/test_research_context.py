from __future__ import annotations

import json
from pathlib import Path

from halpha.config import load_config
from halpha.pipeline import run_pipeline
from halpha.storage import write_json


def test_pipeline_generates_research_context_with_embedded_materials(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    result = run_pipeline(
        config,
        config_path=config_path,
        stage_handlers={
            "collect_market_data": _write_market_raw,
            "collect_text_events": _write_text_raw,
            "run_codex_report": _skip_codex_report,
        },
    )

    assert result.succeeded is True
    assert result.failed_stage is None

    context = (result.run.analysis_dir / "research_context.md").read_text(encoding="utf-8")
    assert "artifact_type: research_context" in context
    assert "audience: codex_cli" in context
    assert "language_target: zh-CN" in context
    assert "raw_market: raw/market.json" in context
    assert "raw_text_events: raw/text_events.json" in context
    assert "market_material: analysis/market_material.md" in context
    assert "text_material: analysis/text_material.md" in context
    assert "## source_policy" in context
    assert "allowed_sources_only: true" in context
    assert "fabricate_missing_sources: false" in context
    assert "financial_advice: false" in context
    assert "## generation_constraints" in context
    assert "do_not_invent_prices_events_links_sources: true" in context
    assert "include_context_specific_risk_notes: true" in context
    assert "avoid_generic_disclaimers: true" in context
    assert "prefer_tables_for_comparable_data: true" in context
    assert "group_multi_symbol_sections_by_symbol: true" in context
    assert "title_is_h1_not_section: true" in context
    assert "synthesis_should_not_repeat_prior_sections: true" in context
    assert "quant_signal_requirements:" in context
    assert "include_signal_conclusions: true" in context
    assert "include_evidence_near_conclusions: true" in context
    assert "include_uncertainty_near_conclusions: true" in context
    assert "include_watch_points: true" in context
    assert "include_risk_notes: true" in context
    assert "do_not_calculate_signals_from_raw_ohlcv_history: true" in context
    assert "do_not_inspect_shared_ohlcv_storage: true" in context
    assert "required_sections:" in context
    assert "- 核心摘要" in context
    assert "- 标题" not in context
    assert "- market_overview" not in context
    assert '<embed path="analysis/market_material.md">' in context
    assert "artifact_type: analysis_market_material" in context
    assert '<embed path="analysis/text_material.md">' in context
    assert "artifact_type: analysis_text_material" in context
    assert "content_text: Source-provided event text." in context

    manifest = json.loads(result.run.manifest_path.read_text(encoding="utf-8"))
    assert manifest["artifacts"]["research_context"] == "analysis/research_context.md"
    research_stage = _stage(manifest, "build_research_context")
    codex_context_stage = _stage(manifest, "build_codex_context")
    report_stage = _stage(manifest, "run_codex_report")
    assert research_stage["status"] == "succeeded"
    assert research_stage["artifacts"] == ["analysis/research_context.md"]
    assert codex_context_stage["status"] == "succeeded"
    assert report_stage["status"] == "succeeded"


def test_research_context_marks_disabled_text_material_as_not_generated(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, text_enabled=False)
    config = load_config(config_path)

    result = run_pipeline(
        config,
        config_path=config_path,
        stage_handlers={
            "collect_market_data": _write_market_raw,
            "run_codex_report": _skip_codex_report,
        },
    )

    assert result.succeeded is True
    assert result.failed_stage is None
    assert not (result.run.analysis_dir / "text_material.md").exists()

    context = (result.run.analysis_dir / "research_context.md").read_text(encoding="utf-8")
    assert "market_material: analysis/market_material.md" in context
    assert "text_material: null" in context
    assert "artifact: analysis/text_material.md" in context
    assert "status: not_generated" in context


def test_research_context_embeds_market_signal_material_when_quant_enabled(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, quant_enabled=True, text_enabled=False)
    config = load_config(config_path)

    result = run_pipeline(
        config,
        config_path=config_path,
        stage_handlers={
            "collect_market_data": _write_market_raw,
            "collect_text_events": _noop_stage,
            "sync_ohlcv": _noop_stage,
            "build_market_data_views": _write_market_data_views,
            "evaluate_market_strategy_signals": _write_strategy_signals,
            "run_codex_report": _skip_codex_report,
        },
    )

    assert result.succeeded is True
    context = (result.run.analysis_dir / "research_context.md").read_text(encoding="utf-8")
    manifest = json.loads(result.run.manifest_path.read_text(encoding="utf-8"))
    assert "market_data_views: raw/market_data_views.json" in context
    assert "market_strategy_signals: analysis/market_strategy_signals.json" in context
    assert "market_signals: analysis/market_signals.json" in context
    assert "market_signal_material: analysis/market_signal_material.md" in context
    assert '<embed path="analysis/market_signal_material.md">' in context
    assert "artifact_type: analysis_market_signal_material" in context
    assert "raw_ohlcv_history_embedded: false" in context
    assert "include_signal_conclusions: true" in context
    assert "include_evidence_near_conclusions: true" in context
    assert "include_uncertainty_near_conclusions: true" in context
    assert "record_type: market_signal" in context
    assert "signal_id: market_signal:tsmom_vol_scaled:binance:BTCUSDT:1d:2026-06-03T00:00:00Z" in context
    assert "open_time:" not in context
    assert manifest["artifacts"]["market_signal_material"] == "analysis/market_signal_material.md"
    assert manifest["artifacts"]["research_context"] == "analysis/research_context.md"


def test_research_context_fails_when_enabled_material_is_missing(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    result = run_pipeline(
        config,
        config_path=config_path,
        stage_handlers={
            "collect_market_data": _write_market_raw,
            "collect_text_events": _write_text_raw,
            "build_analysis_materials": _skip_analysis_materials,
        },
    )

    assert result.succeeded is False
    assert result.failed_stage == "build_research_context"
    assert result.reason == "analysis/market_material.md was not found; build_analysis_materials must run first."
    assert not (result.run.analysis_dir / "research_context.md").exists()

    manifest = json.loads(result.run.manifest_path.read_text(encoding="utf-8"))
    assert _stage(manifest, "build_research_context")["status"] == "failed"
    assert manifest["errors"] == [
        {
            "stage": "build_research_context",
            "message": "analysis/market_material.md was not found; build_analysis_materials must run first.",
        }
    ]


def _write_config(
    tmp_path: Path,
    *,
    text_enabled: bool = True,
    quant_enabled: bool = False,
) -> Path:
    config_path = tmp_path / "config.yaml"
    text_block = (
        """
text:
  enabled: true
  max_items: 1
  sources:
    - name: coindesk
      type: rss
      url: https://www.coindesk.com/arc/outboundfeeds/rss/
"""
        if text_enabled
        else """
text:
  enabled: false
"""
    )
    ohlcv_block = (
        """
  ohlcv:
    storage_dir: data/market/ohlcv
    timeframes:
      - 1d
    lookback:
      1d: 3
"""
        if quant_enabled
        else ""
    )
    quant_block = (
        """
quant:
  enabled: true
  engine: vectorbt
  strategies:
    - name: tsmom_vol_scaled
"""
        if quant_enabled
        else ""
    )
    config_path.write_text(
        f"""
run:
  output_dir: runs
  timezone: Asia/Shanghai
market:
  enabled: true
  source: binance
  symbols:
    - BTCUSDT
{ohlcv_block.rstrip()}
{text_block.rstrip()}
{quant_block.rstrip()}
report:
  title: Daily Market Brief
  language: zh-CN
codex:
  enabled: true
  command: codex
  args:
    - exec
    - --sandbox
    - read-only
    - "-"
  timeout_seconds: 300
""".strip(),
        encoding="utf-8",
    )
    return config_path


def _write_market_raw(config, run) -> list[str]:
    write_json(
        run.raw_dir / "market.json",
        {
            "schema_version": 1,
            "artifact_type": "market_raw",
            "collector": "market",
            "collection_method": "public_http",
            "source": {
                "name": "binance",
                "url": "https://data-api.binance.vision",
            },
            "collected_at": "2026-06-05T00:30:00Z",
            "items": [
                {
                    "id": "market:binance:BTCUSDT:2026-06-05T00:30:00Z",
                    "symbol": "BTCUSDT",
                    "as_of": "2026-06-05T00:30:00Z",
                    "metrics": {
                        "price": "68000.00",
                        "change_24h_pct": "1.25",
                        "volume_24h": "123.45",
                        "quote_volume_24h": "8394600.00",
                    },
                    "source": {
                        "name": "binance",
                        "url": "https://data-api.binance.vision",
                    },
                }
            ],
            "errors": [],
        },
    )
    run.manifest["artifacts"]["raw_market"] = "raw/market.json"
    run.manifest["counts"]["market_items"] = 1
    return ["raw/market.json"]


def _write_text_raw(config, run) -> list[str]:
    write_json(
        run.raw_dir / "text_events.json",
        {
            "schema_version": 1,
            "artifact_type": "text_events_raw",
            "collector": "text",
            "collection_method": "rss",
            "collected_at": "2026-06-05T00:31:00Z",
            "sources": [
                {
                    "name": "coindesk",
                    "type": "rss",
                    "url": "https://www.coindesk.com/arc/outboundfeeds/rss/",
                }
            ],
            "items": [
                {
                    "id": "text:coindesk:event-1",
                    "type": "rss_item",
                    "title": "Bitcoin market event",
                    "published_at": "2026-06-05T00:30:00Z",
                    "source": {
                        "name": "coindesk",
                        "url": "https://www.coindesk.com/arc/outboundfeeds/rss/",
                    },
                    "link": "https://example.com/bitcoin-event",
                    "content_text": "Source-provided event text.",
                    "language": None,
                }
            ],
            "errors": [],
        },
    )
    run.manifest["artifacts"]["raw_text_events"] = "raw/text_events.json"
    run.manifest["counts"]["text_event_items"] = 1
    return ["raw/text_events.json"]


def _write_market_data_views(config, run) -> list[str]:
    write_json(
        run.raw_dir / "market_data_views.json",
        {
            "schema_version": 1,
            "artifact_type": "market_data_views",
            "created_at": "2026-06-05T00:00:00Z",
            "source_artifacts": ["data/market/metadata/ohlcv_sync_state.json"],
            "views": [
                {
                    "view_id": "ohlcv_view:binance:BTCUSDT:1d:2026-06-03T00:00:00Z",
                    "source": "binance",
                    "symbol": "BTCUSDT",
                    "timeframe": "1d",
                    "requested_lookback": 3,
                    "input_window_start": "2026-06-01T00:00:00Z",
                    "input_window_end": "2026-06-03T00:00:00Z",
                    "latest_candle_time": "2026-06-03T00:00:00Z",
                    "row_count": 3,
                    "storage_ref": "data/market/ohlcv/source=binance/symbol=BTCUSDT/timeframe=1d",
                    "included_columns": ["open_time", "open", "high", "low", "close", "volume"],
                    "insufficient_data": False,
                    "warnings": [],
                }
            ],
        },
    )
    run.manifest["artifacts"]["market_data_views"] = "raw/market_data_views.json"
    run.manifest["counts"]["market_data_views"] = 1
    run.manifest["counts"]["market_data_views_insufficient_data"] = 0
    return ["raw/market_data_views.json"]


def _write_strategy_signals(config, run) -> list[str]:
    write_json(
        run.analysis_dir / "market_strategy_signals.json",
        {
            "schema_version": 1,
            "artifact_type": "market_strategy_signals",
            "created_at": "2026-06-05T00:00:00Z",
            "source_artifacts": ["raw/market_data_views.json"],
            "signals": [
                {
                    "strategy_signal_id": (
                        "strategy_signal:tsmom_vol_scaled:binance:BTCUSDT:1d:2026-06-03T00:00:00Z"
                    ),
                    "strategy_name": "tsmom_vol_scaled",
                    "source": "binance",
                    "symbol": "BTCUSDT",
                    "timeframe": "1d",
                    "input_view_id": "ohlcv_view:binance:BTCUSDT:1d:2026-06-03T00:00:00Z",
                    "input_window_start": "2026-06-01T00:00:00Z",
                    "input_window_end": "2026-06-03T00:00:00Z",
                    "latest_candle_time": "2026-06-03T00:00:00Z",
                    "direction": "bullish",
                    "strength": "medium",
                    "confidence": "medium",
                    "key_values": {"latest_close": 106.0, "row_count": 3},
                    "evidence": ["return_window_pct is 6.0% over the configured return window."],
                    "uncertainty": [
                        "Strategy uses OHLCV close prices only and excludes text events."
                    ],
                    "insufficient_data": False,
                    "source_artifacts": ["raw/market_data_views.json"],
                    "created_at": "2026-06-05T00:00:00Z",
                }
            ],
        },
    )
    run.manifest["artifacts"]["market_strategy_signals"] = "analysis/market_strategy_signals.json"
    run.manifest["counts"]["market_strategy_signals"] = 1
    run.manifest["counts"]["market_strategy_signals_insufficient_data"] = 0
    return ["analysis/market_strategy_signals.json"]


def _skip_analysis_materials(config, run) -> list[str]:
    return []


def _noop_stage(config, run) -> list[str]:
    return []


def _skip_codex_report(config, run) -> list[str]:
    return []


def _stage(manifest: dict, name: str) -> dict:
    return next(stage for stage in manifest["stages"] if stage["name"] == name)
