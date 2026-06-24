from __future__ import annotations

import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from halpha.cli import main
from halpha.config import load_config
from halpha.pipeline import PipelineError, STAGE_ORDER, run_pipeline, run_pipeline_stage
from halpha.pipeline_stages import StageSelectionError, stages_after, validate_optional_stage, validate_stage


@pytest.fixture(autouse=True)
def _isolate_artifact_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


def test_pipeline_records_failed_stage_without_fake_artifacts(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    result = run_pipeline(
        config,
        config_path=config_path,
        stage_handlers={"collect_market_data": _failed_market_stage},
    )

    assert result.succeeded is False
    assert result.exit_code == 3
    assert result.failed_stage == "collect_market_data"
    assert result.run.raw_dir.is_dir()
    assert result.run.analysis_dir.is_dir()
    assert result.run.codex_context_dir.is_dir()
    assert result.run.report_dir.is_dir()
    assert not (result.run.raw_dir / "market.json").exists()
    assert not (result.run.analysis_dir / "market_material.md").exists()
    assert not (result.run.report_dir / "report.md").exists()

    manifest = json.loads(result.run.manifest_path.read_text(encoding="utf-8"))
    assert manifest["status"] == "failed"
    assert manifest["stage_order"] == list(STAGE_ORDER)
    assert manifest["codex"] == {
        "enabled": True,
        "command": "codex",
        "status": "not_started",
        "exit_code": None,
    }
    assert manifest["stages"][0]["name"] == "collect_market_data"
    assert manifest["stages"][0]["status"] == "failed"
    assert manifest["stages"][0]["started_at"].endswith("Z")
    assert manifest["stages"][0]["finished_at"].endswith("Z")
    assert manifest["stages"][0]["artifacts"] == []
    expected_error = {
        "stage": "collect_market_data",
        "message": "stage collect_market_data is not implemented",
    }
    assert manifest["stages"][0]["error"] == expected_error
    assert manifest["errors"] == [expected_error]
    _assert_manifest_timeline(manifest)


def test_pipeline_stage_registry_selection_helpers_match_stage_order() -> None:
    assert stages_after("build_research_context") == [
        "build_codex_context",
        "run_codex_report",
        "validate_product_contracts",
    ]

    validate_optional_stage(None, option_name="--until")
    validate_stage("collect_market_data", option_name="stage")

    with pytest.raises(StageSelectionError, match="--until must be one of:"):
        validate_optional_stage("missing_stage", option_name="--until")


def test_pipeline_records_successful_stage_lifecycle_before_later_failure(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    def collect_market_data(config, run) -> list[str]:
        artifact = run.raw_dir / "market.json"
        artifact.write_text("{}", encoding="utf-8")
        return ["raw/market.json"]

    result = run_pipeline(
        config,
        config_path=config_path,
        stage_handlers={
            "collect_market_data": collect_market_data,
            "collect_text_events": _failed_text_stage,
        },
    )

    assert result.succeeded is False
    manifest = json.loads(result.run.manifest_path.read_text(encoding="utf-8"))
    assert manifest["stages"][0]["name"] == "collect_market_data"
    assert manifest["stages"][0]["status"] == "succeeded"
    assert manifest["stages"][0]["started_at"].endswith("Z")
    assert manifest["stages"][0]["finished_at"].endswith("Z")
    assert manifest["stages"][0]["artifacts"] == ["raw/market.json"]
    assert "error" not in manifest["stages"][0]
    assert manifest["stages"][1]["name"] == "collect_derivatives_market_data"
    assert manifest["stages"][1]["status"] == "succeeded"
    assert manifest["stages"][1]["artifacts"] == []
    assert manifest["stages"][2]["name"] == "sync_derivatives_market_history"
    assert manifest["stages"][2]["status"] == "succeeded"
    assert manifest["stages"][2]["artifacts"] == []
    assert manifest["stages"][3]["name"] == "build_derivatives_market_views"
    assert manifest["stages"][3]["status"] == "succeeded"
    assert manifest["stages"][3]["artifacts"] == []
    assert manifest["stages"][4]["name"] == "build_derivatives_market_context"
    assert manifest["stages"][4]["status"] == "succeeded"
    assert manifest["stages"][4]["artifacts"] == []
    assert manifest["stages"][5]["name"] == "collect_macro_calendar_data"
    assert manifest["stages"][5]["status"] == "succeeded"
    assert manifest["stages"][5]["artifacts"] == []
    assert manifest["stages"][6]["name"] == "sync_macro_calendar_history"
    assert manifest["stages"][6]["status"] == "succeeded"
    assert manifest["stages"][6]["artifacts"] == []
    assert manifest["stages"][7]["name"] == "build_macro_calendar_views"
    assert manifest["stages"][7]["status"] == "succeeded"
    assert manifest["stages"][7]["artifacts"] == []
    assert manifest["stages"][8]["name"] == "build_macro_calendar_context"
    assert manifest["stages"][8]["status"] == "succeeded"
    assert manifest["stages"][8]["artifacts"] == []
    assert manifest["stages"][9]["name"] == "build_macro_calendar_material"
    assert manifest["stages"][9]["status"] == "succeeded"
    assert manifest["stages"][9]["artifacts"] == []
    assert manifest["stages"][10]["name"] == "collect_onchain_flow_data"
    assert manifest["stages"][10]["status"] == "succeeded"
    assert manifest["stages"][10]["artifacts"] == []
    assert manifest["stages"][11]["name"] == "sync_onchain_flow_history"
    assert manifest["stages"][11]["status"] == "succeeded"
    assert manifest["stages"][11]["artifacts"] == []
    assert manifest["stages"][12]["name"] == "build_onchain_flow_views"
    assert manifest["stages"][12]["status"] == "succeeded"
    assert manifest["stages"][12]["artifacts"] == []
    assert manifest["stages"][13]["name"] == "build_onchain_flow_context"
    assert manifest["stages"][13]["status"] == "succeeded"
    assert manifest["stages"][13]["artifacts"] == []
    assert manifest["stages"][14]["name"] == "build_onchain_flow_material"
    assert manifest["stages"][14]["status"] == "succeeded"
    assert manifest["stages"][14]["artifacts"] == []
    assert manifest["stages"][15]["name"] == "collect_text_events"
    assert manifest["stages"][15]["status"] == "failed"
    assert manifest["stages"][15]["started_at"].endswith("Z")
    assert manifest["stages"][15]["finished_at"].endswith("Z")
    assert manifest["stages"][15]["artifacts"] == []
    assert manifest["stages"][15]["error"] == {
        "stage": "collect_text_events",
        "message": "stage collect_text_events is not implemented",
    }
    assert manifest["errors"] == [manifest["stages"][15]["error"]]
    assert not (result.run.raw_dir / "text_events.json").exists()
    assert not (result.run.report_dir / "report.md").exists()
    _assert_manifest_timeline(manifest)


def test_pipeline_records_finished_at_after_stage_handler_returns(tmp_path: Path, monkeypatch) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    current = [datetime(2026, 6, 5, 0, 0, tzinfo=timezone.utc)]

    def fake_clock(now):
        return lambda: current[0]

    def collect_market_data(config, run) -> list[str]:
        current[0] = current[0] + timedelta(minutes=5)
        return []

    monkeypatch.setattr("halpha.pipeline._clock", fake_clock)

    result = run_pipeline(
        config,
        config_path=config_path,
        until_stage="collect_market_data",
        stage_handlers={"collect_market_data": collect_market_data},
    )

    assert result.succeeded is True
    manifest = json.loads(result.run.manifest_path.read_text(encoding="utf-8"))
    assert manifest["stages"][0]["started_at"] == "2026-06-05T00:00:00Z"
    assert manifest["stages"][0]["finished_at"] == "2026-06-05T00:05:00Z"
    assert manifest["finished_at"] == "2026-06-05T00:05:00Z"


def test_pipeline_records_finished_at_after_stage_handler_failure(tmp_path: Path, monkeypatch) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    current = [datetime(2026, 6, 5, 0, 0, tzinfo=timezone.utc)]

    def fake_clock(now):
        return lambda: current[0]

    def collect_market_data(config, run) -> None:
        current[0] = current[0] + timedelta(minutes=3)
        raise PipelineError("stage collect_market_data failed", stage="collect_market_data", exit_code=3)

    monkeypatch.setattr("halpha.pipeline._clock", fake_clock)

    result = run_pipeline(
        config,
        config_path=config_path,
        stage_handlers={"collect_market_data": collect_market_data},
    )

    assert result.succeeded is False
    manifest = json.loads(result.run.manifest_path.read_text(encoding="utf-8"))
    assert manifest["stages"][0]["started_at"] == "2026-06-05T00:00:00Z"
    assert manifest["stages"][0]["finished_at"] == "2026-06-05T00:03:00Z"
    assert manifest["finished_at"] == "2026-06-05T00:03:00Z"
    _assert_manifest_timeline(manifest)


def test_pipeline_unexpected_exception_diagnostic_redacts_private_values(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    secret = "http://private-proxy.example:7890"
    config.setdefault("market", {})["proxy"] = {"url": secret}

    def collect_market_data(config, run) -> None:
        raise RuntimeError(f"{secret} failed in {config_path}")

    result = run_pipeline(
        config,
        config_path=config_path,
        stage_handlers={"collect_market_data": collect_market_data},
    )

    assert result.succeeded is False
    manifest_text = result.run.manifest_path.read_text(encoding="utf-8")
    manifest = json.loads(manifest_text)
    error = manifest["stages"][0]["error"]
    assert error["diagnostic"] == {"exception_type": "RuntimeError", "traceback_embedded": False}
    assert manifest["config_path"] == "config.yaml"
    assert "<redacted>" in error["message"]
    assert secret not in manifest_text
    assert str(config_path) not in manifest_text
    assert str(tmp_path) not in manifest_text


def test_stage_rerun_records_finished_at_after_handler_returns(tmp_path: Path, monkeypatch) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    initial = run_pipeline(
        config,
        config_path=config_path,
        until_stage="collect_market_data",
        stage_handlers={"collect_market_data": lambda config, run: []},
        now=datetime(2026, 6, 5, 0, 0, tzinfo=timezone.utc),
    )
    parent_manifest = initial.run.manifest_path.read_text(encoding="utf-8")
    current = [datetime(2026, 6, 5, 1, 0, tzinfo=timezone.utc)]

    def fake_clock(now):
        return lambda: current[0]

    def collect_market_data(config, run) -> list[str]:
        current[0] = current[0] + timedelta(minutes=7)
        return []

    monkeypatch.setattr("halpha.pipeline._clock", fake_clock)

    result = run_pipeline_stage(
        config,
        config_path=config_path,
        run_dir=initial.run.run_dir,
        stage="collect_market_data",
        stage_handlers={"collect_market_data": collect_market_data},
    )

    assert result.succeeded is True
    assert result.run.run_dir != initial.run.run_dir
    assert initial.run.manifest_path.read_text(encoding="utf-8") == parent_manifest
    manifest = json.loads(result.run.manifest_path.read_text(encoding="utf-8"))
    rerun_stage = manifest["stages"][0]
    assert rerun_stage["name"] == "collect_market_data"
    assert rerun_stage["mode"] == "recomputed"
    assert rerun_stage["started_at"] == "2026-06-05T01:00:00Z"
    assert rerun_stage["finished_at"] == "2026-06-05T01:07:00Z"
    assert manifest["parent_run_id"] == initial.run.run_id
    assert manifest["stage_rerun"]["downstream_closure"] == ["collect_market_data"]
    assert manifest["finished_at"] == "2026-06-05T01:07:00Z"


def test_stage_rerun_creates_derived_run_and_reuses_only_upstream_artifacts(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    parent_handlers = _noop_handlers(
        {
            "collect_market_data": _write_raw_artifact("market.json", "parent market", "market"),
            "collect_text_events": _write_raw_artifact("text_events.json", "parent text", "text_events"),
        }
    )
    parent = run_pipeline(
        config,
        config_path=config_path,
        until_stage="collect_text_events",
        stage_handlers=parent_handlers,
        now=datetime(2026, 6, 5, 0, 0, tzinfo=timezone.utc),
    )
    parent_manifest = parent.run.manifest_path.read_text(encoding="utf-8")

    child = run_pipeline_stage(
        config,
        config_path=config_path,
        run_dir=parent.run.run_dir,
        stage="collect_text_events",
        stage_handlers=_noop_handlers(
            {"collect_text_events": _write_raw_artifact("text_events.json", "child text", "text_events")}
        ),
        now=datetime(2026, 6, 5, 1, 0, tzinfo=timezone.utc),
    )

    assert child.succeeded is True
    assert child.run.run_dir != parent.run.run_dir
    assert parent.run.manifest_path.read_text(encoding="utf-8") == parent_manifest
    assert (parent.run.raw_dir / "text_events.json").read_text(encoding="utf-8") == "parent text"
    assert (child.run.raw_dir / "market.json").read_text(encoding="utf-8") == "parent market"
    assert (child.run.raw_dir / "text_events.json").read_text(encoding="utf-8") == "child text"

    manifest = _manifest(child.run.run_dir)
    assert manifest["parent_run_id"] == parent.run.run_id
    assert manifest["lineage"]["parent_run_id"] == parent.run.run_id
    assert manifest["stage_rerun"]["requested_operation_id"] == "collect_text_events"
    assert manifest["stage_rerun"]["downstream_closure"] == ["collect_text_events"]
    assert manifest["stage_rerun"]["reused_artifacts"] == ["raw/market.json"]
    assert _stage(manifest, "collect_market_data")["mode"] == "reused"
    assert _stage(manifest, "collect_text_events")["mode"] == "recomputed"


def test_stage_rerun_preserves_no_codex_parent_skip(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    parent = run_pipeline(
        config,
        config_path=config_path,
        skip_codex=True,
        stage_handlers=_noop_handlers(),
    )

    def fail_if_codex_runs(config, run):
        raise AssertionError("Codex should remain skipped for a no-Codex parent rerun.")

    result = run_pipeline_stage(
        config,
        config_path=config_path,
        run_dir=parent.run.run_dir,
        stage="build_codex_context",
        stage_handlers=_noop_handlers({"run_codex_report": fail_if_codex_runs}),
    )

    assert result.succeeded is True
    manifest = _manifest(result.run.run_dir)
    assert manifest["validation"] == {
        "mode": "stage_rerun",
        "until_stage": None,
        "skip_codex": True,
    }
    assert _stage(manifest, "run_codex_report")["status"] == "skipped"
    assert manifest["codex"]["status"] == "skipped"
    assert manifest["codex"]["skip_reason"] == "--no-codex requested"


def test_failed_run_resumes_in_place_from_failed_operation(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    failed = run_pipeline(
        config,
        config_path=config_path,
        stage_handlers=_noop_handlers({"collect_text_events": _failed_text_stage}),
    )

    result = run_pipeline_stage(
        config,
        config_path=config_path,
        run_dir=failed.run.run_dir,
        stage="collect_text_events",
        stage_handlers=_noop_handlers(
            {"collect_text_events": _write_raw_artifact("text_events.json", "ok", "text_events")}
        ),
    )

    assert result.succeeded is True
    assert result.run.run_dir == failed.run.run_dir
    manifest = _manifest(result.run.run_dir)
    assert manifest["errors"] == []
    assert _stage(manifest, "collect_text_events")["mode"] == "resume"
    assert _stage(manifest, "collect_text_events")["status"] == "succeeded"
    assert all(stage["status"] != "failed" for stage in manifest["stages"])


def test_failed_run_resume_drops_partial_failed_stage_outputs(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    def fail_after_partial_text_artifact(config, run) -> None:
        artifact = run.raw_dir / "text_events.json"
        artifact.write_text("stale", encoding="utf-8")
        run.manifest["artifacts"]["raw_text_events"] = "raw/text_events.json"
        raise PipelineError("text stage failed", stage="collect_text_events", exit_code=3)

    failed = run_pipeline(
        config,
        config_path=config_path,
        stage_handlers=_noop_handlers({"collect_text_events": fail_after_partial_text_artifact}),
    )

    result = run_pipeline_stage(
        config,
        config_path=config_path,
        run_dir=failed.run.run_dir,
        stage="collect_text_events",
        stage_handlers=_noop_handlers({"collect_text_events": _noop_stage}),
    )

    assert result.succeeded is True
    manifest = _manifest(result.run.run_dir)
    assert "raw_text_events" not in manifest["artifacts"]
    assert not (result.run.raw_dir / "text_events.json").exists()


def test_stage_rerun_rejects_missing_upstream_artifact(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    parent = run_pipeline(
        config,
        config_path=config_path,
        until_stage="collect_text_events",
        stage_handlers=_noop_handlers(
            {
                "collect_market_data": _write_raw_artifact("market.json", "parent market", "market"),
                "collect_text_events": _write_raw_artifact("text_events.json", "parent text", "text_events"),
            }
        ),
    )
    (parent.run.raw_dir / "market.json").unlink()

    with pytest.raises(PipelineError, match="reusable upstream artifact raw/market.json"):
        run_pipeline_stage(
            config,
            config_path=config_path,
            run_dir=parent.run.run_dir,
            stage="collect_text_events",
            stage_handlers=_noop_handlers(),
        )


def test_pipeline_uses_utc_run_id_and_does_not_overwrite_existing_run_dir(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    now = datetime(2026, 6, 5, 8, 30, tzinfo=timezone(timedelta(hours=8)))

    stage_handlers = {"collect_market_data": _failed_market_stage}
    first = run_pipeline(config, config_path=config_path, stage_handlers=stage_handlers, now=now)
    second = run_pipeline(config, config_path=config_path, stage_handlers=stage_handlers, now=now)

    assert first.run.run_id == "20260605T003000Z"
    assert second.run.run_id == "20260605T003000Z-01"
    assert first.run.run_dir != second.run.run_dir
    assert first.run.manifest_path.exists()
    assert second.run.manifest_path.exists()
    manifest = json.loads(first.run.manifest_path.read_text(encoding="utf-8"))
    assert manifest["started_at"] == "2026-06-05T00:30:00Z"
    assert manifest["stages"][0]["started_at"] == "2026-06-05T00:30:00Z"
    assert manifest["stages"][0]["finished_at"] == "2026-06-05T00:30:00Z"
    assert manifest["finished_at"] == "2026-06-05T00:30:00Z"
    _assert_manifest_timeline(manifest)


def test_pipeline_uses_cwd_artifact_root_for_subdirectory_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    config_dir = tmp_path / "configs"
    config_dir.mkdir()
    config_path = Path("configs/local.yaml")
    (tmp_path / config_path).write_text(
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
""".strip(),
        encoding="utf-8",
    )
    config = load_config(config_path)

    result = run_pipeline(
        config,
        config_path=config_path,
        until_stage="collect_market_data",
        now=datetime(2026, 6, 20, tzinfo=timezone.utc),
        stage_handlers={"collect_market_data": lambda config, run: []},
    )

    assert result.succeeded is True
    assert result.run.run_dir.parent == tmp_path / "runs"
    assert not (config_dir / "runs").exists()


def test_cli_run_reports_report_manifest_and_zero_exit(tmp_path: Path, capsys, monkeypatch) -> None:
    config_path = _write_config(tmp_path)
    monkeypatch.setattr("halpha.collectors.market.urlopen", _fake_urlopen)
    monkeypatch.setattr("halpha.collectors.text.urlopen", _fake_rss_urlopen)
    monkeypatch.setattr("halpha.codex.runner.subprocess.run", _fake_codex_run)

    exit_code = main(["run", "--config", str(config_path)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Halpha run succeeded." in captured.out
    assert "report:" in captured.out
    assert "manifest:" in captured.out

    report_paths = sorted(tmp_path.glob("runs/*/report/report.md"))
    assert len(report_paths) == 1
    assert "## 风险提示" in report_paths[0].read_text(encoding="utf-8")


def test_cli_run_returns_codex_failure_exit_code(tmp_path: Path, capsys, monkeypatch) -> None:
    config_path = _write_config(tmp_path)
    monkeypatch.setattr("halpha.collectors.market.urlopen", _fake_urlopen)
    monkeypatch.setattr("halpha.collectors.text.urlopen", _fake_rss_urlopen)
    monkeypatch.setattr("halpha.codex.runner.subprocess.run", _fake_codex_failure_run)

    exit_code = main(["run", "--config", str(config_path)])

    captured = capsys.readouterr()
    assert exit_code == 17
    assert "Halpha run failed." in captured.out
    assert "stage: run_codex_report" in captured.out
    assert "reason: Codex command failed with exit code 17." in captured.out
    assert "manifest:" in captured.out
    assert not list(tmp_path.glob("runs/*/report/report.md"))


def test_cli_run_no_codex_skips_report_without_fake_report(tmp_path: Path, capsys, monkeypatch) -> None:
    config_path = _write_config(tmp_path)
    monkeypatch.setattr("halpha.collectors.market.urlopen", _fake_urlopen)
    monkeypatch.setattr("halpha.collectors.text.urlopen", _fake_rss_urlopen)

    def fail_if_codex_runs(*args, **kwargs):
        raise AssertionError("Codex should not run in --no-codex mode.")

    monkeypatch.setattr("halpha.codex.runner.subprocess.run", fail_if_codex_runs)

    exit_code = main(["run", "--config", str(config_path), "--no-codex"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Halpha run succeeded." in captured.out
    assert "codex: skipped" in captured.out
    assert "report:" not in captured.out

    run_dir = _single_run_dir(tmp_path)
    manifest = _manifest(run_dir)
    assert manifest["status"] == "succeeded"
    assert manifest["validation"] == {
        "mode": "run",
        "skip_codex": True,
        "until_stage": None,
    }
    assert manifest["codex"]["status"] == "skipped"
    assert manifest["codex"]["exit_code"] is None
    assert manifest["codex"]["skip_reason"] == "--no-codex requested"
    codex_stage = _stage(manifest, "run_codex_report")
    assert codex_stage["status"] == "skipped"
    assert codex_stage["artifacts"] == []
    assert manifest["stages"][-1]["name"] == "validate_product_contracts"
    assert manifest["stages"][-1]["status"] == "succeeded"
    assert manifest["stages"][-1]["artifacts"] == ["analysis/product_contract_validation.json"]
    assert (run_dir / "codex_context" / "prompt.md").is_file()
    assert (run_dir / "analysis" / "product_contract_validation.json").is_file()
    assert not (run_dir / "report" / "report.md").exists()
    assert "report" not in manifest["artifacts"]


def test_cli_run_until_marks_later_stages_not_run(tmp_path: Path, capsys, monkeypatch) -> None:
    config_path = _write_config(tmp_path)
    monkeypatch.setattr("halpha.collectors.market.urlopen", _fake_urlopen)
    monkeypatch.setattr("halpha.collectors.text.urlopen", _fake_rss_urlopen)

    def fail_if_codex_runs(*args, **kwargs):
        raise AssertionError("Codex should not run after --until build_research_context.")

    monkeypatch.setattr("halpha.codex.runner.subprocess.run", fail_if_codex_runs)

    exit_code = main(["run", "--config", str(config_path), "--until", "build_research_context"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Halpha run succeeded." in captured.out
    assert "report:" not in captured.out

    run_dir = _single_run_dir(tmp_path)
    manifest = _manifest(run_dir)
    assert manifest["validation"] == {
        "mode": "run",
        "skip_codex": False,
        "until_stage": "build_research_context",
    }
    assert _stage(manifest, "build_research_context")["status"] == "succeeded"
    codex_context = _stage(manifest, "build_codex_context")
    codex_report = _stage(manifest, "run_codex_report")
    assert codex_context["status"] == "not_run"
    assert codex_context["reason"] == "--until build_research_context requested"
    assert codex_report["status"] == "not_run"
    assert codex_report["reason"] == "--until build_research_context requested"
    assert manifest["codex"]["status"] == "not_run"
    assert manifest["codex"]["skip_reason"] == "--until build_research_context requested"
    assert (run_dir / "analysis" / "research_context.md").is_file()
    assert not (run_dir / "codex_context" / "prompt.md").exists()
    assert not (run_dir / "report" / "report.md").exists()


def test_cli_stage_creates_derived_run_from_existing_run_dir(tmp_path: Path, capsys, monkeypatch) -> None:
    config_path = _write_config(tmp_path)
    monkeypatch.setattr("halpha.collectors.market.urlopen", _fake_urlopen)
    monkeypatch.setattr("halpha.collectors.text.urlopen", _fake_rss_urlopen)

    assert main(["run", "--config", str(config_path), "--until", "build_analysis_materials"]) == 0
    parent_run_dir = _single_run_dir(tmp_path)
    assert not (parent_run_dir / "analysis" / "research_context.md").exists()
    parent_manifest = (parent_run_dir / "run_manifest.json").read_text(encoding="utf-8")

    exit_code = main(
        [
            "stage",
            "build_research_context",
            "--config",
            str(config_path),
            "--run-dir",
            str(parent_run_dir),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Halpha stage succeeded." in captured.out
    assert "stage: build_research_context" in captured.out
    assert (parent_run_dir / "run_manifest.json").read_text(encoding="utf-8") == parent_manifest
    assert not (parent_run_dir / "analysis" / "research_context.md").exists()

    run_dirs = sorted((tmp_path / "runs").iterdir())
    assert len(run_dirs) == 2
    derived_run_dir = next(path for path in run_dirs if path != parent_run_dir)
    assert (derived_run_dir / "analysis" / "research_context.md").is_file()

    manifest = _manifest(derived_run_dir)
    assert manifest["parent_run_id"] == parent_run_dir.name
    assert manifest["artifacts"]["research_context"] == "analysis/research_context.md"
    assert manifest["stage_rerun"]["requested_operation_id"] == "build_research_context"
    rerun_stage = _stage(manifest, "build_research_context")
    assert rerun_stage["mode"] == "recomputed"
    assert rerun_stage["status"] == "succeeded"
    assert rerun_stage["artifacts"] == ["analysis/research_context.md"]


def test_cli_validation_stage_names_are_actionable_and_do_not_create_runs(
    tmp_path: Path,
    capsys,
) -> None:
    config_path = _write_config(tmp_path)

    run_exit = main(["run", "--config", str(config_path), "--until", "missing_stage"])
    run_output = capsys.readouterr().out
    assert run_exit == 2
    assert "Halpha run failed." in run_output
    assert "stage: cli" in run_output
    assert "--until must be one of:" in run_output
    assert not (tmp_path / "runs").exists()

    run_dir = tmp_path / "existing-run"
    run_dir.mkdir()
    stage_exit = main(
        [
            "stage",
            "missing_stage",
            "--config",
            str(config_path),
            "--run-dir",
            str(run_dir),
        ]
    )
    stage_output = capsys.readouterr().out
    assert stage_exit == 2
    assert "Halpha stage failed." in stage_output
    assert "stage: cli" in stage_output
    assert "stage must be one of:" in stage_output
    assert not (run_dir / "run_manifest.json").exists()


def _write_config(tmp_path: Path) -> Path:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
run:
  output_dir: runs
  timezone: Asia/Shanghai
market:
  enabled: true
  source: binance
  symbols:
    - BTCUSDT
text:
  enabled: true
  max_items: 1
  sources:
    - name: coindesk
      type: rss
      url: https://www.coindesk.com/arc/outboundfeeds/rss/
report:
  title: Daily Market Brief
  language: zh-CN
codex:
  enabled: true
  command: codex
  args:
    - exec
    - --sandbox
    - read-only
    - "-"
  timeout_seconds: 300
""".strip(),
        encoding="utf-8",
    )
    return config_path


def _single_run_dir(tmp_path: Path) -> Path:
    run_dirs = sorted((tmp_path / "runs").iterdir())
    assert len(run_dirs) == 1
    return run_dirs[0]


def _manifest(run_dir: Path) -> dict:
    return json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))


def _stage(manifest: dict, name: str) -> dict:
    return next(stage for stage in manifest["stages"] if stage["name"] == name)


def _noop_handlers(overrides: dict[str, object] | None = None) -> dict[str, object]:
    handlers: dict[str, object] = {stage: _noop_stage for stage in STAGE_ORDER}
    if overrides:
        handlers.update(overrides)
    return handlers


def _noop_stage(config, run) -> list[str]:
    return []


def _write_raw_artifact(name: str, content: str, artifact_key: str):
    def handler(config, run) -> list[str]:
        artifact = run.raw_dir / name
        artifact.write_text(content, encoding="utf-8")
        ref = f"raw/{name}"
        run.manifest["artifacts"][artifact_key] = ref
        return [ref]

    return handler


def _assert_manifest_timeline(manifest: dict) -> None:
    stages = manifest["stages"]
    assert manifest["started_at"] <= stages[0]["started_at"]
    for stage in stages:
        assert stage["started_at"] <= stage["finished_at"]
    assert stages[-1]["finished_at"] <= manifest["finished_at"]


def _failed_market_stage(config, run) -> None:
    raise PipelineError(
        "stage collect_market_data is not implemented",
        stage="collect_market_data",
        exit_code=3,
    )


def _failed_text_stage(config, run) -> None:
    raise PipelineError(
        "stage collect_text_events is not implemented",
        stage="collect_text_events",
        exit_code=3,
    )


def _fake_urlopen(request, timeout):
    return _FakeResponse(
        {
            "symbol": "BTCUSDT",
            "lastPrice": "68000.00",
            "priceChangePercent": "1.25",
            "volume": "123.45",
            "quoteVolume": "8394600.00",
            "closeTime": 1780619400000,
        }
    )


def _fake_rss_urlopen(request, timeout):
    return _FakeBytesResponse(
        b"""<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0">
  <channel>
    <item>
      <title>Market event</title>
      <link>https://example.com/market-event</link>
      <guid>event-1</guid>
      <pubDate>Fri, 05 Jun 2026 00:30:00 GMT</pubDate>
      <description>Source-provided event text.</description>
    </item>
  </channel>
</rss>
"""
    )


def _fake_codex_run(command, input, text, encoding, errors, capture_output, timeout, cwd):
    assert command[1:] == ["exec", "--sandbox", "read-only", "-"]
    assert "Generate a Simplified Chinese Markdown market intelligence report" in input
    assert "Use Chinese section headings only." in input
    assert text is True
    assert encoding == "utf-8"
    assert errors == "replace"
    assert capture_output is True
    assert timeout == 300
    assert cwd.name
    return subprocess.CompletedProcess(
        command,
        0,
        stdout="# 每日市场简报\n\n## 风险提示\n公开来源较少，后续事件可能改变当前观察。\n",
        stderr="",
    )


def _fake_codex_failure_run(command, input, text, encoding, errors, capture_output, timeout, cwd):
    return subprocess.CompletedProcess(
        command,
        17,
        stdout="partial report",
        stderr="Codex failed",
    )


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class _FakeBytesResponse:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def read(self) -> bytes:
        return self.payload
