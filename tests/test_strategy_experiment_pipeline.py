from __future__ import annotations

import json
from pathlib import Path

from halpha.config import load_config
from halpha.market.ohlcv_store import OHLCVParquetStore
from halpha.pipeline import run_pipeline


def test_pipeline_writes_strategy_experiment_gate_material(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, lookback=5)
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

    result = run_pipeline(
        config,
        config_path=config_path,
        until_stage="run_strategy_research",
        stage_handlers={
            "collect_market_data": _noop_stage,
            "collect_text_events": _noop_stage,
            "sync_ohlcv": _noop_stage,
        },
    )

    experiment = json.loads((result.run.analysis_dir / "strategy_experiment.json").read_text(encoding="utf-8"))
    gates = json.loads(
        (result.run.analysis_dir / "strategy_effectiveness_gates.json").read_text(encoding="utf-8")
    )
    material = (result.run.analysis_dir / "strategy_experiment_material.md").read_text(encoding="utf-8")
    manifest = json.loads(result.run.manifest_path.read_text(encoding="utf-8"))

    assert result.succeeded is True
    assert experiment["artifact_type"] == "strategy_experiment"
    assert experiment["source_artifacts"] == ["analysis/strategy_benchmark_suite.json"]
    assert experiment["inputs"]["benchmark_suite_artifact"] == "analysis/strategy_benchmark_suite.json"
    assert experiment["coverage"]["strategy_candidates"] == 1
    assert experiment["coverage"]["benchmark_records"] == 1
    assert experiment["coverage"]["evaluations"] == 1
    assert gates["artifact_type"] == "strategy_effectiveness_gates"
    assert gates["source_artifacts"] == ["analysis/strategy_experiment.json"]
    assert gates["records"][0]["source_artifacts"] == ["analysis/strategy_experiment.json"]
    assert gates["records"][0]["strategy_name"] == "tsmom_vol_scaled"
    assert gates["records"][0]["gate_inputs"]["benchmark_coverage"]["benchmark_records"] == 1
    assert "artifact_type: analysis_strategy_experiment_material" in material
    assert "record_type: strategy_effectiveness_gate" in material
    assert "benchmark_coverage:" in material
    assert "cost_drag:" in material
    assert "baseline_comparison:" in material
    assert "walk_forward_stability:" in material
    assert "overfitting_risk:" in material
    assert "codex_may_generate_gate_outcomes: false" in material
    assert "effective_candidate_is_live_trading_approval: false" in material
    assert manifest["artifacts"]["strategy_experiment"] == "analysis/strategy_experiment.json"
    assert manifest["artifacts"]["strategy_effectiveness_gates"] == (
        "analysis/strategy_effectiveness_gates.json"
    )
    assert manifest["artifacts"]["strategy_experiment_material"] == (
        "analysis/strategy_experiment_material.md"
    )
    assert manifest["counts"]["strategy_experiment_candidates"] == 1
    assert manifest["counts"]["strategy_experiment_evaluations"] == 1
    assert manifest["counts"]["strategy_gate_candidates"] == 1
    assert manifest["counts"]["strategy_experiment_material_records"] == 1
    assert manifest["strategy_experiment"]["status"] == "succeeded"
    assert _stage(manifest, "build_strategy_experiment_material")["artifacts"] == [
        "analysis/strategy_experiment.json",
        "analysis/strategy_effectiveness_gates.json",
        "analysis/strategy_experiment_material.md",
    ]


def _write_config(tmp_path: Path, *, lookback: int) -> Path:
    config_path = tmp_path / "config.yaml"
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
  enabled: true
  engine: vectorbt
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


def _record(
    *,
    source: str = "binance",
    symbol: str = "BTCUSDT",
    timeframe: str = "1d",
    open_time: str,
    close: float,
) -> dict[str, object]:
    return {
        "source": source,
        "symbol": symbol,
        "timeframe": timeframe,
        "open_time": open_time,
        "open": close - 1,
        "high": close + 2,
        "low": close - 2,
        "close": close,
        "volume": 10,
        "fetched_at": "2026-06-05T00:00:00Z",
    }


def _noop_stage(config, run) -> list[str]:
    return []


def _stage(manifest: dict, name: str) -> dict:
    for stage in manifest["stages"]:
        if stage["name"] == name:
            return stage
        for task in stage.get("tasks", []):
            if task["name"] == name:
                return task
    raise AssertionError(f"stage or task {name} not found")
