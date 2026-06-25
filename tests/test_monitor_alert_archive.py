from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from halpha.config import load_config
from halpha.monitor.monitoring import run_monitor_cycle
from halpha.monitor.state_store import MonitorStateRepository


@pytest.fixture(autouse=True)
def _isolate_artifact_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


def test_monitor_cycle_emits_first_alert_and_persists_cooldown_state(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, cooldown_seconds=1800)
    config = load_config(config_path)

    result = run_monitor_cycle(
        config,
        config_path=config_path,
        now=_time(0),
        pipeline_runner=_pipeline_with_alerts(tmp_path, "run-1", [_alert_record(priority="P1")]),
    )

    archive_records = _archive_records(config_path)
    cooldown = _cooldown_summary(config_path, now=_time(1))
    cycle_manifest = _json(result.manifest_path)

    assert result.succeeded is True
    assert [record["status"] for record in archive_records] == ["emitted"]
    assert archive_records[0]["priority"] == "P1"
    assert archive_records[0]["decision_id"] == "alert_decision:BTCUSDT:1d:assessment-1"
    assert archive_records[0]["source_artifacts"] == ["analysis/alert_decisions.json"]
    assert archive_records[0]["cooldown_until"] == "2026-01-01T00:30:00Z"
    assert cooldown["fields"]["artifact_type"] == "monitor_alert_cooldown_state"
    assert cooldown["fields"]["record_count"] == 1
    assert cooldown["fields"]["active_record_count"] == 1
    assert _cooldown_summary(config_path, now=_time(31))["fields"]["expired_record_count"] == 1
    assert cycle_manifest["alert_archive"]["status"] == "succeeded"
    assert cycle_manifest["alert_archive"]["archive"] == ".halpha/state.sqlite"
    assert cycle_manifest["alert_archive"]["counts"]["emitted"] == 1
    assert cycle_manifest["alert_archive"]["counts"]["records"] == 1
    assert not (tmp_path / "monitor" / "alert_archive.jsonl").exists()
    assert not (tmp_path / "monitor" / "alert_cooldown_state.json").exists()
    assert not (tmp_path / "monitor" / "alert_archive_state.json").exists()


def test_monitor_cycle_persistence_retry_is_idempotent(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, cooldown_seconds=1800)
    config = load_config(config_path)

    result = run_monitor_cycle(
        config,
        config_path=config_path,
        now=_time(0),
        pipeline_runner=_pipeline_with_alerts(tmp_path, "run-1", [_alert_record(priority="P1")]),
    )
    repository = MonitorStateRepository(config_path=config_path)
    cycle = repository.get_cycle(result.cycle_id)
    assert cycle is not None

    def fail_if_replayed(_cooldown_state):  # noqa: ANN001
        raise AssertionError("retrying a persisted terminal cycle must not rebuild alert archive records")

    summary = repository.persist_cycle_with_archive_builder(
        cycle,
        build_archive=fail_if_replayed,
        updated_at="2026-01-01T00:01:00Z",
    )

    archive = _archive_summary(config_path)
    cooldown = _cooldown_summary(config_path, now=_time(1))
    assert summary["counts"]["records"] == 1
    assert archive["fields"]["counts"]["records"] == 1
    assert archive["fields"]["counts"]["emitted"] == 1
    assert cooldown["fields"]["record_count"] == 1
    assert cooldown["fields"]["active_record_count"] == 1


def test_monitor_cycle_suppresses_duplicate_alert_key_in_same_cycle(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    alert = _alert_record(priority="P1")

    run_monitor_cycle(
        config,
        config_path=config_path,
        now=_time(0),
        pipeline_runner=_pipeline_with_alerts(tmp_path, "run-1", [alert, dict(alert)]),
    )

    archive_records = _archive_records(config_path)

    assert [record["status"] for record in archive_records] == ["suppressed_duplicate", "emitted"]
    assert archive_records[0]["alert_key"] == archive_records[1]["alert_key"]
    assert archive_records[0]["suppression_reasons"] == ["duplicate_alert_key_in_cycle"]


def test_monitor_cycle_suppresses_alert_during_cooldown_across_cycles(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, cooldown_seconds=3600)
    config = load_config(config_path)

    run_monitor_cycle(
        config,
        config_path=config_path,
        now=_time(0),
        pipeline_runner=_pipeline_with_alerts(tmp_path, "run-1", [_alert_record(priority="P1")]),
    )
    run_monitor_cycle(
        config,
        config_path=config_path,
        now=_time(10),
        pipeline_runner=_pipeline_with_alerts(tmp_path, "run-2", [_alert_record(priority="P1")]),
    )

    archive_records = _archive_records(config_path)
    archive = _archive_summary(config_path)

    assert [record["status"] for record in archive_records] == ["suppressed_cooldown", "emitted"]
    assert archive_records[0]["suppression_reasons"] == ["cooldown_active"]
    assert archive_records[0]["cooldown_until"] == "2026-01-01T01:00:00Z"
    assert archive["fields"]["counts"]["suppressed_cooldown"] == 1


def test_monitor_cycle_suppresses_no_alert_records_without_cooldown(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    run_monitor_cycle(
        config,
        config_path=config_path,
        now=_time(0),
        pipeline_runner=_pipeline_with_alerts(tmp_path, "run-1", [_alert_record(priority="no_alert")]),
    )

    archive_records = _archive_records(config_path)
    cooldown = _cooldown_summary(config_path, now=_time(1))

    assert [record["status"] for record in archive_records] == ["suppressed_no_alert"]
    assert archive_records[0]["suppression_reasons"] == ["priority_no_alert"]
    assert cooldown["fields"]["record_count"] == 0


def test_monitor_cycle_archives_degraded_alert_record_as_skipped(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    run_monitor_cycle(
        config,
        config_path=config_path,
        now=_time(0),
        pipeline_runner=_pipeline_with_alerts(
            tmp_path,
            "run-1",
            [
                {
                    "priority": "unknown",
                    "attention_decision": "unknown",
                    "scope": {"symbol": "BTCUSDT"},
                }
            ],
        ),
    )

    archive_records = _archive_records(config_path)

    assert [record["status"] for record in archive_records] == ["skipped"]
    assert archive_records[0]["suppression_reasons"] == [
        "missing_alert_decision_id",
        "missing_priority",
        "missing_attention_decision",
        "missing_timeframe",
    ]


def test_monitor_alert_archive_preserves_personalized_link_without_private_values(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    run_monitor_cycle(
        config,
        config_path=config_path,
        now=_time(0),
        pipeline_runner=_pipeline_with_alerts(
            tmp_path,
            "run-1",
            [
                _alert_record(
                    priority="P1",
                    personalized={
                        "personalized_constraint_id": "personalized:BTCUSDT:1d:watch",
                        "personalized_state": "watch",
                        "personalized_action": "downgrade",
                        "personalized_evidence": ["PRIVATE_NOTE_SHOULD_NOT_APPEAR"],
                        "personalized_uncertainty": ["PRIVATE_HOLDING_SHOULD_NOT_APPEAR"],
                    },
                )
            ],
        ),
    )

    database_text = (tmp_path / ".halpha" / "state.sqlite").read_bytes().decode("latin1", errors="ignore")
    archive_record = _archive_records(config_path)[0]

    assert archive_record["personalized_context_present"] is True
    assert "PRIVATE_NOTE_SHOULD_NOT_APPEAR" not in database_text
    assert "PRIVATE_HOLDING_SHOULD_NOT_APPEAR" not in database_text


def test_alert_summary_returns_latest_bounded_sample_and_latest_metadata(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    repository = MonitorStateRepository(config_path=config_path)
    records = [
        _archive_record(index, cycle_id=f"cycle-{index // 3}", created_at=f"2026-01-01T00:{index:02d}:00Z")
        for index in range(8)
    ]
    records.append(_archive_record(8, cycle_id="cycle-latest-a", created_at="2026-01-01T00:08:00Z"))
    records.append(_archive_record(9, cycle_id="cycle-latest-b", created_at="2026-01-01T00:08:00Z"))
    for cycle_id in sorted({str(record["cycle_id"]) for record in records}):
        repository.save_cycle(_cycle_record(cycle_id), updated_at="2026-01-01T00:10:00Z")

    repository.import_alert_records(records, monitor_output_dir="monitor", updated_at="2026-01-01T00:10:00Z")

    summary = repository.alert_summary(monitor_output_dir="monitor", limit=3)
    fields = summary["fields"]
    sample = fields["sample_records"]

    assert fields["counts"]["records"] == 10
    assert fields["counts"]["emitted"] == 10
    assert fields["sample_truncated"] is True
    assert fields["sample_record_limit"] == 3
    assert fields["sample_order"] == "newest_first"
    assert fields["updated_at"] == "2026-01-01T00:08:00Z"
    assert fields["last_cycle_id"] == "cycle-latest-b"
    assert [record["record_id"] for record in sample] == ["record-9", "record-8", "record-7"]
    assert [record["sample_order"] for record in sample] == [1, 2, 3]
    assert {record["record_id"] for record in sample}.isdisjoint({"record-0", "record-1", "record-2"})

    zero_sample = repository.alert_summary(monitor_output_dir="monitor", limit=0)["fields"]
    assert zero_sample["sample_records"] == []
    assert zero_sample["sample_truncated"] is True
    assert zero_sample["updated_at"] == "2026-01-01T00:08:00Z"
    assert zero_sample["last_cycle_id"] == "cycle-latest-b"


def _write_config(tmp_path: Path, *, cooldown_seconds: int = 3600) -> Path:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        f"""
run:
  output_dir: runs
market:
  enabled: false
text:
  enabled: false
  sources: []
report:
  language: zh-CN
codex:
  enabled: false
monitor:
  output_dir: monitor
  cooldown_seconds: {cooldown_seconds}
""".strip(),
        encoding="utf-8",
    )
    return config_path


def _pipeline_with_alerts(tmp_path: Path, run_id: str, records: list[Any]):
    def pipeline(config, *, config_path, until_stage, skip_codex, run_trigger=None):  # noqa: ANN001
        run_dir = tmp_path / "runs" / run_id
        analysis_dir = run_dir / "analysis"
        analysis_dir.mkdir(parents=True, exist_ok=True)
        (analysis_dir / "alert_decisions.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "artifact_type": "alert_decisions",
                    "records": records,
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        return SimpleNamespace(
            succeeded=True,
            exit_code=0,
            failed_stage=None,
            reason=None,
            run=SimpleNamespace(
                run_id=run_id,
                run_dir=run_dir,
                manifest_path=run_dir / "run_manifest.json",
                manifest={
                    "status": "succeeded",
                    "artifacts": {"alert_decisions": "analysis/alert_decisions.json"},
                    "stages": [],
                },
            ),
        )

    return pipeline


def _alert_record(*, priority: str, personalized: dict[str, Any] | None = None) -> dict[str, Any]:
    attention_decision = "no_alert" if priority == "no_alert" else "review_soon"
    record = {
        "alert_decision_id": "alert_decision:BTCUSDT:1d:assessment-1",
        "status": "suppressed" if priority == "no_alert" else "active",
        "priority": priority,
        "scope": {
            "symbol": "BTCUSDT",
            "timeframe": "1d",
            "assessment_id": "assessment-1",
            "topic_ids": ["topic-1"],
            "event_signal_ids": ["signal-1"],
        },
        "attention_decision": attention_decision,
        "requires_user_attention": priority in {"P0", "P1"},
        "source_artifacts": ["analysis/alert_decisions.json"],
    }
    if personalized:
        record.update(personalized)
    return record


def _archive_record(index: int, *, cycle_id: str, created_at: str) -> dict[str, Any]:
    return {
        "record_id": f"record-{index}",
        "cycle_id": cycle_id,
        "created_at": created_at,
        "status": "emitted",
        "alert_key": f"BTCUSDT:1d:{index}",
        "decision_id": f"decision-{index}",
        "symbol": "BTCUSDT",
        "timeframe": "1d",
        "priority": "P1",
        "attention_decision": "watch",
        "requires_user_attention": True,
        "suppression_reasons": [],
        "source_artifacts": ["analysis/alert_decisions.json"],
    }


def _cycle_record(cycle_id: str) -> dict[str, Any]:
    return {
        "cycle_id": cycle_id,
        "monitor_output_dir": "monitor",
        "cycle_manifest": f"monitor/cycles/{cycle_id}/monitor_cycle_manifest.json",
        "cycle_mode": "once",
        "trigger_source": "cli",
        "status": "succeeded",
        "started_at": "2026-01-01T00:00:00Z",
        "finished_at": "2026-01-01T00:10:00Z",
        "config_ref": "config.yaml",
        "target_stage": "build_materials",
        "no_codex": True,
        "exit_code": 0,
        "run_id": cycle_id.replace("cycle", "run"),
        "run_dir": f"runs/{cycle_id.replace('cycle', 'run')}",
        "run_manifest": f"runs/{cycle_id.replace('cycle', 'run')}/run_manifest.json",
        "alert_archive": {"status": "succeeded", "counts": {"records": 0}},
        "warnings": [],
        "errors": [],
    }


def _archive_records(config_path: Path) -> list[dict[str, Any]]:
    return _archive_summary(config_path, limit=100)["fields"]["sample_records"]


def _archive_summary(config_path: Path, *, limit: int = 100) -> dict[str, Any]:
    return MonitorStateRepository(config_path=config_path).alert_summary(monitor_output_dir="monitor", limit=limit)


def _cooldown_summary(config_path: Path, *, now: datetime) -> dict[str, Any]:
    return MonitorStateRepository(config_path=config_path).cooldown_summary(monitor_output_dir="monitor", now=now)


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _time(minutes: int) -> datetime:
    return datetime(2026, 1, 1, 0, minutes, tzinfo=timezone.utc)
