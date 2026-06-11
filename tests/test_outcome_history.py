from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from halpha.outcome_history import write_outcome_history
from halpha.pipeline import RunContext


def test_outcome_history_appends_records_and_updates_manifest(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    run = _run_context(tmp_path, config_path, "run-1")
    _write_outcome_evaluations(run, [_evaluation("target-1")])

    artifacts = write_outcome_history({}, run, now="2026-06-05T00:00:00Z")

    state = _state(tmp_path)
    records = _history_records(tmp_path)
    record = records[0]

    assert artifacts == ["data/research/metadata/outcome_history_state.json"]
    assert state["status"] == "ok"
    assert state["totals"]["records"] == 1
    assert state["totals"]["inserted_records"] == 1
    assert record["stable_outcome_key"].startswith("outcome_history:")
    assert record["target_id"] == "target-1"
    assert record["source_run_id"] == "source-run"
    assert record["evaluation_run_ids"] == ["run-1"]
    assert record["latest_evaluation_run_id"] == "run-1"
    assert record["outcome_state"] == "aligned"
    assert record["metrics"]["return_pct"] == 0.04
    assert record["source_artifacts"] == [
        "data/market/metadata/ohlcv_sync_state.json",
        "runs/run-1/analysis/outcome_evaluations.json",
        "runs/run-1/analysis/outcome_targets.json",
    ]
    assert run.manifest["artifacts"]["outcome_history_state"] == (
        "data/research/metadata/outcome_history_state.json"
    )
    assert run.manifest["counts"]["outcome_history_records"] == 1


def test_outcome_history_deduplicates_repeated_evaluations(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    run = _run_context(tmp_path, config_path, "run-1")
    _write_outcome_evaluations(run, [_evaluation("target-1")])

    write_outcome_history({}, run, now="2026-06-05T00:00:00Z")
    write_outcome_history({}, run, now="2026-06-05T00:01:00Z")

    state = _state(tmp_path)
    records = _history_records(tmp_path)

    assert state["status"] == "ok"
    assert state["totals"]["records"] == 1
    assert state["totals"]["duplicate_records"] == 1
    assert state["totals"]["updated_records"] == 0
    assert state["totals"]["conflicting_duplicates"] == 0
    assert records[0]["evaluation_run_ids"] == ["run-1"]


def test_outcome_history_warns_on_conflicting_same_run_duplicate(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    run = _run_context(tmp_path, config_path, "run-1")
    _write_outcome_evaluations(run, [_evaluation("target-1", outcome_state="aligned")])
    write_outcome_history({}, run, now="2026-06-05T00:00:00Z")

    _write_outcome_evaluations(run, [_evaluation("target-1", outcome_state="not_aligned")])
    write_outcome_history({}, run, now="2026-06-05T00:01:00Z")

    state = _state(tmp_path)
    record = _history_records(tmp_path)[0]

    assert state["status"] == "warning"
    assert state["totals"]["records"] == 1
    assert state["totals"]["duplicate_records"] == 1
    assert state["totals"]["updated_records"] == 1
    assert state["totals"]["conflicting_duplicates"] == 1
    assert "conflicting duplicate outcome history record:" in state["warnings"][0]
    assert record["status"] == "warning"
    assert record["outcome_state"] == "not_aligned"
    assert "conflicting duplicate outcome history record:" in record["warnings"][0]


def _write_config(tmp_path: Path) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text("run:\n  output_dir: runs\n", encoding="utf-8")
    return path


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


def _write_outcome_evaluations(run: RunContext, evaluations: list[dict[str, Any]]) -> None:
    artifact = {
        "schema_version": 1,
        "artifact_type": "outcome_evaluations",
        "run_id": run.run_id,
        "created_at": "2026-06-05T00:00:00Z",
        "status": "ok",
        "evaluation_policy": {},
        "evaluations": evaluations,
        "counts": {"evaluations": len(evaluations)},
        "source_artifacts": ["analysis/outcome_targets.json"],
        "warnings": [],
        "errors": [],
    }
    text = json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True)
    (run.analysis_dir / "outcome_evaluations.json").write_text(f"{text}\n", encoding="utf-8")


def _evaluation(target_id: str, *, outcome_state: str = "aligned") -> dict[str, Any]:
    return {
        "outcome_id": f"outcome:{target_id}:run-1",
        "target_id": target_id,
        "target_kind": "market_signal",
        "source_run_id": "source-run",
        "evaluation_run_id": "run-1",
        "evaluated_at": "2026-06-05T00:00:00Z",
        "evaluation_status": "evaluated",
        "outcome_state": outcome_state,
        "observation_window": {
            "source_as_of": "2026-06-04T00:00:00Z",
            "start": "2026-06-05T00:00:00Z",
            "end": "2026-06-05T00:00:00Z",
            "horizon_end": "2026-06-05T00:00:00Z",
            "sample_rows": 1,
            "no_lookahead": True,
            "excluded_at_or_before_source_as_of": True,
        },
        "metrics": {"return_pct": 0.04},
        "evidence": ["Observation rows are strictly after target source_as_of."],
        "source_artifacts": ["analysis/outcome_targets.json", "data/market/metadata/ohlcv_sync_state.json"],
        "warnings": [],
        "errors": [],
    }


def _state(tmp_path: Path) -> dict[str, Any]:
    return json.loads(
        (tmp_path / "data" / "research" / "metadata" / "outcome_history_state.json").read_text(
            encoding="utf-8"
        )
    )


def _history_records(tmp_path: Path) -> list[dict[str, Any]]:
    history = json.loads(
        (tmp_path / "data" / "research" / "outcomes" / "outcome_history.json").read_text(
            encoding="utf-8"
        )
    )
    return history["records"]
