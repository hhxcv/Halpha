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

### M1 — Quant Signal Report

Status: active.

Goal:

```text
Improve report value by building a real historical OHLCV data flow and generating structured, source-aware quantitative signals for report generation.
```

The loop is complete when Halpha can:

* store reusable historical OHLCV data for configured symbols outside per-run report directories;
* incrementally update historical OHLCV data to the latest available closed candles;
* support enough configured timeframes for basic long-period and intraday quantitative signals;
* provide deterministic OHLCV data views for strategy execution;
* run a small set of basic, explainable quantitative signal strategies;
* generate structured market signal artifacts with direction, strength, confidence, evidence, input window, and uncertainty;
* prepare AI-readable market signal material without embedding large raw OHLCV history into Codex context;
* integrate market signal material into Codex context and report requirements;
* produce a Simplified Chinese Markdown research report that includes quantitative signal conclusions, evidence, watch points, and risk notes;
* keep the M1 product path covered by tests and verified by a real-source run.

M1 favors:

* quantitative signal generation;
* real historical OHLCV data;
* incremental local data reuse;
* simple and explainable strategies;
* mature open-source libraries for data access, storage, querying, and indicator calculation when they reduce implementation risk;
* strategy inputs based on raw OHLCV-style data;
* AI-readable outputs based on strategy conclusions and bounded market context;
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
* database-backed market history;
* multi-exchange data aggregation;
* generalized strategy plugin architecture;
* vector database or semantic search;
* dashboard UI;
* hosted service design;
* multi-user features.


## Completed Milestones

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
