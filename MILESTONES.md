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

### M13 - Feature, Factor, and Multi-Source Signal Engine

Status: active.

Goal:

```text
Convert implemented price, strategy, derivatives, macro/calendar, on-chain flow, event, outcome, and data-quality evidence into deterministic feature, factor, and normalized multi-source signal artifacts that later fusion can consume without source-specific special cases.
```

The loop is complete when Halpha can:

* preserve the M12 on-chain flow, M11 macro/calendar, M10 derivatives, market-structure, outcome tracking, data-quality, event intelligence, alert decision, strategy evaluation, decision-intelligence, Codex context, and report paths instead of replacing them;
* define durable feature, factor, and multi-source signal contracts for source references, calculation windows, factor taxonomy, score, direction, confidence, uncertainty, warnings, errors, degraded states, and Codex boundaries;
* produce `analysis/feature_snapshots.json` from implemented current-run bounded inputs such as market views, strategy evidence, derivatives context, macro/calendar context, on-chain flow context, event intelligence, outcome tracking, and data quality where available;
* produce `analysis/factor_states.json` with a small initial deterministic taxonomy for trend, volatility, liquidity, leverage, macro risk, event pressure, on-chain flow, and evidence quality;
* produce `analysis/multi_source_signals.json` as normalized research signals derived from factor states, not trading instructions, action levels, price forecasts, or position sizing;
* produce bounded `analysis/factor_signal_material.md` for Codex and final report generation without embedding full raw streams, reusable histories, current-run views, or full intermediate JSON by default;
* explicitly distinguish available, missing, stale, partial, degraded, insufficient-evidence, conflicting, neutral, supportive, cautionary, and failed factor or signal states instead of silently omitting weak inputs;
* connect factor and multi-source signal evidence into report context and strategy interpretation as conservative source-aware evidence while leaving M14 intelligence fusion and decision-policy replacement out of scope;
* ensure Codex may explain Halpha-generated feature, factor, and signal material but must not create feature records, factor scores, signal states, action levels, forecasts, or trading advice;
* support focused validation through existing run, until-stage, single-stage, data inspection, no-Codex, and full Codex product paths;
* add tests for contract shape, multi-source feature extraction, factor scoring, source agreement, source conflict, missing input, stale input, material boundaries, Codex input boundaries, data-quality visibility, and report constraints;
* verify the M13 product path with automated tests and real-source local runs.

M13 favors:

* deterministic, inspectable feature and factor records over hidden scoring logic;
* a small useful factor taxonomy over a broad premature factor library;
* source-aware and uncertainty-aware records over blended black-box scores;
* additive artifacts over replacing existing strategy, risk, event, macro, derivatives, on-chain, outcome, or data-quality artifacts;
* bounded AI-readable material over raw record dumps;
* conservative normalized research signals over trading advice or portfolio actions;
* preserving the main command path: `python -m halpha run --config config.example.yaml`.

M13 does not require:

* broad factor libraries, ML factor discovery, factor optimization, feature-store services, vector databases, or hidden model state;
* M14 intelligence fusion, fusion-driven decision-policy replacement, automatic strategy promotion, or strategy lifecycle automation;
* user-state personalization, dashboard UI, hosted services, scheduler, daemon, websocket, push notification, or alert delivery runtime;
* new derivatives, macro, on-chain, event, or market data sources beyond existing implemented sources;
* portfolio automation, position sizing, trading execution, broker integration, or exchange account operations;
* making Codex or another LLM the source of feature records, factor scores, normalized signal states, risk levels, action recommendations, forecasts, or trading advice.

## Completed Milestones

### M12 - On-Chain and Exchange Flow Context Foundation

Status: completed.

Goal:

```text
Add conservative on-chain and exchange-flow context for crypto-specific liquidity, network-activity, and source-availability risk evidence without turning Halpha into an on-chain analytics platform, address-labeling system, or predictive flow model.
```

The loop is complete when Halpha can:

* preserve the M11 macro/calendar, M10 derivatives, market-structure, outcome tracking, data-quality, event intelligence, alert decision, strategy evaluation, decision-intelligence, Codex context, and report paths instead of replacing them;
* define durable on-chain and exchange-flow contracts for stablecoin supply, broad chain activity, network congestion, exchange-flow source availability, source metadata, freshness, warnings, errors, and Codex boundaries;
* collect configured public on-chain or flow evidence from stable unauthenticated sources where available;
* produce inspectable raw, reusable local-history, current-run view, analysis, and material artifacts without embedding full reusable stores into Codex input;
* normalize flow evidence with asset or chain scope, data class, source refs, observation timestamp, metric units, freshness state, warnings, and errors;
* explicitly distinguish implemented, skipped, unavailable, stale, partial, degraded, normal, abnormal, insufficient-data, and failed data classes instead of silently treating missing flow evidence as neutral;
* generate deterministic on-chain flow context artifacts such as `analysis/onchain_flow_context.json` with stablecoin liquidity, chain activity, network congestion, and exchange-flow source-availability states;
* generate bounded `analysis/onchain_flow_material.md` for Codex and final report generation;
* connect on-chain flow context into market regime, risk assessment, decision recommendations, watch triggers, alert decisions, outcome accountability, and strategy interpretation only as conservative evidence;
* ensure Codex may explain Halpha-generated on-chain flow context but must not create on-chain events, address labels, exchange-flow states, risk levels, price forecasts, or trading instructions;
* support focused validation through existing run, until-stage, single-stage, data inspection, no-Codex, and full Codex product paths;
* add tests for config validation, public source parsing, disabled source, missing source, stale data, partial collection, abnormal stablecoin supply change, elevated network activity, network congestion, exchange-flow unavailable behavior, risk integration, watch trigger integration, material boundaries, and report constraints;
* verify the M12 product path with automated tests and real-source local runs.

M12 favors:

* stable public unauthenticated sources over paid terminals, account APIs, address-labeling vendors, or fragile scraped pages;
* broad liquidity and network-activity context over address-level forensic analytics;
* deterministic Halpha-owned context states over AI-generated flow interpretation;
* source availability and degraded-state records over fabricated exchange-flow metrics;
* bounded on-chain context over large raw chain or address dumps;
* conservative use in risk, watch, alert, and report interpretation over directional prediction;
* preserving the main command path: `python -m halpha run --config config.example.yaml`.

M12 does not require:

* full on-chain analytics, wallet clustering, address labeling, entity attribution, token transfer graph analysis, or exchange reserve proof;
* authenticated APIs, paid data vendors, hosted services, account-specific data, exchange account access, balances, orders, deposits, withdrawals, or user wallet access;
* reliable exchange netflow where only paid, account-bound, proprietary, or non-periodic sources are available;
* websocket streaming, mempool monitoring runtime, scheduler, daemon, push notification, dashboard, or alert delivery runtime;
* portfolio automation, position sizing, trading execution, broker integration, or exchange account operations;
* user-state personalization, unified feature and factor engine, intelligence fusion layer, or strategy lifecycle automation;
* making Codex or another LLM the source of on-chain records, flow states, risk levels, watch triggers, alert priorities, forecasts, or trading advice.

### M11 - Macro and Calendar Context Foundation

Status: completed.

Goal:

```text
Add macro and scheduled-event context as conservative risk, watch-condition, event-intelligence, and report evidence without turning Halpha into a macro forecaster or alert runtime.
```

The loop is complete when Halpha can:

* preserve the M10 derivatives, market-structure, outcome tracking, data-quality, event intelligence, alert decision, strategy evaluation, decision-intelligence, Codex context, and report paths instead of replacing them;
* define durable macro and calendar contracts for scheduled economic releases, central-bank events, broad macro proxy observations where stable public sources are available, source metadata, freshness, impact scope, warnings, errors, and Codex boundaries;
* collect configured public macro and calendar evidence from stable unauthenticated sources where available;
* produce inspectable raw, reusable local-history, current-run view, analysis, and material artifacts without embedding full reusable stores into Codex input;
* normalize scheduled catalysts with event time, source time zone, affected market scope, event class, importance, source refs, freshness state, warnings, and errors;
* explicitly distinguish upcoming scheduled risk from confirmed realized market impact;
* explicitly distinguish implemented, skipped, unavailable, stale, partial, degraded, no-event, and failed data classes instead of silently treating missing macro evidence as neutral;
* generate deterministic macro and calendar context artifacts such as `analysis/macro_calendar_context.json` with scheduled catalyst, recent catalyst, no-event, stale, and unavailable states;
* generate bounded `analysis/macro_calendar_material.md` for Codex and final report generation;
* connect macro and calendar context into market regime, risk assessment, decision recommendations, watch triggers, alert decisions, outcome accountability, and strategy interpretation only as conservative evidence;
* ensure Codex may explain Halpha-generated macro and calendar context but must not create macro events, infer missing source data, assign risk levels, forecast releases, or generate trading instructions;
* support focused validation through existing run, until-stage, single-stage, data inspection, no-Codex, and full Codex product paths;
* add tests for upcoming event, recent event, no-event, stale calendar, missing source, duplicate event, source-time-zone handling, partial collection, risk integration, watch trigger integration, material boundaries, and report constraints;
* verify the M11 product path with automated tests and real-source local runs.

M11 favors:

* scheduled catalyst awareness over macro prediction;
* official or stable public sources over terminal-only, paid, authenticated, or fragile scraped data;
* deterministic Halpha-owned context states over AI-generated macro interpretation;
* bounded macro context over large calendar dumps;
* explicit source availability, freshness, and time-zone states over fabricated neutral evidence;
* preserving the main command path: `python -m halpha run --config config.example.yaml`.

M11 does not require:

* macro forecasting, economic surprise modeling, nowcasting, central-bank policy prediction, or asset price prediction;
* paid data terminals, authenticated APIs, hosted services, or account-specific data;
* scheduler, daemon, websocket, push notification, dashboard, or alert delivery runtime;
* portfolio automation, position sizing, trading execution, exchange account access, or broker integration;
* on-chain flow, user-state personalization, unified feature and factor engine, intelligence fusion layer, or strategy lifecycle automation;
* making Codex or another LLM the source of macro events, risk levels, watch triggers, alert priorities, forecasts, or trading advice.

### M10 - Derivatives and Market Structure Data Foundation

Status: completed.

Goal:

```text
Add the first high-value non-price market context that materially improves risk, regime, strategy, decision, alert, outcome, and report interpretation through source-aware derivatives and bounded market-structure evidence.
```

The loop is complete when Halpha can:

* preserve the M9 outcome tracking, local research data, data-quality, event intelligence, alert decision, strategy evaluation, decision-intelligence, Codex context, and report paths instead of replacing them;
* define durable derivatives and market-structure data contracts for funding rates, open interest, premium or basis, bounded spread or depth summaries, liquidation-summary source availability, quality checks, downstream consumers, and Codex boundaries;
* collect configured public derivatives and market-structure data from stable unauthenticated sources where available;
* produce inspectable raw, reusable local-history, current-run view, analysis, and material artifacts without embedding full reusable stores into Codex input;
* normalize funding, open interest, mark or index premium, basis, spread, depth, and liquidation-summary availability or evidence into source-aware records with symbol, market type, timestamp, source endpoint, value units, warnings, and errors;
* explicitly distinguish implemented, skipped, unavailable, stale, partial, degraded, and failed data classes instead of silently treating missing derivatives evidence as neutral;
* generate deterministic derivatives context artifacts such as `analysis/derivatives_market_context.json` with leverage, funding, open-interest, premium or basis, liquidity, market-structure, and liquidation-availability states;
* generate bounded `analysis/derivatives_market_material.md` for Codex and final report generation;
* connect derivatives context into market regime, risk assessment, decision recommendations, watch triggers, alert decisions, outcome accountability, and strategy interpretation only as conservative evidence;
* ensure Codex may explain Halpha-generated derivatives context but must not create derivatives signals, infer missing market-structure data, assign risk levels, or generate trading instructions;
* support focused validation through existing run, until-stage, single-stage, data inspection, no-Codex, and full Codex product paths;
* add tests for source parsing, config validation, missing source, stale data, partial collection, extreme funding, open-interest expansion, premium or basis stress, spread or depth degradation, liquidation-source unavailable behavior, risk integration, material boundaries, and report constraints;
* verify the M10 product path with automated tests and real-source local runs.

M10 favors:

* derivatives and market-structure context over broader data expansion;
* public unauthenticated endpoints over account, order, position, margin, or trading APIs;
* low-frequency bounded summaries over streaming microstructure;
* deterministic Halpha-owned context states over AI-generated market-structure conclusions;
* explicit source availability and quality states over fabricated neutral evidence;
* preserving the main command path: `python -m halpha run --config config.example.yaml`.

M10 does not require:

* exchange account access, balances, orders, positions, margin state, portfolio automation, trading execution, or position sizing;
* websocket streaming, tick storage, high-frequency order-book replay, scheduler, daemon, or alert delivery runtime;
* execution-grade market microstructure, slippage modeling from order books, or liquidation monitoring service;
* new exchange coverage beyond the first configured stable public source;
* macro data, on-chain data, user-state personalization, dashboard UI, hosted services, ML prediction, or automatic strategy optimization;
* making Codex or another LLM the source of derivatives context, risk levels, market-structure conclusions, action recommendations, alert priorities, or price forecasts.

### M9 - Outcome Tracking and Research Feedback Foundation

Status: completed.

Goal:

```text
Turn prior Halpha signals, event assessments, alert decisions, and decision-support recommendations into deterministic outcome records that show what later happened, improve research accountability, and feed future calibration without turning Halpha into trading execution or a forecasting guarantee.
```

The loop is complete when Halpha can:

* preserve the M8 local research data catalog, run index, text-event history, data-quality summary, Codex context governance, strategy evaluation, decision-intelligence, event assessment, alert decision, and report path instead of replacing them;
* define durable outcome tracking contracts for outcome targets, source records, as-of timestamps, maturity horizons, evaluation windows, observable metrics, outcome states, warnings, and downstream consumers;
* identify prior evaluable records from the local run index and per-run artifacts, including market signals, strategy gate outcomes, event intelligence assessments, alert decisions, decision recommendations, watch triggers, and data-quality summaries;
* create stable outcome target records with source run id, source artifact, source record id, asset, timeframe, source timestamp, target kind, evaluation horizon, maturity status, expected observation, evidence references, and uncertainty notes;
* evaluate matured market and strategy outcomes from shared OHLCV history using only data after the source timestamp, with explicit no-lookahead rules, data availability checks, return windows, directional alignment, drawdown or adverse excursion where practical, threshold hits, and insufficient-data states;
* evaluate event, alert, and decision follow-through from later Halpha artifacts and reusable text-event history, using deterministic states such as confirmed, contradicted, unresolved, stale, skipped, or insufficient-data rather than subjective hindsight claims;
* persist reusable outcome history outside per-run report directories with stable outcome keys, source run ids, evaluation run ids, maturity horizon, status, metrics, warnings, errors, and source artifact references;
* generate current-run outcome artifacts such as `analysis/outcome_targets.json`, `analysis/outcome_evaluations.json`, and bounded `analysis/outcome_tracking_material.md`;
* connect outcome tracking references into the local research data catalog, run index summaries, data inspection output, research context, Codex context, and the final Simplified Chinese Markdown report only as bounded accountability evidence;
* ensure Codex may explain Halpha-generated outcome states but must not create outcome labels, validate missing histories, infer omitted store contents, or score prior recommendations independently;
* support focused validation through existing run, until-stage, single-stage, and narrow standalone or inspection paths without collecting unnecessary new data or running Codex CLI;
* add tests and golden cases for no-lookahead windows, pending versus matured targets, insufficient OHLCV data, directional alignment, adverse excursion, event follow-through, alert follow-through, decision follow-through, duplicate outcome keys, manifest references, and Codex input boundaries;
* verify the M9 product path with automated tests and real-source local runs, including no-Codex validation and full report validation when Codex CLI use is permitted.

M9 favors:

* research feedback loops over more one-off signal generation;
* post-run evaluation and horizon labeling practices from quantitative research over subjective report grading;
* as-of timestamps, maturity horizons, and no-lookahead checks over convenient but biased hindsight;
* append-only, idempotent local outcome history over mutable hidden state;
* deterministic metrics and state machines over ML-generated correctness scores;
* local JSON, Markdown, Parquet, and SQLite summaries that fit the existing M8 data lake shape;
* explicit pending, matured, evaluated, skipped, stale, insufficient-data, warning, degraded, and failed states over silent omissions;
* bounded Codex context that summarizes outcome evidence instead of embedding full outcome history or raw stores;
* source-linked accountability language that improves report honesty without claiming predictive certainty;
* preserving the main command path: `python -m halpha run --config config.example.yaml`.

M9 does not require:

* live trading execution, order placement, position sizing, portfolio automation, broker or exchange account operations, or realized account PnL;
* judging whether a recommendation was profitable for a user portfolio;
* automatic strategy promotion, parameter optimization, or model retraining based on outcome scores;
* machine learning prediction, reinforcement learning, feature-store design, or custom outcome scoring models;
* new exchange, derivatives, macro, on-chain, market-structure, or public text data sources;
* scheduler, daemon, websocket, streaming, high-frequency polling, or continuous monitoring runtime;
* hosted databases, cloud warehouse deployment, distributed processing, Kafka, Spark, Airflow, Prefect, Redis, Celery, dashboards, or notebook workbenches;
* perfect semantic understanding of event consequences or complete external-world validation;
* storing full reusable outcome history, raw text archives, SQLite tables, Parquet tables, or local data lake tables in Codex context;
* making Codex or another LLM the source of outcome labels, correctness judgments, strategy promotion, alert validation, action recommendations, or price forecasts;
* claiming that favorable historical outcomes guarantee future performance, safe trading, or investment suitability.

### M8 - Local Research Data Lake and Data Quality Foundation

Status: completed.

Goal:

```text
Make local long-term research data, run indexes, reusable text-event history, and data-quality evidence first-class pipeline inputs for future strategy, event, outcome, and monitoring workflows while preserving inspectable per-run artifacts and bounded Codex inputs.
```

The loop is complete when Halpha can:

* preserve the M7 event assessment, alert decision, artifact governance, decision-intelligence, strategy evaluation, text-event intelligence, Codex context, and report path instead of replacing it;
* define durable local research data lake, run index, text-event history, and data-quality contracts in stable project documentation;
* keep shared OHLCV history as reusable local input data outside per-run report directories while making its schema, partitions, source coverage, and update state discoverable through catalog metadata;
* create a local research data catalog that records implemented stores, schemas, partition rules, unique keys, source identity, latest update status, and downstream consumers without exposing machine-local private paths;
* create a local run index that records run IDs, stage status, generated artifacts, key counts, warnings, errors, completion status, and latest successful run references using repo-relative or config-relative paths;
* persist normalized text-event history outside per-run report directories with stable event keys, source identity, canonical URLs, timestamps, content hashes, duplicate grouping, originating run IDs, warnings, and source artifact references;
* deduplicate reusable text-event history deterministically so repeated public items remain traceable without silently hiding conflicts or source changes;
* generate `analysis/data_quality_summary.json` for each product run, covering current-run market data, text data, shared store reuse, schema checks, timestamp checks, duplicate checks, stale data, partial collection failure, degraded states, warnings, and source artifacts;
* connect data-quality summary and local-store references into `run_manifest.json`, research context, Codex context, and the final Simplified Chinese Markdown report only as bounded, decision-relevant evidence;
* ensure Codex input uses concise quality and store summaries instead of full reusable history, raw text archives, or local data lake tables;
* support focused validation through existing run, until-stage, single-stage, and narrowly scoped local inspection paths without fabricating skipped artifacts;
* add tests for catalog records, run index writes, text-event history append and deduplication, quality checks, stale or malformed timestamps, schema drift, partial source failure, manifest references, and Codex input boundaries;
* verify the M8 product path with automated tests and real-source local runs, including no-Codex validation and full report validation when Codex CLI use is permitted.

M8 favors:

* durable local evidence and quality metadata over per-run-only memory;
* Parquet-backed reusable tables for appendable analytical history where practical;
* SQLite for small mutable indexes such as run indexes and latest pointers where plain files become insufficient;
* JSON manifests and Markdown material as stable Halpha-owned downstream contracts;
* deterministic schema, timestamp, source, duplicate, and staleness checks over hidden framework validation state;
* clear separation between raw inputs, reusable local history, current-run views, analysis artifacts, AI-readable material, and final reports;
* repo-relative or config-relative artifact references over machine-local absolute paths;
* bounded Codex context that summarizes quality and relevance instead of embedding large historical stores;
* explicit `ok`, `warning`, `degraded`, `skipped`, and `failed` states over silent data-quality assumptions;
* preserving the main command path: `python -m halpha run --config config.example.yaml`.

M8 does not require:

* outcome tracking for prior recommendations, strategy signals, or alert decisions;
* new exchange, derivatives, macro, on-chain, market-structure, or public text data sources;
* replacing the existing OHLCV store, strategy evaluation layer, text-event intelligence layer, event assessment layer, alert decision layer, or report generation path;
* broad data lake governance, cloud object storage, remote sync, warehouse deployment, hosted database service, or distributed processing;
* adopting Apache Iceberg, Delta Lake, Great Expectations, Kafka, Spark, Airflow, Prefect, Redis, Celery, vector databases, or a microservice architecture;
* making DuckDB, SQL workbenches, dashboards, or ad hoc analytical notebooks part of the required product path;
* storing full reusable history in Codex context or asking Codex to validate data quality;
* automatic data repair that rewrites source evidence without traceable warnings;
* scheduler, daemon, websocket, streaming, high-frequency polling, or continuous monitoring runtime;
* trading execution, order placement, position sizing, portfolio automation, account connection, or exchange account operations;
* claiming that higher data quality guarantees profitable signals, forecasts, or trading outcomes.

### M7 - Alert Decision and Event Reassessment Foundation

Status: completed.

Goal:

```text
Turn structured event intelligence into deterministic event assessment and alert-decision artifacts that explain whether real public events change current decision intelligence, require user attention, or should remain archived low-value noise while preserving local-first artifacts and keeping alert delivery runtime out of scope.
```

The loop is complete when Halpha can:

* preserve the M6 text-event normalization, NLP evidence, topic grouping, event signal, event-market confluence, Codex context, and report path instead of replacing it;
* preserve the existing strategy benchmark, strategy gate, market signal, regime, risk, decision recommendation, watch trigger, previous-run delta, and report path instead of replacing it;
* define durable event assessment and alert decision contracts in the existing event-intelligence and decision-intelligence contract documents;
* generate `analysis/event_intelligence_assessment.json` from current event, market, strategy, regime, risk, decision, and watch-trigger artifacts;
* record affected assets, relevant timeframes, source reliability, event severity, market response relationship, decision impact, confidence, downgrade reasons, uncertainty, warnings, and source artifacts for every assessed event or topic;
* generate `analysis/alert_decisions.json` with deterministic P0, P1, P2, P3, or no-alert outcomes, where alert priority is based on evidence strength, event severity, risk escalation, decision impact, and watch or invalidation relevance;
* keep low-confidence, unrelated, stale, duplicate, or insufficient-evidence events visible as downgraded records instead of silently dropping them or promoting them into alerts;
* generate bounded AI-readable alert or event brief material from event assessment and alert decision artifacts;
* connect event assessment and alert decisions into research context, Codex context, and the final Simplified Chinese Markdown report without letting Codex invent event severity, alert priority, decision impact, or action levels;
* record artifact paths, counts, alert-priority coverage, downgrade coverage, warnings, errors, and degraded states in `run_manifest.json`;
* support focused validation through the existing run, until-stage, and single-stage command paths without fabricating skipped artifacts;
* add tests and fixture-based golden cases for high-severity escalation, risk or decision impact, low-confidence downgrade, unrelated event suppression, duplicate or stale event downgrade, missing-upstream behavior, and report-facing material boundaries;
* verify the M7 product path with automated tests and real-source local runs, including no-Codex validation and full report validation when Codex CLI use is permitted.

M7 favors:

* attention quality and noise suppression over pushing more messages;
* deterministic event assessment and alert priority gates over AI-generated alert decisions;
* evidence-linked P0, P1, P2, P3, and no-alert outcomes over unstructured event summaries;
* explicit downgrade, skipped, stale, duplicate, insufficient-evidence, and degraded states over fabricated urgency;
* connecting events to existing risk, decision, watch trigger, and strategy evidence before claiming user relevance;
* small, inspectable Halpha-owned JSON and Markdown artifacts over hidden runtime state;
* report language that separates event facts, market response, decision impact, uncertainty, and user attention priority;
* preserving the main command path: `python -m halpha run --config config.example.yaml`.

M7 does not require:

* scheduler, daemon, websocket, streaming, high-frequency polling, or continuous 7x24 monitoring runtime;
* email, Telegram, Discord, Slack, Feishu, WeCom, mobile push, or any other alert delivery channel;
* alert cooldown stores, duplicate-delivery suppression across background runs, or monitoring health service;
* new exchange, derivatives, macro, on-chain, or market-structure data sources;
* user profiles, user positions, risk preference configuration, account connection, or exchange account operations;
* dashboard UI, hosted service design, local web service, or workbench;
* database service, vector database, state store redesign, microservices, Kafka, Redis, Celery, or Prefect;
* training custom NLP, ML, or LLM models;
* making Codex or another LLM the source of event assessment, alert priority, decision impact, action recommendations, or price forecasts;
* claiming that an alert decision predicts price, guarantees a market move, or supports trading execution.

### M6 - Pretrained NLP Event Intelligence Foundation

Status: completed.

Goal:

```text
Turn raw public text events into a pretrained-NLP-assisted, source-aware event intelligence layer that normalizes, deduplicates, classifies, and connects market-relevant events to quant and decision artifacts while preserving Halpha-owned deterministic artifact contracts and conservative report boundaries.
```

The loop is complete when Halpha can:

* preserve the M5 strategy benchmark, experiment, gate, decision-intelligence, Codex context, and report path instead of replacing it;
* preserve existing raw text collection and `analysis/text_material.md` as source-aware text material while adding deeper event-intelligence artifacts;
* introduce optional local NLP runtime support for pretrained models without hidden model downloads during normal product runs;
* normalize `raw/text_events.json` into stable event records that preserve source, URL, canonical URL, timestamps, normalized text, warnings, and source artifact references;
* support standalone text-intelligence execution from configured public text sources and from an existing local `raw/text_events.json` artifact;
* use pretrained sentence embeddings for duplicate detection and same-topic grouping, with deterministic merge gates and explicit duplicate, same-topic, related-context, or distinct decisions;
* use pretrained zero-shot classification, financial-tone classification, and open entity extraction as evidence generators for event taxonomy, asset relevance, source context, and topic interpretation;
* keep Halpha-owned deterministic gates as the final authority for accepted event categories, asset relevance, event signals, topic grouping, confidence, warnings, and degraded states;
* generate `analysis/text_event_records.json`, `analysis/text_event_topics.json`, `analysis/text_event_signals.json`, `analysis/event_market_confluence.json`, and `analysis/event_intelligence_material.md`;
* connect event signals with current quant, strategy gate, risk, and decision artifacts so reports can explain event-quant confluence, conflict, or independence;
* record model names, model revisions, thresholds, scores, rule evidence, acceptance or downgrade reasons, warnings, errors, and degraded or skipped model states in inspectable artifacts or manifests;
* add golden text-event fixtures and accuracy checks for high-confidence asset relevance, category classification, duplicate safety, topic grouping, and evidence traceability;
* support human review of recent real-source event-intelligence artifacts as part of local acceptance, with representative misclassifications captured as regression fixtures;
* produce a Simplified Chinese Markdown report that explains structured event evidence, event uncertainty, and event-quant relationships without letting Codex invent event categories, event impacts, action levels, or price forecasts;
* keep the M6 product path covered by tests and verified by standalone text-intelligence and real-source product runs.

M6 favors:

* pretrained NLP models as auditable evidence generators over hand-written-only text processing;
* deterministic Halpha gates over direct model decisions;
* precision for accepted high-confidence event outputs over broad but weak recall;
* explicit `unknown`, `low_confidence`, `skipped`, and `degraded` states over fabricated certainty;
* model metadata, thresholds, scores, matched evidence, and source references in every durable artifact;
* standalone text-intelligence commands that allow quick local validation without running the full report pipeline;
* golden fixtures and human review over trusting a pretrained model in isolation;
* event-quant confluence and conflict interpretation over simple news listing;
* simple, inspectable Halpha-owned JSON and Markdown artifacts over hidden framework objects;
* conservative report language that separates evidence, assumptions, uncertainty, and judgment;
* preserving the main command path: `python -m halpha run --config config.example.yaml`.

M6 does not require:

* training custom NLP, ML, or LLM models from scratch;
* using hosted NLP APIs or remote inference services;
* making pretrained models the final source of event categories, asset relevance, decision recommendations, or report conclusions;
* claiming that event classification is complete semantic understanding;
* perfect duplicate detection or perfect topic clustering for all public text;
* automatic parameter optimization or best-parameter selection;
* additional quantitative strategy candidates;
* portfolio allocation optimization;
* trading execution, order placement, position sizing, or exchange account operations;
* real-time event streaming, scheduler, websocket, daemon, alert delivery runtime, Kafka, Redis, or Celery;
* new exchange or market data sources;
* broad public text source expansion before the configured sources are structured well;
* dashboard UI or hosted service design;
* database service, vector database, state store redesign, microservices, or feature-store design;
* making Codex or another LLM the source of event classification, event impact, event-quant confluence, or action recommendations;
* claiming that an event signal predicts price, guarantees a market move, or supports trading execution.

### M5 - Strategy Iteration and Validation Foundation

Status: completed.

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
