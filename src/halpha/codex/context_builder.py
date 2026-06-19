from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from halpha.codex.input_budget import (
    CODEX_CONTEXT_MAX_CHARS,
    CODEX_PROMPT_MAX_CHARS,
    text_budget_record,
    update_codex_input_manifest,
)
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
    update_codex_input_manifest(
        run.manifest,
        codex_context=text_budget_record(
            CODEX_CONTEXT_ARTIFACT,
            context,
            status="included",
            max_chars=CODEX_CONTEXT_MAX_CHARS,
            role="codex_context",
        ),
        codex_prompt=text_budget_record(
            CODEX_PROMPT_ARTIFACT,
            prompt,
            status="sent_to_codex_cli",
            max_chars=CODEX_PROMPT_MAX_CHARS,
            role="codex_prompt",
        ),
    )
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
            "20. When derivatives market material is present, include derivatives and market-structure evidence in the report where it affects market interpretation, risk notes, watch points, or downstream Halpha artifacts.",
            "21. Distinguish confirming, conflicting, no-impact, unavailable, stale, degraded, partial, and failed derivatives evidence conservatively from Halpha material.",
            "22. Do not treat unavailable, stale, degraded, partial, failed, or missing derivatives evidence as low risk.",
            "23. Do not calculate funding pressure, open-interest changes, premium, basis, spread, depth imbalance, or liquidation summaries from raw data.",
            "24. When macro calendar material is present, explain scheduled catalyst timing risk, recent catalyst context, no-event windows, source availability, freshness, time-zone, and data-quality limits only from Halpha material.",
            "25. Distinguish upcoming scheduled catalyst risk from confirmed realized market impact; do not treat a scheduled macro event as a forecast or confirmed market response.",
            "26. Do not generate or revise macro events, macro states, risk levels, watch triggers, alert priorities, source availability, release outcomes, policy outcomes, price forecasts, trading advice, position sizing, or account actions.",
            "27. When on-chain flow material is present, explain stablecoin liquidity, chain activity, network congestion, and exchange-flow source availability only from Halpha material.",
            "28. Distinguish on-chain context from trading signals; do not treat unavailable, stale, partial, failed, insufficient, or missing on-chain evidence as low risk.",
            "29. Do not generate or revise on-chain records, flow states, address labels, risk levels, watch triggers, alert priorities, source availability, price forecasts, trading advice, position sizing, wallet actions, or account actions.",
            "30. When decision intelligence material is present, use it for action-facing decision language and use quantitative material as upstream evidence.",
            "31. Include supported decision coverage for current decision view, what to do, what not to do, tentative opportunities, wait/watch conditions, risk state, invalidation conditions, changes versus previous run, uncertainty, and method limits.",
            "32. Do not invent action levels, signals, prices, strategy conclusions, unsupported trading instructions, or stronger advice than the decision material supports.",
            "33. Do not upgrade WATCH, NO_ACTION, low-confidence, high-risk, conflicting, or insufficient-evidence material into stronger action language.",
            "34. When strategy experiment material is present, identify effective, watchlisted, rejected, and insufficient-evidence strategy candidates from Halpha gate outcomes.",
            "35. Explain benchmark coverage, costs, sample limits, walk-forward evidence, overfitting checks, and uncertainty near strategy effectiveness statements.",
            "36. Do not generate or revise strategy gate statuses, reasons, metrics, or promotion decisions.",
            "37. When event intelligence material is present, explain Halpha-generated event evidence, topic grouping, source coverage, recency, uncertainty, and event-quant confluence or conflict where supported.",
            "38. Use only Halpha-generated event categories, event signals, event impacts, and event-market relationships from the event intelligence material.",
            "39. Do not generate or revise event classifications, event impacts, event-market relationships, action levels, price forecasts, trading advice, position sizing, or account actions.",
            "40. Treat unknown, low-confidence, skipped, degraded, conflicting, or insufficient event evidence conservatively.",
            "41. Treat financial tone as event-text evidence only, not as a trading signal or price forecast.",
            "42. When alert decision material is present, explain Halpha-generated P0, P1, P2, P3, and no-alert states where supported.",
            "43. Use only Halpha-generated alert priority, event severity, decision impact, downgrade reasons, suppression reasons, and uncertainty from the alert decision material.",
            "44. Do not generate or revise alert priority, event severity, decision impact, action levels, alert delivery, price forecasts, trading advice, position sizing, or account actions.",
            "45. When data quality material is present, explain Halpha-generated quality status only where it affects interpretation.",
            "46. Do not generate or revise data-quality checks, validation results, store contents, catalog contents, run-index contents, raw archive contents, or reusable history records.",
            "47. When outcome tracking material is present, explain Halpha-generated outcome states only as accountability evidence.",
            "48. Do not create outcome labels, validate missing histories, infer omitted outcome stores, score prior recommendations independently, or rank strategies from outcomes.",
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
            "Strategy experiment gate material rules:",
            "",
            "- Use Halpha-generated effectiveness gate statuses only: effective, watchlisted, rejected, or insufficient-evidence.",
            "- Identify effective candidates as research candidates only, not as trading approvals or return guarantees.",
            "- Identify rejected or watchlisted candidates when relevant and explain the Halpha-provided reasons.",
            "- Keep benchmark coverage, net and baseline comparison, cost drag, sample quality, walk-forward evidence, parameter-stability, overfitting-risk, and uncertainty near each effectiveness statement.",
            "- Do not upgrade rejected, watchlisted, unstable, or insufficient-evidence candidates into stronger action language.",
            "- Do not calculate new gate metrics, select best parameters, propose trades, forecast returns, size positions, or suggest account actions from experiment material.",
            "",
            "Derivatives market material rules:",
            "",
            "- Use derivatives market material as Halpha-generated market-structure context, not as a source for new derivatives analysis.",
            "- Explain funding pressure, open-interest pressure, premium or basis stress, bounded spread or depth degradation, liquidation-source availability, and source-quality limits only when supported by the material.",
            "- Distinguish confirming, conflicting, no-impact, unavailable, stale, degraded, partial, and failed derivatives evidence conservatively.",
            "- Keep source availability, uncertainty, and data-quality limits near derivatives-related statements.",
            "- Do not treat unavailable, stale, degraded, partial, failed, or missing derivatives evidence as low risk.",
            "- Do not generate or revise derivatives states, risk levels, signals, source availability, liquidation summaries, price forecasts, return promises, trading advice, position sizing, or account actions.",
            "- Do not calculate funding pressure, open-interest changes, premium, basis, spread, depth imbalance, or liquidation summaries from raw data.",
            "- If derivatives market material is absent, do not recreate it from raw derivatives artifacts, reusable derivatives history, current-run views, or other material.",
            "",
            "Macro calendar material rules:",
            "",
            "- Use macro calendar material as Halpha-generated scheduled-catalyst context, not as a source for new macro analysis.",
            "- Explain scheduled catalysts, recent catalysts, no-event windows, stale, unavailable, degraded, partial, failed, source-availability, freshness, time-zone, and data-quality states only when supported by the material.",
            "- Distinguish scheduled catalyst risk from confirmed realized market impact; realized impact is not evaluated unless Halpha material says otherwise.",
            "- Keep source availability, source time-zone handling, freshness, uncertainty, and data-quality limits near macro/calendar statements.",
            "- Do not treat no-event windows, stale sources, unavailable sources, degraded sources, partial collection, failed collection, or missing macro evidence as low risk.",
            "- Do not generate or revise macro/calendar records, states, severities, source availability, risk levels, watch triggers, alert priorities, signals, realized impact, price forecasts, return promises, trading advice, position sizing, or account actions.",
            "- Do not forecast economic releases, central-bank decisions, policy outcomes, asset prices, or returns from macro calendar material.",
            "- If macro calendar material is absent, do not recreate it from raw macro artifacts, reusable macro/calendar history, current-run views, context JSON, or other material.",
            "",
            "On-chain flow material rules:",
            "",
            "- Use on-chain flow material as Halpha-generated liquidity, usage, congestion, and source-availability context, not as a source for new chain analysis.",
            "- Explain stablecoin liquidity, chain activity, network congestion, exchange-flow source availability, source freshness, and data-quality limits only when supported by the material.",
            "- Distinguish on-chain context from trading signals, price forecasts, address intelligence, wallet attribution, and exchange-flow pressure.",
            "- Keep source availability, freshness, uncertainty, and data-quality limits near on-chain statements.",
            "- Do not treat unavailable, stale, partial, failed, insufficient, or missing on-chain evidence as low risk.",
            "- Do not generate or revise on-chain records, flow states, address labels, risk levels, watch triggers, alert priorities, source availability, price forecasts, return promises, trading advice, position sizing, wallet actions, or account actions.",
            "- Do not calculate stablecoin supply changes, transaction changes, mempool changes, exchange inflows, exchange outflows, or address labels from raw data.",
            "- If on-chain flow material is absent, do not recreate it from raw on-chain artifacts, reusable on-chain history, current-run views, context JSON, or other material.",
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
            "Event intelligence material rules:",
            "",
            "- Use event intelligence material as Halpha-generated event evidence, not as a source for new event analysis.",
            "- Explain source coverage, topic grouping, event signal status, recency, uncertainty, and event-quant confluence or conflict when those artifacts exist.",
            "- Keep event evidence and uncertainty near each event-related conclusion.",
            "- Do not generate or revise event taxonomy labels, event categories, event impacts, event-market relationships, action levels, strategy gates, price forecasts, return promises, or trading advice.",
            "- Do not upgrade unknown, low-confidence, skipped, degraded, conflicting, or insufficient event evidence into stronger conclusions.",
            "- Do not turn event signals, financial tone, or confluence records into trading instructions, position sizing, account actions, or investment recommendations.",
            "- If event intelligence material is absent or degraded, do not recreate it from raw text.",
            "",
            "Alert decision material rules:",
            "",
            "- Use alert decision material as Halpha-generated attention-priority evidence, not as a source for new alert analysis.",
            "- Explain P0, P1, P2, P3, and no-alert state only when supported by alert decision material.",
            "- Keep downgrade reasons, suppression reasons, evidence strength, warnings, and uncertainty near alert-state statements.",
            "- Do not generate or revise alert priorities, event severity, decision impact, action levels, alert delivery, price forecasts, return promises, trading advice, position sizing, or account actions.",
            "- If alert decision material is absent, do not recreate alert priorities from raw events or other material.",
            "",
            "Data quality material rules:",
            "",
            "- Use data quality material as Halpha-generated reliability evidence, not as a source for new validation work.",
            "- Explain ok, warning, degraded, skipped, and failed states only from the provided data quality material.",
            "- Keep collection errors, timestamp warnings, duplicate warnings, source gaps, and shared-store limits near affected report statements.",
            "- Treat store references as references only; do not inspect, infer, summarize, or recreate omitted catalog, SQLite, Parquet, raw archive, or reusable history contents.",
            "- Do not generate or revise data-quality checks, validation results, schema conclusions, store contents, or run-index contents.",
            "- If data quality material is absent, do not recreate quality conclusions from raw text, raw market data, or other material.",
            "",
            "Outcome tracking material rules:",
            "",
            "- Use outcome tracking material as Halpha-generated accountability evidence, not as a source for new outcome scoring.",
            "- Explain confirmed, contradicted, aligned, not_aligned, unresolved, stale, skipped, pending, and insufficient-data states only when supported by outcome material.",
            "- Keep outcome evidence, source run ids, evaluation run ids, uncertainty, warnings, and data limits near each accountability statement.",
            "- Treat missing or insufficient later evidence as missing or insufficient, not as proof that a prior view was right or wrong.",
            "- Do not generate or revise outcome labels, validate missing histories, infer omitted store contents, inspect full outcome history, score prior recommendations independently, rank strategies from outcomes, forecast returns, or provide trading instructions.",
            "- If outcome tracking material is absent, do not recreate outcome tracking from raw artifacts, run indexes, stores, or other material.",
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
        "strategy_experiment": artifacts.get("strategy_experiment"),
        "strategy_effectiveness_gates": artifacts.get("strategy_effectiveness_gates"),
        "strategy_experiment_material": artifacts.get("strategy_experiment_material"),
        "market_signals": artifacts.get("market_signals"),
        "market_signal_material": artifacts.get("market_signal_material"),
        "data_quality_summary": artifacts.get("data_quality_summary"),
        "data_quality_material": artifacts.get("data_quality_material"),
        "raw_derivatives_market": artifacts.get("raw_derivatives_market"),
        "derivatives_market_state": artifacts.get("derivatives_market_state"),
        "derivatives_market_views": artifacts.get("derivatives_market_views"),
        "derivatives_market_context": artifacts.get("derivatives_market_context"),
        "derivatives_market_material": artifacts.get("derivatives_market_material"),
        "macro_calendar_context": artifacts.get("macro_calendar_context"),
        "macro_calendar_material": artifacts.get("macro_calendar_material"),
        "raw_onchain_flow": artifacts.get("raw_onchain_flow"),
        "onchain_flow_state": artifacts.get("onchain_flow_state"),
        "onchain_flow_views": artifacts.get("onchain_flow_views"),
        "onchain_flow_context": artifacts.get("onchain_flow_context"),
        "onchain_flow_material": artifacts.get("onchain_flow_material"),
        "outcome_tracking_material": artifacts.get("outcome_tracking_material"),
        "market_material": artifacts.get("market_material"),
        "text_material": artifacts.get("text_material"),
        "research_context": artifacts.get("research_context"),
        "codex_context": CODEX_CONTEXT_ARTIFACT,
        "codex_prompt": CODEX_PROMPT_ARTIFACT,
    }
    if artifacts.get("outcome_tracking_material"):
        index.update(
            {
                "outcome_targets": artifacts.get("outcome_targets"),
                "outcome_evaluations": artifacts.get("outcome_evaluations"),
                "outcome_history_state": artifacts.get("outcome_history_state"),
                "outcome_tracking_material": artifacts.get("outcome_tracking_material"),
            }
        )
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
    if artifacts.get("event_intelligence_material"):
        index.update(
            {
                "text_event_records": artifacts.get("text_event_records"),
                "text_entity_evidence": artifacts.get("text_entity_evidence"),
                "text_event_classification_evidence": artifacts.get("text_event_classification_evidence"),
                "text_event_topics": artifacts.get("text_event_topics"),
                "text_event_signals": artifacts.get("text_event_signals"),
                "event_market_confluence": artifacts.get("event_market_confluence"),
                "event_intelligence_material": artifacts.get("event_intelligence_material"),
            }
        )
    if artifacts.get("alert_decision_material"):
        index.update(
            {
                "event_intelligence_assessment": artifacts.get("event_intelligence_assessment"),
                "alert_decisions": artifacts.get("alert_decisions"),
                "alert_decision_material": artifacts.get("alert_decision_material"),
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
