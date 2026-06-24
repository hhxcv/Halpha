from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from halpha.config import load_config
from halpha.macro.macro_calendar_history import sync_macro_calendar_history
from halpha.macro.macro_calendar_views import _load_macro_calendar_view_records, build_macro_calendar_views
from halpha.pipeline import RunContext, run_pipeline
from halpha.storage import write_json


def test_macro_calendar_history_and_views_use_bounded_current_windows(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    old_run = _run_context(tmp_path, config_path, "run-old")
    _write_raw(
        old_run,
        [_macro_item("2026-05-01T00:00:00Z")],
        window_start="2026-04-01T00:00:00Z",
        window_end="2026-05-31T00:00:00Z",
    )
    sync_macro_calendar_history(config, old_run, now="2026-05-01T01:00:00Z")

    result = run_pipeline(
        config,
        config_path=config_path,
        until_stage="build_source_evidence",
        stage_handlers={
            "collect_market_data": _noop_stage,
            "collect_macro_calendar_data": _write_current_macro_raw_stage,
            "sync_macro_calendar_history": lambda config, run: sync_macro_calendar_history(
                config,
                run,
                now="2026-06-18T01:00:00Z",
            ),
            "build_macro_calendar_views": lambda config, run: build_macro_calendar_views(
                config,
                run,
                now="2026-06-18T01:01:00Z",
            ),
        },
    )

    assert result.succeeded is True
    state = _state(tmp_path)
    stored_records = _stored_records(tmp_path)
    views = _views(result)
    view = views["views"][0]
    loaded_window = _load_macro_calendar_view_records(view, config_path=config_path)
    manifest = _manifest(result)
    catalog = _catalog(tmp_path)
    catalog_store = next(store for store in catalog["stores"] if store["name"] == "macro_calendar_history")

    assert state["status"] == "ok"
    assert state["totals"]["records"] == 3
    assert state["groups"][0]["storage_ref"] == (
        "data/macro/calendar/source=federal_reserve_fomc/data_class=central_bank_event/region=US"
    )
    assert len(stored_records) == 3
    assert stored_records[0]["origin_run_ids"] == ["run-old"]
    assert views["source_artifacts"] == ["data/macro/metadata/macro_calendar_state.json"]
    assert len(views["views"]) == 1
    assert view["view_id"] == (
        "macro_calendar_view:central_bank_event:federal_reserve_fomc:US:2026-07-29T00:00:00Z"
    )
    assert view["input_window_start"] == "2026-06-10T00:00:00Z"
    assert view["input_window_end"] == "2026-07-31T00:00:00Z"
    assert view["event_count"] == 2
    assert view["included_record_count"] == 2
    assert view["omitted_record_count"] == 0
    assert view["status"] == "succeeded"
    assert view["storage_ref"] == (
        "data/macro/calendar/source=federal_reserve_fomc/data_class=central_bank_event/region=US"
    )
    assert [record["scheduled_at"] for record in view["records"]] == [
        "2026-06-17T00:00:00Z",
        "2026-07-29T00:00:00Z",
    ]
    assert "2026-05-01T00:00:00Z" not in json.dumps(view)
    assert [record["scheduled_at"] for record in loaded_window] == [
        "2026-06-17T00:00:00Z",
        "2026-07-29T00:00:00Z",
    ]
    assert manifest["artifacts"]["macro_calendar_state"] == "data/macro/metadata/macro_calendar_state.json"
    assert manifest["artifacts"]["macro_calendar_views"] == "raw/macro_calendar_views.json"
    assert manifest["counts"]["macro_calendar_history_records"] == 3
    assert manifest["counts"]["macro_calendar_view_events"] == 2
    assert catalog_store["record_count"] == 3
    assert catalog_store["details"]["incoming_records"] == 2
    assert catalog_store["source_artifacts"] == [
        "data/macro/metadata/macro_calendar_schema.json",
        "data/macro/metadata/macro_calendar_state.json",
    ]


def test_macro_calendar_history_deduplicates_repeated_records_with_run_traceability(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    first_run = _run_context(tmp_path, config_path, "run-1")
    second_run = _run_context(tmp_path, config_path, "run-2")
    item = _macro_item("2026-06-17T00:00:00Z")

    _write_raw(first_run, [item])
    sync_macro_calendar_history(config, first_run, now="2026-06-18T01:00:00Z")
    _write_raw(second_run, [item])
    sync_macro_calendar_history(config, second_run, now="2026-06-18T02:00:00Z")

    state = _state(tmp_path)
    records = _stored_records(tmp_path)

    assert state["totals"]["records"] == 1
    assert state["totals"]["duplicate_records"] == 1
    assert state["totals"]["updated_records"] == 1
    assert records[0]["origin_run_ids"] == ["run-1", "run-2"]
    assert records[0]["first_seen_run_id"] == "run-1"
    assert records[0]["last_seen_run_id"] == "run-2"
    assert records[0]["source_artifacts"] == [
        "runs/run-1/raw/macro_calendar.json",
        "runs/run-2/raw/macro_calendar.json",
    ]


def test_macro_calendar_views_record_stale_current_window(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    old_run = _run_context(tmp_path, config_path, "run-old")
    _write_raw(
        old_run,
        [_macro_item("2025-01-29T00:00:00Z")],
        window_start="2025-01-01T00:00:00Z",
        window_end="2025-02-28T00:00:00Z",
    )
    sync_macro_calendar_history(config, old_run, now="2025-01-29T01:00:00Z")

    result = run_pipeline(
        config,
        config_path=config_path,
        until_stage="build_source_evidence",
        stage_handlers={
            "collect_market_data": _noop_stage,
            "collect_macro_calendar_data": _write_stale_macro_raw_stage,
            "sync_macro_calendar_history": lambda config, run: sync_macro_calendar_history(
                config,
                run,
                now="2026-06-18T01:00:00Z",
            ),
            "build_macro_calendar_views": lambda config, run: build_macro_calendar_views(
                config,
                run,
                now="2026-06-18T01:01:00Z",
            ),
        },
    )

    assert result.succeeded is True
    state = _state(tmp_path)
    view = _views(result)["views"][0]
    manifest = _manifest(result)

    assert state["status"] == "warning"
    assert state["totals"]["records"] == 1
    assert state["availability"][0]["status"] == "stale"
    assert view["status"] == "stale"
    assert view["event_count"] == 0
    assert view["records"] == []
    assert view["latest_observation_time"] == "2025-01-29T00:00:00Z"
    assert manifest["counts"]["macro_calendar_views_stale"] == 1
    assert manifest["macro_calendar_views"]["status"] == "warning"


def _write_config(tmp_path: Path) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(
        """
run:
  output_dir: runs
market:
  enabled: true
  source: binance
  symbols:
    - BTCUSDT
macro_calendar:
  enabled: true
  source: federal_reserve_fomc
  data_classes:
    - central_bank_event
  regions:
    - US
  lookback_days: 8
  lookahead_days: 43
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


def _write_current_macro_raw_stage(config: dict[str, Any], run: RunContext) -> list[str]:
    _write_raw(
        run,
        [
            _macro_item("2026-06-17T00:00:00Z"),
            _macro_item("2026-07-29T00:00:00Z"),
        ],
        window_start="2026-06-10T00:00:00Z",
        window_end="2026-07-31T00:00:00Z",
    )
    run.manifest["artifacts"]["raw_macro_calendar"] = "raw/macro_calendar.json"
    return ["raw/macro_calendar.json"]


def _write_stale_macro_raw_stage(config: dict[str, Any], run: RunContext) -> list[str]:
    _write_raw(
        run,
        [],
        window_start="2026-06-10T00:00:00Z",
        window_end="2026-07-31T00:00:00Z",
        availability_status="stale",
    )
    run.manifest["artifacts"]["raw_macro_calendar"] = "raw/macro_calendar.json"
    return ["raw/macro_calendar.json"]


def _write_raw(
    run: RunContext,
    items: list[dict[str, Any]],
    *,
    window_start: str = "2026-06-10T00:00:00Z",
    window_end: str = "2026-07-31T00:00:00Z",
    availability_status: str = "succeeded",
) -> None:
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
            "collected_at": "2026-06-18T01:00:00Z",
            "window": {
                "lookback_start": window_start,
                "lookahead_end": window_end,
            },
            "items": items,
            "availability": [
                {
                    "source": "federal_reserve_fomc",
                    "data_class": "central_bank_event",
                    "status": availability_status,
                    "record_count": len(items),
                    "parsed_record_count": len(items),
                    "error_count": 0,
                    "endpoint": "fomc_calendars",
                }
            ],
            "warnings": [],
            "errors": [],
        },
    )


def _macro_item(scheduled_at: str) -> dict[str, Any]:
    return {
        "item_id": f"macro_calendar:central_bank_event:federal_reserve_fomc:US:fomc_meeting:{scheduled_at}",
        "data_class": "central_bank_event",
        "source": "federal_reserve_fomc",
        "event_name": "Federal Open Market Committee meeting",
        "event_type": "fomc_meeting",
        "region": "US",
        "affected_assets": ["BTCUSDT"],
        "scheduled_at": scheduled_at,
        "source_timezone": "America/New_York",
        "importance": "high",
        "source_published_at": None,
        "endpoint": "fomc_calendars",
        "metrics": {},
        "units": {},
        "raw_fields": {
            "source_url": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
            "time_precision": "date",
        },
        "warnings": [],
        "errors": [],
        "collected_at": "2026-06-18T01:00:00Z",
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
    return json.loads((tmp_path / "data" / "macro" / "metadata" / "macro_calendar_state.json").read_text(encoding="utf-8"))


def _stored_records(tmp_path: Path) -> list[dict[str, Any]]:
    return json.loads(
        (
            tmp_path
            / "data"
            / "macro"
            / "calendar"
            / "source=federal_reserve_fomc"
            / "data_class=central_bank_event"
            / "region=US"
            / "records.json"
        ).read_text(encoding="utf-8")
    )


def _views(result) -> dict[str, Any]:
    return json.loads((result.run.raw_dir / "macro_calendar_views.json").read_text(encoding="utf-8"))


def _manifest(result) -> dict[str, Any]:
    return json.loads(result.run.manifest_path.read_text(encoding="utf-8"))


def _catalog(tmp_path: Path) -> dict[str, Any]:
    return json.loads((tmp_path / "data" / "research" / "metadata" / "research_data_catalog.json").read_text(encoding="utf-8"))


def _noop_stage(config, run) -> list[str]:
    return []
