from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from halpha.cli import main
from halpha.config import load_config
from halpha.monitor.monitoring import run_monitor_loop
from halpha.monitor.state_store import MonitorStateRepository


@pytest.fixture(autouse=True)
def _isolate_artifact_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


def test_monitor_loop_runs_finite_count_and_writes_health_state(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    pipeline = _pipeline_factory(tmp_path, statuses=["succeeded", "succeeded"])

    result = run_monitor_loop(
        config,
        config_path=config_path,
        max_cycles=2,
        interval_seconds=1,
        now=_time(),
        pipeline_runner=pipeline,
    )

    health_state = _health_state(config_path)
    cycle_manifests = _cycle_manifests(tmp_path)

    assert result.succeeded is True
    assert result.completed_cycles == 2
    assert result.stop_reason == "max_cycles_reached"
    assert len(cycle_manifests) == 2
    assert {manifest["cycle_mode"] for manifest in cycle_manifests} == {"loop"}
    assert {manifest["loop_id"] for manifest in cycle_manifests} == {result.loop_id}
    assert sorted(manifest["cycle_sequence"] for manifest in cycle_manifests) == [1, 2]
    assert health_state["latest_loop"]["loop_id"] == result.loop_id
    assert health_state["latest_loop"]["completed_cycles"] == 2
    assert health_state["cycle_count"] == 2
    assert result.health_state_path == tmp_path / ".halpha" / "state.sqlite"
    assert not (tmp_path / "monitor" / "monitor_health_state.json").exists()


def test_monitor_loop_stops_on_failed_cycle_and_health_records_failure(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    pipeline = _pipeline_factory(tmp_path, statuses=["succeeded", "failed"])

    result = run_monitor_loop(
        config,
        config_path=config_path,
        max_cycles=3,
        interval_seconds=1,
        now=_time(),
        pipeline_runner=pipeline,
    )

    health_state = _health_state(config_path)

    assert result.succeeded is False
    assert result.completed_cycles == 2
    assert result.stop_reason == "cycle_failed"
    assert result.exit_code == 3
    assert health_state["latest_loop"]["status"] == "failed"
    assert health_state["latest_loop"]["stop_reason"] == "cycle_failed"
    assert health_state["failed_cycle_count"] == 1
    assert health_state["latest_cycle_status"] == "failed"
    assert health_state["error_count"] >= 1


def test_monitor_run_rejects_invalid_loop_interval(tmp_path: Path, capsys) -> None:
    config_path = _write_config(tmp_path)

    with pytest.raises(SystemExit) as exc:
        main(
            [
                "monitor",
                "run",
                "--config",
                str(config_path),
                "--max-cycles",
                "2",
                "--interval-seconds",
                "0",
            ]
        )

    assert exc.value.code == 2
    assert "must be a positive integer" in capsys.readouterr().err


def test_monitor_inspect_summarizes_health_without_running_pipeline(
    tmp_path: Path,
    capsys,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    run_monitor_loop(
        config,
        config_path=config_path,
        max_cycles=1,
        interval_seconds=1,
        now=_time(),
        pipeline_runner=_pipeline_factory(tmp_path, statuses=["succeeded"]),
    )

    def fail_monitor_execution(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("monitor inspect must not run monitor cycles")

    monkeypatch.setattr("halpha.cli.run_monitor_cycle", fail_monitor_execution)
    monkeypatch.setattr("halpha.cli.run_monitor_loop", fail_monitor_execution)

    exit_code = main(["monitor", "inspect", "--config", str(config_path)])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Halpha monitor inspection succeeded." in output
    assert "latest_cycle_status: succeeded" in output
    assert "alert_archive_status: succeeded" in output
    assert "alert_records: 1" in output
    assert "alert_emitted: 1" in output
    assert "cooldown_records: 1" in output
    assert "latest_loop_completed_cycles: 1" in output


def test_monitor_inspect_handles_missing_archive_state(tmp_path: Path, capsys) -> None:
    config_path = _write_config(tmp_path)

    exit_code = main(["monitor", "inspect", "--config", str(config_path)])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "latest_cycle_status: missing" in output
    assert "alert_archive_status: missing" in output
    assert "alert_records: 0" in output
    assert "cooldown_records: 0" in output


def test_monitor_inspect_output_omits_private_alert_values(tmp_path: Path, capsys) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    run_monitor_loop(
        config,
        config_path=config_path,
        max_cycles=1,
        interval_seconds=1,
        now=_time(),
        pipeline_runner=_pipeline_factory(
            tmp_path,
            statuses=["succeeded"],
            alert_record=_alert_record(
                {
                    "personalized_constraint_id": "personalized:BTCUSDT:1d:watch",
                    "personalized_state": "watch",
                    "personalized_action": "downgrade",
                    "personalized_evidence": ["PRIVATE_NOTE_SHOULD_NOT_PRINT"],
                }
            ),
        ),
    )

    exit_code = main(["monitor", "inspect", "--config", str(config_path)])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "PRIVATE_NOTE_SHOULD_NOT_PRINT" not in output
    assert "personalized:BTCUSDT:1d:watch" not in output


def _write_config(tmp_path: Path) -> Path:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
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
  interval_seconds: 1
  cooldown_seconds: 3600
""".strip(),
        encoding="utf-8",
    )
    return config_path


def _pipeline_factory(
    tmp_path: Path,
    *,
    statuses: list[str],
    alert_record: dict[str, Any] | None = None,
):
    calls = {"count": 0}

    def pipeline(config, *, config_path, until_stage, skip_codex, run_trigger=None):  # noqa: ANN001
        calls["count"] += 1
        status = statuses[calls["count"] - 1]
        run_id = f"run-{calls['count']}"
        run_dir = tmp_path / "runs" / run_id
        analysis_dir = run_dir / "analysis"
        analysis_dir.mkdir(parents=True, exist_ok=True)
        if status == "succeeded":
            (analysis_dir / "alert_decisions.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "artifact_type": "alert_decisions",
                        "records": [alert_record or _alert_record()],
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
        return SimpleNamespace(
            succeeded=status == "succeeded",
            exit_code=0 if status == "succeeded" else 3,
            failed_stage=None if status == "succeeded" else "collect_market_data",
            reason=None if status == "succeeded" else "simulated source failure",
            run=SimpleNamespace(
                run_id=run_id,
                run_dir=run_dir,
                manifest_path=run_dir / "run_manifest.json",
                manifest={
                    "status": status,
                    "artifacts": {"alert_decisions": "analysis/alert_decisions.json"}
                    if status == "succeeded"
                    else {},
                    "stages": [],
                },
            ),
        )

    return pipeline


def _alert_record(extra: dict[str, Any] | None = None) -> dict[str, Any]:
    record = {
        "alert_decision_id": "alert_decision:BTCUSDT:1d:assessment-1",
        "status": "active",
        "priority": "P1",
        "scope": {
            "symbol": "BTCUSDT",
            "timeframe": "1d",
            "assessment_id": "assessment-1",
            "topic_ids": ["topic-1"],
            "event_signal_ids": ["signal-1"],
        },
        "attention_decision": "review_soon",
        "requires_user_attention": True,
        "source_artifacts": ["analysis/alert_decisions.json"],
    }
    if extra:
        record.update(extra)
    return record


def _cycle_manifests(tmp_path: Path) -> list[dict[str, Any]]:
    return [
        _json(path)
        for path in sorted((tmp_path / "monitor" / "cycles").glob("*/monitor_cycle_manifest.json"))
    ]


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _health_state(config_path: Path) -> dict[str, Any]:
    return MonitorStateRepository(config_path=config_path).health_state(monitor_output_dir="monitor", base=config_path.parent)


def _time() -> datetime:
    return datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
