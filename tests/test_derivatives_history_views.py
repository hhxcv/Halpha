from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from halpha.config import load_config
from halpha.market.derivatives_history import sync_derivatives_market_history
from halpha.market.derivatives_market_views import build_derivatives_market_views, load_derivatives_market_view_records
from halpha.pipeline import RunContext, run_pipeline
from halpha.storage import write_json
from history_traceability_helpers import assert_history_traceability


@pytest.fixture(autouse=True)
def _isolate_artifact_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


def test_derivatives_history_and_views_use_bounded_current_windows(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, data_classes=["funding_rate"])
    config = load_config(config_path)

    result = run_pipeline(
        config,
        config_path=config_path,
        until_stage="build_source_evidence",
        stage_handlers={
            "collect_market_data": _noop_stage,
            "collect_derivatives_market_data": _write_funding_raw_stage,
            "sync_derivatives_market_history": lambda config, run: sync_derivatives_market_history(
                config,
                run,
                now="2026-06-18T01:00:00Z",
            ),
            "build_derivatives_market_views": lambda config, run: build_derivatives_market_views(
                config,
                run,
                now="2026-06-18T01:01:00Z",
            ),
        },
    )

    assert result.succeeded is True
    state = _state(tmp_path)
    stored_records = _stored_records(tmp_path, data_class="funding_rate", period="8h")
    views = _views(result)
    view = views["views"][0]
    loaded_window = load_derivatives_market_view_records(view, config_path=config_path)
    manifest = _manifest(result)

    assert state["status"] == "ok"
    assert state["totals"]["records"] == 3
    assert state["groups"][0]["storage_ref"] == (
        "data/market/derivatives/source=binance_usdm/data_class=funding_rate/symbol=BTCUSDT/period=8h"
    )
    assert len(stored_records) == 3
    assert stored_records[0]["origin_run_ids"] == [result.run.run_id]
    assert views["source_artifacts"] == ["data/market/metadata/derivatives_market_state.json"]
    assert len(views["views"]) == 1
    _assert_view_contract(
        view,
        {
            "view_id": "derivatives_view:funding_rate:binance_usdm:BTCUSDT:8h:2026-06-18T00:00:00Z",
            "data_class": "funding_rate",
            "source": "binance_usdm",
            "symbol": "BTCUSDT",
            "period": "8h",
            "input_window_start": "2026-06-17T16:00:00Z",
            "input_window_end": "2026-06-18T00:00:00Z",
            "row_count": 2,
            "status": "succeeded",
            "storage_ref": (
                "data/market/derivatives/source=binance_usdm/data_class=funding_rate/symbol=BTCUSDT/period=8h"
            ),
            "insufficient_data": False,
            "source_artifacts": ["data/market/metadata/derivatives_market_state.json"],
        },
    )
    assert view["market_type"] == "usd_m_futures"
    assert view["requested_lookback"] == 2
    assert view["latest_observation_time"] == "2026-06-18T00:00:00Z"
    assert view["included_columns"] == ["as_of", "endpoint", "metrics", "units", "warnings", "errors"]
    assert view["warnings"] == []
    assert view["errors"] == []
    assert "records" not in view
    assert [record["as_of"] for record in loaded_window] == [
        "2026-06-17T16:00:00Z",
        "2026-06-18T00:00:00Z",
    ]
    assert manifest["artifacts"]["derivatives_market_state"] == "data/market/metadata/derivatives_market_state.json"
    assert manifest["artifacts"]["derivatives_market_views"] == "raw/derivatives_market_views.json"
    assert manifest["counts"]["derivatives_market_history_records"] == 3
    assert manifest["counts"]["derivatives_market_views"] == 1
    assert manifest["counts"]["derivatives_market_views_insufficient_data"] == 0
    assert manifest["derivatives_market_views"]["storage_refs"] == [
        "data/market/derivatives/source=binance_usdm/data_class=funding_rate/symbol=BTCUSDT/period=8h"
    ]


def test_derivatives_history_deduplicates_repeated_records_with_run_traceability(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, data_classes=["funding_rate"])
    config = load_config(config_path)
    first_run = _run_context(tmp_path, config_path, "run-1")
    second_run = _run_context(tmp_path, config_path, "run-2")
    item = _derivatives_item("2026-06-18T00:00:00Z", funding_rate=0.0001)

    _write_raw(first_run, [item])
    sync_derivatives_market_history(config, first_run, now="2026-06-18T01:00:00Z")
    _write_raw(second_run, [item])
    sync_derivatives_market_history(config, second_run, now="2026-06-18T02:00:00Z")

    state = _state(tmp_path)
    records = _stored_records(tmp_path, data_class="funding_rate", period="8h")

    assert state["totals"]["records"] == 1
    assert state["totals"]["duplicate_records"] == 1
    assert state["totals"]["updated_records"] == 1
    assert_history_traceability(
        records[0],
        origin_run_ids=["run-1", "run-2"],
        first_seen_run_id="run-1",
        last_seen_run_id="run-2",
        source_artifacts=[
            "runs/run-1/raw/derivatives_market.json",
            "runs/run-2/raw/derivatives_market.json",
        ],
    )


def test_derivatives_views_record_missing_history_state(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, data_classes=["funding_rate"])
    config = load_config(config_path)

    result = run_pipeline(
        config,
        config_path=config_path,
        until_stage="build_source_evidence",
        stage_handlers={
            "collect_market_data": _noop_stage,
            "collect_derivatives_market_data": _noop_stage,
        },
    )

    assert result.succeeded is True
    views = _views(result)
    view = views["views"][0]
    manifest = _manifest(result)

    assert view["view_id"] == "derivatives_view:funding_rate:binance_usdm:BTCUSDT:8h:missing"
    assert view["status"] == "missing_history"
    assert view["row_count"] == 0
    assert view["insufficient_data"] is True
    assert manifest["counts"]["derivatives_market_views"] == 1
    assert manifest["counts"]["derivatives_market_views_insufficient_data"] == 1


def test_disabled_derivatives_config_skips_history_and_views(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, derivatives_enabled=False)
    config = load_config(config_path)

    result = run_pipeline(
        config,
        config_path=config_path,
        until_stage="build_source_evidence",
        stage_handlers={"collect_market_data": _noop_stage},
    )

    manifest = _manifest(result)
    assert result.succeeded is True
    assert not (tmp_path / "data" / "market" / "metadata" / "derivatives_market_state.json").exists()
    assert not (result.run.raw_dir / "derivatives_market_views.json").exists()
    assert "derivatives_market_state" not in manifest["artifacts"]
    assert "derivatives_market_views" not in manifest["artifacts"]
    assert manifest["counts"]["derivatives_market_history_records"] == 0
    assert manifest["counts"]["derivatives_market_views"] == 0


def _assert_view_contract(view: dict[str, Any], expected: dict[str, Any]) -> None:
    assert {key: view.get(key) for key in expected} == expected


def _write_config(
    tmp_path: Path,
    *,
    derivatives_enabled: bool = True,
    data_classes: list[str] | None = None,
) -> Path:
    data_classes = data_classes or ["funding_rate"]
    data_class_lines = "\n".join(f"      - {data_class}" for data_class in data_classes)
    enabled_value = "true" if derivatives_enabled else "false"
    extra_derivatives = ""
    if derivatives_enabled:
        extra_derivatives = f"""
    source: binance_usdm
    symbols:
      - BTCUSDT
    data_classes:
{data_class_lines}
    periods:
      - 1h
    lookback:
      1h: 2
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
  derivatives:
    enabled: {enabled_value}
{extra_derivatives.rstrip()}
text:
  enabled: false
report:
  language: zh-CN
codex:
  enabled: false
""".strip(),
        encoding="utf-8",
    )
    return path


def _write_funding_raw_stage(config: dict[str, Any], run: RunContext) -> list[str]:
    _write_raw(
        run,
        [
            _derivatives_item("2026-06-17T08:00:00Z", funding_rate=0.00005),
            _derivatives_item("2026-06-17T16:00:00Z", funding_rate=0.00010),
            _derivatives_item("2026-06-18T00:00:00Z", funding_rate=0.00015),
        ],
    )
    run.manifest["artifacts"]["raw_derivatives_market"] = "raw/derivatives_market.json"
    return ["raw/derivatives_market.json"]


def _write_raw(run: RunContext, items: list[dict[str, Any]]) -> None:
    write_json(
        run.raw_dir / "derivatives_market.json",
        {
            "schema_version": 1,
            "artifact_type": "derivatives_market_raw",
            "collector": "derivatives_market",
            "collection_method": "public_http",
            "source": {"name": "binance_usdm", "url": "https://fapi.binance.com"},
            "collected_at": "2026-06-18T01:00:00Z",
            "items": items,
            "availability": [],
            "warnings": [],
            "errors": [],
        },
    )


def _derivatives_item(as_of: str, *, funding_rate: float) -> dict[str, Any]:
    return {
        "item_id": f"derivatives_market:funding_rate:binance_usdm:BTCUSDT:8h:{as_of}",
        "data_class": "funding_rate",
        "source": "binance_usdm",
        "market_type": "usd_m_futures",
        "symbol": "BTCUSDT",
        "period": "8h",
        "as_of": as_of,
        "endpoint": "funding_rate_history",
        "request_class": "funding_rate_history",
        "metrics": {"funding_rate": funding_rate},
        "units": {"funding_rate": "ratio"},
        "raw_fields": {"fundingRate": f"{funding_rate:.8f}", "fundingTime": as_of},
        "warnings": [],
        "errors": [],
    }


def _run_context(tmp_path: Path, config_path: Path, run_id: str) -> RunContext:
    run_dir = tmp_path / "runs" / run_id
    raw_dir = run_dir / "raw"
    analysis_dir = run_dir / "analysis"
    codex_context_dir = run_dir / "codex_context"
    report_dir = run_dir / "report"
    for directory in (raw_dir, analysis_dir, codex_context_dir, report_dir):
        directory.mkdir(parents=True, exist_ok=True)
    return RunContext(
        run_id=run_id,
        run_dir=run_dir,
        raw_dir=raw_dir,
        analysis_dir=analysis_dir,
        codex_context_dir=codex_context_dir,
        report_dir=report_dir,
        manifest_path=run_dir / "run_manifest.json",
        config_path=config_path,
        manifest={"artifacts": {}, "counts": {}, "errors": []},
    )


def _state(tmp_path: Path) -> dict[str, Any]:
    return json.loads((tmp_path / "data" / "market" / "metadata" / "derivatives_market_state.json").read_text(encoding="utf-8"))


def _stored_records(tmp_path: Path, *, data_class: str, period: str) -> list[dict[str, Any]]:
    return json.loads(
        (
            tmp_path
            / "data"
            / "market"
            / "derivatives"
            / "source=binance_usdm"
            / f"data_class={data_class}"
            / "symbol=BTCUSDT"
            / f"period={period}"
            / "records.json"
        ).read_text(encoding="utf-8")
    )


def _views(result) -> dict[str, Any]:
    return json.loads((result.run.raw_dir / "derivatives_market_views.json").read_text(encoding="utf-8"))


def _manifest(result) -> dict[str, Any]:
    return json.loads(result.run.manifest_path.read_text(encoding="utf-8"))


def _noop_stage(config, run) -> list[str]:
    return []
