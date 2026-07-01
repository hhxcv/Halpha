from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from halpha.cli import _require_monitor_startup, main
from halpha.config import load_config
from halpha.monitor.monitoring import run_monitor_cycle
from halpha.runtime.monitor_service import MonitorServiceError


@pytest.fixture(autouse=True)
def _isolate_artifact_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


def test_monitor_help_describes_health_service_without_run_workflow(capsys) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["monitor", "--help"])

    output = capsys.readouterr().out
    assert exc.value.code == 0
    assert "Manage the local Monitor health service." in output
    assert "start" in output
    assert "status" in output
    assert "stop" in output
    assert "restart" in output
    assert "service" in output
    assert "inspect" in output


def test_monitor_inspect_help_does_not_require_state(capsys) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["monitor", "inspect", "--help"])

    output = capsys.readouterr().out
    assert exc.value.code == 0
    assert "Inspect local Monitor health state." in output
    assert "--config" in output


def test_monitor_status_does_not_require_loadable_config(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "broken.yaml"
    config_path.write_text("run: [", encoding="utf-8")

    exit_code = main(["monitor", "status", "--config", str(config_path)])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Halpha monitor status." in output
    assert "status: not_found" in output


def test_monitor_start_rejects_invalid_config(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "broken.yaml"
    config_path.write_text("run: [", encoding="utf-8")

    exit_code = main(["monitor", "start", "--config", str(config_path)])

    output = capsys.readouterr().out
    assert exit_code == 2
    assert "Halpha monitor failed." in output
    assert "stage: config" in output


def test_monitor_service_startup_guard_uses_explicit_error() -> None:
    with pytest.raises(MonitorServiceError, match="monitor startup config was not loaded for start"):
        _require_monitor_startup(None, action="start")


def test_monitor_cycle_uses_default_personalized_stage_and_no_codex(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, monitor_block=None)
    config = load_config(config_path)
    calls: list[dict[str, object]] = []

    def fake_pipeline(config, *, config_path, until_stage, skip_codex, run_trigger=None):  # noqa: ANN001
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
    assert calls == [{"until_stage": "build_materials", "skip_codex": True}]
    assert cycle_manifest["cycle_id"] == "cycle-20260102T030405000000Z"
    assert cycle_manifest["source_artifacts"] == {"alert_decisions": "analysis/alert_decisions.json"}


def test_monitor_run_once_records_pipeline_failure(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    def failed_pipeline(config, *, config_path, until_stage, skip_codex, run_trigger=None):  # noqa: ANN001
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
