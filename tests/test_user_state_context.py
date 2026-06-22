import json
from pathlib import Path

import pytest

from halpha.pipeline import PipelineError, RunContext
from halpha.decision.user_state import build_user_state_context


def test_build_user_state_context_skips_when_not_configured(tmp_path: Path) -> None:
    run = _run_context(tmp_path)

    artifacts = build_user_state_context({}, run, now="2026-06-05T00:00:00Z")

    assert artifacts == ["analysis/user_state_context.json"]
    artifact = _read_artifact(run)
    assert artifact["status"] == "skipped"
    assert artifact["mode"] == "general"
    assert artifact["source"]["configured"] is False
    assert artifact["privacy"]["omitted_private_values"] == 0
    assert run.manifest["artifacts"]["user_state_context"] == "analysis/user_state_context.json"
    assert run.manifest["user_state_context"]["status"] == "skipped"
    assert run.manifest["counts"]["user_state_watchlist_records"] == 0
    assert run.manifest["counts"]["user_state_errors"] == 0


def test_build_user_state_context_sanitizes_valid_yaml(tmp_path: Path) -> None:
    user_state_path = tmp_path / "user_state.local.yaml"
    user_state_path.write_text(
        """
schema_version: 1
watchlist:
  - symbol: btcusdt
    timeframes: [1h, 1d]
    relevance: high
disabled_assets:
  - symbol: dogeusdt
    reason_code: disabled_by_user
risk:
  preference: conservative
  max_risk_state: high
  max_action_level: WATCH
  allow_new_exposure: false
preferred_timeframes:
  - 1d
  - 1h
strategy_preferences:
  preferred:
    - breakout_atr_trend
  disabled:
    - example_strategy
manual_exposure_notes:
  - symbol: ethusdt
    exposure_state: watch
    private_note: do not leak
""".strip(),
        encoding="utf-8",
    )
    run = _run_context(tmp_path)

    build_user_state_context(
        {"user_state": {"enabled": True, "path": "user_state.local.yaml"}},
        run,
        now="2026-06-05T00:00:00Z",
    )

    artifact = _read_artifact(run)
    serialized = json.dumps(artifact, sort_keys=True)
    assert artifact["status"] == "ok"
    assert artifact["mode"] == "personalized"
    assert artifact["source"] == {
        "configured": True,
        "source_ref": "configured_user_state",
        "raw_path_embedded": False,
        "raw_file_embedded": False,
    }
    assert artifact["watchlist"] == [{"symbol": "BTCUSDT", "timeframes": ["1d", "1h"], "relevance": "high"}]
    assert artifact["disabled_assets"] == [{"symbol": "DOGEUSDT", "reason_code": "disabled_by_user"}]
    assert artifact["risk"] == {
        "preference": "conservative",
        "max_risk_state": "high",
        "max_action_level": "WATCH",
        "allow_new_exposure": False,
    }
    assert artifact["manual_exposure_summary"] == [
        {"symbol": "ETHUSDT", "exposure_state": "watch", "private_note_omitted": True}
    ]
    assert "do not leak" not in serialized
    assert str(user_state_path) not in serialized
    assert artifact["privacy"]["private_notes_embedded"] is False
    assert artifact["privacy"]["machine_paths_embedded"] is False
    assert artifact["privacy"]["omitted_private_values"] == 1
    assert run.manifest["user_state_context"]["mode"] == "personalized"
    assert run.manifest["counts"]["user_state_watchlist_records"] == 1
    assert run.manifest["counts"]["user_state_omitted_private_values"] == 1


def test_build_user_state_context_accepts_valid_json(tmp_path: Path) -> None:
    user_state_path = tmp_path / "state.json"
    user_state_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "watchlist": [{"symbol": "SOLUSDT"}],
                "risk": {"preference": "balanced"},
            }
        ),
        encoding="utf-8",
    )
    run = _run_context(tmp_path)

    build_user_state_context(
        {"user_state": {"enabled": True, "path": "state.json"}},
        run,
        now="2026-06-05T00:00:00Z",
    )

    artifact = _read_artifact(run)
    assert artifact["status"] == "ok"
    assert artifact["watchlist"] == [{"symbol": "SOLUSDT"}]
    assert artifact["risk"] == {"preference": "balanced"}


def test_build_user_state_context_invalid_input_omits_private_values(tmp_path: Path) -> None:
    user_state_path = tmp_path / "private-state.yaml"
    user_state_path.write_text(
        """
schema_version: 2
watchlist:
  - symbol: BTCUSDT
    private_note: hidden local note
manual_exposure_notes:
  - symbol: BTCUSDT
    exposure_state: watch
    private_note: another hidden note
""".strip(),
        encoding="utf-8",
    )
    run = _run_context(tmp_path)

    with pytest.raises(PipelineError, match="configured user-state input is invalid") as exc_info:
        build_user_state_context(
            {"user_state": {"enabled": True, "path": "private-state.yaml"}},
            run,
            now="2026-06-05T00:00:00Z",
        )

    artifact = _read_artifact(run)
    serialized = json.dumps(artifact, sort_keys=True)
    error_text = str(exc_info.value) + json.dumps(exc_info.value.error_details, sort_keys=True)
    assert artifact["status"] == "failed"
    assert artifact["mode"] == "invalid"
    assert "schema_version must be 1." in [error["message"] for error in artifact["errors"]]
    assert "hidden local note" not in serialized
    assert "another hidden note" not in serialized
    assert str(user_state_path) not in serialized
    assert "hidden local note" not in error_text
    assert "another hidden note" not in error_text
    assert str(user_state_path) not in error_text
    assert run.manifest["counts"]["user_state_errors"] == len(artifact["errors"])


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


def _read_artifact(run: RunContext) -> dict:
    return json.loads((run.analysis_dir / "user_state_context.json").read_text(encoding="utf-8"))
