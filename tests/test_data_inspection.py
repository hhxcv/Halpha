from __future__ import annotations

import json
from pathlib import Path

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
    assert "latest_successful_run_id=run-1" in output
    assert "text_event_history: ok" in output
    assert "records=2" in output
    assert "ohlcv_history: ok" in output
    assert "items=1" in output
    assert "derivatives_market_history: skipped" in output
    assert "macro_calendar_history: skipped" in output
    assert "onchain_flow_history: skipped" in output
    assert "feature_factor_artifacts: skipped" in output
    assert "data_quality_summary: degraded" in output
    assert "run_id=run-1" in output
    assert "checks=25" in output
    assert "degraded=1" in output
    assert "runs/run-1/analysis/data_quality_summary.json" in output
    assert "CREATE TABLE" not in output
    assert "content_text" not in output
    assert "stable_event_key" not in output
    assert str(tmp_path) not in output


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
    assert "run_id=run-without-quality" in output
    assert "run_status=succeeded" in output


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
                "checks": 25,
                "ok": 25 - degraded_count - warning_count,
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
