from __future__ import annotations

import json
from pathlib import Path
import sqlite3

import pytest

from halpha.cli import main
from halpha.pipeline import RunContext
from halpha.run_index import write_run_index
from halpha.storage import write_json


def test_data_inspect_reports_missing_optional_stores_without_private_config_values(
    tmp_path: Path,
    capsys,
) -> None:
    config_path = _write_config(
        tmp_path,
        ohlcv_enabled=False,
        proxy_url="http://private-host.local:18080",
    )

    exit_code = main(["data", "inspect", "--config", str(config_path)])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Halpha data inspection succeeded." in output
    assert "status: ok" in output
    assert "research_data_catalog: skipped" in output
    assert "run_index: skipped" in output
    assert "text_event_history: skipped" in output
    assert "ohlcv_history: skipped" in output
    assert "derivatives_market_history: skipped" in output
    assert "macro_calendar_history: skipped" in output
    assert "onchain_flow_history: skipped" in output
    assert "feature_factor_artifacts: skipped" in output
    assert "intelligence_fusion: skipped" in output
    assert "strategy_lifecycle: skipped" in output
    assert "personalized_risk: skipped" in output
    assert "product_validation: skipped" in output
    assert "workbench: skipped" in output
    assert "data_quality_summary: skipped" in output
    assert "private-host" not in output
    assert "18080" not in output
    assert str(tmp_path) not in output


def test_data_inspect_reports_local_stores_and_degraded_quality_summary(
    tmp_path: Path,
    capsys,
) -> None:
    config_path = _write_config(tmp_path, ohlcv_enabled=True)
    run = _write_run_with_quality(tmp_path, config_path, quality_status="degraded")
    _write_store_metadata(tmp_path, run)

    exit_code = main(["data", "inspect", "--config", str(config_path)])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Halpha data inspection succeeded." in output
    assert "status: degraded" in output
    assert "research_data_catalog: ok" in output
    assert "stores=3" in output
    assert "store_statuses: ohlcv_history=ok, run_index=ok, text_event_history=ok" in output
    assert "run_index: ok" in output
    assert "latest_run_id=run-1" in output
    assert "latest_successful_run_id=run-1" in output
    assert "selected_run_id=run-1" in output
    assert "selected_run_source=latest_successful_run" in output
    assert "text_event_history: ok" in output
    assert "records=2" in output
    assert "ohlcv_history: ok" in output
    assert "items=1" in output
    assert "derivatives_market_history: skipped" in output
    assert "macro_calendar_history: skipped" in output
    assert "onchain_flow_history: skipped" in output
    assert "feature_factor_artifacts: skipped" in output
    assert "intelligence_fusion: skipped" in output
    assert "strategy_lifecycle: skipped" in output
    assert "personalized_risk: skipped" in output
    assert "product_validation: skipped" in output
    assert "workbench: skipped" in output
    assert "data_quality_summary: degraded" in output
    assert "run_id=run-1" in output
    assert "checks=30" in output
    assert "degraded=1" in output
    assert "runs/run-1/analysis/data_quality_summary.json" in output
    assert "CREATE TABLE" not in output
    assert "content_text" not in output
    assert "stable_event_key" not in output
    assert str(tmp_path) not in output


def test_data_inspect_ignores_latest_run_index_outside_project_root(
    tmp_path: Path,
    capsys,
) -> None:
    config_path = _write_config(tmp_path, ohlcv_enabled=True)
    run = _write_run_with_quality(tmp_path, config_path, quality_status="ok")
    outside_dir = tmp_path.parent / "outside-data-inspect-run"
    write_json(
        outside_dir / "run_manifest.json",
        {
            "schema_version": 1,
            "run_id": run.run_id,
            "status": "succeeded",
            "private_note": "outside data inspect manifest was read",
        },
    )
    with sqlite3.connect(tmp_path / "data" / "research" / "index.sqlite") as connection:
        connection.execute("UPDATE runs SET run_dir = ? WHERE run_id = ?", (str(outside_dir), run.run_id))
        connection.commit()

    exit_code = main(["data", "inspect", "--config", str(config_path)])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "data_quality_summary: skipped" in output
    assert "outside data inspect manifest was read" not in output
    assert str(outside_dir) not in output


def test_data_inspect_uses_specific_run_dir_and_reports_missing_quality_as_skipped(
    tmp_path: Path,
    capsys,
) -> None:
    config_path = _write_config(tmp_path, ohlcv_enabled=False)
    run_dir = tmp_path / "runs" / "run-without-quality"
    run_dir.mkdir(parents=True)
    write_json(
        run_dir / "run_manifest.json",
        {
            "schema_version": 1,
            "run_id": "run-without-quality",
            "status": "succeeded",
            "artifacts": {},
            "counts": {},
            "stages": [],
            "errors": [],
        },
    )

    exit_code = main(
        [
            "data",
            "inspect",
            "--config",
            str(config_path),
            "--run-dir",
            "runs/run-without-quality",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "data_quality_summary: skipped" in output
    assert "personalized_risk: skipped" in output
    assert "product_validation: skipped" in output
    assert "workbench: skipped" in output
    assert "run_id=run-without-quality" in output
    assert "run_status=succeeded" in output


def test_data_inspect_reports_workbench_outputs_without_dumping_summary(
    tmp_path: Path,
    capsys,
) -> None:
    config_path = _write_config(tmp_path, ohlcv_enabled=False)
    workbench_dir = tmp_path / "runs" / "workbench" / "latest"
    write_json(
        workbench_dir / "workbench_summary.json",
        {
            "schema_version": 1,
            "artifact_type": "workbench_summary",
            "status": "partial",
            "generated_at": "2026-06-20T00:00:00Z",
            "latest_run": {"fields": {"run_id": "run-1", "run_status": "succeeded"}},
            "decision_state": {"status": "available"},
            "alert_state": {"status": "available"},
            "monitor_state": {"status": "available"},
            "outcome_state": {"status": "partial"},
            "strategy_state": {"status": "available"},
            "data_quality_state": {"status": "partial"},
            "index_outputs": {
                "status": "available",
                "markdown": "runs/workbench/latest/index.md",
                "html": "runs/workbench/latest/index.html",
            },
            "warnings": ["bounded warning"],
            "errors": [],
            "source_artifacts": {"analysis": {"decision": "analysis/decision_recommendations.json"}},
        },
    )
    (workbench_dir / "index.md").write_text("# Halpha Workbench\n", encoding="utf-8")
    (workbench_dir / "index.html").write_text("<!doctype html>\n", encoding="utf-8")

    exit_code = main(["data", "inspect", "--config", str(config_path)])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "workbench: partial" in output
    assert "artifact=runs/workbench/latest/workbench_summary.json" in output
    assert "latest_run_id=run-1" in output
    assert "decision_state=available" in output
    assert "outcome_state=partial" in output
    assert "index_markdown=runs/workbench/latest/index.md" in output
    assert "index_html=runs/workbench/latest/index.html" in output
    assert "bounded warning" not in output
    assert "analysis/decision_recommendations.json" not in output


def test_data_inspect_reports_product_validation_without_raw_records(
    tmp_path: Path,
    capsys,
) -> None:
    config_path = _write_config(tmp_path, ohlcv_enabled=False)
    run = _write_run_with_quality(tmp_path, config_path, quality_status="ok")
    _write_product_validation_artifact(run, status="failed")

    exit_code = main(
        [
            "data",
            "inspect",
            "--config",
            str(config_path),
            "--run-dir",
            "runs/run-1",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "product_validation: failed" in output
    assert "checks=4" in output
    assert "failed=1" in output
    assert "warning=1" in output
    assert "source_refs=run_manifest.json,analysis/risk_assessment.json" in output
    assert "artifact=runs/run-1/analysis/product_contract_validation.json" in output
    assert "private validation detail" not in output
    assert "check_id" not in output


def test_data_inspect_reports_feature_factor_artifacts_and_codex_budget(
    tmp_path: Path,
    capsys,
) -> None:
    config_path = _write_config(tmp_path, ohlcv_enabled=False)
    run = _write_run_with_quality(tmp_path, config_path, quality_status="ok")
    _write_m13_inspection_artifacts(run)

    exit_code = main(
        [
            "data",
            "inspect",
            "--config",
            str(config_path),
            "--run-dir",
            "runs/run-1",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "feature_factor_artifacts: warning" in output
    assert "feature_records=2" in output
    assert "factor_records=2" in output
    assert "signal_records=1" in output
    assert "signal_conflicting=1" in output
    assert "material_records=5" in output
    assert "material_omitted_records=3" in output
    assert "m13_quality_ok=3" in output
    assert "m13_quality_warning=1" in output
    assert "codex_budget_status=included" in output
    assert "codex_budget_chars=2048" in output
    assert "codex_budget_over_budget=False" in output
    assert "feature_id" not in output
    assert "factor_id" not in output
    assert "signal_id" not in output


def test_data_inspect_reports_intelligence_fusion_artifacts_and_codex_budget(
    tmp_path: Path,
    capsys,
) -> None:
    config_path = _write_config(tmp_path, ohlcv_enabled=False)
    run = _write_run_with_quality(tmp_path, config_path, quality_status="ok")
    _write_fusion_inspection_artifacts(run)

    exit_code = main(
        [
            "data",
            "inspect",
            "--config",
            str(config_path),
            "--run-dir",
            "runs/run-1",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "intelligence_fusion: warning" in output
    assert "fusion_records=3" in output
    assert "fusion_state_counts=conflicting:1,supportive:2" in output
    assert "fusion_conflict_counts=severe:1" in output
    assert "fusion_risk_override_counts=block:1" in output
    assert "fusion_event_override_counts=watch:1" in output
    assert "decision_linked_records=2" in output
    assert "decision_adjusted_records=1" in output
    assert "alert_linked_records=2" in output
    assert "alert_adjusted_records=1" in output
    assert "material_records=3" in output
    assert "material_omitted_records=2" in output
    assert "fusion_quality_ok=1" in output
    assert "fusion_quality_warning=1" in output
    assert "codex_budget_status=included" in output
    assert "codex_budget_chars=3072" in output
    assert "fusion_record_id" not in output
    assert "bounded fusion evidence" not in output


def test_data_inspect_reports_strategy_lifecycle_artifacts_without_raw_records(
    tmp_path: Path,
    capsys,
) -> None:
    config_path = _write_config(tmp_path, ohlcv_enabled=False)
    run = _write_run_with_quality(tmp_path, config_path, quality_status="ok")
    _write_lifecycle_inspection_artifacts(run)

    exit_code = main(
        [
            "data",
            "inspect",
            "--config",
            str(config_path),
            "--run-dir",
            "runs/run-1",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "strategy_lifecycle: warning" in output
    assert "state_artifact=analysis/strategy_lifecycle_state.json" in output
    assert "material_artifact=analysis/strategy_lifecycle_material.md" in output
    assert "lifecycle_status_counts=degraded:1,effective:1,retired:1" in output
    assert "lifecycle_records=3" in output
    assert "lifecycle_degraded=1" in output
    assert "lifecycle_retired=1" in output
    assert "lifecycle_policy_records=1" in output
    assert "material_records=3" in output
    assert "material_omitted_records=0" in output
    assert "codex_budget_status=included" in output
    assert "strategy_lifecycle:private" not in output
    assert "private lifecycle policy reason" not in output
    assert str(tmp_path) not in output


def test_data_inspect_reports_personalized_risk_artifacts_and_codex_budget(
    tmp_path: Path,
    capsys,
) -> None:
    config_path = _write_config(tmp_path, ohlcv_enabled=False)
    run = _write_run_with_quality(tmp_path, config_path, quality_status="ok")
    _write_m15_inspection_artifacts(run)

    exit_code = main(
        [
            "data",
            "inspect",
            "--config",
            str(config_path),
            "--run-dir",
            "runs/run-1",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "personalized_risk: warning" in output
    assert "user_state_status=ok" in output
    assert "user_state_mode=personalized" in output
    assert "user_state_watchlist_records=2" in output
    assert "user_state_disabled_assets=1" in output
    assert "user_state_omitted_private_values=1" in output
    assert "constraint_records=3" in output
    assert "constraint_state_counts=risk_limit_downgraded:1,watchlist_relevant:2" in output
    assert "constraint_action_counts=annotate:2,downgrade:1" in output
    assert "integration_status=succeeded" in output
    assert "decision_linked_records=2" in output
    assert "decision_adjusted_records=1" in output
    assert "watch_linked_records=1" in output
    assert "alert_adjusted_records=1" in output
    assert "material_records=3" in output
    assert "material_omitted_records=1" in output
    assert "m15_quality_ok=2" in output
    assert "m15_quality_warning=1" in output
    assert "codex_budget_status=included" in output
    assert "codex_budget_chars=1536" in output
    assert "configured_user_state" not in output
    assert "private_note" not in output
    assert str(tmp_path) not in output


def test_data_inspect_reports_derivatives_store_and_current_run_views(
    tmp_path: Path,
    capsys,
) -> None:
    config_path = _write_config(tmp_path, ohlcv_enabled=False, derivatives_enabled=True)
    run = _write_run_with_quality(tmp_path, config_path, quality_status="ok")
    _write_derivatives_store_metadata(tmp_path)
    _write_derivatives_views(run)

    exit_code = main(["data", "inspect", "--config", str(config_path)])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "status: ok" in output
    assert "derivatives_market_history: ok" in output
    assert "records=3" in output
    assert "groups=1" in output
    assert "schema_version=1" in output
    assert "views=2" in output
    assert "insufficient_views=1" in output
    assert "skipped_views=1" in output
    assert "derivatives_market_state.json" in output
    assert str(tmp_path) not in output


def test_data_inspect_reports_macro_calendar_store_and_current_run_views(
    tmp_path: Path,
    capsys,
) -> None:
    config_path = _write_config(tmp_path, ohlcv_enabled=False, macro_enabled=True)
    run = _write_run_with_quality(tmp_path, config_path, quality_status="ok")
    _write_macro_store_metadata(tmp_path)
    _write_macro_calendar_views(run)

    exit_code = main(["data", "inspect", "--config", str(config_path)])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "status: ok" in output
    assert "macro_calendar_history: ok" in output
    assert "records=2" in output
    assert "groups=1" in output
    assert "schema_version=1" in output
    assert "duplicate_records=1" in output
    assert "conflicting_duplicates=1" in output
    assert "availability_records=2" in output
    assert "no_event_records=1" in output
    assert "partial_records=1" in output
    assert "views=4" in output
    assert "view_records=1" in output
    assert "no_event_views=1" in output
    assert "stale_views=1" in output
    assert "skipped_views=1" in output
    assert "macro_calendar_state.json" in output
    assert "fomc_meeting" not in output
    assert str(tmp_path) not in output


def test_data_inspect_reports_onchain_flow_store_and_current_run_views(
    tmp_path: Path,
    capsys,
) -> None:
    config_path = _write_config(tmp_path, ohlcv_enabled=False, onchain_enabled=True)
    run = _write_run_with_quality(tmp_path, config_path, quality_status="ok")
    _write_onchain_flow_store_metadata(tmp_path)
    _write_onchain_flow_views(run)

    exit_code = main(["data", "inspect", "--config", str(config_path)])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "status: ok" in output
    assert "onchain_flow_history: ok" in output
    assert "records=4" in output
    assert "groups=1" in output
    assert "schema_version=1" in output
    assert "duplicate_records=1" in output
    assert "conflicting_duplicates=1" in output
    assert "availability_records=2" in output
    assert "partial_records=1" in output
    assert "unavailable_records=1" in output
    assert "views=4" in output
    assert "view_records=2" in output
    assert "bounded_views=1" in output
    assert "stale_views=1" in output
    assert "skipped_views=1" in output
    assert "onchain_flow_state.json" in output
    assert "total_circulating_usd" not in output
    assert str(tmp_path) not in output


def test_data_inspect_returns_error_for_missing_requested_run_dir(tmp_path: Path, capsys) -> None:
    config_path = _write_config(tmp_path, ohlcv_enabled=False)

    exit_code = main(
        [
            "data",
            "inspect",
            "--config",
            str(config_path),
            "--run-dir",
            "runs/missing",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 3
    assert "Halpha data inspection failed." in output
    assert "stage: data_inspect" in output
    assert "requested run directory was not found" in output


def test_data_inspect_help_mentions_run_dir(capsys) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["data", "inspect", "--help"])

    output = capsys.readouterr().out
    assert exc.value.code == 0
    assert "Inspect local stores and data-quality state." in output
    assert "--config" in output
    assert "--run-dir" in output


def _write_config(
    tmp_path: Path,
    *,
    ohlcv_enabled: bool,
    derivatives_enabled: bool = False,
    macro_enabled: bool = False,
    onchain_enabled: bool = False,
    proxy_url: str | None = None,
) -> Path:
    proxy_block = (
        f"""
  proxy:
    enabled: true
    url: {proxy_url}
"""
        if proxy_url
        else """
  proxy:
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
      1d: 10
"""
        if ohlcv_enabled
        else ""
    )
    derivatives_block = (
        """
  derivatives:
    enabled: true
    source: binance_usdm
    symbols:
      - BTCUSDT
    data_classes:
      - funding_rate
      - open_interest
    periods:
      - 5m
    lookback:
      5m: 2
"""
        if derivatives_enabled
        else ""
    )
    macro_block = (
        """
macro_calendar:
  enabled: true
  source: federal_reserve_fomc
  data_classes:
    - central_bank_event
  regions:
    - US
  lookback_days: 7
  lookahead_days: 45
"""
        if macro_enabled
        else """
macro_calendar:
  enabled: false
"""
    )
    onchain_block = (
        """
onchain_flow:
  enabled: true
  source: public_aggregate
  data_classes:
    - stablecoin_supply
    - exchange_flow_availability
  assets:
    - ALL_STABLECOINS
    - BTC
  chains:
    - all
    - bitcoin
  lookback_days: 7
"""
        if onchain_enabled
        else """
onchain_flow:
  enabled: false
"""
    )
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        f"""
run:
  output_dir: runs
  timezone: Asia/Shanghai
market:
  enabled: true
  source: binance
{proxy_block.rstrip()}
  symbols:
    - BTCUSDT
{ohlcv_block.rstrip()}
{derivatives_block.rstrip()}
{macro_block.rstrip()}
{onchain_block.rstrip()}
text:
  enabled: false
report:
  title: Daily Market Brief
  language: zh-CN
codex:
  enabled: false
""".strip(),
        encoding="utf-8",
    )
    return config_path


def _write_run_with_quality(tmp_path: Path, config_path: Path, *, quality_status: str) -> RunContext:
    run_dir = tmp_path / "runs" / "run-1"
    raw_dir = run_dir / "raw"
    analysis_dir = run_dir / "analysis"
    codex_context_dir = run_dir / "codex_context"
    report_dir = run_dir / "report"
    for directory in (raw_dir, analysis_dir, codex_context_dir, report_dir):
        directory.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": 1,
        "run_id": "run-1",
        "status": "succeeded",
        "started_at": "2026-06-05T00:00:00Z",
        "finished_at": "2026-06-05T00:10:00Z",
        "artifacts": {"data_quality_summary": "analysis/data_quality_summary.json"},
        "counts": {},
        "stages": [{"name": "build_data_quality_summary", "status": "succeeded"}],
        "codex": {"status": "skipped"},
        "errors": [],
    }
    run = RunContext(
        run_id="run-1",
        run_dir=run_dir,
        raw_dir=raw_dir,
        analysis_dir=analysis_dir,
        codex_context_dir=codex_context_dir,
        report_dir=report_dir,
        manifest_path=run_dir / "run_manifest.json",
        config_path=config_path,
        manifest=manifest,
    )
    write_json(run.manifest_path, manifest)
    warning_messages = ["one configured source returned partial data."] if quality_status != "ok" else []
    degraded_count = 1 if quality_status == "degraded" else 0
    warning_count = 1 if quality_status == "warning" else 0
    write_json(
        analysis_dir / "data_quality_summary.json",
        {
            "schema_version": 1,
            "artifact_type": "data_quality_summary",
            "run_id": "run-1",
            "created_at": "2026-06-05T00:10:00Z",
            "status": quality_status,
            "counts": {
                "checks": 30,
                "ok": 30 - degraded_count - warning_count,
                "warning": warning_count,
                "degraded": degraded_count,
                "skipped": 0,
                "failed": 0,
                "warnings": len(warning_messages),
                "errors": 0,
            },
            "checks": [],
            "warnings": warning_messages,
            "errors": [],
            "source_artifacts": ["raw/market.json"],
        },
    )
    summary = write_run_index(run, now="2026-06-05T00:10:00Z")
    run.manifest["run_index"] = summary
    return run


def _write_product_validation_artifact(run: RunContext, *, status: str) -> None:
    run.manifest["artifacts"]["product_contract_validation"] = "analysis/product_contract_validation.json"
    write_json(run.manifest_path, run.manifest)
    write_json(
        run.analysis_dir / "product_contract_validation.json",
        {
            "schema_version": 1,
            "artifact_type": "product_contract_validation",
            "run_id": run.run_id,
            "status": status,
            "counts": {
                "checks": 4,
                "ok": 2,
                "warning": 1,
                "degraded": 0,
                "failed": 1,
                "skipped": 0,
                "warnings": 1,
                "errors": 1,
            },
            "checks": [
                {
                    "check_id": "artifact_ref:analysis/risk_assessment.json",
                    "status": "failed",
                    "message": "private validation detail",
                }
            ],
            "source_artifacts": [
                "run_manifest.json",
                "analysis/risk_assessment.json",
                "analysis/decision_recommendations.json",
            ],
            "warnings": ["private validation detail"],
            "errors": ["private validation detail"],
        },
    )


def _write_m13_inspection_artifacts(run: RunContext) -> None:
    run.manifest["artifacts"].update(
        {
            "feature_snapshots": "analysis/feature_snapshots.json",
            "factor_states": "analysis/factor_states.json",
            "multi_source_signals": "analysis/multi_source_signals.json",
            "factor_signal_material": "analysis/factor_signal_material.md",
        }
    )
    run.manifest["feature_snapshots"] = {
        "status": "ok",
        "artifact": "analysis/feature_snapshots.json",
        "records": 2,
        "coverage_records": 3,
        "warnings": 0,
        "errors": 0,
    }
    run.manifest["factor_states"] = {
        "status": "ok",
        "artifact": "analysis/factor_states.json",
        "records": 2,
        "warnings": 0,
        "errors": 0,
    }
    run.manifest["multi_source_signals"] = {
        "status": "warning",
        "artifact": "analysis/multi_source_signals.json",
        "records": 1,
        "conflicting": 1,
        "warnings": 1,
        "errors": 0,
    }
    run.manifest["factor_signal_material"] = {
        "status": "ok",
        "artifact": "analysis/factor_signal_material.md",
    }
    run.manifest["counts"].update(
        {
            "feature_snapshots": 2,
            "feature_snapshot_coverage_records": 3,
            "feature_snapshot_warnings": 0,
            "feature_snapshot_errors": 0,
            "factor_states": 2,
            "factor_state_warnings": 0,
            "factor_state_errors": 0,
            "multi_source_signals": 1,
            "multi_source_signal_conflicting": 1,
            "multi_source_signal_warnings": 1,
            "multi_source_signal_errors": 0,
            "factor_signal_material_records": 5,
            "factor_signal_material_omitted_records": 3,
        }
    )
    run.manifest["codex_input"] = {
        "materials": {
            "analysis/factor_signal_material.md": {
                "status": "included",
                "chars": 2048,
                "over_budget": False,
                "warnings": [],
            }
        }
    }
    write_json(run.manifest_path, run.manifest)

    quality_path = run.analysis_dir / "data_quality_summary.json"
    quality = json.loads(quality_path.read_text(encoding="utf-8"))
    quality["checks"] = [
        _quality_check("feature_snapshots", "ok"),
        _quality_check("factor_states", "ok"),
        _quality_check("multi_source_signals", "warning"),
        _quality_check("factor_signal_material", "ok"),
    ]
    quality["counts"] = {
        "checks": 4,
        "ok": 3,
        "warning": 1,
        "degraded": 0,
        "skipped": 0,
        "failed": 0,
        "warnings": 1,
        "errors": 0,
    }
    quality["status"] = "warning"
    quality["warnings"] = ["one multi-source signal is conflicting."]
    write_json(quality_path, quality)


def _write_fusion_inspection_artifacts(run: RunContext) -> None:
    run.manifest["artifacts"].update(
        {
            "intelligence_fusion": "analysis/intelligence_fusion.json",
            "intelligence_fusion_material": "analysis/intelligence_fusion_material.md",
        }
    )
    run.manifest["intelligence_fusion"] = {
        "status": "warning",
        "artifact": "analysis/intelligence_fusion.json",
        "records": 3,
        "state_counts": {"supportive": 2, "conflicting": 1},
        "confluence_counts": {"aligned": 2},
        "conflict_counts": {"severe": 1},
        "risk_override_counts": {"block": 1},
        "event_override_counts": {"watch": 1},
        "outcome_feedback_counts": {"mixed": 1, "supportive": 2},
        "warnings": 1,
        "errors": 0,
    }
    run.manifest["intelligence_fusion_integration"] = {
        "status": "succeeded",
        "source_artifact": "analysis/intelligence_fusion.json",
        "decision_records": 2,
        "decision_linked_records": 2,
        "decision_adjusted_records": 1,
        "alert_records": 2,
        "alert_linked_records": 2,
        "alert_adjusted_records": 1,
        "warnings": 0,
        "errors": 0,
    }
    run.manifest["intelligence_fusion_material"] = {
        "status": "ok",
        "artifact": "analysis/intelligence_fusion_material.md",
        "selected_records": 3,
        "omitted_records": 2,
        "warnings": 0,
        "errors": 0,
    }
    run.manifest["counts"].update(
        {
            "intelligence_fusion_records": 3,
            "intelligence_fusion_warnings": 1,
            "intelligence_fusion_errors": 0,
            "intelligence_fusion_supportive_records": 2,
            "intelligence_fusion_conflicting_records": 1,
            "intelligence_fusion_decision_linked_records": 2,
            "intelligence_fusion_decision_adjusted_records": 1,
            "intelligence_fusion_alert_linked_records": 2,
            "intelligence_fusion_alert_adjusted_records": 1,
            "intelligence_fusion_material_records": 3,
            "intelligence_fusion_material_omitted_records": 2,
        }
    )
    run.manifest["codex_input"] = {
        "materials": {
            "analysis/intelligence_fusion_material.md": {
                "status": "included",
                "chars": 3072,
                "over_budget": False,
                "warnings": [],
            }
        }
    }
    write_json(run.manifest_path, run.manifest)

    quality_path = run.analysis_dir / "data_quality_summary.json"
    quality = json.loads(quality_path.read_text(encoding="utf-8"))
    quality["checks"] = [
        _quality_check("intelligence_fusion", "warning"),
        _quality_check("intelligence_fusion_material", "ok"),
    ]
    quality["counts"] = {
        "checks": 2,
        "ok": 1,
        "warning": 1,
        "degraded": 0,
        "skipped": 0,
        "failed": 0,
        "warnings": 1,
        "errors": 0,
    }
    quality["status"] = "warning"
    quality["warnings"] = ["one intelligence fusion record is conflicting."]
    write_json(quality_path, quality)


def _write_lifecycle_inspection_artifacts(run: RunContext) -> None:
    run.manifest["artifacts"].update(
        {
            "strategy_lifecycle_state": "analysis/strategy_lifecycle_state.json",
            "strategy_lifecycle_material": "analysis/strategy_lifecycle_material.md",
        }
    )
    run.manifest["strategy_lifecycle_state"] = {
        "status": "warning",
        "artifact": "analysis/strategy_lifecycle_state.json",
        "records": 3,
        "lifecycle_status_counts": {"effective": 1, "degraded": 1, "retired": 1},
        "warnings": 1,
        "errors": 0,
    }
    run.manifest["strategy_lifecycle_material"] = {
        "status": "ok",
        "artifact": "analysis/strategy_lifecycle_material.md",
        "selected_records": 3,
        "omitted_records": 0,
        "warnings": 0,
        "errors": 0,
    }
    run.manifest["counts"].update(
        {
            "strategy_lifecycle_records": 3,
            "strategy_lifecycle_effective": 1,
            "strategy_lifecycle_active_candidate": 0,
            "strategy_lifecycle_watchlisted": 0,
            "strategy_lifecycle_rejected": 0,
            "strategy_lifecycle_degraded": 1,
            "strategy_lifecycle_retired": 1,
            "strategy_lifecycle_insufficient_evidence": 0,
            "strategy_lifecycle_failed": 0,
            "strategy_lifecycle_policy_records": 1,
            "strategy_lifecycle_warnings": 1,
            "strategy_lifecycle_errors": 0,
            "strategy_lifecycle_material_records": 3,
            "strategy_lifecycle_material_omitted_records": 0,
        }
    )
    run.manifest["codex_input"] = {
        "materials": {
            "analysis/strategy_lifecycle_material.md": {
                "status": "included",
                "chars": 2048,
                "over_budget": False,
                "warnings": [],
            }
        }
    }
    write_json(
        run.analysis_dir / "strategy_lifecycle_state.json",
        {
            "schema_version": 1,
            "artifact_type": "strategy_lifecycle_state",
            "status": "warning",
            "counts": {"by_lifecycle_status": {"effective": 1, "degraded": 1, "retired": 1}},
            "records": [
                {
                    "lifecycle_record_id": "strategy_lifecycle:private:BTCUSDT:1d",
                    "lifecycle_status": "retired",
                    "retirement": {
                        "state": "explicitly_retired",
                        "policy_refs": ["private lifecycle policy reason"],
                    },
                }
            ],
            "warnings": ["one lifecycle record requires review."],
            "errors": [],
        },
    )
    (run.analysis_dir / "strategy_lifecycle_material.md").write_text(
        "# strategy_lifecycle_material\n",
        encoding="utf-8",
    )
    write_json(run.manifest_path, run.manifest)


def _write_m15_inspection_artifacts(run: RunContext) -> None:
    run.manifest["artifacts"].update(
        {
            "user_state_context": "analysis/user_state_context.json",
            "personalized_risk_constraints": "analysis/personalized_risk_constraints.json",
            "personalized_risk_material": "analysis/personalized_risk_material.md",
        }
    )
    run.manifest["user_state_context"] = {
        "status": "ok",
        "mode": "personalized",
        "artifact": "analysis/user_state_context.json",
        "watchlist_records": 2,
        "disabled_assets": 1,
        "preferred_timeframes": 2,
        "strategy_preference_records": 1,
        "manual_exposure_summary_records": 1,
        "omitted_private_values": 1,
        "warnings": 0,
        "errors": 0,
    }
    run.manifest["personalized_risk_constraints"] = {
        "status": "warning",
        "artifact": "analysis/personalized_risk_constraints.json",
        "records": 3,
        "state_counts": {"watchlist_relevant": 2, "risk_limit_downgraded": 1},
        "action_counts": {"annotate": 2, "downgrade": 1},
        "warnings": 1,
        "errors": 0,
    }
    run.manifest["personalized_risk_integration"] = {
        "status": "succeeded",
        "source_artifact": "analysis/personalized_risk_constraints.json",
        "decision_records": 2,
        "decision_linked_records": 2,
        "decision_adjusted_records": 1,
        "watch_records": 1,
        "watch_linked_records": 1,
        "watch_adjusted_records": 0,
        "alert_records": 2,
        "alert_linked_records": 2,
        "alert_adjusted_records": 1,
        "warnings": 0,
        "errors": 0,
    }
    run.manifest["personalized_risk_material"] = {
        "status": "ok",
        "artifact": "analysis/personalized_risk_material.md",
        "selected_records": 3,
        "omitted_records": 1,
        "warnings": 0,
        "errors": 0,
    }
    run.manifest["counts"].update(
        {
            "user_state_watchlist_records": 2,
            "user_state_disabled_assets": 1,
            "user_state_preferred_timeframes": 2,
            "user_state_strategy_preference_records": 1,
            "user_state_manual_exposure_summary_records": 1,
            "user_state_omitted_private_values": 1,
            "personalized_risk_constraint_records": 3,
            "personalized_risk_decision_linked_records": 2,
            "personalized_risk_decision_adjusted_records": 1,
            "personalized_risk_watch_linked_records": 1,
            "personalized_risk_watch_adjusted_records": 0,
            "personalized_risk_alert_linked_records": 2,
            "personalized_risk_alert_adjusted_records": 1,
            "personalized_risk_material_records": 3,
            "personalized_risk_material_omitted_records": 1,
        }
    )
    run.manifest["codex_input"] = {
        "materials": {
            "analysis/personalized_risk_material.md": {
                "status": "included",
                "chars": 1536,
                "over_budget": False,
                "warnings": [],
            }
        }
    }
    write_json(run.manifest_path, run.manifest)

    quality_path = run.analysis_dir / "data_quality_summary.json"
    quality = json.loads(quality_path.read_text(encoding="utf-8"))
    quality["checks"] = [
        _quality_check("user_state_context", "ok"),
        _quality_check("personalized_risk_constraints", "warning"),
        _quality_check("personalized_risk_material", "ok"),
    ]
    quality["counts"] = {
        "checks": 3,
        "ok": 2,
        "warning": 1,
        "degraded": 0,
        "skipped": 0,
        "failed": 0,
        "warnings": 1,
        "errors": 0,
    }
    quality["status"] = "warning"
    quality["warnings"] = ["one personalized constraint is conservative."]
    write_json(quality_path, quality)


def _quality_check(name: str, status: str) -> dict[str, object]:
    return {
        "name": name,
        "scope": "analysis",
        "status": status,
        "summary": f"{name} status: {status}",
        "warning_count": 1 if status == "warning" else 0,
        "error_count": 0,
        "source_artifacts": [],
        "details": {"warnings": ["conflict"] if status == "warning" else [], "errors": []},
    }


def _write_derivatives_store_metadata(tmp_path: Path) -> None:
    write_json(
        tmp_path / "data" / "market" / "metadata" / "derivatives_market_schema.json",
        {
            "schema_version": 1,
            "artifact_type": "derivatives_market_schema",
            "identity": ["source", "market_type", "data_class", "symbol", "period", "as_of"],
        },
    )
    write_json(
        tmp_path / "data" / "market" / "metadata" / "derivatives_market_state.json",
        {
            "schema_version": 1,
            "artifact_type": "derivatives_market_state",
            "updated_at": "2026-06-05T00:10:00Z",
            "status": "ok",
            "storage_path": "data/market/derivatives",
            "totals": {"records": 3},
            "groups": [{"source": "binance_usdm", "data_class": "funding_rate", "row_count": 3}],
            "warnings": [],
            "errors": [],
        },
    )


def _write_derivatives_views(run: RunContext) -> None:
    write_json(
        run.raw_dir / "derivatives_market_views.json",
        {
            "schema_version": 1,
            "artifact_type": "derivatives_market_views",
            "created_at": "2026-06-05T00:10:00Z",
            "views": [
                {
                    "view_id": "derivatives_view:funding_rate:binance_usdm:BTCUSDT:8h:latest",
                    "status": "succeeded",
                    "latest_observation_time": "2026-06-05T00:00:00Z",
                    "insufficient_data": False,
                    "warnings": [],
                    "errors": [],
                },
                {
                    "view_id": "derivatives_view:spread_depth:binance_usdm:skipped",
                    "status": "skipped",
                    "latest_observation_time": None,
                    "insufficient_data": True,
                    "warnings": ["spread_depth derivatives views are not implemented."],
                    "errors": [],
                },
            ],
            "warnings": [],
            "errors": [],
        },
    )


def _write_macro_store_metadata(tmp_path: Path) -> None:
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
            "updated_at": "2026-06-05T00:10:00Z",
            "status": "ok",
            "storage_path": "data/macro/calendar",
            "totals": {
                "records": 2,
                "duplicate_records": 1,
                "conflicting_duplicates": 1,
            },
            "groups": [
                {
                    "source": "federal_reserve_fomc",
                    "data_class": "central_bank_event",
                    "region": "US",
                    "row_count": 2,
                }
            ],
            "availability": [
                {
                    "source": "federal_reserve_fomc",
                    "data_class": "central_bank_event",
                    "region": "US",
                    "status": "no_event",
                },
                {
                    "source": "federal_reserve_fomc",
                    "data_class": "central_bank_event",
                    "region": "US",
                    "status": "partial",
                },
            ],
            "warnings": [],
            "errors": [],
        },
    )


def _write_macro_calendar_views(run: RunContext) -> None:
    write_json(
        run.raw_dir / "macro_calendar_views.json",
        {
            "schema_version": 1,
            "artifact_type": "macro_calendar_views",
            "created_at": "2026-06-05T00:10:00Z",
            "views": [
                {
                    "view_id": "macro_calendar_view:central_bank_event:federal_reserve_fomc:US:latest",
                    "status": "succeeded",
                    "latest_observation_time": "2026-06-05T00:00:00Z",
                    "event_count": 1,
                    "included_record_count": 1,
                    "records": [{"event_type": "fomc_meeting"}],
                    "warnings": [],
                    "errors": [],
                },
                {
                    "view_id": "macro_calendar_view:central_bank_event:federal_reserve_fomc:US:no_event",
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


def _write_onchain_flow_store_metadata(tmp_path: Path) -> None:
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
            "updated_at": "2026-06-05T00:10:00Z",
            "status": "ok",
            "storage_path": "data/onchain/flow",
            "totals": {
                "records": 4,
                "duplicate_records": 1,
                "conflicting_duplicates": 1,
            },
            "groups": [
                {
                    "source": "defillama_stablecoins",
                    "data_class": "stablecoin_supply",
                    "asset": "ALL_STABLECOINS",
                    "chain": "all",
                    "row_count": 4,
                }
            ],
            "availability": [
                {
                    "source": "defillama_stablecoins",
                    "data_class": "stablecoin_supply",
                    "status": "partial",
                },
                {
                    "source": "public_aggregate",
                    "data_class": "exchange_flow_availability",
                    "status": "unavailable",
                },
            ],
            "warnings": [],
            "errors": [],
        },
    )


def _write_onchain_flow_views(run: RunContext) -> None:
    write_json(
        run.raw_dir / "onchain_flow_views.json",
        {
            "schema_version": 1,
            "artifact_type": "onchain_flow_views",
            "created_at": "2026-06-05T00:10:00Z",
            "views": [
                {
                    "view_id": "onchain_flow_view:stablecoin_supply:defillama_stablecoins:ALL_STABLECOINS:all:latest",
                    "status": "bounded",
                    "latest_observation_time": "2026-06-05T00:00:00Z",
                    "included_record_count": 2,
                    "records": [{"total_circulating_usd": 123.0}],
                    "warnings": [],
                    "errors": [],
                },
                {
                    "view_id": "onchain_flow_view:stablecoin_supply:defillama_stablecoins:ALL_STABLECOINS:all:partial",
                    "status": "partial",
                    "latest_observation_time": None,
                    "included_record_count": 0,
                    "records": [],
                    "warnings": [],
                    "errors": [],
                },
                {
                    "view_id": "onchain_flow_view:stablecoin_supply:defillama_stablecoins:ALL_STABLECOINS:all:stale",
                    "status": "stale",
                    "latest_observation_time": None,
                    "included_record_count": 0,
                    "records": [],
                    "warnings": [],
                    "errors": [],
                },
                {
                    "view_id": "onchain_flow_view:exchange_flow_availability:public_aggregate:BTC:bitcoin:skipped",
                    "status": "skipped",
                    "latest_observation_time": None,
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


def _write_store_metadata(tmp_path: Path, run: RunContext) -> None:
    write_json(
        tmp_path / "data" / "research" / "metadata" / "research_data_catalog.json",
        {
            "schema_version": 1,
            "artifact_type": "research_data_catalog",
            "generated_at": "2026-06-05T00:10:00Z",
            "status": "ok",
            "stores": [
                {"name": "ohlcv_history", "status": "ok"},
                {"name": "run_index", "status": "ok"},
                {"name": "text_event_history", "status": "ok"},
            ],
            "counts": {"stores": 3, "records": 5, "warnings": 0, "errors": 0},
            "warnings": [],
            "errors": [],
        },
    )
    write_json(
        tmp_path / "data" / "research" / "metadata" / "text_event_history_state.json",
        {
            "schema_version": 1,
            "status": "ok",
            "updated_at": "2026-06-05T00:10:00Z",
            "totals": {"records": 2},
            "sources": [{"source": "coindesk"}],
            "warnings": [],
            "errors": [],
        },
    )
    write_json(
        tmp_path / "data" / "market" / "metadata" / "ohlcv_schema.json",
        {
            "schema_version": 1,
            "unique_key": ["source", "symbol", "timeframe", "open_time"],
        },
    )
    write_json(
        tmp_path / "data" / "market" / "metadata" / "ohlcv_sync_state.json",
        {
            "schema_version": 1,
            "status": "ok",
            "updated_at": "2026-06-05T00:10:00Z",
            "items": [{"source": "binance", "symbol": "BTCUSDT", "timeframe": "1d", "row_count": 3}],
            "warnings": [],
            "errors": [],
        },
    )
