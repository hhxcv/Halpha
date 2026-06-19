from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from halpha.config import load_config
from halpha.multi_source_signals import build_multi_source_signals
from halpha.pipeline import RunContext, run_pipeline
from halpha.storage import write_json


def test_multi_source_signals_pipeline_writes_agreement_records_and_manifest(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    result = run_pipeline(
        config,
        config_path=config_path,
        until_stage="build_multi_source_signals",
        stage_handlers={
            "collect_market_data": _noop_stage,
            "build_feature_snapshots": _noop_stage,
            "build_factor_states": _write_supportive_factor_states,
        },
    )

    assert result.succeeded is True
    artifact = _multi_source_signals(result.run)
    manifest = _manifest(result.run)
    signal = _record(artifact, symbol="BTCUSDT", timeframe="1d")

    assert artifact["artifact_type"] == "multi_source_signals"
    assert signal["state"] == "supportive"
    assert signal["direction"] == "supportive"
    assert 0.0 < signal["score"] <= 1.0
    assert signal["contributing_factor_ids"] == ["factor:liquidity:btcusdt:1d", "factor:trend:btcusdt:1d"]
    assert signal["supportive_factor_ids"] == ["factor:liquidity:btcusdt:1d", "factor:trend:btcusdt:1d"]
    assert signal["cautionary_factor_ids"] == []
    assert "analysis/factor_states.json" in signal["source_artifacts"]
    assert manifest["artifacts"]["multi_source_signals"] == "analysis/multi_source_signals.json"
    assert manifest["counts"]["multi_source_signals"] == len(artifact["records"])
    assert manifest["multi_source_signals"]["state_counts"]["supportive"] == 1
    assert _stage(manifest, "build_multi_source_signals")["artifacts"] == [
        "analysis/multi_source_signals.json"
    ]
    assert "market_signals" not in manifest["artifacts"]


def test_multi_source_signals_detect_conflicting_factor_directions(tmp_path: Path) -> None:
    run = _run_context(tmp_path)
    _write_factor_states(
        run,
        records=[
            _factor("factor:trend:btcusdt:1d", "trend", direction="supportive", state="supportive", score=0.7),
            _factor("factor:liquidity:btcusdt:1d", "liquidity", direction="cautionary", state="cautionary", score=-0.5),
        ],
    )

    build_multi_source_signals({}, run, now="2026-06-05T00:00:00Z")

    artifact = _multi_source_signals(run)
    signal = _record(artifact, symbol="BTCUSDT", timeframe="1d")
    assert signal["state"] == "conflicting"
    assert signal["direction"] == "conflicting"
    assert signal["confidence"] == "low"
    assert signal["factor_score_summary"]["supportive"] == 1
    assert signal["factor_score_summary"]["cautionary"] == 1
    assert manifest_count(artifact, "conflicting") == 1


def test_multi_source_signals_emit_insufficient_state_for_missing_factor_input(tmp_path: Path) -> None:
    run = _run_context(tmp_path)
    _write_factor_states(
        run,
        records=[
            _factor(
                "factor:trend:global",
                "trend",
                symbol=None,
                timeframe=None,
                direction="unknown",
                state="insufficient_evidence",
                score=0.0,
            )
        ],
    )

    build_multi_source_signals({}, run, now="2026-06-05T00:00:00Z")

    signal = _record(_multi_source_signals(run))
    assert signal["state"] == "insufficient_evidence"
    assert signal["direction"] == "unknown"
    assert signal["score"] == 0.0
    assert signal["insufficient_factor_ids"] == ["factor:trend:global"]


def test_multi_source_signals_preserve_neutral_and_degraded_states(tmp_path: Path) -> None:
    run = _run_context(tmp_path)
    _write_factor_states(
        run,
        records=[
            _factor("factor:trend:btcusdt:1d", "trend", direction="neutral", state="neutral", score=0.0),
            _factor(
                "factor:evidence_quality:btcusdt:1d",
                "evidence_quality",
                direction="cautionary",
                state="degraded",
                score=-0.2,
                warning="Evidence quality is degraded.",
            ),
        ],
    )

    build_multi_source_signals({}, run, now="2026-06-05T00:00:00Z")

    signal = _record(_multi_source_signals(run), symbol="BTCUSDT", timeframe="1d")
    assert signal["state"] == "degraded"
    assert signal["direction"] == "neutral"
    assert signal["degraded_factor_ids"] == ["factor:evidence_quality:btcusdt:1d"]
    assert signal["neutral_factor_ids"] == ["factor:trend:btcusdt:1d"]
    assert "Evidence quality is degraded." in signal["warnings"]


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


def _run_context(tmp_path: Path) -> RunContext:
    run_dir = tmp_path / "run"
    raw_dir = run_dir / "raw"
    analysis_dir = run_dir / "analysis"
    codex_context_dir = run_dir / "codex_context"
    report_dir = run_dir / "report"
    for directory in (raw_dir, analysis_dir, codex_context_dir, report_dir):
        directory.mkdir(parents=True, exist_ok=True)
    return RunContext(
        run_id="test-run",
        run_dir=run_dir,
        raw_dir=raw_dir,
        analysis_dir=analysis_dir,
        codex_context_dir=codex_context_dir,
        report_dir=report_dir,
        manifest_path=run_dir / "run_manifest.json",
        config_path=tmp_path / "config.yaml",
        manifest={"artifacts": {}, "counts": {}, "stages": [], "codex": {}, "errors": []},
    )


def _write_supportive_factor_states(config: dict[str, Any], run: RunContext) -> list[str]:
    _write_factor_states(
        run,
        records=[
            _factor("factor:trend:btcusdt:1d", "trend", direction="supportive", state="supportive", score=0.7),
            _factor("factor:liquidity:btcusdt:1d", "liquidity", direction="supportive", state="supportive", score=0.4),
        ],
    )
    return ["analysis/factor_states.json"]


def _write_factor_states(run: RunContext, *, records: list[dict[str, Any]]) -> None:
    write_json(
        run.analysis_dir / "factor_states.json",
        {
            "schema_version": 1,
            "artifact_type": "factor_states",
            "run_id": run.run_id,
            "created_at": "2026-06-05T00:00:00Z",
            "status": "ok",
            "records": records,
            "counts": {
                "records": len(records),
                "factors_by_type": {},
                "direction_counts": {},
                "state_counts": {},
                "confidence_counts": {},
                "warnings": 0,
                "errors": 0,
            },
            "warnings": [],
            "errors": [],
            "source_artifacts": ["analysis/feature_snapshots.json"],
        },
    )
    run.manifest["artifacts"]["factor_states"] = "analysis/factor_states.json"


def _factor(
    factor_id: str,
    factor_type: str,
    *,
    symbol: str | None = "BTCUSDT",
    timeframe: str | None = "1d",
    direction: str,
    state: str,
    score: float,
    warning: str | None = None,
) -> dict[str, Any]:
    return {
        "factor_id": factor_id,
        "factor_type": factor_type,
        "scope": {
            "symbol": symbol,
            "timeframe": timeframe,
            "asset": None,
            "chain": None,
            "region": None,
        },
        "state": state,
        "direction": direction,
        "score": score,
        "score_unit": "bounded_-1_to_1",
        "confidence": "medium",
        "calculation_window": {
            "start": "2026-06-01T00:00:00Z",
            "end": "2026-06-05T00:00:00Z",
            "feature_count": 1,
        },
        "input_feature_ids": [f"feature:{factor_id}"],
        "evidence": [f"{factor_id} evidence"],
        "uncertainty": [],
        "warnings": [warning] if warning else [],
        "errors": [],
        "source_artifacts": ["analysis/factor_states.json"],
    }


def _noop_stage(config: dict[str, Any], run: RunContext) -> list[str]:
    return []


def _multi_source_signals(run: RunContext) -> dict[str, Any]:
    return json.loads((run.analysis_dir / "multi_source_signals.json").read_text(encoding="utf-8"))


def _manifest(run: RunContext) -> dict[str, Any]:
    return json.loads(run.manifest_path.read_text(encoding="utf-8"))


def _record(
    artifact: dict[str, Any],
    *,
    symbol: str | None = None,
    timeframe: str | None = None,
) -> dict[str, Any]:
    for record in artifact["records"]:
        scope = record["scope"]
        if scope.get("symbol") == symbol and scope.get("timeframe") == timeframe:
            return record
    raise AssertionError(f"signal record not found: {symbol} {timeframe}")


def _stage(manifest: dict[str, Any], name: str) -> dict[str, Any]:
    return next(stage for stage in manifest["stages"] if stage["name"] == name)


def manifest_count(artifact: dict[str, Any], state: str) -> int:
    return int(artifact["counts"]["state_counts"].get(state, 0))
