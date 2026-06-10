from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from halpha.pipeline import PipelineError, RunContext


STAGE_NAME = "build_codex_context"
RESEARCH_CONTEXT_ARTIFACT = "analysis/research_context.md"
CODEX_CONTEXT_ARTIFACT = "codex_context/context.md"
CODEX_PROMPT_ARTIFACT = "codex_context/prompt.md"


def build_codex_context(config: dict[str, Any], run: RunContext) -> list[str]:
    research_context = _read_research_context(run)
    artifact_index = _artifact_index(run)
    context = render_context(artifact_index=artifact_index, research_context=research_context)
    prompt = render_prompt(
        context,
        report_title=_report_title(config),
        generated_at=_report_generated_at(run),
    )

    context_path = run.codex_context_dir / "context.md"
    prompt_path = run.codex_context_dir / "prompt.md"
    context_path.write_text(context, encoding="utf-8")
    prompt_path.write_text(prompt, encoding="utf-8")

    run.manifest["artifacts"]["codex_context"] = CODEX_CONTEXT_ARTIFACT
    run.manifest["artifacts"]["codex_prompt"] = CODEX_PROMPT_ARTIFACT
    return [CODEX_CONTEXT_ARTIFACT, CODEX_PROMPT_ARTIFACT]


def render_context(*, artifact_index: dict[str, Any], research_context: str) -> str:
    return "\n".join(
        [
            "# codex_context",
            "",
            "## artifact_index",
            "",
            "```yaml",
            _yaml_block(artifact_index).rstrip(),
            "```",
            "",
            "## research_context",
            "",
            f'<embed path="{RESEARCH_CONTEXT_ARTIFACT}">',
            research_context.rstrip(),
            "</embed>",
            "",
        ]
    )


def render_prompt(context: str, *, report_title: str, generated_at: str) -> str:
    return "\n".join(
        [
            "You are the report-generation step for Halpha.",
            "",
            "Generate a Simplified Chinese Markdown market intelligence report from the local context below.",
            "Use Chinese section headings only. Do not include English section names in headings.",
            "",
            "Title:",
            "",
            f"- The first line must be a single H1 title: # {report_title}（生成时间：{generated_at}）",
            "- Do not create a separate title section.",
            "- Do not calculate or rewrite the generation time; use the exact time above.",
            "",
            "Rules:",
            "",
            "1. Use only the facts, source text, and derived material in the provided context.",
            "2. Do not invent prices, events, links, sources, or certainty.",
            "3. Preserve source awareness. When a fact is used, keep its source name nearby.",
            "4. If a source URL is missing, say that the source URL was not provided.",
            "5. Distinguish facts, assumptions, uncertainties, and judgment.",
            "6. Use cautious language for market interpretation.",
            "7. Write compactly. Avoid filler, generic disclaimers, repeated definitions, and repeated conclusions.",
            "8. Use Markdown tables for market data, event calendars, and other comparable non-strategy data when practical.",
            "9. When multiple symbols or coins appear, organize each main section with symbol-level subheadings such as ### BTCUSDT and ### ETHUSDT.",
            "10. Do not modify repository files or execute actions; write the report content only.",
            "11. When market signal material is present, include quantitative signal conclusions in the report.",
            "12. Keep quantitative signal evidence and uncertainty near the related signal conclusions.",
            "13. Derive quantitative watch points and risk notes only from provided market signal material.",
            "14. Do not calculate new quantitative signals from raw OHLCV history or inspect shared OHLCV storage.",
            "15. Do not provide trading instructions, position sizing, account actions, or investment recommendations.",
            "16. Do not fabricate strategy signals, strategy conclusions, backtest results, return promises, or unsupported certainty.",
            "17. Halpha inserts the complete quant strategy run table after Codex output; do not recreate the full strategy run table.",
            "18. When strategy evaluation material is present, explain strategy reliability, cost assumptions, baseline comparison, sample limits, and uncertainty where they affect interpretation.",
            "19. Do not upgrade weak, fragile, unstable, costly, short-sample, high-turnover, or insufficient-evidence evaluation material into stronger action language.",
            "20. When decision intelligence material is present, use it for action-facing decision language and use quantitative material as upstream evidence.",
            "21. Include supported decision coverage for current decision view, what to do, what not to do, tentative opportunities, wait/watch conditions, risk state, invalidation conditions, changes versus previous run, uncertainty, and method limits.",
            "22. Do not invent action levels, signals, prices, strategy conclusions, unsupported trading instructions, or stronger advice than the decision material supports.",
            "23. Do not upgrade WATCH, NO_ACTION, low-confidence, high-risk, conflicting, or insufficient-evidence material into stronger action language.",
            "",
            "Quantitative strategy material rules:",
            "",
            "- When strategy material exists, explain upstream strategy conclusions from the provided material only as needed for interpretation.",
            "- Keep strategy assumptions, evidence, and uncertainty adjacent to each cited strategy conclusion.",
            "- Do not list every strategy/source/symbol/timeframe row; use the post-processed strategy table as the complete row-level display.",
            "- When strategy signals disagree, describe the conflict and related risk notes before synthesis.",
            "- Treat backtest diagnostics as historical research material only; do not describe them as forecasts, expected returns, or proof of future performance.",
            "- Do not derive new quantitative conclusions from raw OHLCV, shared OHLCV storage, or unstated calculations.",
            "- Do not give trading instructions, position sizing, account actions, return promises, or investment recommendations.",
            "",
            "Strategy evaluation material rules:",
            "",
            "- When strategy evaluation material exists, mention cost assumptions, baseline comparison, sample limits, reliability, and uncertainty where they affect interpretation.",
            "- Use Halpha-generated evaluation metrics only; do not calculate new returns, drawdowns, baselines, risk ratios, or parameter rankings.",
            "- Treat walk-forward, parameter-stability, and overfitting-risk evidence as bounded historical research evidence, not proof of future performance.",
            "- If evidence is weak, fragile, unstable, costly, short-sample, high-turnover, or insufficient, say so before synthesis and avoid stronger action language.",
            "- Do not select best parameters, propose trades, forecast returns, size positions, or suggest account actions from evaluation material.",
            "",
            "Decision intelligence material rules:",
            "",
            "- Use decision intelligence material for deterministic decision synthesis; use quantitative material as evidence.",
            "- Cover current decision view, what to do, what not to do, tentative opportunities, wait/watch conditions, risk state, invalidation conditions, changes versus previous run, uncertainty, and method limits when the material exists.",
            "- Keep evidence, risk conditions, confidence, conflicts, and uncertainty near each decision statement.",
            "- Treat WATCH, NO_ACTION, low confidence, high risk, conflicts, or insufficient evidence conservatively.",
            "- When previous-run delta status is no_previous_run, state that no previous successful decision-intelligence run was available instead of fabricating changes.",
            "- Do not invent action levels, signals, prices, strategy conclusions, unsupported trading instructions, position sizing, account actions, return promises, or investment recommendations.",
            "",
            "Report style:",
            "",
            "- Core summary: 3-5 bullets maximum. Each bullet should add a distinct takeaway.",
            "- Market overview: prefer a compact table for source, symbol, price, change, volume, and timestamp.",
            "- Text events: group by symbol or theme; use tables for event lists when possible.",
            "- Quantitative conclusions: interpret signal direction, conflict, confidence, and uncertainty; do not restate every strategy run row or numeric field.",
            "- Synthesis: explain cross-source implications, conflicts, and what would change the assessment. Do not repeat the post-processed strategy table or earlier event summaries.",
            "- Watch points: focus on observable upcoming events, threshold changes, conflicting-signal resolution, and source-confirmed catalysts.",
            "- Risk notes: include only context-specific risks from the provided materials, such as upcoming macro events, conflicting signals, volatility, data limitations, source gaps, or source-specific uncertainty.",
            "- Do not include fixed boilerplate such as generic financial-advice disclaimers in the risk section.",
            "",
            "Required sections:",
            "",
            "- 核心摘要",
            "- 市场概览",
            "- 文本事件",
            "- 综合判断",
            "- 观察要点",
            "- 风险提示",
            "",
            "<context>",
            context.rstrip(),
            "</context>",
            "",
        ]
    )


def _read_research_context(run: RunContext) -> str:
    path = run.analysis_dir / "research_context.md"
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise PipelineError(
            f"{RESEARCH_CONTEXT_ARTIFACT} was not found; build_research_context must run first.",
            stage=STAGE_NAME,
            exit_code=3,
        ) from exc


def _artifact_index(run: RunContext) -> dict[str, Any]:
    artifacts = run.manifest.get("artifacts", {})
    index = {
        "raw_market": artifacts.get("raw_market"),
        "raw_text_events": artifacts.get("raw_text_events"),
        "quant_strategy_runs": artifacts.get("quant_strategy_runs"),
        "strategy_evaluation_summary": artifacts.get("strategy_evaluation_summary"),
        "strategy_evaluation_material": artifacts.get("strategy_evaluation_material"),
        "market_signals": artifacts.get("market_signals"),
        "market_signal_material": artifacts.get("market_signal_material"),
        "market_material": artifacts.get("market_material"),
        "text_material": artifacts.get("text_material"),
        "research_context": artifacts.get("research_context"),
        "codex_context": CODEX_CONTEXT_ARTIFACT,
        "codex_prompt": CODEX_PROMPT_ARTIFACT,
    }
    if artifacts.get("decision_intelligence_material"):
        index.update(
            {
                "market_regime_assessment": artifacts.get("market_regime_assessment"),
                "risk_assessment": artifacts.get("risk_assessment"),
                "decision_recommendations": artifacts.get("decision_recommendations"),
                "watch_triggers": artifacts.get("watch_triggers"),
                "decision_intelligence_delta": artifacts.get("decision_intelligence_delta"),
                "decision_intelligence_material": artifacts.get("decision_intelligence_material"),
            }
        )
    return index


def _report_title(config: dict[str, Any]) -> str:
    report = config.get("report", {})
    title = report.get("title") if isinstance(report, dict) else None
    if isinstance(title, str) and title.strip():
        return title.strip()
    return "每日市场情报简报"


def _report_generated_at(run: RunContext) -> str:
    value = run.manifest.get("started_at")
    if not isinstance(value, str) or not value.strip():
        raise PipelineError(
            "run_manifest.started_at must exist before building Codex context.",
            stage=STAGE_NAME,
            exit_code=3,
        )
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PipelineError(
            "run_manifest.started_at must be an ISO 8601 UTC timestamp.",
            stage=STAGE_NAME,
            exit_code=3,
        ) from exc
    if parsed.tzinfo is None:
        raise PipelineError(
            "run_manifest.started_at must include a UTC offset.",
            stage=STAGE_NAME,
            exit_code=3,
        )
    timestamp = parsed.astimezone(timezone(timedelta(hours=8)))
    return timestamp.strftime("%Y-%m-%d %H:%M:%S UTC+08:00")


def _yaml_block(data: dict[str, Any]) -> str:
    try:
        import yaml
    except ModuleNotFoundError as exc:
        raise PipelineError(
            "PyYAML is required to write YAML Codex context records.",
            stage=STAGE_NAME,
            exit_code=1,
        ) from exc

    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
