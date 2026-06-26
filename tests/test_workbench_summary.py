from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from halpha.pipeline import RunContext
from halpha.data.run_index import write_run_index
from halpha.monitor.state_store import MonitorArchivePersistence, MonitorStateRepository
from halpha.storage import write_json
from halpha.workbench.workbench import build_workbench_summary, render_workbench_html
from halpha.workbench.workbench_rendering import render_workbench_markdown


@pytest.fixture(autouse=True)
def _isolate_artifact_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


def test_workbench_summary_records_complete_local_state(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    run = _write_run(tmp_path, config_path)
    _write_complete_artifacts(run, tmp_path)
    run.manifest["run_index"] = write_run_index(run, now="2026-06-20T00:05:00Z")
    write_json(run.manifest_path, run.manifest)

    result = build_workbench_summary(
        {"run": {"output_dir": "runs"}},
        config_path=config_path,
        now=datetime(2026, 6, 20, 0, 6, tzinfo=timezone.utc),
    )

    summary = result.summary
    assert result.summary_path == tmp_path / "runs" / "workbench" / "latest" / "workbench_summary.json"
    assert json.loads(result.summary_path.read_text(encoding="utf-8")) == summary
    assert (tmp_path / "runs" / "workbench" / "latest" / "index.md").is_file()
    assert (tmp_path / "runs" / "workbench" / "latest" / "index.html").is_file()
    assert summary["status"] == "available"
    assert summary["generated_at"] == "2026-06-20T00:06:00Z"
    assert summary["display"] == {
        "timezone": "Asia/Shanghai",
        "generated_at": "2026-06-20 08:06:00 Asia/Shanghai (UTC+08:00)",
    }
    assert summary["index_outputs"] == {
        "status": "available",
        "markdown": "runs/workbench/latest/index.md",
        "html": "runs/workbench/latest/index.html",
    }
    assert summary["source_selection"]["status"] == "available"
    assert summary["latest_run"]["fields"]["run_id"] == "run-1"
    assert summary["latest_run"]["fields"]["report"]["status"] == "available"
    assert summary["decision_state"]["status"] == "available"
    assert summary["decision_state"]["fields"]["decision_records"] == 2
    assert summary["alert_state"]["fields"]["archive_state"]["counts"]["records"] == 3
    assert summary["alert_state"]["fields"]["archive_state"]["updated_at"] == "2026-06-20T00:11:00Z"
    assert summary["alert_state"]["fields"]["archive_state"]["last_cycle_id"] == "cycle-2"
    assert summary["alert_state"]["fields"]["archive_state"]["sample_order"] == "newest_first"
    assert summary["alert_state"]["fields"]["archive_state"]["sample_record_limit"] == 20
    assert summary["alert_state"]["fields"]["archive_state"]["sample_truncated"] is False
    assert summary["monitor_state"]["fields"]["cycle_count"] == 2
    assert summary["outcome_state"]["fields"]["history_records"] == 7
    assert summary["strategy_state"]["fields"]["strategy_gate_effective"] == 3
    assert summary["strategy_state"]["fields"]["strategy_lifecycle_records"] == 3
    assert summary["strategy_state"]["fields"]["strategy_lifecycle_degraded"] == 1
    assert summary["strategy_state"]["fields"]["strategy_lifecycle_retired"] == 1
    assert summary["strategy_state"]["fields"]["strategy_lifecycle_state_status"] == "available"
    assert summary["product_validation_state"]["status"] == "available"
    assert summary["product_validation_state"]["fields"]["checks"] == 12
    assert summary["product_validation_state"]["fields"]["failed"] == 0
    assert summary["product_validation_state"]["fields"]["source_artifact_refs"] == [
        "run_manifest.json",
        "analysis/risk_assessment.json",
    ]
    assert summary["data_quality_state"]["fields"]["checks"] == 10
    assert summary["source_artifacts"]["analysis"]["decision_recommendations"] == "analysis/decision_recommendations.json"
    assert summary["source_artifacts"]["analysis"]["strategy_lifecycle_state"] == "analysis/strategy_lifecycle_state.json"
    assert summary["source_artifacts"]["analysis"]["product_contract_validation"] == (
        "analysis/product_contract_validation.json"
    )
    assert summary["omitted"]["full_intermediate_json_embedded"] is False
    assert summary["codex_boundary"]["codex_input_by_default"] is False
    markdown = (tmp_path / "runs" / "workbench" / "latest" / "index.md").read_text(encoding="utf-8")
    html = (tmp_path / "runs" / "workbench" / "latest" / "index.html").read_text(encoding="utf-8")
    assert "# Halpha Workbench" in markdown
    assert "Generated at: `2026-06-20 08:06:00 Asia/Shanghai (UTC+08:00)`" in markdown
    assert "../../run-1/report/report.md" in markdown
    assert "Decision and watch" in markdown
    assert "Product validation" in markdown
    assert "failed checks: 0" in markdown
    assert "degraded lifecycle: 1" in markdown
    assert "<table>" in html
    assert "Generated at: <code>2026-06-20 08:06:00 Asia/Shanghai (UTC+08:00)</code>" in html
    assert "../../run-1/report/report.md" in html
    assert "Product validation" in html
    assert "retired lifecycle: 1" in html


def test_workbench_summary_handles_missing_run_index(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)

    result = build_workbench_summary(
        {"run": {"output_dir": "runs"}},
        config_path=config_path,
        now=datetime(2026, 6, 20, 0, 0, tzinfo=timezone.utc),
    )

    summary = result.summary
    assert result.summary_path.is_file()
    assert summary["status"] == "missing"
    assert summary["source_selection"]["status"] == "missing"
    assert summary["source_selection"]["source_artifact"] == ".halpha/state.sqlite"
    assert summary["latest_run"]["status"] == "missing"
    assert summary["product_validation_state"]["status"] == "missing"
    assert "local run index was not found." in summary["warnings"]
    assert summary["source_artifacts"] == {}
    markdown = (tmp_path / "runs" / "workbench" / "latest" / "index.md").read_text(encoding="utf-8")
    assert "Status: `missing`" in markdown
    assert "- none" in markdown


def test_workbench_summary_marks_invalid_artifacts_failed(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    run = _write_run(tmp_path, config_path)
    run.manifest["artifacts"].update(
        {
            "risk_assessment": "analysis/risk_assessment.json",
            "decision_recommendations": "analysis/decision_recommendations.json",
            "watch_triggers": "analysis/watch_triggers.json",
        }
    )
    write_json(run.manifest_path, run.manifest)
    write_json(run.analysis_dir / "risk_assessment.json", _artifact("risk_assessment"))
    (run.analysis_dir / "decision_recommendations.json").write_text("{not-json", encoding="utf-8")
    write_json(run.analysis_dir / "watch_triggers.json", _artifact("watch_triggers"))

    result = build_workbench_summary(
        {"run": {"output_dir": "runs"}},
        config_path=config_path,
        run_dir=Path("runs/run-1"),
        now=datetime(2026, 6, 20, 0, 0, tzinfo=timezone.utc),
    )

    summary = result.summary
    assert summary["status"] == "failed"
    assert summary["source_selection"]["mode"] == "explicit_run"
    assert summary["decision_state"]["status"] == "failed"
    assert any(
        item["name"] == "decision_recommendations" and item["status"] == "failed"
        for item in summary["decision_state"]["details"]["artifacts"]
    )
    assert "analysis/decision_recommendations.json decision_recommendations.json is not valid JSON" in " ".join(
        summary["errors"]
    )


def test_workbench_html_escapes_summary_text() -> None:
    html = render_workbench_html(
        {
            "status": "<script>alert(1)</script>",
            "generated_at": "2026-06-20T00:00:00Z",
            "source_selection": {"run_dir": "runs/run-1"},
            "latest_run": {
                "fields": {
                    "run_id": "<script>alert(2)</script>",
                    "run_status": "succeeded",
                    "report": {"status": "available", "artifact": "report/report.md"},
                }
            },
            "decision_state": {"status": "available", "fields": {"decision_records": 1}},
            "alert_state": {"status": "missing", "fields": {}},
            "monitor_state": {"status": "missing", "fields": {}},
            "outcome_state": {"status": "missing", "fields": {}},
            "strategy_state": {"status": "available", "fields": {"strategy_gate_effective": 3}},
            "product_validation_state": {"status": "available", "fields": {"checks": 4, "failed": 0}},
            "data_quality_state": {"status": "available", "fields": {"warnings": 0}},
            "source_artifacts": {},
            "warnings": ["<private-note>"],
            "errors": [],
        }
    )

    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "&lt;script&gt;alert(2)&lt;/script&gt;" in html
    assert "&lt;private-note&gt;" in html
    assert "<script>" not in html


def test_workbench_markdown_renderer_links_relative_artifacts() -> None:
    markdown = render_workbench_markdown(
        {
            "status": "available",
            "generated_at": "2026-06-20T00:00:00Z",
            "source_selection": {"run_dir": "runs/run-1"},
            "latest_run": {
                "fields": {
                    "run_id": "run-1",
                    "run_status": "succeeded",
                    "report": {"status": "available", "artifact": "report/report.md"},
                }
            },
            "decision_state": {"status": "available", "fields": {"decision_records": 2}},
            "alert_state": {"status": "missing", "fields": {}},
            "monitor_state": {"status": "missing", "fields": {}},
            "outcome_state": {"status": "missing", "fields": {}},
            "strategy_state": {"status": "available", "fields": {"strategy_gate_effective": 3}},
            "product_validation_state": {"status": "available", "fields": {"checks": 4, "failed": 0}},
            "data_quality_state": {"status": "available", "fields": {"warnings": 0}},
            "source_artifacts": {
                "run_manifest": "runs/run-1/run_manifest.json",
                "report": "report/report.md",
                "analysis": {"risk_assessment": "analysis/risk_assessment.json"},
            },
            "warnings": ["review warning"],
            "errors": ["review error"],
        }
    )

    assert "[`report/report.md`](../../run-1/report/report.md)" in markdown
    assert "- run_manifest: [`runs/run-1/run_manifest.json`](../../run-1/run_manifest.json)" in markdown
    assert "- analysis.risk_assessment: [`analysis/risk_assessment.json`](../../run-1/analysis/risk_assessment.json)" in markdown
    assert "- review warning" in markdown
    assert "- review error" in markdown


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
text:
  enabled: false
codex:
  enabled: false
""".strip(),
        encoding="utf-8",
    )
    return path


def _write_run(tmp_path: Path, config_path: Path) -> RunContext:
    run_dir = tmp_path / "runs" / "run-1"
    raw_dir = run_dir / "raw"
    analysis_dir = run_dir / "analysis"
    codex_context_dir = run_dir / "codex_context"
    report_dir = run_dir / "report"
    for path in (raw_dir, analysis_dir, codex_context_dir, report_dir):
        path.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": 1,
        "run_id": "run-1",
        "status": "succeeded",
        "started_at": "2026-06-20T00:00:00Z",
        "finished_at": "2026-06-20T00:05:00Z",
        "artifacts": {},
        "counts": {},
        "stages": [],
        "codex": {"status": "skipped"},
        "errors": [],
    }
    return RunContext(
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


def _write_complete_artifacts(run: RunContext, tmp_path: Path) -> None:
    run.manifest["artifacts"].update(
        {
            "report": "report/report.md",
            "risk_assessment": "analysis/risk_assessment.json",
            "decision_recommendations": "analysis/decision_recommendations.json",
            "watch_triggers": "analysis/watch_triggers.json",
            "alert_decisions": "analysis/alert_decisions.json",
            "outcome_targets": "analysis/outcome_targets.json",
            "outcome_evaluations": "analysis/outcome_evaluations.json",
            "strategy_evaluation_summary": "analysis/strategy_evaluation_summary.json",
            "strategy_experiment": "analysis/strategy_experiment.json",
            "strategy_effectiveness_gates": "analysis/strategy_effectiveness_gates.json",
            "strategy_lifecycle_state": "analysis/strategy_lifecycle_state.json",
            "strategy_lifecycle_material": "analysis/strategy_lifecycle_material.md",
            "product_contract_validation": "analysis/product_contract_validation.json",
            "data_quality_summary": "analysis/data_quality_summary.json",
        }
    )
    run.manifest["counts"].update(
        {
            "risk_assessment_records": 2,
            "risk_assessment_high_or_extreme_records": 1,
            "risk_assessment_blocking_records": 0,
            "decision_recommendation_records": 2,
            "decision_recommendation_actionable_records": 1,
            "decision_recommendation_risk_blocked_records": 0,
            "watch_trigger_records": 4,
            "alert_decision_records": 5,
            "alert_decision_attention_records": 2,
            "outcome_targets": 4,
            "outcome_evaluations": 4,
            "outcome_evaluations_evaluated": 2,
            "outcome_evaluations_pending": 1,
            "outcome_evaluations_insufficient_data": 1,
            "strategy_evaluation_records": 3,
            "strategy_evaluation_succeeded": 3,
            "strategy_gate_candidates": 4,
            "strategy_gate_effective": 3,
            "strategy_gate_watchlisted": 1,
            "strategy_gate_rejected": 0,
            "strategy_gate_insufficient_evidence": 0,
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
            "product_contract_validation_checks": 12,
            "product_contract_validation_warning": 0,
            "product_contract_validation_degraded": 0,
            "product_contract_validation_failed": 0,
            "data_quality_checks": 10,
            "data_quality_warnings": 0,
            "data_quality_errors": 0,
            "data_quality_degraded_checks": 0,
            "data_quality_failed_checks": 0,
        }
    )
    (run.report_dir / "report.md").write_text("# report\n", encoding="utf-8")
    for key, ref in run.manifest["artifacts"].items():
        if not ref.startswith("analysis/"):
            continue
        write_json(run.run_dir / ref, _artifact(key, counts={"records": 1}))
    write_json(
        run.analysis_dir / "product_contract_validation.json",
        {
            "schema_version": 1,
            "artifact_type": "product_contract_validation",
            "run_id": run.run_id,
            "status": "ok",
            "counts": {
                "checks": 12,
                "ok": 12,
                "warning": 0,
                "degraded": 0,
                "failed": 0,
                "skipped": 0,
                "warnings": 0,
                "errors": 0,
            },
            "checks": [],
            "source_artifacts": ["run_manifest.json", "analysis/risk_assessment.json"],
            "warnings": [],
            "errors": [],
        },
    )
    _write_monitor_cycle_state(run.config_path, tmp_path, cycle_id="cycle-1", record_statuses=["emitted"])
    _write_monitor_cycle_state(
        run.config_path,
        tmp_path,
        cycle_id="cycle-2",
        record_statuses=["suppressed_duplicate", "suppressed_cooldown"],
        started_at="2026-06-20T00:10:00Z",
        finished_at="2026-06-20T00:11:00Z",
    )
    write_json(
        tmp_path / "data" / "research" / "metadata" / "outcome_history_state.json",
        {
            "schema_version": 1,
            "artifact_type": "outcome_history_state",
            "status": "ok",
            "totals": {"records": 7},
        },
    )
    write_json(run.manifest_path, run.manifest)


def _write_monitor_cycle_state(
    config_path: Path,
    tmp_path: Path,
    *,
    cycle_id: str,
    record_statuses: list[str],
    started_at: str = "2026-06-20T00:08:00Z",
    finished_at: str = "2026-06-20T00:09:00Z",
) -> None:
    write_json(
        tmp_path / "runs" / "monitor" / "cycles" / cycle_id / "monitor_cycle_manifest.json",
        {"artifact_type": "monitor_cycle_manifest", "cycle_id": cycle_id, "status": "succeeded"},
    )
    records = [
        {
            "record_id": f"{cycle_id}-record-{index}",
            "cycle_id": cycle_id,
            "created_at": finished_at,
            "status": status,
            "alert_key": f"{cycle_id}-alert-{index}",
            "decision_id": f"{cycle_id}-decision-{index}",
            "symbol": "BTCUSDT",
            "timeframe": "1d",
            "priority": "P1",
            "attention_decision": "review_soon",
            "requires_user_attention": status == "emitted",
            "suppression_reasons": [],
            "cooldown_until": "2026-06-20T01:00:00Z" if status != "suppressed_duplicate" else None,
            "source_artifacts": ["analysis/alert_decisions.json"],
            "personalized_context": {"present": False},
            "source_run": {"run_id": "run-1", "run_manifest": "runs/run-1/run_manifest.json"},
        }
        for index, status in enumerate(record_statuses)
    ]
    counts = {
        "records": len(records),
        "emitted": sum(1 for status in record_statuses if status == "emitted"),
        "suppressed_duplicate": sum(1 for status in record_statuses if status == "suppressed_duplicate"),
        "suppressed_cooldown": sum(1 for status in record_statuses if status == "suppressed_cooldown"),
        "suppressed_no_alert": sum(1 for status in record_statuses if status == "suppressed_no_alert"),
        "skipped": sum(1 for status in record_statuses if status == "skipped"),
    }
    summary = {
        "status": "succeeded",
        "state_store": ".halpha/state.sqlite",
        "archive": ".halpha/state.sqlite",
        "cooldown_state": ".halpha/state.sqlite",
        "archive_state": ".halpha/state.sqlite",
        "counts": counts,
        "warnings": [],
        "errors": [],
    }
    MonitorStateRepository(config_path=config_path).persist_cycle_with_archive_builder(
        {
            "cycle_id": cycle_id,
            "monitor_output_dir": "runs/monitor",
            "cycle_manifest": f"runs/monitor/cycles/{cycle_id}/monitor_cycle_manifest.json",
            "cycle_mode": "once",
            "loop_id": None,
            "cycle_sequence": None,
            "trigger_source": "cli",
            "status": "succeeded",
            "started_at": started_at,
            "finished_at": finished_at,
            "config_ref": "config.yaml",
            "target_stage": "build_personalized_risk_material",
            "no_codex": True,
            "exit_code": 0,
            "run_id": "run-1",
            "run_dir": "runs/run-1",
            "run_manifest": "runs/run-1/run_manifest.json",
            "product_run": {"run_id": "run-1", "status": "succeeded"},
            "source_artifacts": {"alert_decisions": "analysis/alert_decisions.json"},
            "alert_archive": summary,
            "warnings": [],
            "errors": [],
        },
        build_archive=lambda _cooldown: MonitorArchivePersistence(
            summary=summary,
            records=records,
            cooldown_records={},
        ),
        updated_at=finished_at,
    )


def _artifact(artifact_type: str, *, counts: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "artifact_type": artifact_type,
        "status": "ok",
        "counts": counts or {},
        "warnings": [],
        "errors": [],
    }
