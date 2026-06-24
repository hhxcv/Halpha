from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from halpha.config import load_config
from halpha.data.data_quality import build_data_quality_summary
from halpha.data.data_quality_groups import POST_DATA_QUALITY_CHECK_NAMES
from halpha.data.data_quality_post_artifacts import post_data_quality_artifact_checks
from halpha.pipeline import RunContext, run_pipeline
from halpha.pipeline_stages import OPERATION_ORDER
from halpha.storage import write_json


@pytest.fixture(autouse=True)
def _isolate_artifact_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


def test_data_quality_summary_records_clean_current_run_state(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, include_ohlcv=False)
    config = load_config(config_path)
    result = run_pipeline(
        config,
        config_path=config_path,
        until_stage="build_materials",
        stage_handlers=_handlers_for_data_quality(),
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
    assert _check(summary, "raw_onchain_flow")["status"] == "skipped"
    assert _check(summary, "onchain_flow_history")["status"] == "skipped"
    assert _check(summary, "onchain_flow_views")["status"] == "skipped"
    assert _check(summary, "onchain_flow_context")["status"] == "skipped"
    for name in (
        "feature_snapshots",
        "factor_states",
        "multi_source_signals",
        "intelligence_fusion",
        "user_state_context",
        "personalized_risk_constraints",
    ):
        post_artifact_check = _check(summary, name)
        assert post_artifact_check["status"] == "ok"
    assert _check(summary, "text_event_history")["status"] == "ok"
    run_index = _check(summary, "run_index")
    assert run_index["status"] == "skipped"
    assert "terminal state projection committed after the final manifest" in run_index["summary"]
    assert run_index["details"]["terminal_state_projection"] is True
    assert run_index["details"]["committed_after_final_manifest"] is True
    assert run_index["details"]["stage_time_skip_is_expected"] is True
    assert run_index["details"]["report_as_final_missing"] is False


def test_post_data_quality_artifact_checks_report_stage_time_skips(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, include_ohlcv=False)
    run = _run_context(tmp_path, config_path)

    checks = post_data_quality_artifact_checks(run, expected=False)

    assert {check["name"] for check in checks} == POST_DATA_QUALITY_CHECK_NAMES
    assert len(checks) == 6
    for check in checks:
        assert check["status"] == "skipped"
        assert check["scope"] == "analysis"
        assert check["source_artifacts"]
        assert check["details"]["stage_time_skip_is_expected"] is True
        assert check["details"]["report_as_final_missing"] is False
        assert "produced by" in check["summary"]


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
    _write_final_structured_artifacts(run)

    build_data_quality_summary(_config(include_ohlcv=False, text_enabled=False), run, now="2026-06-05T00:00:00Z")

    summary = _summary(run.analysis_dir)
    assert summary["status"] == "degraded"
    assert _check(summary, "raw_text")["status"] == "skipped"
    assert _check(summary, "ohlcv_store")["status"] == "skipped"
    assert _check(summary, "partial_collection")["status"] == "degraded"


def test_data_quality_summary_reports_ohlcv_view_continuity_and_freshness(
    tmp_path: Path,
) -> None:
    config_path = _write_config(tmp_path)
    run = _run_context(tmp_path, config_path)
    _write_market_raw({}, run)
    run.manifest["ohlcv_sync"] = {"status": "succeeded", "warnings": [], "errors": []}
    run.manifest["counts"]["market_data_views_insufficient_data"] = 1
    write_json(
        run.raw_dir / "market_data_views.json",
        {
            "artifact_type": "market_data_views",
            "views": [
                {
                    "source": "binance",
                    "symbol": "BTCUSDT",
                    "timeframe": "1d",
                    "status": "degraded",
                    "quality_status": "degraded",
                    "warnings": ["binance BTCUSDT 1d is missing 1 expected OHLCV interval(s)."],
                    "quality": {
                        "status": "degraded",
                        "stale_latest_candle": True,
                        "duplicate_open_time_count": 1,
                        "duplicate_open_time_samples": [
                            {"open_time": "2026-06-03T00:00:00Z", "duplicate_count": 1}
                        ],
                        "missing_interval_count": 1,
                        "missing_interval_samples": [
                            {
                                "after_open_time": "2026-06-01T00:00:00Z",
                                "before_open_time": "2026-06-03T00:00:00Z",
                                "expected_next_open_time": "2026-06-02T00:00:00Z",
                                "missing_intervals": 1,
                            }
                        ],
                    },
                }
            ],
        },
    )

    build_data_quality_summary(_config(text_enabled=False), run, now="2026-06-05T00:00:00Z")

    ohlcv = _check(_summary(run.analysis_dir), "ohlcv_store")
    assert ohlcv["status"] == "degraded"
    assert ohlcv["details"]["insufficient_views"] == 1
    assert ohlcv["details"]["degraded_views"] == 1
    assert ohlcv["details"]["stale_views"] == 1
    assert ohlcv["details"]["duplicate_open_times"] == 1
    assert ohlcv["details"]["missing_intervals"] == 1
    assert ohlcv["details"]["quality_samples"]["missing_intervals"][0]["expected_next_open_time"] == (
        "2026-06-02T00:00:00Z"
    )


def test_data_quality_summary_includes_final_structured_artifact_checks_ok(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, include_ohlcv=False)
    run = _run_context(tmp_path, config_path)
    _write_initial_quality_summary(run)
    _write_market_raw({}, run)
    _write_feature_factor_artifacts(run)
    _write_fusion_artifacts(run)
    _write_personalized_risk_artifacts(run)

    build_data_quality_summary(_config(include_ohlcv=False, text_enabled=False), run, now="2026-06-05T00:00:00Z")

    summary = _summary(run.analysis_dir)
    assert summary["status"] == "ok"
    assert summary["counts"]["checks"] == 25
    assert _check(summary, "feature_snapshots")["status"] == "ok"
    assert _check(summary, "factor_states")["status"] == "ok"
    assert _check(summary, "multi_source_signals")["status"] == "ok"
    fusion = _check(summary, "intelligence_fusion")
    assert fusion["status"] == "ok"
    assert fusion["details"]["records"] == 2
    assert fusion["details"]["state_counts"]["supportive"] == 2
    user_state = _check(summary, "user_state_context")
    assert user_state["status"] == "ok"
    assert user_state["details"]["mode"] == "personalized"
    assert user_state["details"]["privacy_boundaries_present"] is True
    personalized = _check(summary, "personalized_risk_constraints")
    assert personalized["status"] == "ok"
    assert personalized["details"]["state_counts"]["watchlist_relevant"] == 1
    assert personalized["details"]["action_counts"]["annotate"] == 1
    assert personalized["details"]["decision_linked_records"] == 1
    assert run.manifest["counts"]["data_quality_checks"] == 25


def test_data_quality_summary_includes_final_structured_artifact_checks_warning(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, include_ohlcv=False)
    run = _run_context(tmp_path, config_path)
    _write_initial_quality_summary(run)
    _write_market_raw({}, run)
    _write_feature_factor_artifacts(run, feature_status="warning", feature_warnings=["one source was partial."])
    _write_fusion_artifacts(run)
    _write_personalized_risk_artifacts(run)

    build_data_quality_summary(_config(include_ohlcv=False, text_enabled=False), run, now="2026-06-05T00:00:00Z")

    summary = _summary(run.analysis_dir)
    assert summary["status"] == "warning"
    feature = _check(summary, "feature_snapshots")
    assert feature["status"] == "warning"
    assert feature["warning_count"] == 1


def test_data_quality_summary_includes_final_structured_artifact_checks_degraded(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, include_ohlcv=False)
    run = _run_context(tmp_path, config_path)
    _write_initial_quality_summary(run)
    _write_market_raw({}, run)
    _write_feature_factor_artifacts(run, factor_status="degraded")
    _write_fusion_artifacts(run)
    _write_personalized_risk_artifacts(run)

    build_data_quality_summary(_config(include_ohlcv=False, text_enabled=False), run, now="2026-06-05T00:00:00Z")

    summary = _summary(run.analysis_dir)
    assert summary["status"] == "degraded"
    assert _check(summary, "factor_states")["status"] == "degraded"


def test_data_quality_summary_includes_fusion_artifact_checks_warning_degraded_and_failed(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, include_ohlcv=False)
    run = _run_context(tmp_path, config_path)
    _write_initial_quality_summary(run)
    _write_market_raw({}, run)
    _write_feature_factor_artifacts(run)
    _write_fusion_artifacts(run, status="warning", state="conflicting", conflict_state="severe")
    _write_personalized_risk_artifacts(run)

    build_data_quality_summary(_config(include_ohlcv=False, text_enabled=False), run, now="2026-06-05T00:00:00Z")

    summary = _summary(run.analysis_dir)
    fusion = _check(summary, "intelligence_fusion")
    assert summary["status"] == "warning"
    assert fusion["status"] == "warning"
    assert fusion["details"]["conflicting_records"] == 2
    assert fusion["details"]["conflict_counts"]["severe"] == 2

    run = _run_context(tmp_path, config_path)
    _write_initial_quality_summary(run)
    _write_market_raw({}, run)
    _write_feature_factor_artifacts(run)
    _write_fusion_artifacts(run, status="warning", state="degraded")
    _write_personalized_risk_artifacts(run)

    build_data_quality_summary(_config(include_ohlcv=False, text_enabled=False), run, now="2026-06-05T00:00:00Z")

    summary = _summary(run.analysis_dir)
    fusion = _check(summary, "intelligence_fusion")
    assert summary["status"] == "degraded"
    assert fusion["status"] == "degraded"
    assert fusion["details"]["degraded_records"] == 2

    run = _run_context(tmp_path, config_path)
    _write_initial_quality_summary(run)
    _write_market_raw({}, run)
    _write_feature_factor_artifacts(run)
    _write_fusion_artifacts(run, status="failed", state="failed", errors=["fusion failed"])
    _write_personalized_risk_artifacts(run)

    build_data_quality_summary(_config(include_ohlcv=False, text_enabled=False), run, now="2026-06-05T00:00:00Z")

    summary = _summary(run.analysis_dir)
    fusion = _check(summary, "intelligence_fusion")
    assert summary["status"] == "failed"
    assert fusion["status"] == "failed"
    assert fusion["error_count"] == 1
    assert fusion["details"]["failed_records"] == 2


def test_data_quality_summary_reports_missing_final_structured_artifacts_as_failed(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, include_ohlcv=False)
    run = _run_context(tmp_path, config_path)
    _write_initial_quality_summary(run)
    _write_market_raw({}, run)

    build_data_quality_summary(_config(include_ohlcv=False, text_enabled=False), run, now="2026-06-05T00:00:00Z")

    summary = _summary(run.analysis_dir)
    assert summary["status"] == "failed"
    assert summary["counts"]["failed"] == 6
    assert _check(summary, "feature_snapshots")["details"]["report_as_final_missing"] is True
    assert _check(summary, "intelligence_fusion")["details"]["report_as_final_missing"] is True
    assert _check(summary, "personalized_risk_constraints")["details"]["report_as_final_missing"] is True


def test_data_quality_summary_reports_derivatives_quality_states(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, include_ohlcv=False)
    run = _run_context(tmp_path, config_path)
    _write_market_raw({}, run)
    _write_derivatives_raw(run)
    _write_derivatives_state(tmp_path)
    _write_derivatives_views(run)
    _write_final_structured_artifacts(run)
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
    _write_final_structured_artifacts(run)
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

    assert _check(summary, "partial_collection")["status"] == "degraded"


def test_data_quality_summary_reports_onchain_flow_quality_states(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, include_ohlcv=False)
    run = _run_context(tmp_path, config_path)
    _write_market_raw({}, run)
    _write_onchain_flow_raw(run)
    _write_onchain_flow_state(tmp_path)
    _write_onchain_flow_views(run)
    _write_onchain_flow_context(run)
    _write_final_structured_artifacts(run)
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


def _handlers_for_data_quality() -> dict[str, Any]:
    handlers = {
        operation: _noop_stage
        for operation in OPERATION_ORDER
        if operation not in {"build_text_event_records", "build_data_quality_summary"}
    }
    handlers.update(
        {
            "collect_market_data": _write_market_raw,
            "collect_text_events": _write_text_raw,
            "build_feature_snapshots": _write_feature_factor_stage,
            "build_intelligence_fusion": _write_fusion_stage,
            "build_personalized_risk_constraints": _write_personalized_risk_stage,
        }
    )
    return handlers


def _write_feature_factor_stage(config, run) -> list[str]:
    _write_feature_factor_artifacts(run)
    return [
        "analysis/feature_snapshots.json",
        "analysis/factor_states.json",
        "analysis/multi_source_signals.json",
    ]


def _write_fusion_stage(config, run) -> list[str]:
    _write_fusion_artifacts(run)
    return ["analysis/intelligence_fusion.json"]


def _write_personalized_risk_stage(config, run) -> list[str]:
    _write_personalized_risk_artifacts(run)
    return ["analysis/user_state_context.json", "analysis/personalized_risk_constraints.json"]


def _write_final_structured_artifacts(run: RunContext) -> None:
    _write_feature_factor_artifacts(run)
    _write_fusion_artifacts(run)
    _write_personalized_risk_artifacts(run)


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


def _write_feature_factor_artifacts(
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


def _write_fusion_artifacts(
    run: RunContext,
    *,
    status: str = "ok",
    state: str = "supportive",
    conflict_state: str = "none",
    errors: list[str] | None = None,
) -> None:
    errors = errors or []
    state_counts = {
        "supportive": 0,
        "cautionary": 0,
        "conflicting": 0,
        "risk_blocked": 0,
        "event_overridden": 0,
        "insufficient_evidence": 0,
        "degraded": 0,
        "failed": 0,
        "neutral": 0,
    }
    state_counts[state] = 2
    records = [
        {
            "fusion_record_id": f"fusion:BTCUSDT:{index}",
            "scope": {"symbol": "BTCUSDT", "timeframe": "1d"},
            "state": state,
            "direction": "bullish" if state == "supportive" else "unknown",
            "confidence": "medium",
            "confluence": {"state": "aligned" if state == "supportive" else "none"},
            "conflict": {"state": conflict_state},
            "risk_override": {"state": "none"},
            "event_override": {"state": "none"},
            "outcome_feedback": {"state": "supportive"},
            "evidence": ["bounded fusion evidence"],
            "uncertainty": [],
            "warnings": [],
            "errors": [{"message": message} for message in errors],
            "source_artifacts": ["analysis/multi_source_signals.json"],
        }
        for index in range(2)
    ]
    write_json(
        run.analysis_dir / "intelligence_fusion.json",
        {
            "schema_version": 1,
            "artifact_type": "intelligence_fusion",
            "run_id": run.run_id,
            "created_at": "2026-06-05T00:00:00Z",
            "status": status,
            "records": records,
            "coverage": [{"source_layer": "factor", "source_artifact": "analysis/multi_source_signals.json"}],
            "counts": {
                "records": 2,
                "state_counts": state_counts,
                "confluence_counts": {"aligned": 2 if state == "supportive" else 0},
                "conflict_counts": {conflict_state: 2},
                "risk_override_counts": {"none": 2},
                "event_override_counts": {"none": 2},
                "outcome_feedback_counts": {"supportive": 2},
                "warnings": 0,
                "errors": len(errors),
            },
            "warnings": [],
            "errors": [{"message": message} for message in errors],
            "source_artifacts": ["analysis/multi_source_signals.json"],
        },
    )
    run.manifest["artifacts"]["intelligence_fusion"] = "analysis/intelligence_fusion.json"
    run.manifest["intelligence_fusion"] = {
        "status": status,
        "artifact": "analysis/intelligence_fusion.json",
        "records": 2,
        "state_counts": state_counts,
        "confluence_counts": {"aligned": 2 if state == "supportive" else 0},
        "conflict_counts": {conflict_state: 2},
        "risk_override_counts": {"none": 2},
        "event_override_counts": {"none": 2},
        "outcome_feedback_counts": {"supportive": 2},
        "warnings": 0,
        "errors": len(errors),
    }
    run.manifest["counts"]["intelligence_fusion_records"] = 2
    run.manifest["counts"]["intelligence_fusion_warnings"] = 0
    run.manifest["counts"]["intelligence_fusion_errors"] = len(errors)
    run.manifest["counts"][f"intelligence_fusion_{state}_records"] = 2
    run.manifest["counts"]["intelligence_fusion_decision_linked_records"] = 1
    run.manifest["counts"]["intelligence_fusion_decision_adjusted_records"] = 0
    run.manifest["counts"]["intelligence_fusion_alert_linked_records"] = 1
    run.manifest["counts"]["intelligence_fusion_alert_adjusted_records"] = 0


def _write_personalized_risk_artifacts(run: RunContext) -> None:
    write_json(
        run.analysis_dir / "user_state_context.json",
        {
            "schema_version": 1,
            "artifact_type": "user_state_context",
            "run_id": run.run_id,
            "created_at": "2026-06-05T00:00:00Z",
            "status": "ok",
            "mode": "personalized",
            "source": {
                "configured": True,
                "source_ref": "configured_user_state",
                "raw_path_embedded": False,
                "raw_file_embedded": False,
            },
            "privacy": {
                "private_notes_embedded": False,
                "machine_paths_embedded": False,
                "account_identifiers_embedded": False,
                "holdings_values_embedded": False,
                "omitted_private_values": 1,
            },
            "watchlist": [{"symbol": "BTCUSDT", "timeframes": ["1d"], "relevance": "high"}],
            "disabled_assets": [],
            "risk": {"preference": "conservative", "max_action_level": "WATCH"},
            "preferred_timeframes": ["1d"],
            "strategy_preferences": {"preferred": [], "disabled": []},
            "manual_exposure_summary": [
                {"symbol": "BTCUSDT", "exposure_state": "watch", "private_note_omitted": True}
            ],
            "counts": {
                "watchlist_records": 1,
                "disabled_assets": 0,
                "preferred_timeframes": 1,
                "strategy_preference_records": 0,
                "manual_exposure_summary_records": 1,
                "omitted_private_values": 1,
                "warnings": 0,
                "errors": 0,
            },
            "warnings": [],
            "errors": [],
            "source_artifacts": [],
        },
    )
    run.manifest["artifacts"]["user_state_context"] = "analysis/user_state_context.json"
    run.manifest["user_state_context"] = {
        "status": "ok",
        "mode": "personalized",
        "artifact": "analysis/user_state_context.json",
        "watchlist_records": 1,
        "disabled_assets": 0,
        "preferred_timeframes": 1,
        "strategy_preference_records": 0,
        "manual_exposure_summary_records": 1,
        "omitted_private_values": 1,
        "warnings": 0,
        "errors": 0,
    }
    run.manifest["counts"]["user_state_watchlist_records"] = 1
    run.manifest["counts"]["user_state_disabled_assets"] = 0
    run.manifest["counts"]["user_state_preferred_timeframes"] = 1
    run.manifest["counts"]["user_state_strategy_preference_records"] = 0
    run.manifest["counts"]["user_state_manual_exposure_summary_records"] = 1
    run.manifest["counts"]["user_state_omitted_private_values"] = 1
    run.manifest["counts"]["user_state_warnings"] = 0
    run.manifest["counts"]["user_state_errors"] = 0

    state_counts = {
        "general": 0,
        "watchlist_relevant": 1,
        "disabled_asset_blocked": 0,
        "risk_limit_downgraded": 0,
        "timeframe_mismatch": 0,
        "strategy_preference_note": 0,
        "insufficient_user_state": 0,
        "skipped": 0,
        "degraded": 0,
        "failed": 0,
    }
    action_counts = {"annotate": 1, "downgrade": 0, "block": 0, "none": 0, "skip": 0}
    write_json(
        run.analysis_dir / "personalized_risk_constraints.json",
        {
            "schema_version": 1,
            "artifact_type": "personalized_risk_constraints",
            "run_id": run.run_id,
            "created_at": "2026-06-05T00:00:00Z",
            "status": "ok",
            "records": [
                {
                    "constraint_id": "personalized:btcusdt:1d:watchlist_relevant",
                    "scope": {"symbol": "BTCUSDT", "timeframe": "1d"},
                    "state": "watchlist_relevant",
                    "action": "annotate",
                    "severity": "info",
                    "confidence": "high",
                    "reason_codes": ["watchlist_match"],
                    "matched_user_state": {"watchlist": True},
                    "upstream_records": [],
                    "evidence": ["bounded personalized evidence"],
                    "uncertainty": [],
                    "warnings": [],
                    "errors": [],
                    "source_artifacts": ["analysis/user_state_context.json"],
                }
            ],
            "coverage": [{"source_layer": "decision_recommendations", "status": "ok"}],
            "counts": {
                "records": 1,
                "state_counts": state_counts,
                "action_counts": action_counts,
                "warnings": 0,
                "errors": 0,
            },
            "warnings": [],
            "errors": [],
            "source_artifacts": ["analysis/user_state_context.json"],
        },
    )
    run.manifest["artifacts"]["personalized_risk_constraints"] = "analysis/personalized_risk_constraints.json"
    run.manifest["personalized_risk_constraints"] = {
        "status": "ok",
        "artifact": "analysis/personalized_risk_constraints.json",
        "records": 1,
        "state_counts": state_counts,
        "action_counts": action_counts,
        "warnings": 0,
        "errors": 0,
    }
    run.manifest["counts"]["personalized_risk_constraint_records"] = 1
    run.manifest["counts"]["personalized_risk_decision_linked_records"] = 1
    run.manifest["counts"]["personalized_risk_decision_adjusted_records"] = 0
    run.manifest["counts"]["personalized_risk_watch_linked_records"] = 1
    run.manifest["counts"]["personalized_risk_watch_adjusted_records"] = 0
    run.manifest["counts"]["personalized_risk_alert_linked_records"] = 1
    run.manifest["counts"]["personalized_risk_alert_adjusted_records"] = 0

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

