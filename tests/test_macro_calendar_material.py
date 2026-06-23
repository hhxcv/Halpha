from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from halpha.analysis.macro_calendar_material import build_macro_calendar_material
from halpha.config import load_config
from halpha.pipeline import PipelineError, RunContext, run_pipeline
from halpha.storage import write_json


REPORT_STDOUT = "\n".join(
    [
        "# \u6bcf\u65e5\u5e02\u573a\u7b80\u62a5",
        "",
        "## \u5e02\u573a\u6982\u89c8",
        "",
        "Codex generated market overview.",
        "",
        "## \u7efc\u5408\u5224\u65ad",
        "",
        "Codex generated synthesis.",
        "",
        "## \u98ce\u9669\u63d0\u793a",
        "",
        "\u6570\u636e\u7a97\u53e3\u8f83\u77ed\uff0c\u9700\u8981\u7ee7\u7eed\u89c2\u5bdf\u516c\u5f00\u4e8b\u4ef6\u548c\u4ef7\u683c\u53d8\u5316\u3002",
        "",
    ]
)


@pytest.fixture(autouse=True)
def _isolate_artifact_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


def test_macro_calendar_material_summarizes_context_without_full_stores(tmp_path: Path) -> None:
    run = _run_context(tmp_path)
    _write_context(run, records=_many_context_records())

    assert build_macro_calendar_material(_macro_enabled_config(), run) == [
        "analysis/macro_calendar_material.md"
    ]

    material = (run.analysis_dir / "macro_calendar_material.md").read_text(encoding="utf-8")
    assert "artifact_type: analysis_macro_calendar_material" in material
    assert "## source_policy" in material
    assert "codex_may_generate_macro_events: false" in material
    assert "codex_may_generate_risk_levels: false" in material
    assert "codex_may_generate_watch_triggers: false" in material
    assert "codex_may_generate_alert_priorities: false" in material
    assert "full_raw_macro_calendar_artifacts_embedded: false" in material
    assert "full_reusable_macro_calendar_history_embedded: false" in material
    assert "full_macro_calendar_context_json_embedded: false" in material
    assert "## scheduled_catalysts" in material
    assert "macro_calendar_context:scheduled_catalyst:federal_reserve_fomc:US:FOMC:2026-07-29T00:00:00Z:0" in material
    assert "## no_event_and_unavailable_sources" in material
    assert "source availability is stale." in material
    assert "omitted_record_count: 2" in material
    assert "scheduled catalyst timing risk" in material
    assert "confirmed realized market impact" in material
    assert "FULL_MACRO_CONTEXT_JSON_SHOULD_NOT_APPEAR" not in material
    assert "CREATE TABLE" not in material

    assert run.manifest["artifacts"]["macro_calendar_material"] == "analysis/macro_calendar_material.md"
    assert run.manifest["counts"]["macro_calendar_material_records"] == 5
    assert run.manifest["counts"]["macro_calendar_material_omitted_records"] == 2
    assert run.manifest["macro_calendar_material"]["context_records"] == 7


def test_macro_calendar_material_skips_when_macro_calendar_disabled(tmp_path: Path) -> None:
    run = _run_context(tmp_path)

    assert build_macro_calendar_material({"macro_calendar": {"enabled": False}}, run) == []
    assert not (run.analysis_dir / "macro_calendar_material.md").exists()
    assert run.manifest["counts"]["macro_calendar_material_records"] == 0
    assert run.manifest["counts"]["macro_calendar_material_omitted_records"] == 0


def test_macro_calendar_material_requires_context_when_enabled(tmp_path: Path) -> None:
    run = _run_context(tmp_path)

    with pytest.raises(PipelineError) as error:
        build_macro_calendar_material(_macro_enabled_config(), run)

    assert str(error.value) == (
        "analysis/macro_calendar_context.json was not found; "
        "build_macro_calendar_context must run first."
    )


def test_pipeline_embeds_macro_calendar_material_in_research_and_codex_context(
    tmp_path: Path,
) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    result = run_pipeline(
        config,
        config_path=config_path,
        stage_handlers={
            "build_macro_calendar_context": _write_pipeline_context,
            "run_codex_report": _skip_codex_report,
        },
    )

    assert result.succeeded is True
    run_dir = result.run.run_dir
    material = (run_dir / "analysis/macro_calendar_material.md").read_text(encoding="utf-8")
    research_context = (run_dir / "analysis/research_context.md").read_text(encoding="utf-8")
    codex_context = (run_dir / "codex_context/context.md").read_text(encoding="utf-8")
    prompt = (run_dir / "codex_context/prompt.md").read_text(encoding="utf-8")
    manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))

    assert "artifact_type: analysis_macro_calendar_material" in material
    assert "macro_calendar_context: analysis/macro_calendar_context.json" in research_context
    assert "macro_calendar_material: analysis/macro_calendar_material.md" in research_context
    assert '<embed path="analysis/macro_calendar_material.md">' in research_context
    assert "artifact_type: analysis_macro_calendar_material" in research_context
    assert "macro_calendar_material: analysis/macro_calendar_material.md" in codex_context
    assert "artifact_type: analysis_macro_calendar_material" in codex_context
    assert "FULL_MACRO_CONTEXT_JSON_SHOULD_NOT_APPEAR" not in codex_context
    assert "Macro calendar material rules:" in prompt
    assert "scheduled catalyst risk from confirmed realized market impact" in prompt
    assert "Do not generate or revise macro/calendar records" in prompt
    assert "Do not forecast economic releases" in prompt
    assert "full_raw_macro_calendar_artifacts_embedded: false" in codex_context
    assert "full_reusable_macro_calendar_history_embedded: false" in codex_context
    assert "full_macro_calendar_context_json_embedded: false" in codex_context

    material_records = {
        record["artifact"]: record for record in manifest["codex_input"]["materials"]
    }
    budget = material_records["analysis/macro_calendar_material.md"]
    assert budget["status"] == "included"
    assert budget["chars"] == len(material)
    assert budget["over_budget"] is False
    assert manifest["codex_input"]["policy"]["full_macro_calendar_context_json_embedded"] is False


def test_codex_runner_injects_macro_calendar_section_after_codex_stdout(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_path = _write_config(tmp_path, macro_enabled=False, codex_command="fake-codex")
    config = load_config(config_path)

    def fake_run(command, input, text, encoding, errors, capture_output, timeout, cwd):
        return subprocess.CompletedProcess(command, 0, stdout=REPORT_STDOUT, stderr="")

    monkeypatch.setattr("halpha.codex.runner.subprocess.run", fake_run)

    result = run_pipeline(
        config,
        config_path=config_path,
        stage_handlers={"build_codex_context": _write_prompt_and_macro_calendar_material},
    )

    assert result.succeeded is True
    report = (result.run.report_dir / "report.md").read_text(encoding="utf-8")
    macro_heading = "## \u5b8f\u89c2\u65e5\u5386\u4e0e\u8c03\u5ea6\u98ce\u9669\u8bc1\u636e"
    synthesis_heading = "## \u7efc\u5408\u5224\u65ad"
    assert macro_heading in report
    assert report.index(macro_heading) < report.index(synthesis_heading)
    assert "analysis/macro_calendar_material.md" in report
    assert "\u8ba1\u5212\u4e2d\u50ac\u5316\u5242" in report
    assert "succeeded/upcoming" in report
    assert "not_evaluated" in report
    assert "\u4e0d\u4ee3\u8868\u5df2\u786e\u8ba4\u7684\u5e02\u573a\u5f71\u54cd" in report
    assert "\u4e0d\u7b49\u4e8e\u9884\u6d4b" in report
    assert "\u98ce\u9669\u7b49\u7ea7" in report
    assert "\u4ea4\u6613\u6307\u4ee4" in report
    assert "\u4ef7\u683c\u9884\u6d4b" in report


def _run_context(tmp_path: Path) -> RunContext:
    run_dir = tmp_path / "runs" / "run-1"
    raw_dir = run_dir / "raw"
    analysis_dir = run_dir / "analysis"
    codex_context_dir = run_dir / "codex_context"
    report_dir = run_dir / "report"
    for directory in (raw_dir, analysis_dir, codex_context_dir, report_dir):
        directory.mkdir(parents=True, exist_ok=True)
    return RunContext(
        run_id="run-1",
        run_dir=run_dir,
        raw_dir=raw_dir,
        analysis_dir=analysis_dir,
        codex_context_dir=codex_context_dir,
        report_dir=report_dir,
        manifest_path=run_dir / "run_manifest.json",
        config_path=tmp_path / "config.yaml",
        manifest={"artifacts": {}, "counts": {}, "errors": []},
    )


def _macro_enabled_config() -> dict:
    return {
        "macro_calendar": {
            "enabled": True,
        },
    }


def _write_config(
    tmp_path: Path,
    *,
    macro_enabled: bool = True,
    codex_command: str = "codex",
) -> Path:
    macro_block = (
        """
macro_calendar:
  enabled: true
  source: federal_reserve_fomc
  data_classes:
    - central_bank_event
  regions:
    - US
  lookback_days: 8
  lookahead_days: 43
"""
        if macro_enabled
        else """
macro_calendar:
  enabled: false
"""
    )
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        f"""
run:
  output_dir: runs
  timezone: Asia/Shanghai
market:
  enabled: false
{macro_block.rstrip()}
text:
  enabled: false
report:
  title: Daily Market Brief
  language: zh-CN
codex:
  enabled: true
  command: {codex_command}
  args:
    - exec
    - "-"
  timeout_seconds: 9
""".strip(),
        encoding="utf-8",
    )
    return config_path


def _write_context(run: RunContext, *, records: list[dict]) -> None:
    write_json(
        run.analysis_dir / "macro_calendar_context.json",
        {
            "schema_version": 1,
            "artifact_type": "macro_calendar_context",
            "run_id": run.run_id,
            "created_at": "2026-06-18T01:00:00Z",
            "status": "warning",
            "records": records,
            "counts": {
                "records": len(records),
                "scheduled_catalyst": sum(
                    1 for record in records if record["context_type"] == "scheduled_catalyst"
                ),
                "recent_catalyst": sum(1 for record in records if record["context_type"] == "recent_catalyst"),
                "no_event_window": sum(1 for record in records if record["context_type"] == "no_event_window"),
                "source_availability": sum(
                    1 for record in records if record["context_type"] == "source_availability"
                ),
            },
            "warnings": ["macro calendar context warning"],
            "errors": [],
            "source_artifacts": [
                "raw/macro_calendar_views.json",
                "raw/macro_calendar.json",
                "data/macro/metadata/macro_calendar_state.json",
            ],
            "sentinel": "FULL_MACRO_CONTEXT_JSON_SHOULD_NOT_APPEAR",
        },
    )
    run.manifest["artifacts"]["macro_calendar_context"] = "analysis/macro_calendar_context.json"


def _many_context_records() -> list[dict]:
    records = [
        _context_record(
            context_type="scheduled_catalyst",
            state="upcoming",
            severity="medium",
            index=index,
            scheduled_at=f"2026-07-{29 + index:02d}T00:00:00Z",
        )
        for index in range(6)
    ]
    records.append(
        _context_record(
            context_type="source_availability",
            state="stale",
            severity="low",
            index=6,
            status="stale",
            scheduled_at=None,
            event_name=None,
        )
    )
    return records


def _context_record(
    *,
    context_type: str,
    state: str,
    severity: str,
    index: int,
    status: str = "succeeded",
    scheduled_at: str | None = "2026-07-29T00:00:00Z",
    event_name: str | None = "Federal Open Market Committee meeting",
) -> dict:
    context_event = "FOMC" if event_name else "central_bank_event"
    context_time = scheduled_at or "missing"
    return {
        "context_id": (
            f"macro_calendar_context:{context_type}:federal_reserve_fomc:US:"
            f"{context_event}:{context_time}:{index}"
        ),
        "context_type": context_type,
        "data_class": "central_bank_event",
        "source": "federal_reserve_fomc",
        "event_name": event_name,
        "event_type": "fomc_meeting" if event_name else None,
        "region": "US",
        "scheduled_at": scheduled_at,
        "as_of": "2026-06-18T01:00:00Z",
        "status": status,
        "state": state,
        "severity": severity,
        "confidence": "medium" if status == "succeeded" else "low",
        "time_to_event_hours": 983.0 + index if scheduled_at else None,
        "affected_assets": ["BTCUSDT"],
        "importance": "high" if event_name else None,
        "source_availability": status,
        "realized_impact": {
            "status": "not_evaluated",
            "reason": "macro calendar context records scheduled timing only.",
        },
        "evidence": [
            {
                "source_artifact": "raw/macro_calendar_views.json",
                "evidence_type": context_type,
                "event_name": event_name,
                "scheduled_at": scheduled_at,
                "storage_ref": "data/macro/calendar/source=federal_reserve_fomc",
            }
        ],
        "uncertainty": ["source availability is stale."] if status == "stale" else [],
        "warnings": ["macro calendar source availability is stale: stale"] if status == "stale" else [],
        "errors": [],
        "source_artifacts": [
            "analysis/macro_calendar_context.json",
            "raw/macro_calendar_views.json",
        ],
    }


def _write_pipeline_context(config, run) -> list[str]:
    _write_context(
        run,
        records=[
            _context_record(
                context_type="scheduled_catalyst",
                state="upcoming",
                severity="medium",
                index=0,
            ),
            _context_record(
                context_type="source_availability",
                state="stale",
                severity="low",
                index=1,
                status="stale",
                scheduled_at=None,
                event_name=None,
            ),
        ],
    )
    return ["analysis/macro_calendar_context.json"]


def _write_prompt_and_macro_calendar_material(config, run) -> list[str]:
    run.codex_context_dir.joinpath("prompt.md").write_text("prompt", encoding="utf-8")
    _write_pipeline_context(config, run)
    run.analysis_dir.joinpath("macro_calendar_material.md").write_text(
        "# macro_calendar_material\n",
        encoding="utf-8",
    )
    run.manifest["artifacts"]["codex_prompt"] = "codex_context/prompt.md"
    run.manifest["artifacts"]["macro_calendar_material"] = "analysis/macro_calendar_material.md"
    return ["codex_context/prompt.md"]


def _skip_codex_report(config, run) -> list[str]:
    report = "# Daily Market Brief\n\nGenerated test report.\n"
    (run.report_dir / "report.md").write_text(report, encoding="utf-8")
    run.manifest["artifacts"]["report"] = "report/report.md"
    run.manifest["codex"]["status"] = "succeeded"
    run.manifest["codex"]["exit_code"] = 0
    return ["report/report.md"]
