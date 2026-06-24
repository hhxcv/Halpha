import json
from pathlib import Path

from halpha.decision.personalized_risk import build_personalized_risk_constraints
from halpha.pipeline import RunContext


def test_personalized_risk_constraints_records_general_when_user_state_skipped(tmp_path: Path) -> None:
    run = _run_context(tmp_path)
    _write_user_state(run, status="skipped", mode="general")
    _write_upstreams(run, decisions=[_decision("BTCUSDT", "1d", action_level="TRY_SMALL")])

    build_personalized_risk_constraints({}, run, now="2026-06-05T00:00:00Z")

    artifact = _read_constraints(run)
    record = artifact["records"][0]
    assert artifact["status"] == "skipped"
    assert record["state"] == "general"
    assert record["action"] == "none"
    assert record["reason_codes"] == ["user_state_not_configured"]
    assert run.manifest["artifacts"]["personalized_risk_constraints"] == (
        "analysis/personalized_risk_constraints.json"
    )
    assert run.manifest["counts"]["personalized_risk_constraint_records"] == 1
    assert run.manifest["counts"]["personalized_risk_constraint_state_general"] == 1


def test_personalized_risk_constraints_marks_watchlist_relevant_scope(tmp_path: Path) -> None:
    run = _run_context(tmp_path)
    _write_user_state(run, watchlist=[{"symbol": "BTCUSDT", "timeframes": ["1d"]}])
    _write_upstreams(run, decisions=[_decision("BTCUSDT", "1d")])

    build_personalized_risk_constraints({}, run, now="2026-06-05T00:00:00Z")

    record = _record_for(_read_constraints(run), "BTCUSDT", "1d")
    assert record["state"] == "watchlist_relevant"
    assert record["action"] == "annotate"
    assert record["matched_user_state"]["watchlist"] is True
    assert record["matched_user_state"]["preferred_timeframe"] is True
    assert "watchlist_match" in record["reason_codes"]


def test_personalized_risk_constraints_blocks_disabled_asset(tmp_path: Path) -> None:
    run = _run_context(tmp_path)
    _write_user_state(run, disabled_assets=[{"symbol": "BTCUSDT", "reason_code": "disabled_by_user"}])
    _write_upstreams(run, decisions=[_decision("BTCUSDT", "1d", action_level="DO")])

    build_personalized_risk_constraints({}, run, now="2026-06-05T00:00:00Z")

    record = _record_for(_read_constraints(run), "BTCUSDT", "1d")
    assert record["state"] == "disabled_asset_blocked"
    assert record["action"] == "block"
    assert record["severity"] == "high"
    assert record["matched_user_state"]["disabled_asset"] is True


def test_personalized_risk_constraints_downgrades_risk_limits(tmp_path: Path) -> None:
    run = _run_context(tmp_path)
    _write_user_state(
        run,
        risk={"preference": "conservative", "max_risk_state": "high", "max_action_level": "WATCH", "allow_new_exposure": False},
    )
    _write_upstreams(
        run,
        decisions=[_decision("BTCUSDT", "1d", action_level="DO", risk_level="extreme")],
    )

    build_personalized_risk_constraints({}, run, now="2026-06-05T00:00:00Z")

    record = _record_for(_read_constraints(run), "BTCUSDT", "1d")
    assert record["state"] == "risk_limit_downgraded"
    assert record["action"] == "downgrade"
    assert record["reason_codes"] == ["new_exposure_not_allowed", "risk_action_cap", "risk_state_cap"]


def test_personalized_risk_constraints_detects_timeframe_mismatch(tmp_path: Path) -> None:
    run = _run_context(tmp_path)
    _write_user_state(
        run,
        watchlist=[{"symbol": "BTCUSDT", "timeframes": ["1d"]}],
        preferred_timeframes=["1d"],
    )
    _write_upstreams(run, decisions=[_decision("BTCUSDT", "1h")])

    build_personalized_risk_constraints({}, run, now="2026-06-05T00:00:00Z")

    record = _record_for(_read_constraints(run), "BTCUSDT", "1h")
    assert record["state"] == "timeframe_mismatch"
    assert record["action"] == "downgrade"
    assert record["reason_codes"] == ["timeframe_not_preferred"]


def test_personalized_risk_constraints_records_strategy_preference_note(tmp_path: Path) -> None:
    run = _run_context(tmp_path)
    _write_user_state(run, strategy_preferences={"preferred": ["breakout_atr_trend"], "disabled": []})
    _write_upstreams(
        run,
        decisions=[
            _decision(
                "BTCUSDT",
                "1d",
                evidence=["breakout_atr_trend signal is available for this scope."],
            )
        ],
    )

    build_personalized_risk_constraints({}, run, now="2026-06-05T00:00:00Z")

    record = _record_for(_read_constraints(run), "BTCUSDT", "1d")
    assert record["state"] == "strategy_preference_note"
    assert record["action"] == "annotate"
    assert record["reason_codes"] == ["preferred_strategy_match"]


def test_personalized_risk_constraints_degrades_when_upstream_missing(tmp_path: Path) -> None:
    run = _run_context(tmp_path)
    _write_user_state(run, watchlist=[{"symbol": "BTCUSDT", "timeframes": ["1d"]}])

    build_personalized_risk_constraints({}, run, now="2026-06-05T00:00:00Z")

    artifact = _read_constraints(run)
    record = artifact["records"][0]
    assert artifact["status"] == "degraded"
    assert record["state"] == "insufficient_user_state"
    assert record["action"] == "skip"
    assert artifact["counts"]["warnings"] == 2
    assert run.manifest["counts"]["personalized_risk_constraint_state_insufficient_user_state"] == 1


def test_personalized_risk_constraints_degrades_with_degraded_upstream(tmp_path: Path) -> None:
    run = _run_context(tmp_path)
    _write_user_state(run, watchlist=[{"symbol": "BTCUSDT", "timeframes": ["1d"]}])
    _write_upstreams(
        run,
        decisions=[_decision("BTCUSDT", "1d")],
        decision_status="degraded",
        decision_warnings=["decision evidence is degraded"],
    )

    build_personalized_risk_constraints({}, run, now="2026-06-05T00:00:00Z")

    artifact = _read_constraints(run)
    assert artifact["status"] == "degraded"
    assert artifact["coverage"][0]["source_artifact"] == "analysis/intelligence_fusion.json"
    assert artifact["coverage"][0]["status"] == "degraded"
    assert artifact["records"][0]["state"] == "watchlist_relevant"
    assert artifact["records"][0]["warnings"] == ["At least one optional upstream artifact is missing, degraded, or failed."]


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


def _write_user_state(
    run: RunContext,
    *,
    status: str = "ok",
    mode: str = "personalized",
    watchlist: list[dict] | None = None,
    disabled_assets: list[dict] | None = None,
    risk: dict | None = None,
    preferred_timeframes: list[str] | None = None,
    strategy_preferences: dict | None = None,
) -> None:
    artifact = {
        "schema_version": 1,
        "artifact_type": "user_state_context",
        "run_id": run.run_id,
        "created_at": "2026-06-05T00:00:00Z",
        "status": status,
        "mode": mode,
        "source": {"configured": mode == "personalized", "source_ref": "configured_user_state"},
        "privacy": {"private_notes_embedded": False, "machine_paths_embedded": False},
        "watchlist": watchlist or [],
        "disabled_assets": disabled_assets or [],
        "risk": risk or {},
        "preferred_timeframes": preferred_timeframes or [],
        "strategy_preferences": strategy_preferences or {"preferred": [], "disabled": []},
        "manual_exposure_summary": [],
        "counts": {},
        "warnings": [],
        "errors": [],
        "source_artifacts": [],
    }
    (run.analysis_dir / "user_state_context.json").write_text(json.dumps(artifact), encoding="utf-8")


def _write_upstreams(
    run: RunContext,
    *,
    decisions: list[dict] | None = None,
    watches: list[dict] | None = None,
    alerts: list[dict] | None = None,
    fusion: list[dict] | None = None,
    decision_status: str = "ok",
    decision_warnings: list[str] | None = None,
) -> None:
    fusion_records = fusion
    if fusion_records is None:
        fusion_records = [_fusion_from_decision(decision) for decision in decisions or []]
    _write_json_artifact(
        run.analysis_dir / "intelligence_fusion.json",
        "intelligence_fusion",
        "records",
        fusion_records,
        status=decision_status,
        warnings=decision_warnings or [],
    )
    if watches:
        _write_json_artifact(run.analysis_dir / "watch_triggers.json", "watch_triggers", "records", watches)
    if alerts:
        _write_json_artifact(run.analysis_dir / "alert_decisions.json", "alert_decisions", "records", alerts)


def _fusion_from_decision(decision: dict) -> dict:
    return {
        "fusion_record_id": f"fusion:{decision['symbol']}:{decision['timeframe']}",
        "scope": {"symbol": decision["symbol"], "timeframe": decision["timeframe"]},
        "state": "supportive",
        "status": decision.get("status", "ok"),
        "evidence": decision.get("evidence", []),
        "warnings": decision.get("warnings", []),
        "errors": [],
        "source_artifacts": ["analysis/intelligence_fusion.json"],
    }


def _write_json_artifact(
    path: Path,
    artifact_type: str,
    records_key: str,
    records: list[dict],
    *,
    status: str = "ok",
    warnings: list[str] | None = None,
) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "artifact_type": artifact_type,
                "run_id": "run-1",
                "created_at": "2026-06-05T00:00:00Z",
                "status": status,
                records_key: records,
                "warnings": warnings or [],
                "errors": [],
                "source_artifacts": [],
            }
        ),
        encoding="utf-8",
    )


def _decision(
    symbol: str,
    timeframe: str,
    *,
    action_level: str = "WATCH",
    risk_level: str = "low",
    evidence: list[str] | None = None,
) -> dict:
    return {
        "record_id": f"decision:{symbol}:{timeframe}",
        "symbol": symbol,
        "timeframe": timeframe,
        "status": "watch",
        "action_level": action_level,
        "risk_conditions": [f"risk_level={risk_level}; status=succeeded."],
        "evidence": evidence or [],
        "warnings": [],
        "source_artifacts": ["analysis/decision_recommendations.json"],
    }


def _read_constraints(run: RunContext) -> dict:
    return json.loads((run.analysis_dir / "personalized_risk_constraints.json").read_text(encoding="utf-8"))


def _record_for(artifact: dict, symbol: str, timeframe: str) -> dict:
    for record in artifact["records"]:
        if record["scope"] == {"symbol": symbol, "timeframe": timeframe}:
            return record
    raise AssertionError(f"record not found for {symbol} {timeframe}")
