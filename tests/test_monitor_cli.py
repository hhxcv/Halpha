from __future__ import annotations

from pathlib import Path

import pytest

from halpha.cli import main


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
    assert "monitor cycle execution is not implemented yet" in output


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
