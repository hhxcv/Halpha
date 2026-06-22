from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from halpha.config import load_config
from halpha.onchain.onchain_flow_history import sync_onchain_flow_history
from halpha.onchain.onchain_flow_views import _load_onchain_flow_view_records, build_onchain_flow_views
from halpha.pipeline import RunContext, run_pipeline
from halpha.storage import write_json


def test_onchain_flow_history_and_views_use_bounded_current_windows(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, lookback_days=60)
    config = load_config(config_path)
    old_run = _run_context(tmp_path, config_path, "run-old")
    _write_raw(
        old_run,
        [_stablecoin_item("2026-03-01T00:00:00Z", total_circulating_usd=1000.0)],
        window_start="2026-03-01T00:00:00Z",
        window_end="2026-03-01T00:00:00Z",
    )
    sync_onchain_flow_history(config, old_run, now="2026-03-01T01:00:00Z")

    result = run_pipeline(
        config,
        config_path=config_path,
        until_stage="build_onchain_flow_views",
        stage_handlers={
            "collect_market_data": _noop_stage,
            "collect_onchain_flow_data": _write_current_stablecoin_raw_stage,
            "sync_onchain_flow_history": lambda config, run: sync_onchain_flow_history(
                config,
                run,
                now="2026-06-18T01:00:00Z",
            ),
            "build_onchain_flow_views": lambda config, run: build_onchain_flow_views(
                config,
                run,
                now="2026-06-18T01:01:00Z",
            ),
        },
    )

    assert result.succeeded is True
    state = _state(tmp_path)
    stored_records = _stored_records(tmp_path, data_class="stablecoin_supply", asset="ALL_STABLECOINS", chain="all")
    views = _views(result)
    view = views["views"][0]
    loaded_window = _load_onchain_flow_view_records(view, config_path=config_path)
    manifest = _manifest(result)
    catalog = _catalog(tmp_path)
    catalog_store = next(store for store in catalog["stores"] if store["name"] == "onchain_flow_history")

    assert state["status"] == "ok"
    assert state["totals"]["records"] == 53
    assert state["groups"][0]["storage_ref"] == (
        "data/onchain/flow/source=defillama_stablecoins/data_class=stablecoin_supply/"
        "asset=ALL_STABLECOINS/chain=all"
    )
    assert len(stored_records) == 53
    assert stored_records[0]["origin_run_ids"] == ["run-old"]
    assert views["source_artifacts"] == ["data/onchain/metadata/onchain_flow_state.json"]
    assert view["view_id"] == (
        "onchain_flow_view:stablecoin_supply:defillama_stablecoins:"
        "ALL_STABLECOINS:all:2026-06-18T00:00:00Z"
    )
    assert view["input_window_start"] == "2026-04-19T00:00:00Z"
    assert view["input_window_end"] == "2026-06-18T00:00:00Z"
    assert view["row_count"] == 52
    assert view["included_record_count"] == 50
    assert view["omitted_record_count"] == 2
    assert view["status"] == "bounded"
    assert view["storage_ref"] == (
        "data/onchain/flow/source=defillama_stablecoins/data_class=stablecoin_supply/"
        "asset=ALL_STABLECOINS/chain=all"
    )
    assert "2026-03-01T00:00:00Z" not in json.dumps(view)
    assert len(loaded_window) == 50
    assert loaded_window[-1]["as_of"] == "2026-06-18T00:00:00Z"
    assert manifest["artifacts"]["onchain_flow_state"] == "data/onchain/metadata/onchain_flow_state.json"
    assert manifest["artifacts"]["onchain_flow_views"] == "raw/onchain_flow_views.json"
    assert manifest["counts"]["onchain_flow_history_records"] == 53
    assert manifest["counts"]["onchain_flow_view_records"] == 50
    assert manifest["counts"]["onchain_flow_views_bounded"] == 1
    assert catalog_store["record_count"] == 53
    assert catalog_store["details"]["incoming_records"] == 52
    assert catalog_store["source_artifacts"] == [
        "data/onchain/metadata/onchain_flow_schema.json",
        "data/onchain/metadata/onchain_flow_state.json",
    ]


def test_onchain_flow_history_tracks_duplicate_conflicts(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    first_run = _run_context(tmp_path, config_path, "run-1")
    second_run = _run_context(tmp_path, config_path, "run-2")

    _write_raw(first_run, [_stablecoin_item("2026-06-18T00:00:00Z", total_circulating_usd=1000.0)])
    sync_onchain_flow_history(config, first_run, now="2026-06-18T01:00:00Z")
    _write_raw(second_run, [_stablecoin_item("2026-06-18T00:00:00Z", total_circulating_usd=1100.0)])
    sync_onchain_flow_history(config, second_run, now="2026-06-18T02:00:00Z")

    state = _state(tmp_path)
    records = _stored_records(tmp_path, data_class="stablecoin_supply", asset="ALL_STABLECOINS", chain="all")

    assert state["status"] == "warning"
    assert state["totals"]["records"] == 1
    assert state["totals"]["duplicate_records"] == 1
    assert state["totals"]["conflicting_duplicates"] == 1
    assert records[0]["origin_run_ids"] == ["run-1", "run-2"]
    assert records[0]["first_seen_run_id"] == "run-1"
    assert records[0]["last_seen_run_id"] == "run-2"
    assert records[0]["source_artifacts"] == [
        "runs/run-1/raw/onchain_flow.json",
        "runs/run-2/raw/onchain_flow.json",
    ]
    assert records[0]["status"] == "warning"
    assert "conflicting duplicate on-chain flow record" in records[0]["warnings"][0]


def test_disabled_onchain_flow_config_skips_history_and_views(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, enabled=False)
    config = load_config(config_path)

    result = run_pipeline(
        config,
        config_path=config_path,
        until_stage="build_onchain_flow_views",
        stage_handlers={"collect_market_data": _noop_stage},
    )

    manifest = _manifest(result)
    assert result.succeeded is True
    assert not (tmp_path / "data" / "onchain" / "metadata" / "onchain_flow_state.json").exists()
    assert not (result.run.raw_dir / "onchain_flow_views.json").exists()
    assert "onchain_flow_state" not in manifest["artifacts"]
    assert "onchain_flow_views" not in manifest["artifacts"]
    assert manifest["counts"]["onchain_flow_history_records"] == 0
    assert manifest["counts"]["onchain_flow_views"] == 0


def test_onchain_flow_views_preserve_stale_and_unavailable_status(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, data_classes=["stablecoin_supply", "exchange_flow_availability"])
    config = load_config(config_path)
    old_run = _run_context(tmp_path, config_path, "run-old")
    _write_raw(
        old_run,
        [_stablecoin_item("2026-05-01T00:00:00Z", total_circulating_usd=1000.0)],
        window_start="2026-05-01T00:00:00Z",
        window_end="2026-05-01T00:00:00Z",
    )
    sync_onchain_flow_history(config, old_run, now="2026-05-01T01:00:00Z")

    result = run_pipeline(
        config,
        config_path=config_path,
        until_stage="build_onchain_flow_views",
        stage_handlers={
            "collect_market_data": _noop_stage,
            "collect_onchain_flow_data": _write_stale_unavailable_raw_stage,
            "sync_onchain_flow_history": lambda config, run: sync_onchain_flow_history(
                config,
                run,
                now="2026-06-18T01:00:00Z",
            ),
            "build_onchain_flow_views": lambda config, run: build_onchain_flow_views(
                config,
                run,
                now="2026-06-18T01:01:00Z",
            ),
        },
    )

    assert result.succeeded is True
    views = _views(result)["views"]
    stablecoin_view = next(view for view in views if view["data_class"] == "stablecoin_supply")
    exchange_view = next(view for view in views if view["data_class"] == "exchange_flow_availability")
    manifest = _manifest(result)

    assert stablecoin_view["status"] == "stale"
    assert stablecoin_view["row_count"] == 0
    assert stablecoin_view["latest_observation_time"] == "2026-05-01T00:00:00Z"
    assert exchange_view["status"] == "unavailable"
    assert exchange_view["storage_ref"] is None
    assert "must not be treated as neutral" in exchange_view["warnings"][0]
    assert manifest["counts"]["onchain_flow_views_stale"] == 1
    assert manifest["counts"]["onchain_flow_views_unavailable"] == 1


def test_onchain_flow_views_preserve_partial_status(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    result = run_pipeline(
        config,
        config_path=config_path,
        until_stage="build_onchain_flow_views",
        stage_handlers={
            "collect_market_data": _noop_stage,
            "collect_onchain_flow_data": _write_partial_raw_stage,
            "sync_onchain_flow_history": lambda config, run: sync_onchain_flow_history(
                config,
                run,
                now="2026-06-18T01:00:00Z",
            ),
            "build_onchain_flow_views": lambda config, run: build_onchain_flow_views(
                config,
                run,
                now="2026-06-18T01:01:00Z",
            ),
        },
    )

    assert result.succeeded is True
    view = _views(result)["views"][0]
    manifest = _manifest(result)

    assert view["status"] == "partial"
    assert view["row_count"] == 1
    assert view["included_record_count"] == 1
    assert manifest["counts"]["onchain_flow_views_partial"] == 1


def _write_config(
    tmp_path: Path,
    *,
    enabled: bool = True,
    data_classes: list[str] | None = None,
    lookback_days: int = 7,
) -> Path:
    enabled_value = "true" if enabled else "false"
    data_classes = data_classes or ["stablecoin_supply"]
    data_class_lines = "\n".join(f"    - {item}" for item in data_classes)
    enabled_body = ""
    if enabled:
        enabled_body = f"""
  source: public_aggregate
  data_classes:
{data_class_lines}
  assets:
    - ALL_STABLECOINS
    - BTC
  chains:
    - all
    - bitcoin
  lookback_days: {lookback_days}
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
macro_calendar:
  enabled: false
onchain_flow:
  enabled: {enabled_value}
{enabled_body.rstrip()}
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


def _write_current_stablecoin_raw_stage(config: dict[str, Any], run: RunContext) -> list[str]:
    start = datetime(2026, 4, 28, tzinfo=timezone.utc)
    items = [
        _stablecoin_item(
            (start + timedelta(days=index)).isoformat().replace("+00:00", "Z"),
            total_circulating_usd=2000.0 + index,
        )
        for index in range(52)
    ]
    _write_raw(
        run,
        items,
        window_start="2026-04-19T00:00:00Z",
        window_end="2026-06-18T00:00:00Z",
    )
    run.manifest["artifacts"]["raw_onchain_flow"] = "raw/onchain_flow.json"
    return ["raw/onchain_flow.json"]


def _write_stale_unavailable_raw_stage(config: dict[str, Any], run: RunContext) -> list[str]:
    _write_raw(
        run,
        [],
        window_start="2026-06-11T00:00:00Z",
        window_end="2026-06-18T00:00:00Z",
        availability=[
            _stablecoin_availability(status="stale", record_count=0, reason="stablecoin source returned no current rows."),
            _exchange_flow_unavailable_availability(),
        ],
    )
    run.manifest["artifacts"]["raw_onchain_flow"] = "raw/onchain_flow.json"
    return ["raw/onchain_flow.json"]


def _write_partial_raw_stage(config: dict[str, Any], run: RunContext) -> list[str]:
    errors = [
        {
            "source": "defillama_stablecoins",
            "endpoint": "stablecoincharts_all",
            "data_class": "stablecoin_supply",
            "error_type": "parse_error",
            "message": "one stablecoin row could not be parsed",
        }
    ]
    _write_raw(
        run,
        [_stablecoin_item("2026-06-18T00:00:00Z", total_circulating_usd=2200.0)],
        window_start="2026-06-11T00:00:00Z",
        window_end="2026-06-18T00:00:00Z",
        availability=[
            _stablecoin_availability(
                status="partial",
                record_count=1,
                parsed_record_count=2,
                error_count=1,
                reason="stablecoin source parsed with row-level errors.",
            )
        ],
        errors=errors,
    )
    run.manifest["artifacts"]["raw_onchain_flow"] = "raw/onchain_flow.json"
    return ["raw/onchain_flow.json"]


def _write_raw(
    run: RunContext,
    items: list[dict[str, Any]],
    *,
    window_start: str = "2026-06-11T00:00:00Z",
    window_end: str = "2026-06-18T00:00:00Z",
    availability: list[dict[str, Any]] | None = None,
    errors: list[dict[str, Any]] | None = None,
) -> None:
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
            "collected_at": "2026-06-18T01:00:00Z",
            "window": {
                "lookback_start": window_start,
                "lookback_end": window_end,
            },
            "items": items,
            "availability": availability
            if availability is not None
            else [_stablecoin_availability(status="succeeded", record_count=len(items))],
            "warnings": [],
            "errors": errors or [],
        },
    )


def _stablecoin_item(as_of: str, *, total_circulating_usd: float) -> dict[str, Any]:
    return {
        "item_id": f"onchain_flow:stablecoin_supply:defillama_stablecoins:all:{as_of}",
        "data_class": "stablecoin_supply",
        "source": "defillama_stablecoins",
        "asset": "ALL_STABLECOINS",
        "chain": "all",
        "as_of": as_of,
        "endpoint": "stablecoincharts_all",
        "metrics": {"total_circulating_usd": total_circulating_usd},
        "units": {"total_circulating_usd": "USD"},
        "raw_fields": {"source_url": "https://stablecoins.llama.fi/stablecoincharts/all", "date": as_of},
        "warnings": [],
        "errors": [],
    }


def _stablecoin_availability(
    *,
    status: str,
    record_count: int,
    parsed_record_count: int | None = None,
    error_count: int = 0,
    reason: str | None = None,
) -> dict[str, Any]:
    record = {
        "source": "defillama_stablecoins",
        "data_class": "stablecoin_supply",
        "status": status,
        "record_count": record_count,
        "parsed_record_count": record_count if parsed_record_count is None else parsed_record_count,
        "error_count": error_count,
        "endpoint": "stablecoincharts_all",
    }
    if reason is not None:
        record["reason"] = reason
    return record


def _exchange_flow_unavailable_availability() -> dict[str, Any]:
    return {
        "source": "public_aggregate",
        "data_class": "exchange_flow_availability",
        "status": "unavailable",
        "record_count": 0,
        "parsed_record_count": 0,
        "error_count": 0,
        "endpoint": "exchange_flow_periodic_public_source",
        "reason": "missing exchange-flow evidence must not be treated as neutral risk context.",
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
    return json.loads((tmp_path / "data" / "onchain" / "metadata" / "onchain_flow_state.json").read_text(encoding="utf-8"))


def _stored_records(tmp_path: Path, *, data_class: str, asset: str, chain: str) -> list[dict[str, Any]]:
    return json.loads(
        (
            tmp_path
            / "data"
            / "onchain"
            / "flow"
            / "source=defillama_stablecoins"
            / f"data_class={data_class}"
            / f"asset={asset}"
            / f"chain={chain}"
            / "records.json"
        ).read_text(encoding="utf-8")
    )


def _views(result) -> dict[str, Any]:
    return json.loads((result.run.raw_dir / "onchain_flow_views.json").read_text(encoding="utf-8"))


def _manifest(result) -> dict[str, Any]:
    return json.loads(result.run.manifest_path.read_text(encoding="utf-8"))


def _catalog(tmp_path: Path) -> dict[str, Any]:
    return json.loads((tmp_path / "data" / "research" / "metadata" / "research_data_catalog.json").read_text(encoding="utf-8"))


def _noop_stage(config, run) -> list[str]:
    return []
