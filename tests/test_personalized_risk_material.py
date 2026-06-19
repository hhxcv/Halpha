import json
from pathlib import Path

from halpha.analysis.personalized_risk_material import build_personalized_risk_material
from halpha.pipeline import RunContext


def test_personalized_risk_material_bounds_records_and_privacy_fields(tmp_path: Path) -> None:
    run = _run_context(tmp_path)
    _write_user_state(run)
    _write_constraints(
        run,
        [
            _constraint(
                "disabled",
                "BTCUSDT",
                "1d",
                state="disabled_asset_blocked",
                action="block",
                reason_codes=["disabled_asset"],
                matched_user_state={"disabled_asset": True},
            ),
            _constraint(
                "risk",
                "ETHUSDT",
                "1d",
                state="risk_limit_downgraded",
                action="downgrade",
                reason_codes=["risk_action_cap"],
                evidence=["risk.max_action_level=WATCH caps stronger upstream action levels."],
            ),
        ],
    )

    assert build_personalized_risk_material({}, run) == ["analysis/personalized_risk_material.md"]

    material = (run.analysis_dir / "personalized_risk_material.md").read_text(encoding="utf-8")
    assert "artifact_type: analysis_personalized_risk_material" in material
    assert "full_user_state_file_embedded: false" in material
    assert "private_notes_embedded: false" in material
    assert "machine_paths_embedded: false" in material
    assert "account_identifiers_embedded: false" in material
    assert "holdings_values_embedded: false" in material
    assert "full_user_state_context_json_embedded: false" in material
    assert "full_personalized_risk_constraints_json_embedded: false" in material
    assert "codex_may_generate_user_state: false" in material
    assert "codex_may_generate_action_levels: false" in material
    assert "do_not_infer_hidden_user_state: true" in material
    assert "constraint_id: personalized:disabled" in material
    assert "constraint_id: personalized:risk" in material
    assert "omitted_private_values: 1" in material
    assert "C:\\Users\\private\\user_state.yaml" not in material
    assert "local secret note" not in material
    assert "manual_exposure_notes" not in material

    assert run.manifest["artifacts"]["personalized_risk_material"] == (
        "analysis/personalized_risk_material.md"
    )
    assert run.manifest["counts"]["personalized_risk_material_records"] == 2
    assert run.manifest["counts"]["personalized_risk_material_omitted_records"] == 0
    budget = run.manifest["personalized_risk_material"]["codex_input_budget"]
    assert budget["artifact"] == "analysis/personalized_risk_material.md"
    assert budget["role"] == "report_facing_material"
    assert budget["status"] == "pending_research_context_inclusion"
    assert budget["over_budget"] is False


def test_personalized_risk_material_omits_low_priority_records_first(tmp_path: Path) -> None:
    run = _run_context(tmp_path)
    _write_user_state(run)
    records = [
        _constraint("blocked", "BTCUSDT", "1d", state="disabled_asset_blocked", action="block"),
        _constraint("risk", "ETHUSDT", "1d", state="risk_limit_downgraded", action="downgrade"),
    ]
    records.extend(
        _constraint(f"general-{index}", f"ZZZ{index:02d}USDT", "1d", state="general", action="none")
        for index in range(20)
    )
    _write_constraints(run, records)

    build_personalized_risk_material({}, run)

    material = (run.analysis_dir / "personalized_risk_material.md").read_text(encoding="utf-8")
    assert "constraint_id: personalized:blocked" in material
    assert "constraint_id: personalized:risk" in material
    assert "constraint_id: personalized:general-19" not in material
    assert "omitted_record_count: 18" in material
    assert "general: 18" in material
    assert run.manifest["counts"]["personalized_risk_material_records"] == 4
    assert run.manifest["counts"]["personalized_risk_material_omitted_records"] == 18


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


def _write_user_state(run: RunContext) -> None:
    (run.analysis_dir / "user_state_context.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "artifact_type": "user_state_context",
                "run_id": run.run_id,
                "created_at": "2026-06-05T00:00:00Z",
                "status": "ok",
                "mode": "personalized",
                "source": {
                    "configured": True,
                    "source_ref": "C:\\Users\\private\\user_state.yaml",
                    "raw_path_embedded": False,
                    "raw_file_embedded": False,
                },
                "privacy": {
                    "private_notes_embedded": False,
                    "machine_paths_embedded": False,
                    "account_identifiers_embedded": False,
                    "holdings_values_embedded": False,
                    "omitted_private_values": 1,
                },
                "watchlist": [{"symbol": "BTCUSDT", "timeframes": ["1d"], "relevance": "high"}],
                "disabled_assets": [],
                "risk": {"preference": "conservative", "max_action_level": "WATCH"},
                "preferred_timeframes": ["1d"],
                "strategy_preferences": {"preferred": [], "disabled": []},
                "manual_exposure_summary": [
                    {
                        "symbol": "BTCUSDT",
                        "exposure_state": "watch",
                        "private_note_omitted": True,
                        "private_note": "local secret note",
                    }
                ],
                "counts": {
                    "watchlist_records": 1,
                    "disabled_assets": 0,
                    "preferred_timeframes": 1,
                    "strategy_preference_records": 0,
                    "manual_exposure_summary_records": 1,
                    "omitted_private_values": 1,
                    "warnings": 0,
                    "errors": 0,
                },
                "warnings": [],
                "errors": [],
                "source_artifacts": [],
            }
        ),
        encoding="utf-8",
    )


def _write_constraints(run: RunContext, records: list[dict]) -> None:
    (run.analysis_dir / "personalized_risk_constraints.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "artifact_type": "personalized_risk_constraints",
                "run_id": run.run_id,
                "created_at": "2026-06-05T00:00:00Z",
                "status": "ok",
                "records": records,
                "coverage": [
                    {
                        "source_layer": "decision_recommendations",
                        "source_artifact": "analysis/decision_recommendations.json",
                        "status": "ok",
                        "records": 2,
                        "warnings": [],
                        "errors": [],
                    }
                ],
                "counts": {
                    "records": len(records),
                    "state_counts": _count_by(records, "state"),
                    "action_counts": _count_by(records, "action"),
                    "warnings": 0,
                    "errors": 0,
                },
                "warnings": [],
                "errors": [],
                "source_artifacts": [
                    "analysis/user_state_context.json",
                    "analysis/decision_recommendations.json",
                ],
            }
        ),
        encoding="utf-8",
    )


def _constraint(
    suffix: str,
    symbol: str,
    timeframe: str,
    *,
    state: str,
    action: str,
    reason_codes: list[str] | None = None,
    matched_user_state: dict | None = None,
    evidence: list[str] | None = None,
) -> dict:
    return {
        "constraint_id": f"personalized:{suffix}",
        "scope": {"symbol": symbol, "timeframe": timeframe},
        "state": state,
        "action": action,
        "severity": "high" if action in {"block", "downgrade"} else "info",
        "confidence": "high",
        "reason_codes": reason_codes or ["test_reason"],
        "matched_user_state": matched_user_state or {},
        "upstream_records": [
            {
                "source_layer": "decision_recommendations",
                "source_artifact": "analysis/decision_recommendations.json",
                "source_record_id": f"decision:{symbol}:{timeframe}",
                "scope": {"symbol": symbol, "timeframe": timeframe},
                "status": "watch",
                "action_level": "TRY_SMALL",
                "risk_level": "high",
                "evidence_text": "upstream details should not be copied wholesale",
            }
        ],
        "evidence": evidence or ["bounded evidence"],
        "uncertainty": ["bounded uncertainty"],
        "warnings": [],
        "errors": [],
        "source_artifacts": [
            "analysis/user_state_context.json",
            "analysis/decision_recommendations.json",
        ],
    }


def _count_by(records: list[dict], field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        value = str(record.get(field) or "unknown")
        counts[value] = counts.get(value, 0) + 1
    return counts
