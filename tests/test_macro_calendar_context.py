from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from halpha.config import load_config
from halpha.macro.macro_calendar_context import build_macro_calendar_context
from halpha.macro.macro_calendar_history import sync_macro_calendar_history
from halpha.macro.macro_calendar_views import build_macro_calendar_views
from halpha.pipeline import RunContext, run_pipeline
from halpha.storage import write_json


def test_macro_context_builds_upcoming_and_recent_catalysts(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    result = _run_until_context(config, config_path, _write_current_macro_raw_stage)

    assert result.succeeded is True
    context = _context(result)
    manifest = _manifest(result)
    recent = _context_record(context, "recent_catalyst")
    upcoming = _context_record(context, "scheduled_catalyst")

    assert context["status"] == "ok"
    assert context["counts"]["records"] == 2
    assert recent["state"] == "recent"
    assert recent["status"] == "succeeded"
    assert recent["scheduled_at"] == "2026-06-17T00:00:00Z"
    assert recent["realized_impact"]["status"] == "not_evaluated"
    assert "recent scheduled catalyst does not confirm market response." in recent["uncertainty"]
    assert upcoming["state"] == "upcoming"
    assert upcoming["status"] == "succeeded"
    assert upcoming["scheduled_at"] == "2026-07-29T00:00:00Z"
    assert upcoming["time_to_event_hours"] == 983.0
    assert upcoming["severity"] == "medium"
    assert "upcoming scheduled catalyst is timing evidence, not a forecast." in upcoming["uncertainty"]
    assert manifest["artifacts"]["macro_calendar_context"] == "analysis/macro_calendar_context.json"
    assert manifest["counts"]["macro_calendar_context_records"] == 2
    assert manifest["macro_calendar_context"]["scheduled_catalyst"] == 1
    assert manifest["macro_calendar_context"]["recent_catalyst"] == 1


def test_macro_context_records_no_event_window(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    result = _run_until_context(config, config_path, _write_no_event_macro_raw_stage)

    assert result.succeeded is True
    context = _context(result)
    no_event = _context_record(context, "no_event_window")

    assert context["status"] == "ok"
    assert no_event["status"] == "no_event"
    assert no_event["state"] == "no_event"
    assert no_event["scheduled_at"] is None
    assert no_event["realized_impact"]["status"] == "not_evaluated"
    assert "no-event window does not prove macro risk is absent." in no_event["uncertainty"]
    assert context["counts"]["no_event_window"] == 1


def test_macro_context_records_stale_calendar(tmp_path: Path) -> None:
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

    result = _run_until_context(config, config_path, _write_stale_macro_raw_stage)

    assert result.succeeded is True
    context = _context(result)
    stale = _context_record(context, "source_availability")

    assert context["status"] == "warning"
    assert stale["status"] == "stale"
    assert stale["state"] == "stale"
    assert stale["confidence"] == "low"
    assert "source availability is stale." in stale["uncertainty"]
    assert context["counts"]["stale"] == 1


def test_macro_context_omits_duplicate_view_records(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    run = _run_context(tmp_path, config_path, "run-duplicate")
    _write_views(run, [_view_record("2026-07-29T00:00:00Z"), _view_record("2026-07-29T00:00:00Z")])

    artifacts = build_macro_calendar_context(config, run, now="2026-06-18T01:00:00Z")

    context = _context_from_run(run)
    assert artifacts == ["analysis/macro_calendar_context.json"]
    assert context["counts"]["records"] == 1
    assert context["counts"]["scheduled_catalyst"] == 1
    assert any("duplicate macro calendar context input omitted" in warning for warning in context["warnings"])


def test_macro_context_marks_partial_source_with_low_confidence(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    result = _run_until_context(config, config_path, _write_partial_macro_raw_stage)

    assert result.succeeded is True
    context = _context(result)
    catalyst = _context_record(context, "scheduled_catalyst")

    assert context["status"] == "warning"
    assert catalyst["status"] == "partial"
    assert catalyst["state"] == "upcoming"
    assert catalyst["confidence"] == "low"
    assert catalyst["source_availability"] == "partial"
    assert "source availability is partial." in catalyst["uncertainty"]
    assert context["counts"]["partial"] == 1


def _run_until_context(config: dict[str, Any], config_path: Path, raw_stage) -> Any:
    return run_pipeline(
        config,
        config_path=config_path,
        until_stage="build_macro_calendar_context",
        stage_handlers={
            "collect_market_data": _noop_stage,
            "collect_macro_calendar_data": raw_stage,
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
            "build_macro_calendar_context": lambda config, run: build_macro_calendar_context(
                config,
                run,
                now="2026-06-18T01:00:00Z",
            ),
        },
    )


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


def _write_no_event_macro_raw_stage(config: dict[str, Any], run: RunContext) -> list[str]:
    _write_raw(
        run,
        [],
        window_start="2026-06-10T00:00:00Z",
        window_end="2026-07-31T00:00:00Z",
        availability_status="no_event",
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


def _write_partial_macro_raw_stage(config: dict[str, Any], run: RunContext) -> list[str]:
    _write_raw(
        run,
        [_macro_item("2026-07-29T00:00:00Z")],
        window_start="2026-06-10T00:00:00Z",
        window_end="2026-07-31T00:00:00Z",
        availability_status="partial",
    )
    run.manifest["artifacts"]["raw_macro_calendar"] = "raw/macro_calendar.json"
    return ["raw/macro_calendar.json"]


def _write_raw(
    run: RunContext,
    items: list[dict[str, Any]],
    *,
    window_start: str,
    window_end: str,
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


def _write_views(run: RunContext, records: list[dict[str, Any]]) -> None:
    write_json(
        run.raw_dir / "macro_calendar_views.json",
        {
            "schema_version": 1,
            "artifact_type": "macro_calendar_views",
            "created_at": "2026-06-18T01:00:00Z",
            "input_window_start": "2026-06-10T00:00:00Z",
            "input_window_end": "2026-07-31T00:00:00Z",
            "source_artifacts": ["data/macro/metadata/macro_calendar_state.json"],
            "views": [
                {
                    "view_id": "macro_calendar_view:central_bank_event:federal_reserve_fomc:US:2026-07-29T00:00:00Z",
                    "data_class": "central_bank_event",
                    "source": "federal_reserve_fomc",
                    "region": "US",
                    "lookback_days": 8,
                    "lookahead_days": 43,
                    "input_window_start": "2026-06-10T00:00:00Z",
                    "input_window_end": "2026-07-31T00:00:00Z",
                    "latest_observation_time": "2026-07-29T00:00:00Z",
                    "event_count": len(records),
                    "included_record_count": len(records),
                    "omitted_record_count": 0,
                    "status": "succeeded",
                    "storage_ref": "data/macro/calendar/source=federal_reserve_fomc/data_class=central_bank_event/region=US",
                    "included_columns": [
                        "scheduled_at",
                        "event_name",
                        "event_type",
                        "importance",
                        "affected_assets",
                        "endpoint",
                        "warnings",
                        "errors",
                    ],
                    "records": records,
                    "warnings": [],
                    "errors": [],
                    "source_artifacts": ["data/macro/metadata/macro_calendar_state.json"],
                }
            ],
            "warnings": [],
            "errors": [],
        },
    )


def _macro_item(scheduled_at: str) -> dict[str, Any]:
    item = _view_record(scheduled_at)
    return {
        **item,
        "item_id": f"macro_calendar:central_bank_event:federal_reserve_fomc:US:fomc_meeting:{scheduled_at}",
        "data_class": "central_bank_event",
        "source": "federal_reserve_fomc",
        "region": "US",
        "source_timezone": "America/New_York",
        "source_published_at": None,
        "metrics": {},
        "units": {},
        "raw_fields": {
            "source_url": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
            "time_precision": "date",
        },
        "collected_at": "2026-06-18T01:00:00Z",
    }


def _view_record(scheduled_at: str) -> dict[str, Any]:
    return {
        "scheduled_at": scheduled_at,
        "event_name": "Federal Open Market Committee meeting",
        "event_type": "fomc_meeting",
        "importance": "high",
        "affected_assets": ["BTCUSDT"],
        "endpoint": "fomc_calendars",
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


def _context(result) -> dict[str, Any]:
    return json.loads((result.run.analysis_dir / "macro_calendar_context.json").read_text(encoding="utf-8"))


def _context_from_run(run: RunContext) -> dict[str, Any]:
    return json.loads((run.analysis_dir / "macro_calendar_context.json").read_text(encoding="utf-8"))


def _context_record(context: dict[str, Any], context_type: str) -> dict[str, Any]:
    return next(record for record in context["records"] if record["context_type"] == context_type)


def _manifest(result) -> dict[str, Any]:
    return json.loads(result.run.manifest_path.read_text(encoding="utf-8"))


def _noop_stage(config, run) -> list[str]:
    return []
