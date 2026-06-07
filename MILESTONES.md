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

### M2 — Quant Strategy Foundation

Status: active.

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

## Completed Milestones

### M1 — Quant Signal Report

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

### M0 — Core Report Loop

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