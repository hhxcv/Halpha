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

### M1 — Signal-aware Report

Status: active.

Goal:

```text
Improve report value by turning real market data and public information into structured, source-aware signals that can support a more useful research report.
```

The loop is complete when Halpha can:

* collect enough historical market data for configured symbols;
* generate basic market signals from historical market data;
* normalize public information into inspectable event materials;
* generate basic text event signals from public information;
* combine market signals and text signals into a unified signal summary;
* identify aligned, mixed, conflicting, or weak signal conditions;
* prepare Codex context that includes signal evidence, source awareness, and report requirements;
* produce a Simplified Chinese Markdown research report that includes signal matrix, resonance analysis, scenario analysis, watch points, and risk notes.

M1 favors:

* signal-driven report materials;
* simple and explainable market strategies;
* real data and real pipeline artifacts;
* readable local files;
* source-aware text events;
* narrow end-to-end improvements;
* report value over broad system design.

M1 does not require:

* trading execution;
* exchange account operations;
* portfolio automation;
* backtesting framework;
* strategy parameter optimization;
* machine learning prediction;
* database-backed market history;
* multi-exchange data aggregation;
* generalized news crawling;
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
