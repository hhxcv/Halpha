from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from halpha.analysis.onchain_flow_material import build_onchain_flow_material
from halpha.pipeline import PipelineError, RunContext
from halpha.storage import write_json


def test_onchain_flow_material_bounds_selected_records_and_records_omissions(
    tmp_path: Path,
) -> None:
    run = _run_context(tmp_path)
    _write_context(
        run,
        [
            _record("stablecoin_liquidity", "stablecoin_supply", "high", "succeeded", "sharp_supply", "2026-06-01T00:00:00Z"),
            _record("stablecoin_liquidity", "stablecoin_supply", "medium", "stale", "stale", "2026-06-02T00:00:00Z"),
            _record("stablecoin_liquidity", "stablecoin_supply", "low", "succeeded", "normal", "2026-06-03T00:00:00Z"),
            _record("stablecoin_liquidity", "stablecoin_supply", "low", "succeeded", "normal", "2026-06-04T00:00:00Z"),
            _record("stablecoin_liquidity", "stablecoin_supply", "low", "succeeded", "normal", "2026-06-05T00:00:00Z"),
            _record("chain_activity", "chain_activity", "high", "succeeded", "surging_chain_activity", "2026-06-06T00:00:00Z"),
            _record("network_congestion", "network_congestion", "medium", "succeeded", "elevated_network_congestion", "2026-06-07T00:00:00Z"),
            _record(
                "exchange_flow_source_availability",
                "exchange_flow_availability",
                "medium",
                "unavailable",
                "source_unavailable",
                "2026-06-08T00:00:00Z",
            ),
        ],
    )

    artifacts = build_onchain_flow_material(_config(enabled=True), run)

    material = (run.analysis_dir / "onchain_flow_material.md").read_text(encoding="utf-8")
    manifest = run.manifest
    assert artifacts == ["analysis/onchain_flow_material.md"]
    assert "artifact_type: analysis_onchain_flow_material" in material
    assert "codex_may_generate_onchain_records: false" in material
    assert "codex_may_generate_flow_states: false" in material
    assert "codex_may_generate_address_labels: false" in material
    assert "full_raw_onchain_flow_artifacts_embedded: false" in material
    assert "full_reusable_onchain_flow_history_embedded: false" in material
    assert "full_onchain_flow_context_json_embedded: false" in material
    assert "selected_record_limit_per_section: 4" in material
    assert "omitted_record_count: 1" in material
    assert "PRIVATE_RAW_SENTINEL_SHOULD_NOT_APPEAR" not in material
    assert manifest["artifacts"]["onchain_flow_material"] == "analysis/onchain_flow_material.md"
    assert manifest["counts"]["onchain_flow_material_records"] == 7
    assert manifest["counts"]["onchain_flow_material_omitted_records"] == 1
    assert manifest["onchain_flow_material"]["context_records"] == 8
    assert manifest["onchain_flow_material"]["selected_records"] == 7
    assert manifest["onchain_flow_material"]["omitted_records"] == 1
    assert manifest["onchain_flow_material"]["context_type_counts"]["stablecoin_liquidity"] == 5


def test_onchain_flow_material_disabled_records_zero_counts(tmp_path: Path) -> None:
    run = _run_context(tmp_path)

    artifacts = build_onchain_flow_material(_config(enabled=False), run)

    assert artifacts == []
    assert not (run.analysis_dir / "onchain_flow_material.md").exists()
    assert run.manifest["counts"]["onchain_flow_material_records"] == 0
    assert run.manifest["counts"]["onchain_flow_material_omitted_records"] == 0


def test_onchain_flow_material_fails_when_context_is_missing(tmp_path: Path) -> None:
    run = _run_context(tmp_path)

    with pytest.raises(PipelineError, match="analysis/onchain_flow_context.json was not found"):
        build_onchain_flow_material(_config(enabled=True), run)


def _config(*, enabled: bool) -> dict[str, Any]:
    return {"onchain_flow": {"enabled": enabled}}


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
        manifest={"artifacts": {}, "counts": {}, "stages": [], "codex": {}, "errors": []},
    )


def _write_context(run: RunContext, records: list[dict[str, Any]]) -> None:
    write_json(
        run.analysis_dir / "onchain_flow_context.json",
        {
            "schema_version": 1,
            "artifact_type": "onchain_flow_context",
            "run_id": run.run_id,
            "created_at": "2026-06-19T00:00:00Z",
            "status": "warning",
            "records": records,
            "counts": {"records": len(records)},
            "warnings": ["on-chain source warning"],
            "errors": [],
            "source_artifacts": ["raw/onchain_flow_views.json", "raw/onchain_flow.json"],
        },
    )


def _record(
    context_type: str,
    data_class: str,
    severity: str,
    status: str,
    state: str,
    as_of: str,
) -> dict[str, Any]:
    return {
        "context_id": f"onchain_flow_context:{context_type}:source:{data_class}:all:{as_of}",
        "context_type": context_type,
        "data_class": data_class,
        "source": "public_source",
        "asset": "BTC" if data_class != "stablecoin_supply" else "ALL_STABLECOINS",
        "chain": "bitcoin" if data_class != "stablecoin_supply" else "all",
        "as_of": as_of,
        "status": status,
        "state": state,
        "severity": severity,
        "confidence": "low" if status in {"stale", "unavailable"} else "medium",
        "source_availability": status,
        "metrics": {
            "latest_value": 100.0,
            "change_pct": 0.1,
        },
        "thresholds": {"medium_threshold": 0.05},
        "evidence": [
            {
                "source_artifact": "raw/onchain_flow_views.json",
                "metric": data_class,
                "value": 100.0,
            }
        ],
        "uncertainty": ["on-chain context is not a trading signal."],
        "warnings": [f"{data_class} warning"] if status in {"stale", "unavailable"} else [],
        "errors": [],
        "source_artifacts": ["analysis/onchain_flow_context.json", "raw/onchain_flow_views.json"],
        "raw_payload": json.dumps({"sentinel": "PRIVATE_RAW_SENTINEL_SHOULD_NOT_APPEAR"}),
    }
