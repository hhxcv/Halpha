from __future__ import annotations

import json
from pathlib import Path

import pytest

from halpha.analysis.derivatives_market_material import build_derivatives_market_material
from halpha.config import load_config
from halpha.pipeline import PipelineError, RunContext, run_pipeline
from halpha.storage import write_json


def test_derivatives_market_material_summarizes_context_without_full_stores(tmp_path: Path) -> None:
    run = _run_context(tmp_path)
    _write_context(run, records=_many_context_records())
    _write_data_quality_summary(run)

    assert build_derivatives_market_material(_derivatives_enabled_config(), run) == [
        "analysis/derivatives_market_material.md"
    ]

    material = (run.analysis_dir / "derivatives_market_material.md").read_text(encoding="utf-8")
    assert "artifact_type: analysis_derivatives_market_material" in material
    assert "## source_policy" in material
    assert "codex_may_generate_derivatives_states: false" in material
    assert "codex_may_generate_risk_levels: false" in material
    assert "full_raw_derivatives_artifacts_embedded: false" in material
    assert "full_reusable_derivatives_history_embedded: false" in material
    assert "full_derivatives_context_json_embedded: false" in material
    assert "## funding_and_leverage" in material
    assert "derivatives_context:funding_pressure:binance_usdm:BTCUSDT:8h:2026-06-18T00:00:00Z:0" in material
    assert "## liquidation_source_availability" in material
    assert "raw_derivatives_market" in material
    assert "omitted_record_count: 2" in material
    assert "FULL_DERIVATIVES_CONTEXT_JSON_SHOULD_NOT_APPEAR" not in material
    assert "CREATE TABLE" not in material

    assert run.manifest["artifacts"]["derivatives_market_material"] == (
        "analysis/derivatives_market_material.md"
    )
    assert run.manifest["counts"]["derivatives_market_material_records"] == 5
    assert run.manifest["counts"]["derivatives_market_material_omitted_records"] == 2
    assert run.manifest["derivatives_market_material"]["context_records"] == 7


def test_derivatives_market_material_skips_when_derivatives_disabled(tmp_path: Path) -> None:
    run = _run_context(tmp_path)

    assert build_derivatives_market_material({"market": {"derivatives": {"enabled": False}}}, run) == []
    assert not (run.analysis_dir / "derivatives_market_material.md").exists()
    assert run.manifest["counts"]["derivatives_market_material_records"] == 0
    assert run.manifest["counts"]["derivatives_market_material_omitted_records"] == 0


def test_derivatives_market_material_requires_context_when_derivatives_enabled(tmp_path: Path) -> None:
    run = _run_context(tmp_path)

    with pytest.raises(PipelineError) as error:
        build_derivatives_market_material(_derivatives_enabled_config(), run)

    assert str(error.value) == (
        "analysis/derivatives_market_context.json was not found; "
        "build_derivatives_market_context must run first."
    )


def test_pipeline_embeds_derivatives_material_in_research_and_codex_context(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    result = run_pipeline(
        config,
        config_path=config_path,
        stage_handlers={
            "collect_market_data": _write_market_raw,
            "collect_derivatives_market_data": _noop_stage,
            "sync_derivatives_market_history": _noop_stage,
            "build_derivatives_market_views": _noop_stage,
            "build_derivatives_market_context": _write_pipeline_context,
            "run_codex_report": _skip_codex_report,
        },
    )

    assert result.succeeded is True
    run_dir = result.run.run_dir
    material = (run_dir / "analysis/derivatives_market_material.md").read_text(encoding="utf-8")
    research_context = (run_dir / "analysis/research_context.md").read_text(encoding="utf-8")
    codex_context = (run_dir / "codex_context/context.md").read_text(encoding="utf-8")
    prompt = (run_dir / "codex_context/prompt.md").read_text(encoding="utf-8")
    manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))

    assert "artifact_type: analysis_derivatives_market_material" in material
    assert "derivatives_market_context: analysis/derivatives_market_context.json" in research_context
    assert "derivatives_market_material: analysis/derivatives_market_material.md" in research_context
    assert '<embed path="analysis/derivatives_market_material.md">' in research_context
    assert "artifact_type: analysis_derivatives_market_material" in research_context
    assert "derivatives_market_material: analysis/derivatives_market_material.md" in codex_context
    assert "artifact_type: analysis_derivatives_market_material" in codex_context
    assert "FULL_DERIVATIVES_CONTEXT_JSON_SHOULD_NOT_APPEAR" not in codex_context
    assert "Derivatives market material rules:" in prompt
    assert "Do not generate or revise derivatives states" in prompt
    assert "Do not calculate funding pressure" in prompt
    assert "confirming, conflicting, no-impact, unavailable, stale, degraded" in prompt
    assert "Do not treat unavailable, stale, degraded, partial, failed, or missing derivatives evidence as low risk" in prompt

    material_records = {
        record["artifact"]: record for record in manifest["codex_input"]["materials"]
    }
    budget = material_records["analysis/derivatives_market_material.md"]
    assert budget["status"] == "included"
    assert budget["chars"] == len(material)
    assert budget["over_budget"] is False
    assert manifest["codex_input"]["policy"]["full_derivatives_context_json_embedded"] is False


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


def _derivatives_enabled_config() -> dict:
    return {
        "market": {
            "enabled": True,
            "derivatives": {
                "enabled": True,
            },
        },
    }


def _write_context(run: RunContext, *, records: list[dict]) -> None:
    write_json(
        run.analysis_dir / "derivatives_market_context.json",
        {
            "schema_version": 1,
            "artifact_type": "derivatives_market_context",
            "run_id": run.run_id,
            "created_at": "2026-06-18T01:00:00Z",
            "status": "warning",
            "records": records,
            "counts": {
                "records": len(records),
                "funding_pressure": sum(1 for record in records if record["context_type"] == "funding_pressure"),
                "open_interest_pressure": 0,
                "premium_basis_state": 0,
                "liquidity_depth_state": 0,
                "liquidation_availability": sum(
                    1 for record in records if record["context_type"] == "liquidation_availability"
                ),
            },
            "warnings": ["derivatives context warning"],
            "errors": [],
            "source_artifacts": [
                "raw/derivatives_market_views.json",
                "raw/derivatives_market.json",
            ],
            "sentinel": "FULL_DERIVATIVES_CONTEXT_JSON_SHOULD_NOT_APPEAR",
        },
    )
    run.manifest["artifacts"]["derivatives_market_context"] = "analysis/derivatives_market_context.json"


def _many_context_records() -> list[dict]:
    records = [
        _context_record(
            context_type="funding_pressure",
            data_class="funding_rate",
            state="extreme_positive_funding",
            severity="high",
            index=index,
        )
        for index in range(6)
    ]
    records.append(
        _context_record(
            context_type="liquidation_availability",
            data_class="liquidation_summary",
            state="unavailable",
            severity="unknown",
            status="unavailable",
            index=6,
        )
    )
    return records


def _context_record(
    *,
    context_type: str,
    data_class: str,
    state: str,
    severity: str,
    index: int,
    status: str = "succeeded",
) -> dict:
    return {
        "context_id": (
            f"derivatives_context:{context_type}:binance_usdm:BTCUSDT:8h:"
            f"2026-06-18T00:00:00Z:{index}"
        ),
        "context_type": context_type,
        "data_class": data_class,
        "source": "binance_usdm",
        "market_type": "usd_m_futures",
        "symbol": "BTCUSDT",
        "period": "8h",
        "as_of": "2026-06-18T00:00:00Z",
        "status": status,
        "state": state,
        "severity": severity,
        "confidence": "medium" if status == "succeeded" else "low",
        "metrics": {
            "latest_funding_rate": 0.0007 + index / 10000,
            "observations": 3,
        },
        "thresholds": {
            "extreme_positive_funding_rate": 0.0005,
        },
        "evidence": [
            {
                "metric": "funding_rate",
                "value": 0.0007,
                "as_of": "2026-06-18T00:00:00Z",
                "source_artifact": "raw/derivatives_market_views.json",
            }
        ],
        "uncertainty": ["source availability is limited."] if status != "succeeded" else [],
        "warnings": ["source warning"] if status != "succeeded" else [],
        "errors": [],
        "source_artifacts": [
            "analysis/derivatives_market_context.json",
            "raw/derivatives_market_views.json",
        ],
    }


def _write_data_quality_summary(run: RunContext) -> None:
    write_json(
        run.analysis_dir / "data_quality_summary.json",
        {
            "schema_version": 1,
            "artifact_type": "data_quality_summary",
            "run_id": run.run_id,
            "created_at": "2026-06-18T01:05:00Z",
            "status": "warning",
            "counts": {"checks": 1, "warning": 1},
            "checks": [
                {
                    "name": "raw_derivatives_market",
                    "scope": "raw",
                    "status": "warning",
                    "summary": "raw derivatives market has source limitations.",
                    "warning_count": 1,
                    "error_count": 0,
                    "source_artifacts": ["raw/derivatives_market.json"],
                    "details": {
                        "warnings": ["derivatives source availability warning."],
                        "errors": [],
                    },
                }
            ],
            "warnings": ["derivatives source availability warning."],
            "errors": [],
            "source_artifacts": [
                "analysis/data_quality_summary.json",
                "raw/derivatives_market.json",
            ],
        },
    )


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
  derivatives:
    enabled: true
    source: binance_usdm
    symbols:
      - BTCUSDT
    data_classes:
      - funding_rate
      - liquidation_summary
    periods:
      - 1h
      - 8h
      - 1d
    lookback:
      1h: 2
      8h: 2
      1d: 2
text:
  enabled: false
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


def _write_market_raw(config, run) -> list[str]:
    write_json(
        run.raw_dir / "market.json",
        {
            "schema_version": 1,
            "artifact_type": "market_raw",
            "collector": "market",
            "collection_method": "public_http",
            "source": {
                "name": "binance",
                "url": "https://data-api.binance.vision",
            },
            "collected_at": "2026-06-18T00:30:00Z",
            "items": [
                {
                    "id": "market:binance:BTCUSDT:2026-06-18T00:30:00Z",
                    "symbol": "BTCUSDT",
                    "as_of": "2026-06-18T00:30:00Z",
                    "metrics": {
                        "price": "68000.00",
                        "change_24h_pct": "1.25",
                        "volume_24h": "123.45",
                        "quote_volume_24h": "8394600.00",
                    },
                    "source": {
                        "name": "binance",
                        "url": "https://data-api.binance.vision",
                    },
                }
            ],
            "errors": [],
        },
    )
    run.manifest["artifacts"]["raw_market"] = "raw/market.json"
    run.manifest["counts"]["market_items"] = 1
    return ["raw/market.json"]


def _write_pipeline_context(config, run) -> list[str]:
    _write_context(
        run,
        records=[
            _context_record(
                context_type="funding_pressure",
                data_class="funding_rate",
                state="extreme_positive_funding",
                severity="high",
                index=0,
            ),
            _context_record(
                context_type="liquidation_availability",
                data_class="liquidation_summary",
                state="unavailable",
                severity="unknown",
                status="unavailable",
                index=1,
            ),
        ],
    )
    return ["analysis/derivatives_market_context.json"]


def _noop_stage(config, run) -> list[str]:
    return []


def _skip_codex_report(config, run) -> list[str]:
    report = "# Daily Market Brief\n\nGenerated test report.\n"
    (run.report_dir / "report.md").write_text(report, encoding="utf-8")
    run.manifest["artifacts"]["report"] = "report/report.md"
    run.manifest["codex"]["status"] = "succeeded"
    run.manifest["codex"]["exit_code"] = 0
    return ["report/report.md"]
