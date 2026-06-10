# MILESTONES.md

Current and completed milestones only.

This file is not a roadmap.

Do not add future milestones.
Do not add speculative phases.
Do not describe planned work outside the active milestone.

## Rules

- Record the active milestone.
- Record completed milestones after they are complete.
- Keep scope narrow.
- Keep wording factual.
- Do not create future placeholders.
- Do not use this file for architecture brainstorming.
- Do not use this file for feature wishlists.

## Active Milestone

### M5 - Strategy Iteration and Validation Foundation

Status: active.

Goal:

```text
Turn the M4 strategy evaluation layer into a disciplined strategy improvement loop with stronger backtest correctness checks, fixed benchmark evaluation, repeatable strategy experiments, deterministic promotion or rejection gates, and at least three effective strategy research candidates for the main report path.
```

The loop is complete when Halpha can:

* preserve the M4 strategy evaluation, signal, decision-intelligence, Codex context, and report path instead of replacing it;
* strengthen the self-built backtest calculation layer with deterministic golden cases that cover execution timing, costs, turnover, equity, drawdown, risk-adjusted metrics, baselines, and edge cases;
* cross-check the Halpha-owned backtest results against an independent mature backtest or numerical calculation path where practical, while keeping Halpha-owned JSON and Markdown artifacts as the stable downstream contract;
* define a fixed benchmark evaluation suite using shared local OHLCV history for configured symbols, timeframes, and market windows so strategy changes can be compared against the same evidence set;
* run repeatable strategy experiments outside the main report run and write inspectable experiment artifacts with inputs, benchmark coverage, metrics, warnings, gate outcomes, and source artifacts;
* support adding or replacing strategy candidates when current strategies fail the benchmark gates, without turning strategy development into automatic parameter optimization;
* produce deterministic strategy effectiveness gates that mark each candidate as effective, watchlisted, rejected, or insufficient-evidence using net performance, baseline comparison, cost drag, drawdown, walk-forward stability, parameter stability, overfitting risk, trade count, and sample quality;
* have at least three configured strategy candidates reach effective status under the M5 gate criteria as research candidates, not as trading instructions or return guarantees;
* keep rejected or weak strategies visible with explicit failure reasons so poor candidates are not silently promoted into the report path;
* integrate strategy experiment and gate material into research context, Codex context, and the final report where it improves interpretation of current strategy reliability;
* record benchmark, experiment, gate, strategy candidate, warning, error, and coverage counts in `run_manifest.json` or companion experiment manifests;
* keep the M5 product path covered by tests and verified by a real-source run.

M5 favors:

* backtest correctness before strategy complexity;
* golden examples and cross-checks over trust in a single implementation path;
* fixed benchmark comparability over ad hoc latest-run impressions;
* strategy replacement and disciplined candidate iteration over preserving weak strategies;
* deterministic effectiveness gates over automatic best-parameter selection;
* at least three effective research candidates over a large unfiltered strategy list;
* net, cost-aware, baseline-aware, walk-forward-aware evaluation over headline gross returns;
* simple, inspectable Halpha-owned JSON and Markdown artifacts over hidden framework objects;
* conservative report language that separates evidence, assumptions, uncertainty, and judgment;
* preserving the main command path: `python -m halpha run --config config.example.yaml`.

M5 does not require:

* machine learning prediction, ML-based regime classification, or feature-store design;
* automatic parameter optimization or best-parameter selection;
* a generalized strategy plugin marketplace or public strategy SDK;
* portfolio allocation optimization;
* trading execution, order placement, position sizing, or exchange account operations;
* real-time market monitoring, scheduler, websocket, daemon, or alert delivery runtime;
* new exchange or market data sources;
* text event signal generation or event-intelligence scoring;
* dashboard UI or hosted service design;
* database service, state store redesign, microservices, Kafka, Redis, or Celery;
* making Codex or another LLM the source of backtest metrics, strategy gate outcomes, or effective-strategy promotion;
* claiming that an effective research candidate is profitable, safe, or suitable for live trading.

## Completed Milestones

### M4 - Strategy Evaluation Foundation

Status: completed.

Goal:

```text
Improve quantitative research credibility by adding a professional strategy evaluation layer over the existing strategy run artifacts, with cost-aware backtest summaries, benchmark comparison, out-of-sample or walk-forward evaluation, parameter stability diagnostics, overfitting risk notes, and AI-readable evaluation material for the Simplified Chinese Markdown report.
```

The loop is complete when Halpha can:

* preserve the existing strategy, signal, decision-intelligence, Codex context, and report path instead of replacing it;
* generate Halpha-owned strategy evaluation artifacts from `analysis/quant_strategy_runs.json`, current-run OHLCV views, and shared OHLCV history;
* evaluate each configured strategy against simple baselines such as buy-and-hold and no-position cash behavior where applicable;
* record cost-aware backtest metrics including gross return, net return, fees, slippage assumptions, turnover, exposure, trade count, hit rate, volatility, drawdown, and risk-adjusted performance;
* produce equity-curve and drawdown summaries as inspectable research artifacts without turning Halpha into a full trading platform;
* run bounded out-of-sample or walk-forward evaluation that separates training or calibration windows from evaluation windows;
* record parameter sensitivity diagnostics that show stability or fragility across configured parameter ranges without selecting "best" parameters automatically;
* identify overfitting, short-sample, regime-dependence, low-trade-count, high-turnover, and cost-sensitivity warnings as first-class evaluation output;
* integrate strategy evaluation material into downstream market signal material, decision-intelligence material, Codex context, and the final report where it improves interpretation;
* produce a Simplified Chinese Markdown report that explains not only current strategy direction, but also strategy reliability, sample limits, cost assumptions, baseline comparison, and evaluation uncertainty;
* record strategy evaluation artifact paths, counts, warnings, errors, and evaluation coverage in `run_manifest.json`;
* keep the M4 product path covered by tests and verified by a real-source run.

M4 favors:

* evaluation quality over strategy count;
* professional research discipline over complex-looking strategy logic;
* net, cost-aware, baseline-aware diagnostics over headline gross returns;
* out-of-sample and walk-forward evidence over single-window in-sample conclusions;
* parameter stability and robustness notes over parameter optimization;
* simple, inspectable Halpha-owned JSON and Markdown artifacts over hidden framework objects;
* conservative report language that separates evidence, assumptions, uncertainty, and judgment;
* reusable evaluation contracts that can later support more strategies without redesigning the report chain;
* preserving the main command path: `python -m halpha run --config config.example.yaml`.

M4 does not require:

* adding many new strategies;
* making existing strategies more complex before their evaluation quality is visible;
* machine learning prediction, ML-based regime classification, or feature-store design;
* automatic parameter optimization or best-parameter selection;
* portfolio allocation optimization;
* trading execution, order placement, position sizing, or exchange account operations;
* real-time market monitoring, scheduler, websocket, daemon, or alert delivery runtime;
* new exchange or market data sources;
* text event signal generation or event-intelligence scoring;
* dashboard UI or hosted service design;
* database service, state store redesign, microservices, Kafka, Redis, or Celery;
* making Codex or another LLM the source of strategy evaluation results.

### M3 - Decision Intelligence Foundation

Status: completed.

Goal:

```text
Improve report value by converting M2 strategy research artifacts into a first deterministic decision-intelligence layer that produces market regime, risk state, action recommendations, do-not-do guidance, invalidation conditions, watch triggers, previous-run deltas, and AI-readable decision material for the Simplified Chinese Markdown report.
```

The loop is complete when Halpha can:

* preserve M2 strategy research artifacts as the upstream quantitative evidence layer instead of replacing or removing them;
* generate `analysis/market_regime_assessment.json` from M2 strategy and market signal artifacts using deterministic, explainable rules;
* generate `analysis/risk_assessment.json` that identifies risk level, rising risks, blocking risks, data-quality risks, and signal-conflict risks;
* generate `analysis/decision_recommendations.json` with deterministic action levels, recommended actions, do-not-do guidance, confidence, evidence, conflicts, risk conditions, and invalidation conditions;
* generate `analysis/watch_triggers.json` with confirmation, invalidation, risk-escalation, risk-relief, and wait-condition triggers derived from the current strategy, regime, risk, and decision artifacts;
* generate `analysis/decision_intelligence_delta.json` that compares current decision-intelligence artifacts with the previous successful run when available;
* generate `analysis/decision_intelligence_material.md` as AI-readable decision material that summarizes regime, risk, action recommendations, prohibited actions, invalidation conditions, watch triggers, deltas, evidence, and uncertainty;
* integrate decision-intelligence material into `analysis/research_context.md`, `codex_context/context.md`, and `codex_context/prompt.md` without removing the M2 quant material from the report chain;
* produce a Simplified Chinese Markdown report that visibly includes current decision bias, what to do, what not to do, tentative opportunities, watch/wait conditions, risk state, invalidation conditions, and changes versus the previous successful run when supported by artifacts;
* record decision-intelligence artifact paths, counts, warnings, errors, and previous-run comparison status in `run_manifest.json`;
* keep the M3 product path covered by tests and verified by the main real-source run.

M3 favors:

* additive decision-intelligence artifacts derived from M2 artifacts over replacing M2 artifacts;
* Halpha-owned JSON and Markdown artifact contracts over third-party framework objects or hidden AI state;
* deterministic rules, scoring, and gating over LLM-generated action advice;
* conservative action recommendations with explicit evidence, uncertainty, risks, and invalidation conditions;
* small, inspectable artifacts that are easy to review and consume downstream;
* preserving the main command path: `python -m halpha run --config config.example.yaml`;
* report value improvements that help the user understand what to do, what not to do, when to wait, what would invalidate the view, and what changed since the previous run.

M3 does not require:

* removing or replacing `analysis/quant_strategy_runs.json`;
* removing or replacing `analysis/market_strategy_signals.json`;
* removing or replacing `analysis/market_signals.json`;
* removing or replacing `analysis/market_signal_material.md`;
* adding new exchange or market data sources;
* adding real-time market monitoring;
* adding scheduler, daemon, websocket, or alert delivery runtime;
* adding event intelligence or text event signal generation;
* adding user profiles, user positions, account connection, or exchange account operations;
* adding automatic trading, order placement, position sizing, or portfolio management;
* adding machine learning prediction or ML-based regime classification;
* adding a dashboard or workbench UI;
* adding a database service, state store redesign, microservices, Kafka, Redis, or Celery;
* making Codex or another LLM the source of action recommendations.

### M2 - Quant Strategy Foundation

Status: completed.

Goal:

```text
Improve report value by replacing M1 demo-style quantitative signal evaluators with a first set of configurable, vectorbt-backed quantitative strategies that produce inspectable strategy research artifacts, bounded backtest diagnostics, and higher-quality AI-readable quant material.
```

The loop is complete when Halpha can:

* retire the M1 demo-style signal evaluators from the product quant path;
* configure selected quantitative strategies through a strategy-oriented quant configuration;
* run a small set of real, non-demo quantitative strategies using mature open-source quant or numerical computing libraries where they reduce implementation risk;
* generate strategy run artifacts that preserve strategy name, version, parameters, input data window, calculated indicators, generated signals, backtest assumptions, bounded diagnostics, evidence, uncertainty, and warnings;
* generate normalized market signal artifacts from strategy run results for the existing report loop;
* prepare AI-readable quant material that summarizes strategy conclusions, confluence, conflicts, risk state, diagnostics, and uncertainty without exposing large raw OHLCV history to Codex context;
* produce a Simplified Chinese Markdown research report that reflects the improved strategy analysis, including strategy conclusions, evidence, conflict notes, risk notes, and watch points;
* record enough manifest details to explain which strategies ran, which failed, which had insufficient data, which assumptions were used, and which artifacts were generated;
* keep the M2 product path covered by tests and verified by a real-source run.

M2 favors:

* strategy quality over strategy count;
* real strategy behavior over demo signal labels;
* mature open-source frameworks such as vectorbt, pandas, and numpy for indicator calculation, signal generation, portfolio-style research diagnostics, and parameter analysis when they reduce implementation risk;
* Halpha-owned strategy run artifacts and signal contracts over direct exposure of third-party framework objects;
* strategies with explicit assumptions, entry or exit logic, risk controls, evidence, uncertainty, and diagnostics;
* bounded research backtest diagnostics as strategy validation material, not as return promises;
* small but visible report-chain improvements that help AI output reflect upstream quantitative research;
* readable local artifacts;
* reproducible strategy runs;
* narrow end-to-end improvements that preserve the main command path.

M2 does not require:

* migrating M1 demo strategy names or behavior;
* a generalized external strategy plugin system;
* a full backtesting platform;
* a full parameter optimization platform;
* walk-forward analysis;
* machine learning prediction;
* portfolio allocation optimization;
* exchange account operations;
* trading execution;
* order placement, cancellation, or position management;
* real-time market monitoring;
* multi-exchange data aggregation;
* new text event normalization;
* text event signal generation;
* market and text signal resonance analysis;
* dashboard UI;
* hosted service design;
* multi-user features.

### M1 - Quant Signal Report

Status: completed.

Goal:

```text
Improve report value by building a real historical OHLCV data flow and generating structured, source-aware quantitative market signals for report generation.
```

The loop is complete when Halpha can:

* maintain reusable local historical OHLCV data for configured symbols and timeframes outside per-run report directories;
* incrementally update historical OHLCV data to the latest available closed candles;
* support enough configured timeframes for basic long-period and intraday quantitative signal evaluation;
* provide deterministic OHLCV data views for quantitative signal evaluation;
* run a small set of basic, explainable quantitative signal evaluators;
* generate structured market signal artifacts with direction, strength, confidence, evidence, input window, key values, and uncertainty;
* prepare AI-readable market signal material without embedding large raw OHLCV history into Codex context;
* integrate market signal material into the existing research context, Codex context, and report requirements;
* produce a Simplified Chinese Markdown research report that includes quantitative signal conclusions, evidence, watch points, and risk notes;
* keep the M1 product path covered by tests and verified by a real-source run.

M1 favors:

* quantitative market signal generation;
* real finalized OHLCV data;
* incremental local data reuse;
* deterministic strategy input views;
* simple and explainable signal evaluators;
* mature open-source libraries for market data access, storage, querying, and indicator or signal calculation when they reduce implementation risk;
* clear separation between historical OHLCV storage, strategy inputs, signal artifacts, and AI-readable report context;
* strategy inputs based on raw OHLCV-style data;
* AI-readable outputs based on signal conclusions and bounded market context;
* readable local artifacts;
* narrow end-to-end improvements;
* report value over broad quant platform design.

M1 does not require:

* new text event normalization;
* text event signal generation;
* market and text signal resonance analysis;
* generalized public information processing beyond existing M0 behavior;
* trading execution;
* exchange account operations;
* portfolio automation;
* backtesting product flow;
* strategy parameter optimization;
* machine learning prediction;
* database service or database-backed primary history store;
* multi-exchange data aggregation;
* generalized strategy plugin architecture;
* real-time market monitoring;
* vector database or semantic search;
* dashboard UI;
* hosted service design;
* multi-user features.

### M0 - Core Report Loop

Status: completed.

Goal:

```text
Complete the smallest useful Halpha loop that can produce a research report.
```

The loop is complete when Halpha can:

- collect market-related input;
- collect public information input;
- keep input materials inspectable;
- prepare structured research context;
- produce a Simplified Chinese Markdown research report;
- keep enough source awareness for later review.

M0 favors:

- readable files;
- narrow implementation steps;
- source-aware materials;
- one working path over broad architecture.

M0 does not require:

- trading execution;
- exchange account operations;
- portfolio automation;
- hosted service design;
- multi-user features;
- dashboard UI;
- database-backed storage;
- generalized plugin architecture.
