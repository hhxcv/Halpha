from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from halpha.cli import main
from halpha.config import load_config
from halpha.monitor.monitoring import run_monitor_cycle


@pytest.fixture(autouse=True)
def _isolate_artifact_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


def test_monitor_help_mentions_run_and_inspect(capsys) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["monitor", "--help"])

    output = capsys.readouterr().out
    assert exc.value.code == 0
    assert "Manage local monitoring runs." in output
    assert "run" in output
    assert "inspect" in output


def test_monitor_run_help_mentions_dry_run(capsys) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["monitor", "run", "--help"])

    output = capsys.readouterr().out
    assert exc.value.code == 0
    assert "Validate monitor configuration" in output
    assert "--config" in output
    assert "--dry-run" in output
    assert "--once" in output
    assert "--max-cycles" in output
    assert "--interval-seconds" in output


def test_monitor_inspect_help_does_not_require_state(capsys) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["monitor", "inspect", "--help"])

    output = capsys.readouterr().out
    assert exc.value.code == 0
    assert "Inspect local monitor state." in output
    assert "--config" in output


def test_monitor_run_dry_run_uses_defaults_without_running_pipeline(
    tmp_path: Path,
    capsys,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = _write_config(tmp_path, monitor_block=None)

    def fail_pipeline(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("monitor dry-run must not run pipeline stages")

    monkeypatch.setattr("halpha.cli.run_pipeline", fail_pipeline)

    exit_code = main(["monitor", "run", "--config", str(config_path), "--dry-run"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Halpha monitor dry run succeeded." in output
    assert "cycle_execution: not_run" in output
    assert "enabled: false" in output
    assert "interval_seconds: 300" in output
    assert "max_cycles: 1" in output
    assert "cooldown_seconds: 3600" in output
    assert "output_dir: runs/monitor" in output
    assert "target_stage: build_personalized_risk_material" in output
    assert "no_codex: true" in output


def test_monitor_run_dry_run_prints_configured_values(tmp_path: Path, capsys) -> None:
    config_path = _write_config(
        tmp_path,
        monitor_block="""
monitor:
  enabled: true
  interval_seconds: 60
  max_cycles: 2
  cooldown_seconds: 900
  output_dir: local-monitor
  target_stage: build_alert_decision_material
  no_codex: true
""".strip(),
    )

    exit_code = main(["monitor", "run", "--config", str(config_path), "--dry-run"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "enabled: true" in output
    assert "interval_seconds: 60" in output
    assert "max_cycles: 2" in output
    assert "cooldown_seconds: 900" in output
    assert "output_dir: local-monitor" in output
    assert "target_stage: build_alert_decision_material" in output
    assert "no_codex: true" in output


def test_monitor_run_without_dry_run_does_not_execute_pipeline(
    tmp_path: Path,
    capsys,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = _write_config(tmp_path)

    def fail_pipeline(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("monitor skeleton must not run pipeline stages")

    monkeypatch.setattr("halpha.cli.run_pipeline", fail_pipeline)

    exit_code = main(["monitor", "run", "--config", str(config_path)])

    output = capsys.readouterr().out
    assert exit_code == 3
    assert "Halpha monitor run failed." in output
    assert "stage: monitor" in output
    assert "choose --dry-run, --once, or --max-cycles" in output


def test_monitor_run_once_creates_one_product_run_and_cycle_manifest(
    tmp_path: Path,
    capsys,
) -> None:
    config_path = _write_config(
        tmp_path,
        monitor_block="""
monitor:
  enabled: true
  output_dir: monitor
  target_stage: collect_market_data
  no_codex: true
""".strip(),
    )

    exit_code = main(["monitor", "run", "--config", str(config_path), "--once"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Halpha monitor cycle succeeded." in output
    assert "target_stage: collect_market_data" in output
    assert "no_codex: true" in output
    run_dirs = list((tmp_path / "runs").iterdir())
    cycle_manifests = list((tmp_path / "monitor" / "cycles").glob("*/monitor_cycle_manifest.json"))
    assert len(run_dirs) == 1
    assert len(cycle_manifests) == 1

    cycle_manifest = json.loads(cycle_manifests[0].read_text(encoding="utf-8"))
    assert cycle_manifest["artifact_type"] == "monitor_cycle_manifest"
    assert cycle_manifest["cycle_mode"] == "once"
    assert cycle_manifest["trigger_source"] == "cli"
    assert cycle_manifest["status"] == "succeeded"
    assert cycle_manifest["started_at"].endswith("Z")
    assert cycle_manifest["finished_at"].endswith("Z")
    assert cycle_manifest["config_ref"] == "config.yaml"
    assert cycle_manifest["monitor_output_dir"] == "monitor"
    assert cycle_manifest["target_stage"] == "collect_market_data"
    assert cycle_manifest["no_codex"] is True
    assert cycle_manifest["exit_code"] == 0
    assert cycle_manifest["run_id"] == run_dirs[0].name
    assert cycle_manifest["run_dir"] == f"runs/{run_dirs[0].name}"
    assert cycle_manifest["run_manifest"] == f"runs/{run_dirs[0].name}/run_manifest.json"
    assert cycle_manifest["errors"] == []
    assert cycle_manifest["product_run"]["run_id"] == run_dirs[0].name
    assert cycle_manifest["product_run"]["status"] == "succeeded"
    assert cycle_manifest["product_run"]["exit_code"] == 0
    assert cycle_manifest["product_run"]["run_dir"] == f"runs/{run_dirs[0].name}"
    assert cycle_manifest["product_run"]["run_manifest"] == f"runs/{run_dirs[0].name}/run_manifest.json"

    product_manifest = json.loads((run_dirs[0] / "run_manifest.json").read_text(encoding="utf-8"))
    assert product_manifest["stages"][0]["name"] == "collect_market_data"
    assert product_manifest["stages"][0]["status"] == "succeeded"
    assert all(stage["status"] != "running" for stage in product_manifest["stages"])
    codex_stage = next(stage for stage in product_manifest["stages"] if stage["name"] == "run_codex_report")
    assert codex_stage["status"] == "not_run"


def test_monitor_cycle_uses_default_personalized_stage_and_no_codex(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, monitor_block=None)
    config = load_config(config_path)
    calls: list[dict[str, object]] = []

    def fake_pipeline(config, *, config_path, until_stage, skip_codex):  # noqa: ANN001
        calls.append({"until_stage": until_stage, "skip_codex": skip_codex})
        return _pipeline_result(
            tmp_path,
            status="succeeded",
            artifacts={"alert_decisions": "analysis/alert_decisions.json"},
        )

    result = run_monitor_cycle(
        config,
        config_path=config_path,
        now=datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
        pipeline_runner=fake_pipeline,
    )

    cycle_manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert result.succeeded is True
    assert calls == [{"until_stage": "build_personalized_risk_material", "skip_codex": True}]
    assert cycle_manifest["cycle_id"] == "cycle-20260102T030405000000Z"
    assert cycle_manifest["source_artifacts"] == {"alert_decisions": "analysis/alert_decisions.json"}


def test_monitor_run_once_records_pipeline_failure(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    def failed_pipeline(config, *, config_path, until_stage, skip_codex):  # noqa: ANN001
        return _pipeline_result(
            tmp_path,
            status="failed",
            succeeded=False,
            exit_code=3,
            failed_stage="collect_market_data",
            reason="market source unavailable",
        )

    result = run_monitor_cycle(config, config_path=config_path, pipeline_runner=failed_pipeline)

    cycle_manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert result.succeeded is False
    assert result.exit_code == 3
    assert cycle_manifest["status"] == "failed"
    assert cycle_manifest["exit_code"] == 3
    assert cycle_manifest["run_id"] == "run-failed"
    assert cycle_manifest["product_run"]["failed_stage"] == "collect_market_data"
    assert cycle_manifest["errors"] == [
        {"stage": "collect_market_data", "message": "market source unavailable"}
    ]


def test_monitor_run_once_records_invalid_target_stage(tmp_path: Path, capsys) -> None:
    config_path = _write_config(
        tmp_path,
        monitor_block="""
monitor:
  output_dir: monitor
  target_stage: missing_stage
""".strip(),
    )

    exit_code = main(["monitor", "run", "--config", str(config_path), "--once"])

    output = capsys.readouterr().out
    cycle_manifests = list((tmp_path / "monitor" / "cycles").glob("*/monitor_cycle_manifest.json"))
    assert exit_code == 2
    assert "Halpha monitor run failed." in output
    assert "target_stage: missing_stage" in output
    assert len(cycle_manifests) == 1
    cycle_manifest = json.loads(cycle_manifests[0].read_text(encoding="utf-8"))
    assert cycle_manifest["status"] == "failed"
    assert cycle_manifest["exit_code"] == 2
    assert cycle_manifest["run_id"] is None
    assert cycle_manifest["run_dir"] is None
    assert cycle_manifest["run_manifest"] is None
    assert cycle_manifest["product_run"] is None
    assert cycle_manifest["errors"][0]["stage"] == "target_stage"
    assert "--until must be one of:" in cycle_manifest["errors"][0]["message"]


def test_monitor_run_reports_invalid_config(tmp_path: Path, capsys) -> None:
    config_path = _write_config(
        tmp_path,
        monitor_block="""
monitor:
  interval_seconds: 0
""".strip(),
    )

    exit_code = main(["monitor", "run", "--config", str(config_path), "--dry-run"])

    output = capsys.readouterr().out
    assert exit_code == 2
    assert "Halpha monitor run failed." in output
    assert "stage: config" in output
    assert "monitor.interval_seconds must be a positive integer" in output


def _write_config(tmp_path: Path, monitor_block: str | None = "monitor:\n  enabled: false") -> Path:
    monitor_section = f"{monitor_block}\n" if monitor_block else ""
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
{monitor_section}
""".strip(),
        encoding="utf-8",
    )
    return config_path


def _pipeline_result(
    tmp_path: Path,
    *,
    status: str,
    succeeded: bool = True,
    exit_code: int = 0,
    failed_stage: str | None = None,
    reason: str | None = None,
    artifacts: dict[str, str] | None = None,
):
    run_dir = tmp_path / "runs" / f"run-{status}"
    manifest_path = run_dir / "run_manifest.json"
    return SimpleNamespace(
        succeeded=succeeded,
        exit_code=exit_code,
        failed_stage=failed_stage,
        reason=reason,
        run=SimpleNamespace(
            run_id=run_dir.name,
            run_dir=run_dir,
            manifest_path=manifest_path,
            manifest={
                "status": status,
                "artifacts": artifacts or {},
            },
        ),
    )
