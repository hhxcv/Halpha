from __future__ import annotations

import ast
from pathlib import Path
from typing import Callable

from halpha.decision.decision_recommendations import build_decision_recommendations
from halpha.decision.market_regime_assessment import build_market_regime_assessment
from halpha.decision.risk_assessment import build_risk_assessment
from halpha.decision.watch_triggers import build_watch_triggers
from halpha.runtime.pipeline_contracts import RunContext


def test_decision_entry_modules_do_not_import_private_monolith_helpers() -> None:
    for path in (
        Path("src/halpha/decision/decision_artifact_builders.py"),
        Path("src/halpha/decision/market_regime_assessment.py"),
        Path("src/halpha/decision/risk_assessment.py"),
        Path("src/halpha/decision/decision_recommendations.py"),
        Path("src/halpha/decision/watch_triggers.py"),
    ):
        for name in _imported_decision_intelligence_names(path):
            assert not name.startswith("_"), f"{path} imports private decision_intelligence helper {name}"


def test_decision_entry_modules_preserve_quant_disabled_outputs(tmp_path: Path) -> None:
    cases: list[tuple[Callable[..., list[str]], str]] = [
        (build_market_regime_assessment, "market_regime_records"),
        (build_risk_assessment, "risk_assessment_records"),
        (build_decision_recommendations, "decision_recommendation_records"),
        (build_watch_triggers, "watch_trigger_records"),
    ]

    for index, (builder, count_key) in enumerate(cases):
        run = _run_context(tmp_path / str(index))

        artifacts = builder({"quant": {"enabled": False}}, run)

        assert artifacts == []
        assert run.manifest["counts"][count_key] == 0


def _run_context(base: Path) -> RunContext:
    run_dir = base / "runs" / "run-1"
    raw_dir = run_dir / "raw"
    analysis_dir = run_dir / "analysis"
    codex_context_dir = run_dir / "codex"
    report_dir = run_dir / "report"
    for path in (raw_dir, analysis_dir, codex_context_dir, report_dir):
        path.mkdir(parents=True, exist_ok=True)
    return RunContext(
        run_id="run-1",
        run_dir=run_dir,
        raw_dir=raw_dir,
        analysis_dir=analysis_dir,
        codex_context_dir=codex_context_dir,
        report_dir=report_dir,
        manifest_path=run_dir / "run_manifest.json",
        config_path=base / "config.yaml",
        manifest={"artifacts": {}, "counts": {}},
    )


def _imported_decision_intelligence_names(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.module != "halpha.decision.decision_intelligence":
            continue
        names.extend(alias.name for alias in node.names)
    return names
