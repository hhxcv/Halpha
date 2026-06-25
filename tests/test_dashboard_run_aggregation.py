from __future__ import annotations

from pathlib import Path

from halpha.dashboard.run_aggregation import manifest_report_state, run_list_record, run_report_state


def test_run_report_state_keeps_missing_report_as_diagnostic(tmp_path: Path) -> None:
    run_dir = tmp_path / "runs" / "run-1"
    run_dir.mkdir(parents=True)

    state = run_report_state(run_dir, "report/report.md", codex_status="succeeded", base=tmp_path)

    assert state == {
        "status": "missing",
        "artifact": "report/report.md",
        "warning": "recorded report artifact was not found.",
    }


def test_run_list_record_marks_available_report_and_latest_state(tmp_path: Path) -> None:
    run_dir = tmp_path / "runs" / "run-1"
    report_path = run_dir / "report" / "report.md"
    manifest_path = run_dir / "run_manifest.json"
    report_path.parent.mkdir(parents=True)
    report_path.write_text("# Report\n", encoding="utf-8")
    manifest_path.write_text("{}", encoding="utf-8")
    row = (
        "run-1",
        "runs/run-1",
        "2026-06-20T00:00:00Z",
        "2026-06-20T00:01:00Z",
        "succeeded",
        None,
        "succeeded",
        1,
        0,
        "runs/run-1/run_manifest.json",
    )

    record = run_list_record(
        row,
        {"report": ["report/report.md"]},
        base=tmp_path,
        latest={"latest_run_id": "run-1", "latest_successful_run_id": "run-1"},
    )

    assert record["report"] == "report/report.md"
    assert record["report_state"] == {"status": "available", "artifact": "report/report.md"}
    assert record["integrity_state"]["status"] == "available"
    assert record["run_kind"] == "unknown"
    assert record["trigger"] == {"source": "unknown", "intent": "unknown"}
    assert record["disposal_class"] == "legacy_archive"
    assert record["latest_state"] == {"is_latest_run": True, "is_latest_successful_run": True}


def test_run_list_record_exposes_indexed_classification(tmp_path: Path) -> None:
    run_dir = tmp_path / "runs" / "run-1"
    manifest_path = run_dir / "run_manifest.json"
    run_dir.mkdir(parents=True)
    manifest_path.write_text("{}", encoding="utf-8")
    row = (
        "run-1",
        "runs/run-1",
        "2026-06-20T00:00:00Z",
        "2026-06-20T00:01:00Z",
        "succeeded",
        None,
        "skipped",
        0,
        0,
        "runs/run-1/run_manifest.json",
        "monitor_reassessment",
        "Monitor",
        "monitor_reassessment",
        "monitor_reassessment_archive",
        None,
        None,
        "cycle-1",
        "text,macro_calendar",
        None,
        None,
    )

    record = run_list_record(
        row,
        {},
        base=tmp_path,
        latest={"latest_run_id": "run-1", "latest_successful_run_id": "run-1"},
    )

    assert record["run_kind"] == "monitor_reassessment"
    assert record["trigger"] == {
        "source": "Monitor",
        "intent": "monitor_reassessment",
        "monitor_cycle_id": "cycle-1",
        "source_keys": ["text", "macro_calendar"],
    }
    assert record["disposal_class"] == "monitor_reassessment_archive"


def test_manifest_report_state_respects_codex_skipped_without_fake_report(tmp_path: Path) -> None:
    run_dir = tmp_path / "runs" / "run-1"
    run_dir.mkdir(parents=True)

    state = manifest_report_state(run_dir, {"artifacts": {}, "codex": {"status": "skipped"}})

    assert state == {"status": "skipped", "artifact": None}
