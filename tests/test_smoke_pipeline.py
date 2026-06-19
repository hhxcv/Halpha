from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from halpha.cli import main


def test_m0_smoke_pipeline_uses_mocks_without_product_fixtures(
    tmp_path: Path, monkeypatch
) -> None:
    config_path = _write_config(tmp_path)
    requested_urls: list[str] = []
    codex_calls: list[dict] = []
    real_subprocess_run = subprocess.run

    def fake_market_urlopen(request, timeout):
        requested_urls.append(request.full_url)
        symbol = request.full_url.rsplit("=", 1)[-1]
        return _JsonResponse(_market_payload(symbol))

    def fake_text_urlopen(request, timeout):
        requested_urls.append(request.full_url)
        return _BytesResponse(_rss_payload())

    def fake_codex_run(command, *args, **kwargs):
        if kwargs.get("capture_output") is not True or "input" not in kwargs:
            return real_subprocess_run(command, *args, **kwargs)
        codex_calls.append(
            {
                "command": command,
                "input": kwargs["input"],
                "text": kwargs["text"],
                "encoding": kwargs["encoding"],
                "errors": kwargs["errors"],
                "capture_output": kwargs["capture_output"],
                "timeout": kwargs["timeout"],
                "cwd": kwargs["cwd"],
            }
        )
        return subprocess.CompletedProcess(command, 0, stdout=_report_stdout(), stderr="")

    monkeypatch.setattr("halpha.collectors.market.urlopen", fake_market_urlopen)
    monkeypatch.setattr("halpha.collectors.text.urlopen", fake_text_urlopen)
    monkeypatch.setattr("halpha.codex.runner.subprocess.run", fake_codex_run)

    exit_code = main(["run", "--config", str(config_path)])

    assert exit_code == 0
    assert requested_urls == [
        "https://data-api.binance.vision/api/v3/ticker/24hr?symbol=BTCUSDT",
        "https://data-api.binance.vision/api/v3/ticker/24hr?symbol=ETHUSDT",
        "https://example.com/feed.xml",
    ]

    run_dirs = sorted((tmp_path / "runs").iterdir())
    assert len(run_dirs) == 1
    run_dir = run_dirs[0]
    expected_artifacts = [
        "raw/market.json",
        "raw/text_events.json",
        "analysis/text_event_records.json",
        "analysis/text_entity_evidence.json",
        "analysis/text_event_classification_evidence.json",
        "analysis/text_event_topics.json",
        "analysis/text_event_signals.json",
        "analysis/event_intelligence_assessment.json",
        "analysis/alert_decisions.json",
        "analysis/alert_decision_material.md",
        "analysis/event_intelligence_material.md",
        "analysis/data_quality_summary.json",
        "analysis/data_quality_material.md",
        "analysis/outcome_targets.json",
        "analysis/outcome_evaluations.json",
        "analysis/feature_snapshots.json",
        "analysis/market_material.md",
        "analysis/text_material.md",
        "analysis/research_context.md",
        "codex_context/context.md",
        "codex_context/prompt.md",
        "report/report.md",
        "run_manifest.json",
    ]
    for artifact in expected_artifacts:
        assert (run_dir / artifact).is_file()

    manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "succeeded"
    assert manifest["counts"]["market_items"] == 2
    assert manifest["counts"]["text_event_items"] == 1
    assert manifest["ohlcv_sync"]["status"] == "skipped"
    assert manifest["codex"]["status"] == "succeeded"
    assert manifest["codex"]["exit_code"] == 0
    assert manifest["artifacts"] == {
        "codex_context": "codex_context/context.md",
            "codex_prompt": "codex_context/prompt.md",
            "data_quality_summary": "analysis/data_quality_summary.json",
            "data_quality_material": "analysis/data_quality_material.md",
            "outcome_targets": "analysis/outcome_targets.json",
            "outcome_evaluations": "analysis/outcome_evaluations.json",
            "feature_snapshots": "analysis/feature_snapshots.json",
            "market_material": "analysis/market_material.md",
        "raw_market": "raw/market.json",
        "raw_text_events": "raw/text_events.json",
        "report": "report/report.md",
        "research_context": "analysis/research_context.md",
        "research_data_catalog": "data/research/metadata/research_data_catalog.json",
        "run_index": "data/research/index.sqlite",
        "event_intelligence_assessment": "analysis/event_intelligence_assessment.json",
        "alert_decisions": "analysis/alert_decisions.json",
        "alert_decision_material": "analysis/alert_decision_material.md",
        "event_intelligence_material": "analysis/event_intelligence_material.md",
        "text_event_records": "analysis/text_event_records.json",
        "text_event_history_state": "data/research/metadata/text_event_history_state.json",
        "text_event_classification_evidence": "analysis/text_event_classification_evidence.json",
        "text_entity_evidence": "analysis/text_entity_evidence.json",
        "text_event_topics": "analysis/text_event_topics.json",
        "text_event_signals": "analysis/text_event_signals.json",
        "text_material": "analysis/text_material.md",
    }
    assert [(stage["name"], stage["status"]) for stage in manifest["stages"]] == [
        ("collect_market_data", "succeeded"),
        ("collect_derivatives_market_data", "succeeded"),
        ("sync_derivatives_market_history", "succeeded"),
        ("build_derivatives_market_views", "succeeded"),
        ("build_derivatives_market_context", "succeeded"),
        ("collect_macro_calendar_data", "succeeded"),
        ("sync_macro_calendar_history", "succeeded"),
        ("build_macro_calendar_views", "succeeded"),
        ("build_macro_calendar_context", "succeeded"),
        ("build_macro_calendar_material", "succeeded"),
        ("collect_onchain_flow_data", "succeeded"),
        ("sync_onchain_flow_history", "succeeded"),
        ("build_onchain_flow_views", "succeeded"),
        ("build_onchain_flow_context", "succeeded"),
        ("build_onchain_flow_material", "succeeded"),
        ("collect_text_events", "succeeded"),
        ("build_text_event_records", "succeeded"),
        ("build_text_entity_evidence", "succeeded"),
        ("build_text_event_classification_evidence", "succeeded"),
        ("build_text_event_topics", "succeeded"),
        ("build_text_event_signals", "succeeded"),
        ("sync_ohlcv", "succeeded"),
        ("build_market_data_views", "succeeded"),
        ("build_strategy_benchmark_suite", "succeeded"),
        ("evaluate_quant_strategies", "succeeded"),
        ("evaluate_strategy_evaluation", "succeeded"),
        ("build_strategy_experiment_material", "succeeded"),
        ("evaluate_market_strategy_signals", "succeeded"),
        ("build_market_signals", "succeeded"),
        ("build_market_signal_material", "succeeded"),
        ("build_market_regime_assessment", "succeeded"),
        ("build_risk_assessment", "succeeded"),
        ("build_decision_recommendations", "succeeded"),
        ("build_watch_triggers", "succeeded"),
        ("build_event_market_confluence", "succeeded"),
        ("build_event_intelligence_assessment", "succeeded"),
        ("build_alert_decisions", "succeeded"),
        ("build_alert_decision_material", "succeeded"),
        ("build_event_intelligence_material", "succeeded"),
        ("build_decision_intelligence_delta", "succeeded"),
        ("build_decision_intelligence_material", "succeeded"),
        ("build_data_quality_summary", "succeeded"),
        ("build_outcome_targets", "succeeded"),
        ("evaluate_outcomes", "succeeded"),
        ("build_feature_snapshots", "succeeded"),
        ("build_analysis_materials", "succeeded"),
        ("build_research_context", "succeeded"),
        ("build_codex_context", "succeeded"),
        ("run_codex_report", "succeeded"),
    ]
    assert manifest["stages"][-1]["artifacts"] == ["report/report.md"]

    market_raw = json.loads((run_dir / "raw/market.json").read_text(encoding="utf-8"))
    assert market_raw["source"]["name"] == "binance"
    assert [item["symbol"] for item in market_raw["items"]] == ["BTCUSDT", "ETHUSDT"]
    assert market_raw["errors"] == []

    text_raw = json.loads((run_dir / "raw/text_events.json").read_text(encoding="utf-8"))
    assert text_raw["sources"][0]["url"] == "https://example.com/feed.xml"
    assert len(text_raw["items"]) == 1
    assert text_raw["errors"] == []

    market_material = (run_dir / "analysis/market_material.md").read_text(encoding="utf-8")
    text_material = (run_dir / "analysis/text_material.md").read_text(encoding="utf-8")
    assert "artifact_type: analysis_market_material" in market_material
    assert "artifact_type: analysis_text_material" in text_material
    event_material = (run_dir / "analysis/event_intelligence_material.md").read_text(encoding="utf-8")
    alert_material = (run_dir / "analysis/alert_decision_material.md").read_text(encoding="utf-8")
    quality_material = (run_dir / "analysis/data_quality_material.md").read_text(encoding="utf-8")
    assert "artifact_type: analysis_event_intelligence_material" in event_material
    assert "codex_may_generate_event_categories: false" in event_material
    assert "artifact_type: analysis_alert_decision_material" in alert_material
    assert "codex_may_generate_alert_priority: false" in alert_material
    assert "artifact_type: analysis_data_quality_material" in quality_material
    assert "codex_may_generate_quality_checks: false" in quality_material

    prompt = (run_dir / "codex_context/prompt.md").read_text(encoding="utf-8")
    assert "Use Chinese section headings only." in prompt
    assert "Event intelligence material rules:" in prompt
    assert "Alert decision material rules:" in prompt
    assert "Data quality material rules:" in prompt
    assert "Source-provided smoke event." in prompt
    assert codex_calls[0]["input"] == prompt
    assert codex_calls[0]["encoding"] == "utf-8"
    assert codex_calls[0]["cwd"] == run_dir

    report = (run_dir / "report/report.md").read_text(encoding="utf-8")
    assert "## 风险提示" in report
    assert "binance" in report
    assert "coindesk" in report
    assert "tests/fixtures" not in config_path.read_text(encoding="utf-8")


def test_m3_smoke_pipeline_generates_decision_intelligence_report_path_with_test_fakes(
    tmp_path: Path, monkeypatch
) -> None:
    config_path = _write_m3_config(tmp_path)
    requested_urls: list[str] = []
    ohlcv_requests: list[dict] = []
    codex_calls: list[dict] = []
    real_subprocess_run = subprocess.run

    def fake_market_urlopen(request, timeout):
        requested_urls.append(request.full_url)
        symbol = request.full_url.rsplit("=", 1)[-1]
        return _JsonResponse(_market_payload(symbol))

    def fake_text_urlopen(request, timeout):
        requested_urls.append(request.full_url)
        return _BytesResponse(_rss_payload())

    class FakeOHLCVSource:
        def __init__(self, source_name: str, proxy_url: str | None = None) -> None:
            self.source_name = source_name
            self.proxy_url = proxy_url

        def fetch_records(self, *, symbol, timeframe, since=None, limit=None, now=None):
            ohlcv_requests.append(
                {
                    "source": self.source_name,
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "since": since,
                    "limit": limit,
                    "now": now,
                    "proxy_url": self.proxy_url,
                }
            )
            return _ohlcv_records(symbol=symbol, timeframe=timeframe, limit=limit or 4)

    def fake_codex_run(command, *args, **kwargs):
        if kwargs.get("capture_output") is not True or "input" not in kwargs:
            return real_subprocess_run(command, *args, **kwargs)
        codex_calls.append(
            {
                "command": command,
                "input": kwargs["input"],
                "text": kwargs["text"],
                "encoding": kwargs["encoding"],
                "errors": kwargs["errors"],
                "capture_output": kwargs["capture_output"],
                "timeout": kwargs["timeout"],
                "cwd": kwargs["cwd"],
            }
        )
        return subprocess.CompletedProcess(command, 0, stdout=_m3_report_stdout(), stderr="")

    monkeypatch.setattr("halpha.collectors.market.urlopen", fake_market_urlopen)
    monkeypatch.setattr("halpha.collectors.text.urlopen", fake_text_urlopen)
    monkeypatch.setattr("halpha.ohlcv_sync.CCXTOHLCVSource", FakeOHLCVSource)
    monkeypatch.setattr("halpha.codex.runner.subprocess.run", fake_codex_run)

    exit_code = main(["run", "--config", str(config_path)])

    assert exit_code == 0
    assert requested_urls == [
        "https://data-api.binance.vision/api/v3/ticker/24hr?symbol=BTCUSDT",
        "https://data-api.binance.vision/api/v3/ticker/24hr?symbol=ETHUSDT",
        "https://example.com/feed.xml",
    ]
    assert [request["symbol"] for request in ohlcv_requests] == [
        "BTCUSDT",
        "BTCUSDT",
        "ETHUSDT",
        "ETHUSDT",
    ]
    assert [request["timeframe"] for request in ohlcv_requests] == ["1d", "1h", "1d", "1h"]
    assert all(request["source"] == "binance" for request in ohlcv_requests)

    run_dirs = sorted((tmp_path / "runs").iterdir())
    assert len(run_dirs) == 1
    run_dir = run_dirs[0]
    expected_artifacts = [
        "raw/market.json",
        "raw/text_events.json",
        "raw/market_data_views.json",
        "analysis/strategy_benchmark_suite.json",
        "analysis/quant_strategy_runs.json",
        "analysis/strategy_evaluation_summary.json",
        "analysis/strategy_evaluation_material.md",
        "analysis/strategy_experiment.json",
        "analysis/strategy_effectiveness_gates.json",
        "analysis/strategy_experiment_material.md",
        "analysis/market_strategy_signals.json",
        "analysis/market_signals.json",
        "analysis/market_signal_material.md",
        "analysis/market_regime_assessment.json",
        "analysis/risk_assessment.json",
        "analysis/decision_recommendations.json",
        "analysis/watch_triggers.json",
        "analysis/event_market_confluence.json",
        "analysis/event_intelligence_assessment.json",
        "analysis/alert_decisions.json",
        "analysis/alert_decision_material.md",
        "analysis/event_intelligence_material.md",
        "analysis/decision_intelligence_delta.json",
        "analysis/decision_intelligence_material.md",
        "analysis/data_quality_summary.json",
        "analysis/data_quality_material.md",
        "analysis/feature_snapshots.json",
        "analysis/text_event_records.json",
        "analysis/text_entity_evidence.json",
        "analysis/text_event_classification_evidence.json",
        "analysis/text_event_topics.json",
        "analysis/text_event_signals.json",
        "analysis/market_material.md",
        "analysis/text_material.md",
        "analysis/research_context.md",
        "codex_context/context.md",
        "codex_context/prompt.md",
        "report/report.md",
        "run_manifest.json",
    ]
    for artifact in expected_artifacts:
        assert (run_dir / artifact).is_file()
    assert (tmp_path / "data" / "market" / "metadata" / "ohlcv_schema.json").is_file()
    assert (tmp_path / "data" / "market" / "metadata" / "ohlcv_sync_state.json").is_file()

    market_raw = json.loads((run_dir / "raw/market.json").read_text(encoding="utf-8"))
    assert market_raw["source"]["name"] == "binance"
    assert [item["symbol"] for item in market_raw["items"]] == ["BTCUSDT", "ETHUSDT"]
    assert market_raw["errors"] == []

    text_raw = json.loads((run_dir / "raw/text_events.json").read_text(encoding="utf-8"))
    assert text_raw["sources"][0]["url"] == "https://example.com/feed.xml"
    assert len(text_raw["items"]) == 1
    assert text_raw["errors"] == []

    manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "succeeded"
    assert manifest["ohlcv_sync"]["status"] == "succeeded"
    assert manifest["counts"]["ohlcv_sync_items"] == 4
    assert manifest["counts"]["market_data_views"] == 4
    assert manifest["counts"]["market_data_views_insufficient_data"] == 0
    assert manifest["counts"]["strategy_benchmark_records"] == 4
    assert manifest["counts"]["strategy_benchmark_succeeded"] == 4
    assert manifest["counts"]["strategy_benchmark_insufficient_data"] == 0
    assert manifest["counts"]["strategy_benchmark_failed"] == 0
    assert manifest["counts"]["quant_strategy_runs"] == 4
    assert manifest["counts"]["quant_strategy_runs_succeeded"] == 4
    assert manifest["counts"]["strategy_evaluation_records"] == 4
    assert manifest["counts"]["strategy_evaluation_succeeded"] == 4
    assert manifest["counts"]["strategy_evaluation_failed"] == 0
    assert manifest["counts"]["strategy_evaluation_insufficient_data"] == 0
    assert manifest["counts"]["strategy_evaluation_walk_forward_records"] == 0
    assert manifest["counts"]["strategy_evaluation_material_records"] == 4
    assert manifest["counts"]["strategy_experiment_candidates"] == 1
    assert manifest["counts"]["strategy_experiment_evaluations"] == 4
    assert manifest["counts"]["strategy_experiment_evaluations_succeeded"] == 4
    assert manifest["counts"]["strategy_experiment_evaluations_failed"] == 0
    assert manifest["counts"]["strategy_experiment_evaluations_insufficient_data"] == 0
    assert manifest["counts"]["strategy_gate_candidates"] == 1
    assert manifest["counts"]["strategy_experiment_material_records"] == 1
    assert manifest["counts"]["text_event_records"] == 1
    assert manifest["counts"]["text_event_records_with_warnings"] == 1
    assert manifest["counts"]["text_event_record_warnings"] == 1
    assert manifest["counts"]["text_entity_records"] == 1
    assert manifest["counts"]["text_entity_evidence"] == 0
    assert manifest["counts"]["text_asset_relevance_evidence"] == 0
    assert manifest["counts"]["text_event_classification_records"] == 1
    assert manifest["counts"]["text_event_category_candidate_evidence"] == 0
    assert manifest["counts"]["text_event_financial_tone_evidence"] == 0
    assert manifest["counts"]["text_event_topics"] == 1
    assert manifest["counts"]["text_event_topic_pair_decisions"] == 0
    assert manifest["counts"]["text_event_signals"] == 1
    assert manifest["counts"]["text_event_signals_unknown"] == 1
    assert manifest["counts"]["text_event_signals_accepted"] == 0
    assert manifest["counts"]["market_strategy_signals"] == 4
    assert manifest["counts"]["market_strategy_signals_insufficient_data"] == 0
    assert manifest["counts"]["market_signals"] == 4
    assert manifest["counts"]["market_signals_insufficient_data"] == 0
    assert manifest["counts"]["market_signal_material_records"] == 4
    assert manifest["counts"]["market_regime_records"] == 4
    assert manifest["counts"]["market_regime_unknown_records"] == 0
    assert manifest["counts"]["risk_assessment_records"] == 4
    assert manifest["counts"]["risk_assessment_unknown_records"] == 0
    assert manifest["counts"]["risk_assessment_high_or_extreme_records"] == 0
    assert manifest["counts"]["risk_assessment_blocking_records"] == 0
    assert manifest["counts"]["decision_recommendation_records"] == 4
    assert manifest["counts"]["decision_recommendation_actionable_records"] == 4
    assert manifest["counts"]["decision_recommendation_non_actionable_records"] == 0
    assert manifest["counts"]["decision_recommendation_risk_blocked_records"] == 0
    assert manifest["counts"]["watch_trigger_records"] == 20
    assert manifest["counts"]["watch_trigger_linked_records"] == 20
    assert manifest["counts"]["event_market_confluence_records"] == 4
    assert manifest["counts"]["event_market_confluence_insufficient_event_evidence"] == 4
    assert manifest["counts"]["event_intelligence_assessment_records"] == 4
    assert manifest["counts"]["event_intelligence_assessment_downgraded_records"] == 4
    assert manifest["counts"]["event_intelligence_assessment_high_or_critical_records"] == 0
    assert manifest["counts"]["alert_decision_records"] == 4
    assert manifest["counts"]["alert_decision_no_alert_records"] == 4
    assert manifest["counts"]["alert_decision_p0_records"] == 0
    assert manifest["counts"]["alert_decision_p1_records"] == 0
    assert manifest["counts"]["alert_decision_material_records"] == 4
    assert manifest["counts"]["event_intelligence_material_records"] == 1
    assert manifest["counts"]["decision_delta_changed_records"] == 0
    assert manifest["counts"]["decision_intelligence_material_records"] == 4
    assert manifest["counts"]["feature_snapshots"] >= 4
    assert manifest["counts"]["feature_snapshot_coverage_records"] >= 1
    assert manifest["codex"]["status"] == "succeeded"
    assert manifest["codex"]["exit_code"] == 0
    assert manifest["artifacts"]["market_data_views"] == "raw/market_data_views.json"
    assert manifest["artifacts"]["strategy_benchmark_suite"] == "analysis/strategy_benchmark_suite.json"
    assert manifest["artifacts"]["quant_strategy_runs"] == "analysis/quant_strategy_runs.json"
    assert manifest["artifacts"]["strategy_evaluation_summary"] == "analysis/strategy_evaluation_summary.json"
    assert manifest["artifacts"]["strategy_evaluation_material"] == "analysis/strategy_evaluation_material.md"
    assert manifest["artifacts"]["strategy_experiment"] == "analysis/strategy_experiment.json"
    assert manifest["artifacts"]["strategy_effectiveness_gates"] == "analysis/strategy_effectiveness_gates.json"
    assert manifest["artifacts"]["strategy_experiment_material"] == "analysis/strategy_experiment_material.md"
    assert manifest["artifacts"]["market_strategy_signals"] == "analysis/market_strategy_signals.json"
    assert manifest["artifacts"]["market_signals"] == "analysis/market_signals.json"
    assert manifest["artifacts"]["market_signal_material"] == "analysis/market_signal_material.md"
    assert manifest["artifacts"]["market_regime_assessment"] == "analysis/market_regime_assessment.json"
    assert manifest["artifacts"]["risk_assessment"] == "analysis/risk_assessment.json"
    assert manifest["artifacts"]["decision_recommendations"] == "analysis/decision_recommendations.json"
    assert manifest["artifacts"]["watch_triggers"] == "analysis/watch_triggers.json"
    assert manifest["artifacts"]["event_market_confluence"] == "analysis/event_market_confluence.json"
    assert manifest["artifacts"]["event_intelligence_assessment"] == "analysis/event_intelligence_assessment.json"
    assert manifest["artifacts"]["alert_decisions"] == "analysis/alert_decisions.json"
    assert manifest["artifacts"]["alert_decision_material"] == "analysis/alert_decision_material.md"
    assert manifest["artifacts"]["event_intelligence_material"] == "analysis/event_intelligence_material.md"
    assert manifest["artifacts"]["decision_intelligence_delta"] == "analysis/decision_intelligence_delta.json"
    assert manifest["artifacts"]["decision_intelligence_material"] == "analysis/decision_intelligence_material.md"
    assert manifest["artifacts"]["feature_snapshots"] == "analysis/feature_snapshots.json"
    assert manifest["artifacts"]["text_event_records"] == "analysis/text_event_records.json"
    assert manifest["artifacts"]["text_entity_evidence"] == "analysis/text_entity_evidence.json"
    assert manifest["artifacts"]["text_event_classification_evidence"] == (
        "analysis/text_event_classification_evidence.json"
    )
    assert manifest["artifacts"]["text_event_topics"] == "analysis/text_event_topics.json"
    assert manifest["artifacts"]["text_event_signals"] == "analysis/text_event_signals.json"
    assert manifest["artifacts"]["report"] == "report/report.md"
    assert manifest["decision_intelligence"] == {
        "enabled": True,
        "status": "succeeded",
        "artifacts": {
            "market_regime_assessment": "analysis/market_regime_assessment.json",
            "risk_assessment": "analysis/risk_assessment.json",
            "decision_recommendations": "analysis/decision_recommendations.json",
            "watch_triggers": "analysis/watch_triggers.json",
            "decision_intelligence_delta": "analysis/decision_intelligence_delta.json",
            "decision_intelligence_material": "analysis/decision_intelligence_material.md",
        },
        "counts": {
            "regime_records": 4,
            "risk_records": 4,
            "decision_recommendations": 4,
            "watch_triggers": 20,
            "changed_delta_records": 0,
            "decision_material_records": 4,
        },
        "previous_run": {
            "status": "no_previous_run",
            "run_id": None,
            "path": None,
        },
        "warnings": ["No previous successful decision-intelligence run found."],
        "errors": [],
    }

    market_data_views = json.loads((run_dir / "raw/market_data_views.json").read_text(encoding="utf-8"))
    strategy_benchmarks = json.loads(
        (run_dir / "analysis/strategy_benchmark_suite.json").read_text(encoding="utf-8")
    )
    assert len(market_data_views["views"]) == 4
    assert all("records" not in view for view in market_data_views["views"])
    assert all(view["row_count"] == 4 for view in market_data_views["views"])
    assert len(strategy_benchmarks["benchmarks"]) == 4
    assert all("records" not in record for record in strategy_benchmarks["benchmarks"])
    assert all(record["status"] == "succeeded" for record in strategy_benchmarks["benchmarks"])

    strategy_signals = json.loads(
        (run_dir / "analysis/market_strategy_signals.json").read_text(encoding="utf-8")
    )
    market_signals = json.loads(
        (run_dir / "analysis/market_signals.json").read_text(encoding="utf-8")
    )
    market_regime = json.loads(
        (run_dir / "analysis/market_regime_assessment.json").read_text(encoding="utf-8")
    )
    risk_assessment = json.loads(
        (run_dir / "analysis/risk_assessment.json").read_text(encoding="utf-8")
    )
    decision_recommendations = json.loads(
        (run_dir / "analysis/decision_recommendations.json").read_text(encoding="utf-8")
    )
    watch_triggers = json.loads((run_dir / "analysis/watch_triggers.json").read_text(encoding="utf-8"))
    decision_delta = json.loads(
        (run_dir / "analysis/decision_intelligence_delta.json").read_text(encoding="utf-8")
    )
    decision_material = (run_dir / "analysis/decision_intelligence_material.md").read_text(encoding="utf-8")
    alert_decision_material = (run_dir / "analysis/alert_decision_material.md").read_text(encoding="utf-8")
    strategy_runs = json.loads((run_dir / "analysis/quant_strategy_runs.json").read_text(encoding="utf-8"))
    strategy_evaluation = json.loads(
        (run_dir / "analysis/strategy_evaluation_summary.json").read_text(encoding="utf-8")
    )
    strategy_evaluation_material = (
        run_dir / "analysis/strategy_evaluation_material.md"
    ).read_text(encoding="utf-8")
    strategy_experiment = json.loads((run_dir / "analysis/strategy_experiment.json").read_text(encoding="utf-8"))
    strategy_gates = json.loads(
        (run_dir / "analysis/strategy_effectiveness_gates.json").read_text(encoding="utf-8")
    )
    strategy_experiment_material = (
        run_dir / "analysis/strategy_experiment_material.md"
    ).read_text(encoding="utf-8")
    assert len(strategy_runs["runs"]) == 4
    assert len(strategy_evaluation["records"]) == 4
    assert strategy_experiment["coverage"]["strategy_candidates"] == 1
    assert strategy_experiment["coverage"]["evaluations"] == 4
    assert strategy_gates["coverage"]["strategy_candidates"] == 1
    assert "artifact_type: analysis_strategy_evaluation_material" in strategy_evaluation_material
    assert "cost_assumptions:" in strategy_evaluation_material
    assert "baseline_comparison:" in strategy_evaluation_material
    assert "sample_limits:" in strategy_evaluation_material
    assert "reliability:" in strategy_evaluation_material
    assert "codex_may_generate_metrics: false" in strategy_evaluation_material
    assert "artifact_type: analysis_strategy_experiment_material" in strategy_experiment_material
    assert "record_type: strategy_effectiveness_gate" in strategy_experiment_material
    assert "codex_may_generate_gate_outcomes: false" in strategy_experiment_material
    assert "benchmark_coverage:" in strategy_experiment_material
    assert len(strategy_signals["signals"]) == 4
    assert len(market_signals["signals"]) == 4
    assert sorted({signal["strategy_name"] for signal in market_signals["signals"]}) == ["tsmom_vol_scaled"]
    assert all(signal["evidence"] for signal in market_signals["signals"])
    assert all(signal["uncertainty"] for signal in market_signals["signals"])
    assert all("strategy_signal_id" not in signal for signal in market_signals["signals"])
    assert market_regime["artifact_type"] == "market_regime_assessment"
    assert len(market_regime["records"]) == 4
    assert all(record["regime"] == "trend_up" for record in market_regime["records"])
    assert risk_assessment["artifact_type"] == "risk_assessment"
    assert len(risk_assessment["records"]) == 4
    assert all(record["risk_level"] == "low" for record in risk_assessment["records"])
    assert decision_recommendations["artifact_type"] == "decision_recommendations"
    assert len(decision_recommendations["records"]) == 4
    assert all(record["action_level"] == "TRY_SMALL" for record in decision_recommendations["records"])
    assert all(record["evidence"] for record in decision_recommendations["records"])
    assert all(record["invalidation_conditions"] for record in decision_recommendations["records"])
    assert watch_triggers["artifact_type"] == "watch_triggers"
    assert len(watch_triggers["records"]) == 20
    assert sorted({record["type"] for record in watch_triggers["records"]}) == [
        "confirmation",
        "invalidation",
        "recheck_next_run",
        "risk_escalation",
    ]
    assert all(record["linked_decision_record_id"] for record in watch_triggers["records"])
    assert decision_delta["artifact_type"] == "decision_intelligence_delta"
    assert decision_delta["status"] == "no_previous_run"
    assert decision_delta["changes"] == []
    assert manifest["decision_intelligence"]["previous_run"]["status"] == "no_previous_run"
    assert "artifact_type: analysis_decision_intelligence_material" in decision_material
    assert "artifact_type: analysis_alert_decision_material" in alert_decision_material
    assert "codex_may_generate_alert_priority: false" in alert_decision_material
    assert "research_decision_support_only: true" in decision_material
    for artifact in [
        "analysis/market_regime_assessment.json",
        "analysis/risk_assessment.json",
        "analysis/decision_recommendations.json",
        "analysis/watch_triggers.json",
        "analysis/decision_intelligence_delta.json",
    ]:
        assert artifact in decision_material
    assert "## delta_vs_previous_run" in decision_material

    signal_material = (run_dir / "analysis/market_signal_material.md").read_text(encoding="utf-8")
    assert "artifact_type: analysis_market_signal_material" in signal_material
    assert "record_type: market_signal" in signal_material
    assert "key_values:" in signal_material
    assert "evidence:" in signal_material
    assert "uncertainty:" in signal_material
    assert "raw_ohlcv_history_embedded: false" in signal_material
    assert "open_time:" not in signal_material

    context = (run_dir / "codex_context/context.md").read_text(encoding="utf-8")
    prompt = (run_dir / "codex_context/prompt.md").read_text(encoding="utf-8")
    research_context = (run_dir / "analysis/research_context.md").read_text(encoding="utf-8")
    assert "quant_strategy_runs: analysis/quant_strategy_runs.json" in research_context
    assert "strategy_evaluation_summary: analysis/strategy_evaluation_summary.json" in research_context
    assert "strategy_evaluation_material: analysis/strategy_evaluation_material.md" in research_context
    assert "strategy_experiment: analysis/strategy_experiment.json" in research_context
    assert "strategy_effectiveness_gates: analysis/strategy_effectiveness_gates.json" in research_context
    assert "strategy_experiment_material: analysis/strategy_experiment_material.md" in research_context
    assert "market_strategy_signals: analysis/market_strategy_signals.json" in research_context
    assert "market_signals: analysis/market_signals.json" in research_context
    assert "decision_intelligence_material: analysis/decision_intelligence_material.md" in research_context
    assert "alert_decision_material: analysis/alert_decision_material.md" in research_context
    assert "event_intelligence_material: analysis/event_intelligence_material.md" in research_context
    assert "data_quality_material: analysis/data_quality_material.md" in research_context
    assert "artifact_type: analysis_market_signal_material" in research_context
    assert "artifact_type: analysis_strategy_evaluation_material" in research_context
    assert "artifact_type: analysis_strategy_experiment_material" in research_context
    assert "artifact_type: analysis_decision_intelligence_material" in research_context
    assert "artifact_type: analysis_alert_decision_material" in research_context
    assert "artifact_type: analysis_event_intelligence_material" in research_context
    assert "artifact_type: analysis_data_quality_material" in research_context
    assert "artifact_type: analysis_market_signal_material" in context
    assert "artifact_type: analysis_strategy_evaluation_material" in context
    assert "artifact_type: analysis_strategy_experiment_material" in context
    assert "quant_strategy_runs: analysis/quant_strategy_runs.json" in context
    assert "strategy_evaluation_summary: analysis/strategy_evaluation_summary.json" in context
    assert "strategy_evaluation_material: analysis/strategy_evaluation_material.md" in context
    assert "strategy_experiment_material: analysis/strategy_experiment_material.md" in context
    assert "market_strategy_signals: analysis/market_strategy_signals.json" in context
    assert "market_signals: analysis/market_signals.json" in context
    assert "market_signal_material: analysis/market_signal_material.md" in context
    assert "artifact_type: analysis_decision_intelligence_material" in context
    assert "decision_intelligence_material: analysis/decision_intelligence_material.md" in context
    assert "artifact_type: analysis_alert_decision_material" in context
    assert "alert_decision_material: analysis/alert_decision_material.md" in context
    assert "artifact_type: analysis_event_intelligence_material" in context
    assert "event_intelligence_material: analysis/event_intelligence_material.md" in context
    assert "data_quality_material: analysis/data_quality_material.md" in context
    assert "artifact_type: analysis_data_quality_material" in context
    assert "analysis/decision_recommendations.json" in context
    assert "analysis/watch_triggers.json" in context
    assert "raw_ohlcv_history_embedded: false" in context
    assert "open_time:" not in context
    assert "Quantitative conclusions" in prompt
    assert "Strategy evaluation material rules:" in prompt
    assert "Strategy experiment gate material rules:" in prompt
    assert "Use Halpha-generated effectiveness gate statuses only" in prompt
    assert "Do not generate or revise strategy gate statuses" in prompt
    assert "cost assumptions, baseline comparison, sample limits" in prompt
    assert "Use Halpha-generated evaluation metrics only" in prompt
    assert "Decision intelligence material rules:" in prompt
    assert "Event intelligence material rules:" in prompt
    assert "Alert decision material rules:" in prompt
    assert "Data quality material rules:" in prompt
    assert "Do not generate or revise alert priorities" in prompt
    assert "Do not generate or revise data-quality checks" in prompt
    assert "Do not generate or revise event classifications" in prompt
    assert "event-quant confluence or conflict" in prompt
    assert "current decision view" in prompt
    assert "what not to do" in prompt
    assert "wait/watch conditions" in prompt
    assert "changes versus previous run" in prompt
    assert "Do not invent action levels" in prompt
    assert "Do not upgrade WATCH, NO_ACTION" in prompt
    assert "Use Markdown tables for market data" in prompt
    assert "organize each main section with symbol-level subheadings" in prompt
    assert "do not recreate the full strategy run table" in prompt
    assert "do not restate every strategy run row or numeric field" in prompt
    assert "Watch points" in prompt
    assert "Risk notes" in prompt
    assert "Do not include fixed boilerplate" in prompt
    assert "Do not calculate new quantitative signals from raw OHLCV history" in prompt
    assert codex_calls[0]["input"] == prompt
    assert codex_calls[0]["cwd"] == run_dir

    report = (run_dir / "report/report.md").read_text(encoding="utf-8")
    assert "## " + "\u51b3\u7b56\u652f\u6301" in report
    assert "action_level=TRY_SMALL" in report
    assert "decision_bias=tentative_constructive" in report
    assert "cost_assumptions" in report
    assert "baseline_comparison" in report
    assert "sample_limits=short_window" in report
    assert "reliability=low" in report
    assert "risk_level=low" in report
    assert "no_previous_run" in report
    assert "confirmation" in report
    assert "invalidation" in report
    assert "risk_escalation" in report
    assert "recheck_next_run" in report
    assert "## 量化信号结论" in report
    assert "## \u7b56\u7565\u6709\u6548\u6027\u95e8\u69db\u8868" in report
    assert "\u8bc1\u636e\u4e0d\u8db3" in report
    assert "趋势信号" in report
    assert "证据" in report
    assert "## 观察要点" in report
    assert "## 风险提示" in report
    assert "不构成投资建议" not in report
    assert "样本窗口较短" in report
    assert "tests/fixtures" not in config_path.read_text(encoding="utf-8")


def _write_config(tmp_path: Path) -> Path:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
run:
  output_dir: runs
  timezone: Asia/Shanghai
market:
  enabled: true
  source: binance
  symbols:
    - BTCUSDT
    - ETHUSDT
text:
  enabled: true
  max_items: 1
  sources:
    - name: coindesk
      type: rss
      url: https://example.com/feed.xml
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


def _write_m3_config(tmp_path: Path) -> Path:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
run:
  output_dir: runs
  timezone: Asia/Shanghai
market:
  enabled: true
  source: binance
  symbols:
    - BTCUSDT
    - ETHUSDT
  ohlcv:
    storage_dir: data/market/ohlcv
    timeframes:
      - 1d
      - 1h
    lookback:
      1d: 4
      1h: 4
quant:
  enabled: true
  engine: vectorbt
  strategies:
    - name: tsmom_vol_scaled
      enabled: true
      params:
        return_window: 2
        volatility_window: 2
        target_volatility: 0.2
text:
  enabled: true
  max_items: 1
  sources:
    - name: coindesk
      type: rss
      url: https://example.com/feed.xml
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


def _market_payload(symbol: str) -> dict:
    price = "68000.00" if symbol == "BTCUSDT" else "3600.00"
    return {
        "symbol": symbol,
        "lastPrice": price,
        "priceChangePercent": "1.25",
        "volume": "123.45",
        "quoteVolume": "8394600.00",
        "closeTime": _millis(datetime(2026, 6, 5, 0, 30, tzinfo=timezone.utc)),
    }


def _ohlcv_records(*, symbol: str, timeframe: str, limit: int) -> list[dict]:
    base_close = 100.0 if symbol == "BTCUSDT" else 50.0
    base_volume = 10.0 if timeframe == "1d" else 20.0
    records = []
    for index in range(limit):
        close = base_close + index
        records.append(
            {
                "source": "binance",
                "symbol": symbol,
                "timeframe": timeframe,
                "open_time": _ohlcv_open_time(timeframe, index),
                "open": close - 1,
                "high": close + 2,
                "low": close - 2,
                "close": close,
                "volume": base_volume + index * 5,
                "fetched_at": "2026-06-05T00:30:00Z",
            }
        )
    return records


def _ohlcv_open_time(timeframe: str, index: int) -> str:
    if timeframe == "1d":
        day = 1 + index
        return f"2026-06-{day:02d}T00:00:00Z"
    hour = index
    return f"2026-06-05T{hour:02d}:00:00Z"


def _rss_payload() -> bytes:
    return b"""<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0">
  <channel>
    <item>
      <title>Smoke market event</title>
      <link>https://example.com/smoke-event</link>
      <guid>smoke-event-1</guid>
      <pubDate>Fri, 05 Jun 2026 00:30:00 GMT</pubDate>
      <description>Source-provided smoke event.</description>
    </item>
  </channel>
</rss>
"""


def _report_stdout() -> str:
    return "\n".join(
        [
            "# 每日市场情报简报",
            "",
            "## 核心摘要",
            "",
            "binance 和 coindesk 的本地上下文已用于生成报告。",
            "",
            "## 市场概览",
            "",
            "市场观察保持来源意识。",
            "",
            "## 文本事件",
            "",
            "coindesk 提供了公开文本事件。",
            "",
            "## 综合判断",
            "",
            "该判断仅基于测试上下文。",
            "",
            "## 观察要点",
            "",
            "- 继续观察公开来源。",
            "",
            "## 风险提示",
            "",
            "公开来源较少，后续事件可能改变当前观察。",
            "",
        ]
    )


def _m3_report_stdout() -> str:
    return "\n".join(
        [
            "# 每日市场情报简报",
            "",
            "## 核心摘要",
            "",
            "本报告使用了本地量化信号材料和公开文本事件。",
            "",
            "## 市场概览",
            "",
            "binance 市场数据和本地 OHLCV 信号材料已进入报告上下文。",
            "",
            "## 量化信号结论",
            "",
            "- 趋势信号显示 BTCUSDT 与 ETHUSDT 的样本窗口偏强。",
            "- 证据：报告上下文包含 tsmom_vol_scaled 策略信号记录。",
            "- 不确定性：这些信号仅基于 OHLCV 窗口，不包含文本事件信号。",
            "",
            "## 决策支持",
            "",
            "- 当前决策视图：action_level=TRY_SMALL; decision_bias=tentative_constructive.",
            "- strategy_evaluation: cost_assumptions=fees_bps+slippage_bps; baseline_comparison=buy_and_hold/cash.",
            "- reliability=low; sample_limits=short_window; evaluation_uncertainty=insufficient_walk_forward.",
            "- 可以做：仅把 TRY_SMALL 理解为研究决策支持语言，继续跟踪证据是否维持。",
            "- 不要做：不要把该材料解释为仓位、账户动作、自动交易或收益承诺。",
            "- 等待/观察：关注 confirmation、invalidation、risk_escalation 和 recheck_next_run 触发条件。",
            "- 风险状态：risk_level=low，但仍受样本窗口和信号更新限制。",
            "- 失效条件：若趋势信号反转或风险升高，则当前视图失效或降级。",
            "- 前次变化：no_previous_run，未找到可比较的上一次成功决策智能运行。",
            "- 不确定性与方法限制：该判断来自本地量化材料和确定性决策规则，不是交易指令。",
            "",
            "## 文本事件",
            "",
            "coindesk 提供了公开文本事件。",
            "",
            "## 综合判断",
            "",
            "量化信号结论和文本材料共同构成本地研究上下文。",
            "",
            "## 观察要点",
            "",
            "- 继续观察趋势、动量、波动和成交量异常信号的变化。",
            "",
            "## 风险提示",
            "",
            "样本窗口较短，趋势和波动信号可能随新增 OHLCV 数据快速变化。",
            "",
        ]
    )


def _millis(value: datetime) -> int:
    return int(value.timestamp() * 1000)


class _JsonResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class _BytesResponse:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def read(self) -> bytes:
        return self.payload
