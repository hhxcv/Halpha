from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from halpha.config import load_config
from halpha.data_quality import build_data_quality_summary, refresh_m13_data_quality_checks
from halpha.pipeline import RunContext, run_pipeline
from halpha.storage import write_json


def test_data_quality_summary_records_clean_current_run_state(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, include_ohlcv=False)
    config = load_config(config_path)
    result = run_pipeline(
        config,
        config_path=config_path,
        until_stage="build_data_quality_summary",
        stage_handlers={
            "collect_market_data": _write_market_raw,
            "collect_text_events": _write_text_raw,
            "sync_ohlcv": _noop_stage,
            "build_market_data_views": _noop_stage,
        },
    )

    assert result.succeeded is True
    summary = _summary(result.run.analysis_dir)
    manifest = _manifest(result.run.manifest_path)

    assert summary["artifact_type"] == "data_quality_summary"
    assert summary["status"] == "ok"
    assert summary["counts"]["checks"] == 25
    assert summary["counts"]["failed"] == 0
    assert summary["counts"]["degraded"] == 0
    assert manifest["artifacts"]["data_quality_summary"] == "analysis/data_quality_summary.json"
    assert manifest["data_quality_summary"]["status"] == "ok"
    assert _check(summary, "raw_market")["status"] == "ok"
    assert _check(summary, "raw_text")["status"] == "ok"
    assert _check(summary, "ohlcv_store")["status"] == "skipped"
    assert _check(summary, "raw_derivatives_market")["status"] == "skipped"
    assert _check(summary, "derivatives_market_history")["status"] == "skipped"
    assert _check(summary, "derivatives_market_views")["status"] == "skipped"
    assert _check(summary, "raw_macro_calendar")["status"] == "skipped"
    assert _check(summary, "macro_calendar_history")["status"] == "skipped"
    assert _check(summary, "macro_calendar_views")["status"] == "skipped"
    assert _check(summary, "macro_calendar_context")["status"] == "skipped"
    assert _check(summary, "macro_calendar_material")["status"] == "skipped"
    assert _check(summary, "raw_onchain_flow")["status"] == "skipped"
    assert _check(summary, "onchain_flow_history")["status"] == "skipped"
    assert _check(summary, "onchain_flow_views")["status"] == "skipped"
    assert _check(summary, "onchain_flow_context")["status"] == "skipped"
    assert _check(summary, "onchain_flow_material")["status"] == "skipped"
    for name in ("feature_snapshots", "factor_states", "multi_source_signals", "factor_signal_material"):
        m13_check = _check(summary, name)
        assert m13_check["status"] == "skipped"
        assert m13_check["details"]["stage_time_skip_is_expected"] is True
    assert _check(summary, "text_event_history")["status"] == "ok"
    run_index = _check(summary, "run_index")
    assert run_index["status"] == "skipped"
    assert "terminal artifact written after the data-quality stage" in run_index["summary"]
    assert run_index["details"]["stage_time_skip_is_expected"] is True
    assert run_index["details"]["report_as_final_missing"] is False


def test_data_quality_summary_flags_schema_drift_future_timestamp_and_duplicates(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    run = _run_context(tmp_path, config_path)
    write_json(
        run.raw_dir / "market.json",
        {
            "items": [
                {
                    "id": "market:binance:BTCUSDT:future",
                    "symbol": "BTCUSDT",
                    "as_of": "2026-06-06T00:00:00Z",
                    "source": {"name": "binance"},
                }
            ],
            "errors": [],
        },
    )
    write_json(
        run.raw_dir / "text_events.json",
        {"items": [{"id": "broken", "title": "Broken", "source": {"name": "coindesk"}}], "errors": []},
    )
    write_json(
        run.analysis_dir / "text_event_records.json",
        {
            "records": [
                _event_record("one", canonical_url="https://example.com/a", text="one"),
                _event_record("two", canonical_url="https://example.com/a", text="two"),
            ]
        },
    )

    build_data_quality_summary(_config(), run, now="2026-06-05T00:00:00Z")

    summary = _summary(run.analysis_dir)
    assert summary["status"] == "failed"
    assert _check(summary, "raw_market")["status"] == "warning"
    assert "is in the future" in _check(summary, "raw_market")["details"]["warnings"][0]
    assert _check(summary, "raw_text")["status"] == "failed"
    assert "content_text is required" in _check(summary, "raw_text")["details"]["errors"][0]
    text_records = _check(summary, "text_event_records")
    assert text_records["status"] == "warning"
    assert text_records["details"]["duplicate_records"] == 1
    assert text_records["details"]["conflicting_duplicates"] == 1


def test_data_quality_summary_records_partial_collection_and_optional_skips(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, include_ohlcv=False)
    run = _run_context(tmp_path, config_path)
    write_json(
        run.raw_dir / "market.json",
        {
            "items": [
                {
                    "id": "market:binance:BTCUSDT:now",
                    "symbol": "BTCUSDT",
                    "as_of": "2026-06-05T00:00:00Z",
                    "source": {"name": "binance"},
                }
            ],
            "errors": [{"message": "one market source failed"}],
        },
    )
    run.manifest["artifacts"]["raw_market"] = "raw/market.json"

    build_data_quality_summary(_config(include_ohlcv=False, text_enabled=False), run, now="2026-06-05T00:00:00Z")

    summary = _summary(run.analysis_dir)
    assert summary["status"] == "degraded"
    assert _check(summary, "raw_text")["status"] == "skipped"
    assert _check(summary, "ohlcv_store")["status"] == "skipped"
    assert _check(summary, "partial_collection")["status"] == "degraded"


def test_data_quality_summary_refreshes_m13_artifact_checks_ok(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, include_ohlcv=False)
    run = _run_context(tmp_path, config_path)
    _write_initial_quality_summary(run)
    _write_m13_artifacts(run)

    refresh_m13_data_quality_checks(_config(include_ohlcv=False, text_enabled=False), run, now="2026-06-05T00:00:00Z")

    summary = _summary(run.analysis_dir)
    assert summary["status"] == "ok"
    assert summary["counts"]["checks"] == 4
    assert _check(summary, "feature_snapshots")["status"] == "ok"
    assert _check(summary, "factor_states")["status"] == "ok"
    assert _check(summary, "multi_source_signals")["status"] == "ok"
    material = _check(summary, "factor_signal_material")
    assert material["status"] == "ok"
    assert material["details"]["codex_boundaries_present"] is True
    assert material["details"]["codex_budget_status"] == "not_available_before_codex_context"
    assert run.manifest["counts"]["data_quality_checks"] == 4


def test_data_quality_summary_refreshes_m13_artifact_checks_warning(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, include_ohlcv=False)
    run = _run_context(tmp_path, config_path)
    _write_initial_quality_summary(run)
    _write_m13_artifacts(run, feature_status="warning", feature_warnings=["one source was partial."])

    refresh_m13_data_quality_checks(_config(include_ohlcv=False, text_enabled=False), run, now="2026-06-05T00:00:00Z")

    summary = _summary(run.analysis_dir)
    assert summary["status"] == "warning"
    feature = _check(summary, "feature_snapshots")
    assert feature["status"] == "warning"
    assert feature["warning_count"] == 1


def test_data_quality_summary_refreshes_m13_artifact_checks_degraded(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, include_ohlcv=False)
    run = _run_context(tmp_path, config_path)
    _write_initial_quality_summary(run)
    _write_m13_artifacts(run, factor_status="degraded")

    refresh_m13_data_quality_checks(_config(include_ohlcv=False, text_enabled=False), run, now="2026-06-05T00:00:00Z")

    summary = _summary(run.analysis_dir)
    assert summary["status"] == "degraded"
    assert _check(summary, "factor_states")["status"] == "degraded"


def test_data_quality_summary_refreshes_m13_artifact_checks_missing_as_failed(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, include_ohlcv=False)
    run = _run_context(tmp_path, config_path)
    _write_initial_quality_summary(run)

    refresh_m13_data_quality_checks(_config(include_ohlcv=False, text_enabled=False), run, now="2026-06-05T00:00:00Z")

    summary = _summary(run.analysis_dir)
    assert summary["status"] == "failed"
    assert summary["counts"]["failed"] == 4
    assert _check(summary, "feature_snapshots")["details"]["report_as_final_missing"] is True


def test_data_quality_summary_reports_derivatives_quality_states(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, include_ohlcv=False)
    run = _run_context(tmp_path, config_path)
    _write_market_raw({}, run)
    _write_derivatives_raw(run)
    _write_derivatives_state(tmp_path)
    _write_derivatives_views(run)
    run.manifest["derivatives_market_history"] = {
        "status": "warning",
        "artifact": "data/market/metadata/derivatives_market_state.json",
    }

    build_data_quality_summary(
        _config(include_ohlcv=False, text_enabled=False, derivatives_enabled=True),
        run,
        now="2026-06-05T00:00:00Z",
    )

    summary = _summary(run.analysis_dir)
    raw = _check(summary, "raw_derivatives_market")
    history = _check(summary, "derivatives_market_history")
    views = _check(summary, "derivatives_market_views")

    assert summary["status"] == "degraded"
    assert raw["status"] == "degraded"
    assert raw["details"]["items"] == 1
    assert raw["details"]["availability_records"] == 4
    assert raw["details"]["unavailable_records"] == 2
    assert raw["details"]["partial_records"] == 1
    assert raw["details"]["failed_records"] == 1
    assert raw["details"]["stale_records"] == 0
    assert raw["details"]["degraded_records"] == 0
    assert any("metric funding_rate is missing" in warning for warning in raw["details"]["warnings"])
    assert any("is stale" in warning for warning in raw["details"]["warnings"])
    assert any("derivatives availability basis BTCUSDT 5m" in warning for warning in raw["details"]["warnings"])
    assert any(
        "derivatives availability liquidation_summary BTCUSDT source_availability" in warning
        for warning in raw["details"]["warnings"]
    )
    assert "funding rate source returned partial data" in raw["details"]["errors"]

    assert history["status"] == "warning"
    assert history["details"]["records"] == 1
    assert history["details"]["duplicate_records"] == 1
    assert history["details"]["conflicting_duplicates"] == 1
    assert "derivatives endpoint returned an unavailable optional class" in history["details"]["errors"]

    assert views["status"] == "warning"
    assert views["details"]["views"] == 3
    assert views["details"]["insufficient_views"] == 3
    assert views["details"]["missing_history_views"] == 1
    assert views["details"]["skipped_views"] == 1
    assert any("unsupported derivatives class" in warning for warning in views["details"]["warnings"])
    assert _check(summary, "partial_collection")["status"] == "degraded"


def test_data_quality_summary_reports_macro_calendar_quality_states(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, include_ohlcv=False)
    run = _run_context(tmp_path, config_path)
    _write_market_raw({}, run)
    _write_macro_raw(run)
    _write_macro_state(tmp_path)
    _write_macro_views(run)
    _write_macro_context(run)
    _write_macro_material(run)
    run.manifest["macro_calendar_history"] = {
        "status": "warning",
        "artifact": "data/macro/metadata/macro_calendar_state.json",
    }

    build_data_quality_summary(
        _config(include_ohlcv=False, text_enabled=False, macro_enabled=True),
        run,
        now="2026-06-05T00:00:00Z",
    )

    summary = _summary(run.analysis_dir)
    raw = _check(summary, "raw_macro_calendar")
    history = _check(summary, "macro_calendar_history")
    views = _check(summary, "macro_calendar_views")
    context = _check(summary, "macro_calendar_context")
    material = _check(summary, "macro_calendar_material")

    assert summary["status"] == "degraded"
    assert raw["status"] == "degraded"
    assert raw["details"]["items"] == 1
    assert raw["details"]["availability_records"] == 6
    assert raw["details"]["no_event_records"] == 1
    assert raw["details"]["unavailable_records"] == 1
    assert raw["details"]["partial_records"] == 1
    assert raw["details"]["failed_records"] == 1
    assert raw["details"]["stale_records"] == 1
    assert raw["details"]["degraded_records"] == 1
    assert any(
        "macro calendar availability federal_reserve_fomc central_bank_event US" in warning
        for warning in raw["details"]["warnings"]
    )
    assert "macro calendar source failed" in raw["details"]["errors"]

    assert history["status"] == "warning"
    assert history["details"]["records"] == 1
    assert history["details"]["duplicate_records"] == 1
    assert history["details"]["conflicting_duplicates"] == 1
    assert history["details"]["no_event_records"] == 1
    assert "macro calendar duplicate conflict" in history["details"]["warnings"]

    assert views["status"] == "warning"
    assert views["details"]["views"] == 4
    assert views["details"]["records"] == 1
    assert views["details"]["no_event_views"] == 1
    assert views["details"]["stale_views"] == 1
    assert views["details"]["skipped_views"] == 1
    assert any("macro calendar view is stale" in warning for warning in views["details"]["warnings"])

    assert context["status"] == "warning"
    assert context["details"]["records"] == 2
    assert context["details"]["scheduled_catalyst"] == 1
    assert context["details"]["source_availability"] == 1
    assert context["details"]["stale"] == 1

    assert material["status"] == "ok"
    assert material["details"]["selected_records"] == 2
    assert material["details"]["omitted_records"] == 0
    assert material["details"]["codex_boundaries_present"] is True
    assert _check(summary, "partial_collection")["status"] == "degraded"


def test_data_quality_summary_reports_onchain_flow_quality_states(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, include_ohlcv=False)
    run = _run_context(tmp_path, config_path)
    _write_market_raw({}, run)
    _write_onchain_flow_raw(run)
    _write_onchain_flow_state(tmp_path)
    _write_onchain_flow_views(run)
    _write_onchain_flow_context(run)
    _write_onchain_flow_material(run)
    run.manifest["onchain_flow_history"] = {
        "status": "warning",
        "artifact": "data/onchain/metadata/onchain_flow_state.json",
    }

    build_data_quality_summary(
        _config(include_ohlcv=False, text_enabled=False, onchain_enabled=True),
        run,
        now="2026-06-05T00:00:00Z",
    )

    summary = _summary(run.analysis_dir)
    raw = _check(summary, "raw_onchain_flow")
    history = _check(summary, "onchain_flow_history")
    views = _check(summary, "onchain_flow_views")
    context = _check(summary, "onchain_flow_context")
    material = _check(summary, "onchain_flow_material")

    assert summary["status"] == "degraded"
    assert raw["status"] == "degraded"
    assert raw["details"]["items"] == 1
    assert raw["details"]["availability_records"] == 6
    assert raw["details"]["unavailable_records"] == 1
    assert raw["details"]["partial_records"] == 1
    assert raw["details"]["failed_records"] == 1
    assert raw["details"]["stale_records"] == 1
    assert raw["details"]["degraded_records"] == 1
    assert raw["details"]["insufficient_data_records"] == 1
    assert any("metric total_circulating_usd is missing" in warning for warning in raw["details"]["warnings"])
    assert any("on-chain flow availability defillama_stablecoins stablecoin_supply" in warning for warning in raw["details"]["warnings"])
    assert "on-chain source returned partial data" in raw["details"]["errors"]

    assert history["status"] == "warning"
    assert history["details"]["records"] == 1
    assert history["details"]["duplicate_records"] == 1
    assert history["details"]["conflicting_duplicates"] == 1
    assert history["details"]["availability_records"] == 1
    assert history["details"]["partial_records"] == 1
    assert "on-chain duplicate conflict" in history["details"]["warnings"]

    assert views["status"] == "warning"
    assert views["details"]["views"] == 4
    assert views["details"]["records"] == 1
    assert views["details"]["bounded_views"] == 1
    assert views["details"]["partial_views"] == 1
    assert views["details"]["stale_views"] == 1
    assert views["details"]["skipped_views"] == 1
    assert any("on-chain flow view is stale" in warning for warning in views["details"]["warnings"])

    assert context["status"] == "warning"
    assert context["details"]["records"] == 2
    assert context["details"]["stablecoin_liquidity"] == 1
    assert context["details"]["exchange_flow_source_availability"] == 1
    assert context["details"]["stale"] == 1

    assert material["status"] == "ok"
    assert material["details"]["selected_records"] == 2
    assert material["details"]["omitted_records"] == 0
    assert material["details"]["codex_boundaries_present"] is True
    assert _check(summary, "partial_collection")["status"] == "degraded"


def _write_config(tmp_path: Path, *, include_ohlcv: bool = True) -> Path:
    ohlcv = ""
    if include_ohlcv:
        ohlcv = """
  ohlcv:
    storage_dir: data/market/ohlcv
    timeframes:
      - 1d
    lookback:
      1d: 2
"""
    path = tmp_path / "config.yaml"
    path.write_text(
        f"""
run:
  output_dir: runs
market:
  enabled: true
  source: binance
  symbols:
    - BTCUSDT
{ohlcv.rstrip()}
text:
  enabled: true
  max_items: 1
  sources:
    - name: coindesk
      type: rss
      url: https://example.com/rss.xml
report:
  language: zh-CN
codex:
  enabled: false
""".strip(),
        encoding="utf-8",
    )
    return path


def _config(
    *,
    include_ohlcv: bool = True,
    text_enabled: bool = True,
    derivatives_enabled: bool = False,
    macro_enabled: bool = False,
    onchain_enabled: bool = False,
) -> dict[str, Any]:
    market: dict[str, Any] = {
        "enabled": True,
        "source": "binance",
        "symbols": ["BTCUSDT"],
    }
    if include_ohlcv:
        market["ohlcv"] = {"storage_dir": "data/market/ohlcv", "timeframes": ["1d"], "lookback": {"1d": 2}}
    if derivatives_enabled:
        market["derivatives"] = {
            "enabled": True,
            "source": "binance_usdm",
            "symbols": ["BTCUSDT"],
            "data_classes": ["funding_rate", "basis", "open_interest"],
            "periods": ["5m"],
            "lookback": {"5m": 2},
        }
    return {
        "market": market,
        "macro_calendar": {
            "enabled": macro_enabled,
            "source": "federal_reserve_fomc",
            "data_classes": ["central_bank_event"],
            "regions": ["US"],
            "lookback_days": 7,
            "lookahead_days": 45,
        },
        "onchain_flow": {
            "enabled": onchain_enabled,
            "source": "public_aggregate",
            "data_classes": ["stablecoin_supply", "exchange_flow_availability"],
            "assets": ["ALL_STABLECOINS", "BTC"],
            "chains": ["all", "bitcoin"],
            "lookback_days": 7,
        },
        "text": {"enabled": text_enabled},
    }


def _run_context(tmp_path: Path, config_path: Path) -> RunContext:
    run_dir = tmp_path / "runs" / "run-1"
    raw_dir = run_dir / "raw"
    analysis_dir = run_dir / "analysis"
    codex_context_dir = run_dir / "codex_context"
    report_dir = run_dir / "report"
    for directory in (raw_dir, analysis_dir, codex_context_dir, report_dir):
        directory.mkdir(parents=True, exist_ok=True)
    return RunContext(
        run_id="run-1",
        run_dir=run_dir,
        raw_dir=raw_dir,
        analysis_dir=analysis_dir,
        codex_context_dir=codex_context_dir,
        report_dir=report_dir,
        manifest_path=run_dir / "run_manifest.json",
        config_path=config_path,
        manifest={"artifacts": {}, "counts": {}, "errors": []},
    )


def _write_initial_quality_summary(run: RunContext) -> None:
    write_json(
        run.analysis_dir / "data_quality_summary.json",
        {
            "schema_version": 1,
            "artifact_type": "data_quality_summary",
            "run_id": run.run_id,
            "created_at": "2026-06-05T00:00:00Z",
            "status": "ok",
            "checks": [],
            "counts": {
                "checks": 0,
                "ok": 0,
                "warning": 0,
                "degraded": 0,
                "skipped": 0,
                "failed": 0,
                "warnings": 0,
                "errors": 0,
            },
            "warnings": [],
            "errors": [],
            "source_artifacts": [],
        },
    )


def _write_m13_artifacts(
    run: RunContext,
    *,
    feature_status: str = "ok",
    feature_warnings: list[str] | None = None,
    factor_status: str = "ok",
    signal_status: str = "ok",
) -> None:
    feature_warnings = feature_warnings or []
    write_json(
        run.analysis_dir / "feature_snapshots.json",
        {
            "schema_version": 1,
            "artifact_type": "feature_snapshots",
            "run_id": run.run_id,
            "created_at": "2026-06-05T00:00:00Z",
            "status": feature_status,
            "coverage": [{"source_layer": "market", "status": "ok"}],
            "records": [
                {
                    "feature_id": "feature:BTCUSDT:trend",
                    "feature_type": "price_trend",
                    "status": "ok",
                    "warnings": [],
                    "errors": [],
                }
            ],
            "counts": {
                "records": 1,
                "coverage_records": 1,
                "warnings": len(feature_warnings),
                "errors": 0,
            },
            "warnings": feature_warnings,
            "errors": [],
            "source_artifacts": ["analysis/market_signals.json"],
        },
    )
    run.manifest["artifacts"]["feature_snapshots"] = "analysis/feature_snapshots.json"
    run.manifest["feature_snapshots"] = {
        "status": feature_status,
        "artifact": "analysis/feature_snapshots.json",
        "records": 1,
        "coverage_records": 1,
        "warnings": len(feature_warnings),
        "errors": 0,
    }
    run.manifest["counts"]["feature_snapshots"] = 1
    run.manifest["counts"]["feature_snapshot_coverage_records"] = 1
    run.manifest["counts"]["feature_snapshot_warnings"] = len(feature_warnings)
    run.manifest["counts"]["feature_snapshot_errors"] = 0

    write_json(
        run.analysis_dir / "factor_states.json",
        {
            "schema_version": 1,
            "artifact_type": "factor_states",
            "run_id": run.run_id,
            "created_at": "2026-06-05T00:00:00Z",
            "status": factor_status,
            "records": [{"factor_id": "factor:BTCUSDT:trend", "state": "supportive"}],
            "counts": {"records": 1, "warnings": 0, "errors": 0},
            "warnings": [],
            "errors": [],
            "source_artifacts": ["analysis/feature_snapshots.json"],
        },
    )
    run.manifest["artifacts"]["factor_states"] = "analysis/factor_states.json"
    run.manifest["factor_states"] = {
        "status": factor_status,
        "artifact": "analysis/factor_states.json",
        "records": 1,
        "warnings": 0,
        "errors": 0,
    }
    run.manifest["counts"]["factor_states"] = 1
    run.manifest["counts"]["factor_state_warnings"] = 0
    run.manifest["counts"]["factor_state_errors"] = 0

    write_json(
        run.analysis_dir / "multi_source_signals.json",
        {
            "schema_version": 1,
            "artifact_type": "multi_source_signals",
            "run_id": run.run_id,
            "created_at": "2026-06-05T00:00:00Z",
            "status": signal_status,
            "records": [{"signal_id": "signal:BTCUSDT:trend", "state": "supportive"}],
            "counts": {"records": 1, "conflicting": 0, "warnings": 0, "errors": 0},
            "warnings": [],
            "errors": [],
            "source_artifacts": ["analysis/factor_states.json"],
        },
    )
    run.manifest["artifacts"]["multi_source_signals"] = "analysis/multi_source_signals.json"
    run.manifest["multi_source_signals"] = {
        "status": signal_status,
        "artifact": "analysis/multi_source_signals.json",
        "records": 1,
        "conflicting": 0,
        "warnings": 0,
        "errors": 0,
    }
    run.manifest["counts"]["multi_source_signals"] = 1
    run.manifest["counts"]["multi_source_signal_conflicting"] = 0
    run.manifest["counts"]["multi_source_signal_warnings"] = 0
    run.manifest["counts"]["multi_source_signal_errors"] = 0

    material = "\n".join(
        [
            "---",
            "artifact_type: analysis_factor_signal_material",
            "schema_version: 1",
            "---",
            "",
            "codex_may_generate_feature_records: false",
            "codex_may_generate_factor_scores: false",
            "codex_may_generate_signal_states: false",
            "full_feature_snapshots_json_embedded: false",
            "full_factor_states_json_embedded: false",
            "full_multi_source_signals_json_embedded: false",
            "selected_records_only: true",
            "",
        ]
    )
    (run.analysis_dir / "factor_signal_material.md").write_text(material, encoding="utf-8")
    run.manifest["artifacts"]["factor_signal_material"] = "analysis/factor_signal_material.md"
    run.manifest["factor_signal_material"] = {
        "status": "ok",
        "artifact": "analysis/factor_signal_material.md",
    }
    run.manifest["counts"]["factor_signal_material_records"] = 3
    run.manifest["counts"]["factor_signal_material_omitted_records"] = 0


def _write_market_raw(config, run) -> list[str]:
    write_json(
        run.raw_dir / "market.json",
        {
            "items": [
                {
                    "id": "market:binance:BTCUSDT:now",
                    "symbol": "BTCUSDT",
                    "as_of": "2026-06-05T00:00:00Z",
                    "source": {"name": "binance"},
                }
            ],
            "errors": [],
        },
    )
    run.manifest["artifacts"]["raw_market"] = "raw/market.json"
    return ["raw/market.json"]


def _write_text_raw(config, run) -> list[str]:
    write_json(
        run.raw_dir / "text_events.json",
        {
            "collected_at": "2026-06-05T00:00:00Z",
            "items": [
                {
                    "id": "text:coindesk:event-1",
                    "type": "rss_item",
                    "title": "Bitcoin market event",
                    "published_at": "2026-06-05T00:00:00Z",
                    "source": {"name": "coindesk", "url": "https://example.com/rss.xml"},
                    "link": "https://example.com/bitcoin",
                    "content_text": "Bitcoin event.",
                    "language": "en",
                }
            ],
            "errors": [],
        },
    )
    run.manifest["artifacts"]["raw_text_events"] = "raw/text_events.json"
    return ["raw/text_events.json"]


def _write_derivatives_raw(run: RunContext) -> None:
    write_json(
        run.raw_dir / "derivatives_market.json",
        {
            "schema_version": 1,
            "artifact_type": "raw_derivatives_market",
            "collected_at": "2026-06-01T00:00:00Z",
            "items": [
                {
                    "item_id": "derivatives:binance_usdm:funding_rate:BTCUSDT:8h:2026-06-01T00:00:00Z",
                    "data_class": "funding_rate",
                    "source": "binance_usdm",
                    "market_type": "usd_m_futures",
                    "symbol": "BTCUSDT",
                    "period": "8h",
                    "as_of": "2026-06-01T00:00:00Z",
                    "endpoint": "/fapi/v1/fundingRate",
                    "metrics": {"funding_rate": None},
                    "units": {"funding_rate": "ratio"},
                    "raw_fields": {},
                    "warnings": [],
                    "errors": [],
                }
            ],
            "availability": [
                {
                    "source": "binance_usdm",
                    "data_class": "open_interest",
                    "symbol": "BTCUSDT",
                    "period": "5m",
                    "status": "partial",
                    "reason": "partial page",
                },
                {
                    "source": "binance_usdm",
                    "data_class": "basis",
                    "symbol": "BTCUSDT",
                    "period": "5m",
                    "status": "unavailable",
                    "reason": "unsupported interval",
                },
                {
                    "source": "binance_usdm",
                    "data_class": "premium_index",
                    "symbol": "BTCUSDT",
                    "period": "snapshot",
                    "status": "failed",
                    "reason": "timeout",
                },
                {
                    "source": "binance_usdm",
                    "data_class": "liquidation_summary",
                    "symbol": "BTCUSDT",
                    "period": "source_availability",
                    "status": "unavailable",
                    "reason": "periodic public liquidation summary unavailable",
                },
            ],
            "warnings": [],
            "errors": [{"message": "funding rate source returned partial data"}],
        },
    )
    run.manifest["artifacts"]["raw_derivatives_market"] = "raw/derivatives_market.json"


def _write_derivatives_state(tmp_path: Path) -> None:
    write_json(
        tmp_path / "data" / "market" / "metadata" / "derivatives_market_state.json",
        {
            "schema_version": 1,
            "artifact_type": "derivatives_market_state",
            "updated_at": "2026-06-05T00:00:00Z",
            "status": "warning",
            "storage_path": "data/market/derivatives",
            "totals": {
                "records": 1,
                "incoming_records": 2,
                "inserted_records": 1,
                "duplicate_records": 1,
                "conflicting_duplicates": 1,
            },
            "groups": [
                {
                    "source": "binance_usdm",
                    "data_class": "funding_rate",
                    "symbol": "BTCUSDT",
                    "period": "8h",
                    "row_count": 1,
                }
            ],
            "warnings": ["one duplicate derivatives record ignored."],
            "errors": ["derivatives endpoint returned an unavailable optional class"],
        },
    )


def _write_derivatives_views(run: RunContext) -> None:
    write_json(
        run.raw_dir / "derivatives_market_views.json",
        {
            "schema_version": 1,
            "artifact_type": "derivatives_market_views",
            "created_at": "2026-06-05T00:00:00Z",
            "source_artifacts": ["data/market/metadata/derivatives_market_state.json"],
            "views": [
                {
                    "view_id": "derivatives_view:funding_rate:binance_usdm:BTCUSDT:8h:2026-06-01T00:00:00Z",
                    "status": "insufficient_data",
                    "latest_observation_time": "2026-06-01T00:00:00Z",
                    "insufficient_data": True,
                    "warnings": ["funding_rate BTCUSDT has insufficient history."],
                    "errors": [],
                },
                {
                    "view_id": "derivatives_view:open_interest:binance_usdm:BTCUSDT:5m:missing",
                    "status": "missing_history",
                    "latest_observation_time": None,
                    "insufficient_data": True,
                    "warnings": ["open_interest BTCUSDT has no derivatives history."],
                    "errors": [],
                },
                {
                    "view_id": "derivatives_view:spread_depth:binance_usdm:skipped",
                    "status": "skipped",
                    "latest_observation_time": None,
                    "insufficient_data": True,
                    "warnings": ["unsupported derivatives class."],
                    "errors": [],
                },
            ],
            "warnings": [],
            "errors": [],
        },
    )


def _write_macro_raw(run: RunContext) -> None:
    write_json(
        run.raw_dir / "macro_calendar.json",
        {
            "schema_version": 1,
            "artifact_type": "macro_calendar_raw",
            "collector": "macro_calendar",
            "collection_method": "public_http",
            "source": {
                "name": "federal_reserve_fomc",
                "url": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
            },
            "collected_at": "2026-06-01T00:00:00Z",
            "window": {
                "lookback_start": "2026-05-29T00:00:00Z",
                "lookahead_end": "2026-07-20T00:00:00Z",
            },
            "items": [
                {
                    "item_id": "macro_calendar:central_bank_event:federal_reserve_fomc:US:fomc:2026-07-29T00:00:00Z",
                    "data_class": "central_bank_event",
                    "source": "federal_reserve_fomc",
                    "event_name": "Federal Open Market Committee meeting",
                    "event_type": "fomc_meeting",
                    "region": "US",
                    "scheduled_at": "2026-07-29T00:00:00Z",
                    "source_timezone": "America/New_York",
                    "source_published_at": "2026-06-01T00:00:00Z",
                    "importance": "high",
                    "affected_assets": ["BTCUSDT"],
                    "endpoint": "fomc_calendars",
                    "metrics": {},
                    "units": {},
                    "raw_fields": {"time_precision": "date"},
                    "warnings": ["macro calendar item warning"],
                    "errors": [],
                }
            ],
            "availability": [
                {
                    "source": "federal_reserve_fomc",
                    "data_class": "central_bank_event",
                    "region": "US",
                    "status": "no_event",
                    "reason": "no event in window",
                },
                {
                    "source": "federal_reserve_fomc",
                    "data_class": "central_bank_event",
                    "region": "US",
                    "status": "partial",
                    "reason": "partial page",
                },
                {
                    "source": "federal_reserve_fomc",
                    "data_class": "central_bank_event",
                    "region": "US",
                    "status": "unavailable",
                    "reason": "calendar unavailable",
                },
                {
                    "source": "federal_reserve_fomc",
                    "data_class": "central_bank_event",
                    "region": "US",
                    "status": "failed",
                    "reason": "timeout",
                },
                {
                    "source": "federal_reserve_fomc",
                    "data_class": "central_bank_event",
                    "region": "US",
                    "status": "stale",
                    "reason": "calendar stale",
                },
                {
                    "source": "federal_reserve_fomc",
                    "data_class": "central_bank_event",
                    "region": "US",
                    "status": "degraded",
                    "reason": "calendar degraded",
                },
            ],
            "warnings": ["macro calendar raw warning"],
            "errors": [{"message": "macro calendar source failed"}],
        },
    )
    run.manifest["artifacts"]["raw_macro_calendar"] = "raw/macro_calendar.json"


def _write_macro_state(tmp_path: Path) -> None:
    write_json(
        tmp_path / "data" / "macro" / "metadata" / "macro_calendar_schema.json",
        {
            "schema_version": 1,
            "artifact_type": "macro_calendar_schema",
            "identity": ["source", "data_class", "region", "event_name", "scheduled_at"],
        },
    )
    write_json(
        tmp_path / "data" / "macro" / "metadata" / "macro_calendar_state.json",
        {
            "schema_version": 1,
            "artifact_type": "macro_calendar_state",
            "updated_at": "2026-06-05T00:00:00Z",
            "status": "warning",
            "storage_path": "data/macro/calendar",
            "totals": {
                "records": 1,
                "incoming_records": 2,
                "inserted_records": 1,
                "updated_records": 1,
                "duplicate_records": 1,
                "conflicting_duplicates": 1,
            },
            "groups": [
                {
                    "source": "federal_reserve_fomc",
                    "data_class": "central_bank_event",
                    "region": "US",
                    "row_count": 1,
                }
            ],
            "availability": [
                {
                    "source": "federal_reserve_fomc",
                    "data_class": "central_bank_event",
                    "region": "US",
                    "status": "no_event",
                }
            ],
            "warnings": ["macro calendar duplicate conflict"],
            "errors": [],
        },
    )


def _write_macro_views(run: RunContext) -> None:
    write_json(
        run.raw_dir / "macro_calendar_views.json",
        {
            "schema_version": 1,
            "artifact_type": "macro_calendar_views",
            "created_at": "2026-06-05T00:00:00Z",
            "source_artifacts": ["data/macro/metadata/macro_calendar_state.json"],
            "views": [
                {
                    "view_id": "macro_calendar_view:central_bank_event:federal_reserve_fomc:US:latest",
                    "data_class": "central_bank_event",
                    "source": "federal_reserve_fomc",
                    "region": "US",
                    "status": "succeeded",
                    "latest_observation_time": "2026-06-01T00:00:00Z",
                    "event_count": 1,
                    "included_record_count": 1,
                    "records": [],
                    "warnings": ["macro calendar view is stale"],
                    "errors": [],
                },
                {
                    "view_id": "macro_calendar_view:central_bank_event:federal_reserve_fomc:US:no_event",
                    "data_class": "central_bank_event",
                    "source": "federal_reserve_fomc",
                    "region": "US",
                    "status": "no_event",
                    "latest_observation_time": None,
                    "event_count": 0,
                    "included_record_count": 0,
                    "records": [],
                    "warnings": [],
                    "errors": [],
                },
                {
                    "view_id": "macro_calendar_view:central_bank_event:federal_reserve_fomc:US:stale",
                    "data_class": "central_bank_event",
                    "source": "federal_reserve_fomc",
                    "region": "US",
                    "status": "stale",
                    "latest_observation_time": None,
                    "event_count": 0,
                    "included_record_count": 0,
                    "records": [],
                    "warnings": [],
                    "errors": [],
                },
                {
                    "view_id": "macro_calendar_view:central_bank_event:federal_reserve_fomc:US:skipped",
                    "data_class": "central_bank_event",
                    "source": "federal_reserve_fomc",
                    "region": "US",
                    "status": "skipped",
                    "latest_observation_time": None,
                    "event_count": 0,
                    "included_record_count": 0,
                    "records": [],
                    "warnings": [],
                    "errors": [],
                },
            ],
            "warnings": [],
            "errors": [],
        },
    )


def _write_macro_context(run: RunContext) -> None:
    write_json(
        run.analysis_dir / "macro_calendar_context.json",
        {
            "schema_version": 1,
            "artifact_type": "macro_calendar_context",
            "run_id": run.run_id,
            "created_at": "2026-06-05T00:00:00Z",
            "status": "warning",
            "records": [
                {
                    "context_id": "macro_calendar_context:scheduled_catalyst:federal_reserve_fomc:US:FOMC:2026-07-29T00:00:00Z",
                    "context_type": "scheduled_catalyst",
                    "data_class": "central_bank_event",
                    "source": "federal_reserve_fomc",
                    "event_name": "Federal Open Market Committee meeting",
                    "region": "US",
                    "scheduled_at": "2026-07-29T00:00:00Z",
                    "status": "succeeded",
                    "state": "upcoming",
                    "severity": "medium",
                    "warnings": [],
                    "errors": [],
                },
                {
                    "context_id": "macro_calendar_context:source_availability:federal_reserve_fomc:US:FOMC:missing",
                    "context_type": "source_availability",
                    "data_class": "central_bank_event",
                    "source": "federal_reserve_fomc",
                    "event_name": None,
                    "region": "US",
                    "scheduled_at": None,
                    "status": "stale",
                    "state": "stale",
                    "severity": "low",
                    "warnings": ["source availability is stale."],
                    "errors": [],
                },
            ],
            "counts": {
                "records": 2,
                "scheduled_catalyst": 1,
                "recent_catalyst": 0,
                "no_event_window": 0,
                "source_availability": 1,
            },
            "warnings": ["macro calendar context warning"],
            "errors": [],
            "source_artifacts": ["raw/macro_calendar_views.json"],
        },
    )
    run.manifest["artifacts"]["macro_calendar_context"] = "analysis/macro_calendar_context.json"


def _write_macro_material(run: RunContext) -> None:
    material = "\n".join(
        [
            "---",
            "artifact_type: analysis_macro_calendar_material",
            "schema_version: 1",
            "---",
            "",
            "# macro_calendar_material",
            "",
            "codex_may_generate_macro_events: false",
            "codex_may_generate_risk_levels: false",
            "full_raw_macro_calendar_artifacts_embedded: false",
            "full_reusable_macro_calendar_history_embedded: false",
            "full_macro_calendar_context_json_embedded: false",
            "",
        ]
    )
    run.analysis_dir.joinpath("macro_calendar_material.md").write_text(material, encoding="utf-8")
    run.manifest["artifacts"]["macro_calendar_material"] = "analysis/macro_calendar_material.md"
    run.manifest["macro_calendar_material"] = {
        "status": "warning",
        "artifact": "analysis/macro_calendar_material.md",
        "context_records": 2,
        "selected_records": 2,
        "omitted_records": 0,
    }


def _write_onchain_flow_raw(run: RunContext) -> None:
    write_json(
        run.raw_dir / "onchain_flow.json",
        {
            "schema_version": 1,
            "artifact_type": "onchain_flow_raw",
            "collector": "onchain_flow",
            "collection_method": "public_http",
            "source": {
                "name": "public_aggregate",
                "url": "https://stablecoins.llama.fi;https://api.blockchain.info",
            },
            "collected_at": "2026-06-01T00:00:00Z",
            "window": {
                "lookback_start": "2026-05-25T00:00:00Z",
                "lookback_end": "2026-06-01T00:00:00Z",
            },
            "items": [
                {
                    "item_id": "onchain_flow:stablecoin_supply:defillama_stablecoins:all:2026-06-01T00:00:00Z",
                    "data_class": "stablecoin_supply",
                    "source": "defillama_stablecoins",
                    "asset": "ALL_STABLECOINS",
                    "chain": "all",
                    "as_of": "2026-06-01T00:00:00Z",
                    "endpoint": "stablecoincharts_all",
                    "metrics": {"total_circulating_usd": None},
                    "units": {"total_circulating_usd": "USD"},
                    "raw_fields": {},
                    "warnings": ["on-chain item warning"],
                    "errors": [],
                }
            ],
            "availability": [
                {
                    "source": "defillama_stablecoins",
                    "data_class": "stablecoin_supply",
                    "asset": "ALL_STABLECOINS",
                    "chain": "all",
                    "status": "partial",
                    "reason": "partial rows",
                },
                {
                    "source": "blockchain_com_charts",
                    "data_class": "chain_activity",
                    "asset": "BTC",
                    "chain": "bitcoin",
                    "status": "unavailable",
                    "reason": "chart unavailable",
                },
                {
                    "source": "blockchain_com_charts",
                    "data_class": "network_congestion",
                    "asset": "BTC",
                    "chain": "bitcoin",
                    "status": "failed",
                    "reason": "timeout",
                },
                {
                    "source": "defillama_stablecoins",
                    "data_class": "stablecoin_supply",
                    "asset": "ALL_STABLECOINS",
                    "chain": "all",
                    "status": "stale",
                    "reason": "stale rows",
                },
                {
                    "source": "public_aggregate",
                    "data_class": "exchange_flow_availability",
                    "asset": "BTC",
                    "chain": "bitcoin",
                    "status": "degraded",
                    "reason": "limited public evidence",
                },
                {
                    "source": "blockchain_com_charts",
                    "data_class": "chain_activity",
                    "asset": "BTC",
                    "chain": "bitcoin",
                    "status": "insufficient_data",
                    "reason": "short window",
                },
            ],
            "warnings": ["on-chain raw warning"],
            "errors": [{"message": "on-chain source returned partial data"}],
        },
    )
    run.manifest["artifacts"]["raw_onchain_flow"] = "raw/onchain_flow.json"


def _write_onchain_flow_state(tmp_path: Path) -> None:
    write_json(
        tmp_path / "data" / "onchain" / "metadata" / "onchain_flow_schema.json",
        {
            "schema_version": 1,
            "artifact_type": "onchain_flow_schema",
            "identity": ["source", "data_class", "asset", "chain", "as_of"],
        },
    )
    write_json(
        tmp_path / "data" / "onchain" / "metadata" / "onchain_flow_state.json",
        {
            "schema_version": 1,
            "artifact_type": "onchain_flow_state",
            "updated_at": "2026-06-05T00:00:00Z",
            "status": "warning",
            "storage_path": "data/onchain/flow",
            "totals": {
                "records": 1,
                "incoming_records": 2,
                "inserted_records": 1,
                "updated_records": 1,
                "duplicate_records": 1,
                "conflicting_duplicates": 1,
            },
            "groups": [
                {
                    "source": "defillama_stablecoins",
                    "data_class": "stablecoin_supply",
                    "asset": "ALL_STABLECOINS",
                    "chain": "all",
                    "row_count": 1,
                }
            ],
            "availability": [
                {
                    "source": "defillama_stablecoins",
                    "data_class": "stablecoin_supply",
                    "status": "partial",
                }
            ],
            "warnings": ["on-chain duplicate conflict"],
            "errors": [],
        },
    )


def _write_onchain_flow_views(run: RunContext) -> None:
    write_json(
        run.raw_dir / "onchain_flow_views.json",
        {
            "schema_version": 1,
            "artifact_type": "onchain_flow_views",
            "created_at": "2026-06-05T00:00:00Z",
            "source_artifacts": ["data/onchain/metadata/onchain_flow_state.json"],
            "views": [
                {
                    "view_id": "onchain_flow_view:stablecoin_supply:defillama_stablecoins:ALL_STABLECOINS:all:latest",
                    "data_class": "stablecoin_supply",
                    "source": "defillama_stablecoins",
                    "asset": "ALL_STABLECOINS",
                    "chain": "all",
                    "status": "bounded",
                    "latest_observation_time": "2026-06-01T00:00:00Z",
                    "row_count": 2,
                    "included_record_count": 1,
                    "omitted_record_count": 1,
                    "records": [],
                    "warnings": ["on-chain flow view is stale"],
                    "errors": [],
                },
                {
                    "view_id": "onchain_flow_view:stablecoin_supply:defillama_stablecoins:ALL_STABLECOINS:all:partial",
                    "data_class": "stablecoin_supply",
                    "source": "defillama_stablecoins",
                    "asset": "ALL_STABLECOINS",
                    "chain": "all",
                    "status": "partial",
                    "latest_observation_time": None,
                    "row_count": 1,
                    "included_record_count": 0,
                    "omitted_record_count": 0,
                    "records": [],
                    "warnings": [],
                    "errors": [],
                },
                {
                    "view_id": "onchain_flow_view:stablecoin_supply:defillama_stablecoins:ALL_STABLECOINS:all:stale",
                    "data_class": "stablecoin_supply",
                    "source": "defillama_stablecoins",
                    "asset": "ALL_STABLECOINS",
                    "chain": "all",
                    "status": "stale",
                    "latest_observation_time": None,
                    "row_count": 0,
                    "included_record_count": 0,
                    "omitted_record_count": 0,
                    "records": [],
                    "warnings": [],
                    "errors": [],
                },
                {
                    "view_id": "onchain_flow_view:exchange_flow_availability:public_aggregate:BTC:bitcoin:skipped",
                    "data_class": "exchange_flow_availability",
                    "source": "public_aggregate",
                    "asset": "BTC",
                    "chain": "bitcoin",
                    "status": "skipped",
                    "latest_observation_time": None,
                    "row_count": 0,
                    "included_record_count": 0,
                    "omitted_record_count": 0,
                    "records": [],
                    "warnings": [],
                    "errors": [],
                },
            ],
            "warnings": [],
            "errors": [],
        },
    )


def _write_onchain_flow_context(run: RunContext) -> None:
    write_json(
        run.analysis_dir / "onchain_flow_context.json",
        {
            "schema_version": 1,
            "artifact_type": "onchain_flow_context",
            "run_id": run.run_id,
            "created_at": "2026-06-05T00:00:00Z",
            "status": "warning",
            "records": [
                {
                    "context_id": (
                        "onchain_flow_context:stablecoin_liquidity:defillama_stablecoins:"
                        "ALL_STABLECOINS:all:2026-06-01T00:00:00Z"
                    ),
                    "context_type": "stablecoin_liquidity",
                    "data_class": "stablecoin_supply",
                    "source": "defillama_stablecoins",
                    "asset": "ALL_STABLECOINS",
                    "chain": "all",
                    "as_of": "2026-06-01T00:00:00Z",
                    "status": "succeeded",
                    "state": "stablecoin_supply_flat",
                    "severity": "low",
                    "warnings": [],
                    "errors": [],
                },
                {
                    "context_id": "onchain_flow_context:exchange_flow_source_availability:public_aggregate:BTC:bitcoin:missing",
                    "context_type": "exchange_flow_source_availability",
                    "data_class": "exchange_flow_availability",
                    "source": "public_aggregate",
                    "asset": "BTC",
                    "chain": "bitcoin",
                    "as_of": None,
                    "status": "stale",
                    "state": "exchange_flow_unavailable",
                    "severity": "medium",
                    "warnings": ["exchange-flow source availability is stale."],
                    "errors": [],
                },
            ],
            "counts": {
                "records": 2,
                "stablecoin_liquidity": 1,
                "chain_activity": 0,
                "network_congestion": 0,
                "exchange_flow_source_availability": 1,
            },
            "warnings": ["on-chain flow context warning"],
            "errors": [],
            "source_artifacts": ["raw/onchain_flow_views.json"],
        },
    )
    run.manifest["artifacts"]["onchain_flow_context"] = "analysis/onchain_flow_context.json"


def _write_onchain_flow_material(run: RunContext) -> None:
    material = "\n".join(
        [
            "---",
            "artifact_type: analysis_onchain_flow_material",
            "schema_version: 1",
            "---",
            "",
            "# onchain_flow_material",
            "",
            "codex_may_generate_onchain_records: false",
            "codex_may_generate_flow_states: false",
            "codex_may_generate_address_labels: false",
            "codex_may_generate_risk_levels: false",
            "full_raw_onchain_flow_artifacts_embedded: false",
            "full_reusable_onchain_flow_history_embedded: false",
            "full_onchain_flow_context_json_embedded: false",
            "",
        ]
    )
    run.analysis_dir.joinpath("onchain_flow_material.md").write_text(material, encoding="utf-8")
    run.manifest["artifacts"]["onchain_flow_material"] = "analysis/onchain_flow_material.md"
    run.manifest["onchain_flow_material"] = {
        "status": "warning",
        "artifact": "analysis/onchain_flow_material.md",
        "context_records": 2,
        "selected_records": 2,
        "omitted_records": 0,
    }


def _event_record(raw_id: str, *, canonical_url: str, text: str) -> dict[str, Any]:
    return {
        "event_id": f"text_event:coindesk:{raw_id}",
        "raw_item_id": f"text:coindesk:{raw_id}",
        "canonical_url": canonical_url,
        "published_at": "2026-06-05T00:00:00Z",
        "collected_at": "2026-06-05T00:00:00Z",
        "normalized_text": text,
        "warnings": [],
    }


def _noop_stage(config, run) -> list[str]:
    return []


def _summary(analysis_dir: Path) -> dict[str, Any]:
    return json.loads((analysis_dir / "data_quality_summary.json").read_text(encoding="utf-8"))


def _manifest(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _check(summary: dict[str, Any], name: str) -> dict[str, Any]:
    return next(check for check in summary["checks"] if check["name"] == name)
