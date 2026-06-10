from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from halpha.config import load_config
from halpha.ohlcv_store import OHLCVParquetStore
from halpha.pipeline import run_pipeline


def test_pipeline_writes_strategy_evaluation_summary(tmp_path: Path) -> None:
    config_path = _write_strategy_config(tmp_path, lookback=5)
    config = load_config(config_path)
    store = OHLCVParquetStore(tmp_path / "data" / "market" / "ohlcv")
    store.write_records(
        [
            _record(open_time="2026-06-01T00:00:00Z", close=100),
            _record(open_time="2026-06-02T00:00:00Z", close=102),
            _record(open_time="2026-06-03T00:00:00Z", close=104),
            _record(open_time="2026-06-04T00:00:00Z", close=106),
            _record(open_time="2026-06-05T00:00:00Z", close=109),
        ]
    )

    result = _run_pipeline(config, config_path)

    artifact = _strategy_evaluation(result)
    material = _strategy_evaluation_material(result)
    manifest = _manifest(result)
    record = artifact["records"][0]

    assert result.succeeded is True
    assert artifact["artifact_type"] == "strategy_evaluation_summary"
    assert artifact["source_artifacts"] == [
        "analysis/quant_strategy_runs.json",
        "raw/market_data_views.json",
    ]
    assert len(artifact["records"]) == 1
    assert record["status"] == "succeeded"
    assert record["strategy_name"] == "tsmom_vol_scaled"
    assert record["single_window"]["status"] == "succeeded"
    assert record["single_window"]["execution_model"]["lookahead_policy"] == "no_same_bar_execution"
    assert record["single_window"]["cost_assumptions"]["fees_bps"] == 10.0
    assert record["single_window"]["cost_assumptions"]["total_one_way_bps"] == 15.0
    assert "cost_drag_pct" in record["single_window"]["strategy_metrics"]
    assert "buy_and_hold" in record["single_window"]["baseline_metrics"]
    assert "cash" in record["single_window"]["baseline_metrics"]
    assert "excess_return_vs_buy_and_hold_pct" in record["single_window"]["relative_metrics"]
    assert record["single_window"]["equity_curve"]
    assert record["walk_forward"]["enabled"] is True
    assert record["walk_forward"]["status"] == "insufficient_data"
    assert record["walk_forward"]["windows"] == []
    assert record["parameter_stability"] == {"enabled": False, "status": "disabled"}
    assert record["overfitting_risk"]["status"] in {"medium", "elevated"}
    assert record["assessment"]["reliability"] in {"low", "medium"}
    assert record["assessment"]["cost_sensitivity"] in {"low", "medium", "high"}
    assert any(item.startswith("cost_drag_pct:") for item in record["assessment"]["evidence"])
    warning_codes = {item["code"] for item in record["warnings"]}
    assert "historical_research_only" in warning_codes
    assert "insufficient_sample_length" in warning_codes
    assert manifest["artifacts"]["strategy_evaluation_summary"] == (
        "analysis/strategy_evaluation_summary.json"
    )
    assert manifest["artifacts"]["strategy_evaluation_material"] == (
        "analysis/strategy_evaluation_material.md"
    )
    assert manifest["counts"]["strategy_evaluation_records"] == 1
    assert manifest["counts"]["strategy_evaluation_material_records"] == 1
    assert manifest["counts"]["strategy_evaluation_succeeded"] == 1
    assert manifest["counts"]["strategy_evaluation_failed"] == 0
    assert manifest["strategy_evaluation"]["records"] == 1
    assert manifest["strategy_evaluation"]["coverage"] == {
        "quant_strategy_runs": 1,
        "evaluation_records": 1,
        "records_with_single_window": 1,
        "walk_forward_windows": 0,
        "records_with_walk_forward": 0,
        "records_with_parameter_stability": 0,
    }
    assert _stage(manifest, "evaluate_strategy_evaluation")["artifacts"] == [
        "analysis/strategy_evaluation_summary.json",
        "analysis/strategy_evaluation_material.md",
    ]
    assert "artifact_type: analysis_strategy_evaluation_material" in material
    assert "cost_assumptions:" in material
    assert "baseline_comparison:" in material
    assert "walk_forward:" in material
    assert "parameter_stability:" in material
    assert "overfitting_risk:" in material
    assert "codex_may_generate_metrics: false" in material
    assert "best_parameter_selection_allowed: false" in material
    stage_names = [item["name"] for item in manifest["stages"]]
    assert stage_names.index("evaluate_quant_strategies") < stage_names.index(
        "evaluate_strategy_evaluation"
    )
    assert stage_names.index("evaluate_strategy_evaluation") < stage_names.index(
        "evaluate_market_strategy_signals"
    )


def test_pipeline_writes_walk_forward_windows_when_history_is_sufficient(tmp_path: Path) -> None:
    config_path = _write_strategy_config(tmp_path, lookback=240)
    config = load_config(config_path)
    store = OHLCVParquetStore(tmp_path / "data" / "market" / "ohlcv")
    store.write_records(_walk_forward_records())

    result = _run_pipeline(config, config_path)

    artifact = _strategy_evaluation(result)
    manifest = _manifest(result)
    record = artifact["records"][0]
    walk_forward = record["walk_forward"]

    assert result.succeeded is True
    assert walk_forward["status"] == "succeeded"
    assert walk_forward["method"]["params_optimized_per_window"] is False
    assert walk_forward["summary"]["window_count"] == 3
    assert walk_forward["summary"]["succeeded_windows"] == 3
    assert len(walk_forward["windows"]) == 3
    assert walk_forward["windows"][0]["calibration_window"]["rows"] == 60
    assert walk_forward["windows"][0]["evaluation_window"]["rows"] == 60
    assert record["assessment"]["summary"].find("walk_forward_status is succeeded") >= 0
    assert any(
        item.startswith("walk_forward_succeeded_windows:")
        for item in record["assessment"]["evidence"]
    )
    assert manifest["counts"]["strategy_evaluation_walk_forward_records"] == 3
    assert manifest["strategy_evaluation"]["coverage"]["walk_forward_windows"] == 3
    assert manifest["strategy_evaluation"]["coverage"]["records_with_walk_forward"] == 1
    assert manifest["strategy_evaluation"]["coverage"]["records_with_parameter_stability"] == 0


def test_pipeline_records_stable_parameter_stability(tmp_path: Path) -> None:
    config_path = _write_strategy_config(
        tmp_path,
        lookback=5,
        parameter_diagnostics_enabled=True,
        parameter_grid_return_windows=[2],
    )
    config = load_config(config_path)
    store = OHLCVParquetStore(tmp_path / "data" / "market" / "ohlcv")
    store.write_records(
        [
            _record(open_time="2026-06-01T00:00:00Z", close=100),
            _record(open_time="2026-06-02T00:00:00Z", close=102),
            _record(open_time="2026-06-03T00:00:00Z", close=104),
            _record(open_time="2026-06-04T00:00:00Z", close=106),
            _record(open_time="2026-06-05T00:00:00Z", close=109),
        ]
    )

    result = _run_pipeline(config, config_path)

    record = _strategy_evaluation(result)["records"][0]
    manifest = _manifest(result)

    assert result.succeeded is True
    assert record["parameter_stability"]["enabled"] is True
    assert record["parameter_stability"]["status"] == "stable"
    assert record["parameter_stability"]["tested_combinations"] == 1
    assert record["parameter_stability"]["region_counts"]["stable"] == 1
    assert record["parameter_stability"]["warnings"] == []
    assert record["assessment"]["overfitting_risk"] in {"medium", "elevated"}
    assert manifest["counts"]["strategy_evaluation_parameter_stability_records"] == 1
    assert manifest["strategy_evaluation"]["coverage"]["records_with_parameter_stability"] == 1


def test_pipeline_records_fragile_parameter_stability(tmp_path: Path) -> None:
    config_path = _write_strategy_config(
        tmp_path,
        lookback=5,
        parameter_diagnostics_enabled=True,
        parameter_grid_return_windows=[2, 10],
    )
    config = load_config(config_path)
    store = OHLCVParquetStore(tmp_path / "data" / "market" / "ohlcv")
    store.write_records(
        [
            _record(open_time="2026-06-01T00:00:00Z", close=100),
            _record(open_time="2026-06-02T00:00:00Z", close=102),
            _record(open_time="2026-06-03T00:00:00Z", close=104),
            _record(open_time="2026-06-04T00:00:00Z", close=106),
            _record(open_time="2026-06-05T00:00:00Z", close=109),
        ]
    )

    result = _run_pipeline(config, config_path)

    record = _strategy_evaluation(result)["records"][0]
    warning_codes = {item["code"] for item in record["warnings"]}

    assert result.succeeded is True
    assert record["parameter_stability"]["status"] == "fragile"
    assert record["parameter_stability"]["region_counts"]["stable"] == 1
    assert record["parameter_stability"]["region_counts"]["insufficient_data"] == 1
    assert "parameter_stability_fragile" in warning_codes
    assert "overfitting_unstable_parameter_ranking" in warning_codes
    assert record["overfitting_risk"]["status"] == "elevated"


def test_pipeline_records_insufficient_parameter_stability(tmp_path: Path) -> None:
    config_path = _write_strategy_config(
        tmp_path,
        lookback=5,
        parameter_diagnostics_enabled=True,
        parameter_grid_return_windows=[10],
    )
    config = load_config(config_path)
    store = OHLCVParquetStore(tmp_path / "data" / "market" / "ohlcv")
    store.write_records(
        [
            _record(open_time="2026-06-01T00:00:00Z", close=100),
            _record(open_time="2026-06-02T00:00:00Z", close=102),
            _record(open_time="2026-06-03T00:00:00Z", close=104),
            _record(open_time="2026-06-04T00:00:00Z", close=106),
            _record(open_time="2026-06-05T00:00:00Z", close=109),
        ]
    )

    result = _run_pipeline(config, config_path)

    record = _strategy_evaluation(result)["records"][0]
    warning_codes = {item["code"] for item in record["warnings"]}

    assert result.succeeded is True
    assert record["parameter_stability"]["status"] == "insufficient_data"
    assert record["parameter_stability"]["diagnostic_status"] == "no_valid_combinations"
    assert record["parameter_stability"]["region_counts"]["insufficient_data"] == 1
    assert "parameter_stability_insufficient_data" in warning_codes
    assert "overfitting_parameter_evidence_insufficient" in warning_codes


def test_pipeline_records_strategy_evaluation_for_insufficient_upstream_data(tmp_path: Path) -> None:
    config_path = _write_strategy_config(tmp_path, lookback=2)
    config = load_config(config_path)
    store = OHLCVParquetStore(tmp_path / "data" / "market" / "ohlcv")
    store.write_records([_record(open_time="2026-06-05T00:00:00Z", close=109)])

    result = _run_pipeline(config, config_path)

    record = _strategy_evaluation(result)["records"][0]
    manifest = _manifest(result)

    assert result.succeeded is True
    assert record["status"] == "insufficient_data"
    assert record["single_window"]["status"] == "insufficient_data"
    assert record["single_window"]["strategy_run_status"] == "insufficient_data"
    assert record["warnings"][0]["code"] == "upstream_strategy_insufficient_data"
    assert record["error"] is None
    assert manifest["counts"]["strategy_evaluation_records"] == 1
    assert manifest["counts"]["strategy_evaluation_insufficient_data"] == 1
    assert manifest["strategy_evaluation"]["insufficient_data"] == 1
    assert manifest["counts"]["strategy_evaluation_walk_forward_records"] == 0


def test_pipeline_skips_strategy_evaluation_when_quant_disabled(tmp_path: Path) -> None:
    config_path = _write_strategy_config(tmp_path, lookback=2, quant_enabled=False)
    config = load_config(config_path)

    result = run_pipeline(
        config,
        config_path=config_path,
        until_stage="evaluate_strategy_evaluation",
        stage_handlers={
            "collect_market_data": _noop_stage,
            "collect_text_events": _noop_stage,
            "sync_ohlcv": _noop_stage,
        },
    )

    manifest = _manifest(result)

    assert result.succeeded is True
    assert not (result.run.analysis_dir / "strategy_evaluation_summary.json").exists()
    assert not (result.run.analysis_dir / "strategy_evaluation_material.md").exists()
    assert manifest["counts"]["strategy_evaluation_records"] == 0
    assert manifest["counts"]["strategy_evaluation_material_records"] == 0
    assert manifest["strategy_evaluation"] == {
        "enabled": False,
        "records": 0,
        "warnings": [],
        "errors": [],
    }
    assert _stage(manifest, "evaluate_strategy_evaluation")["artifacts"] == []


def _run_pipeline(config: dict[str, Any], config_path: Path):
    return run_pipeline(
        config,
        config_path=config_path,
        stage_handlers={
            "collect_market_data": _noop_stage,
            "collect_text_events": _noop_stage,
            "sync_ohlcv": _noop_stage,
            "build_analysis_materials": _noop_stage,
            "build_research_context": _noop_stage,
            "build_codex_context": _noop_stage,
            "run_codex_report": _noop_stage,
        },
    )


def _write_strategy_config(
    tmp_path: Path,
    *,
    lookback: int,
    quant_enabled: bool = True,
    parameter_diagnostics_enabled: bool = False,
    parameter_grid_return_windows: list[int] | None = None,
) -> Path:
    config_path = tmp_path / "config.yaml"
    return_windows = parameter_grid_return_windows or [2]
    grid_return_window_yaml = "\n".join(f"          - {item}" for item in return_windows)
    parameter_diagnostics_yaml = (
        f"""
  parameter_diagnostics:
    enabled: true
    max_combinations: {len(return_windows)}
    grids:
      tsmom_vol_scaled:
        return_window:
{grid_return_window_yaml}
        volatility_window:
          - 2
        target_volatility:
          - 0.2
"""
        if parameter_diagnostics_enabled
        else ""
    )
    strategies = (
        f"""
  strategies:
    - name: tsmom_vol_scaled
      enabled: true
      params:
        return_window: 2
        volatility_window: 2
        target_volatility: 0.2
      backtest:
        enabled: true
        initial_cash: 10000
        fees_bps: 10
        slippage_bps: 5
        mode: long_flat
{parameter_diagnostics_yaml.rstrip()}
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
  ohlcv:
    storage_dir: data/market/ohlcv
    timeframes:
      - 1d
    lookback:
      1d: {lookback}
quant:
  enabled: {"true" if quant_enabled else "false"}
  engine: vectorbt
{strategies.rstrip()}
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


def _strategy_evaluation(result) -> dict[str, Any]:
    return json.loads((result.run.analysis_dir / "strategy_evaluation_summary.json").read_text(encoding="utf-8"))


def _strategy_evaluation_material(result) -> str:
    return (result.run.analysis_dir / "strategy_evaluation_material.md").read_text(encoding="utf-8")


def _manifest(result) -> dict[str, Any]:
    return json.loads(result.run.manifest_path.read_text(encoding="utf-8"))


def _stage(manifest: dict[str, Any], name: str) -> dict[str, Any]:
    return next(stage for stage in manifest["stages"] if stage["name"] == name)


def _noop_stage(config, run) -> list[str]:
    return []


def _record(*, open_time: str, close: float) -> dict[str, object]:
    return {
        "source": "binance",
        "symbol": "BTCUSDT",
        "timeframe": "1d",
        "open_time": open_time,
        "open": close - 1,
        "high": close + 2,
        "low": close - 2,
        "close": close,
        "volume": 10,
        "fetched_at": "2026-06-05T00:00:00Z",
    }


def _walk_forward_records() -> list[dict[str, object]]:
    closes = (
        [100.0 for _index in range(60)]
        + [100.0 + index for index in range(60)]
        + [160.0 - index for index in range(60)]
        + [100.0 + index for index in range(60)]
    )
    return [
        _record(open_time=_open_time_for_index(index), close=close)
        for index, close in enumerate(closes)
    ]


def _open_time_for_index(index: int) -> str:
    value = date(2026, 1, 1) + timedelta(days=index)
    return f"{value.isoformat()}T00:00:00Z"
