from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from halpha.config import load_config
from halpha.market.market_data_views import build_market_data_views, load_market_data_view_records
from halpha.market.ohlcv_store import OHLCVParquetStore
from halpha.pipeline import run_pipeline


@pytest.fixture(autouse=True)
def _isolate_artifact_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


def test_market_data_views_select_latest_lookback_window(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, lookback=2)
    config = load_config(config_path)
    store = OHLCVParquetStore(tmp_path / "data" / "market" / "ohlcv")
    store.write_records(
        [
            _record(open_time="2026-06-01T00:00:00Z", close=101),
            _record(open_time="2026-06-02T00:00:00Z", close=102),
            _record(open_time="2026-06-03T00:00:00Z", close=103),
        ]
    )

    result = _run_pipeline_with_views(config, config_path)

    artifact = _market_data_views(result)
    view = artifact["views"][0]
    rows = load_market_data_view_records(
        view,
        storage_dir=tmp_path / "data" / "market" / "ohlcv",
    )
    manifest = _manifest(result)

    assert result.succeeded is True
    assert artifact["source_artifacts"] == ["data/market/metadata/ohlcv_sync_state.json"]
    assert len(artifact["views"]) == 1
    assert view == {
        "view_id": "ohlcv_view:binance:BTCUSDT:1d:2026-06-03T00:00:00Z",
        "source": "binance",
        "symbol": "BTCUSDT",
        "timeframe": "1d",
        "requested_lookback": 2,
        "input_window_start": "2026-06-02T00:00:00Z",
        "input_window_end": "2026-06-03T00:00:00Z",
        "latest_candle_time": "2026-06-03T00:00:00Z",
        "row_count": 2,
        "storage_ref": "data/market/ohlcv/source=binance/symbol=BTCUSDT/timeframe=1d",
        "included_columns": ["open_time", "open", "high", "low", "close", "volume"],
        "insufficient_data": False,
        "warnings": [],
    }
    assert rows == [
        {
            "open_time": "2026-06-02T00:00:00Z",
            "open": 101.0,
            "high": 103.0,
            "low": 100.0,
            "close": 102.0,
            "volume": 10.0,
        },
        {
            "open_time": "2026-06-03T00:00:00Z",
            "open": 102.0,
            "high": 104.0,
            "low": 101.0,
            "close": 103.0,
            "volume": 10.0,
        },
    ]
    assert "records" not in view
    assert manifest["artifacts"]["market_data_views"] == "raw/market_data_views.json"
    assert manifest["counts"]["market_data_views"] == 1
    assert manifest["counts"]["market_data_views_insufficient_data"] == 0
    assert _stage(manifest, "build_market_data_views")["artifacts"] == [
        "raw/market_data_views.json"
    ]


def test_market_data_views_record_insufficient_data_state(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, lookback=3)
    config = load_config(config_path)
    store = OHLCVParquetStore(tmp_path / "data" / "market" / "ohlcv")
    store.write_records([_record(open_time="2026-06-01T00:00:00Z", close=101)])

    result = _run_pipeline_with_views(config, config_path)

    artifact = _market_data_views(result)
    view = artifact["views"][0]
    manifest = _manifest(result)

    assert result.succeeded is True
    assert view["row_count"] == 1
    assert view["input_window_start"] == "2026-06-01T00:00:00Z"
    assert view["input_window_end"] == "2026-06-01T00:00:00Z"
    assert view["latest_candle_time"] == "2026-06-01T00:00:00Z"
    assert view["insufficient_data"] is True
    assert view["warnings"] == [
        "binance BTCUSDT 1d has 1 OHLCV rows, below configured lookback 3."
    ]
    assert manifest["counts"]["market_data_views_insufficient_data"] == 1


def test_market_data_views_record_missing_history_as_insufficient(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, lookback=2)
    config = load_config(config_path)

    result = _run_pipeline_with_views(config, config_path)

    artifact = _market_data_views(result)
    view = artifact["views"][0]
    rows = load_market_data_view_records(
        view,
        storage_dir=tmp_path / "data" / "market" / "ohlcv",
    )

    assert result.succeeded is True
    assert view["view_id"] == "ohlcv_view:binance:BTCUSDT:1d:missing"
    assert view["input_window_start"] is None
    assert view["input_window_end"] is None
    assert view["latest_candle_time"] is None
    assert view["row_count"] == 0
    assert view["insufficient_data"] is True
    assert rows == []


def test_market_data_views_skip_when_ohlcv_is_not_configured(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, include_ohlcv=False)
    config = load_config(config_path)

    result = _run_pipeline_with_views(config, config_path)

    manifest = _manifest(result)
    assert result.succeeded is True
    assert not (result.run.raw_dir / "market_data_views.json").exists()
    assert "market_data_views" not in manifest["artifacts"]
    assert manifest["counts"]["market_data_views"] == 0
    assert _stage(manifest, "build_market_data_views")["artifacts"] == []


def test_codex_context_does_not_embed_market_data_views(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, lookback=2)
    config = load_config(config_path)
    store = OHLCVParquetStore(tmp_path / "data" / "market" / "ohlcv")
    store.write_records(
        [
            _record(open_time="2026-06-02T00:00:00Z", close=102),
            _record(open_time="2026-06-03T00:00:00Z", close=103),
        ]
    )

    result = run_pipeline(
        config,
        config_path=config_path,
        stage_handlers={
            "collect_market_data": _noop_stage,
            "collect_text_events": _noop_stage,
            "sync_ohlcv": _noop_stage,
            "build_market_data_views": lambda config, run: build_market_data_views(
                config,
                run,
                now="2026-06-05T00:00:00Z",
            ),
            "build_analysis_materials": _noop_stage,
            "build_research_context": _write_minimal_research_context,
            "run_codex_report": _noop_stage,
        },
    )

    context = (result.run.codex_context_dir / "context.md").read_text(encoding="utf-8")
    assert result.succeeded is True
    assert (result.run.raw_dir / "market_data_views.json").is_file()
    assert "raw/market_data_views.json" not in context
    assert "2026-06-03T00:00:00Z" not in context
    assert "close: 103" not in context


def _run_pipeline_with_views(config: dict[str, Any], config_path: Path):
    return run_pipeline(
        config,
        config_path=config_path,
        stage_handlers={
            "collect_market_data": _noop_stage,
            "collect_text_events": _noop_stage,
            "sync_ohlcv": _noop_stage,
            "build_market_data_views": lambda config, run: build_market_data_views(
                config,
                run,
                now="2026-06-05T00:00:00Z",
            ),
            "build_analysis_materials": _noop_stage,
            "build_research_context": _noop_stage,
            "build_codex_context": _noop_stage,
            "run_codex_report": _noop_stage,
        },
    )


def _write_config(
    tmp_path: Path,
    *,
    include_ohlcv: bool = True,
    lookback: int = 2,
) -> Path:
    ohlcv = ""
    if include_ohlcv:
        ohlcv = f"""
  ohlcv:
    storage_dir: data/market/ohlcv
    timeframes:
      - 1d
    lookback:
      1d: {lookback}
"""
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
{ohlcv.rstrip()}
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


def _market_data_views(result) -> dict[str, Any]:
    return json.loads((result.run.raw_dir / "market_data_views.json").read_text(encoding="utf-8"))


def _manifest(result) -> dict[str, Any]:
    return json.loads(result.run.manifest_path.read_text(encoding="utf-8"))


def _stage(manifest: dict[str, Any], name: str) -> dict[str, Any]:
    return next(
        task
        for stage in manifest["stages"]
        for task in stage.get("tasks", [])
        if task["name"] == name
    )


def _noop_stage(config, run) -> list[str]:
    return []


def _write_minimal_research_context(config, run) -> list[str]:
    path = run.analysis_dir / "research_context.md"
    path.write_text("# research_context\n\nNo quant signal material yet.\n", encoding="utf-8")
    run.manifest["artifacts"]["research_context"] = "analysis/research_context.md"
    return ["analysis/research_context.md"]


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
        "high": close + 1,
        "low": close - 2,
        "close": close,
        "volume": 10,
        "fetched_at": "2026-06-05T00:00:00Z",
    }
