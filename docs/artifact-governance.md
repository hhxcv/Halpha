# Artifact Governance

This document defines how Halpha artifacts are layered, consumed, and admitted
into Codex input. It is a durable contract for humans and AI agents. It is not a
milestone plan.

## Related Docs

- `README.md`: project overview, commands, and product validation.
- `AGENTS.md`: AI-agent rules, artifact expectations, and validation rules.
- `docs/quant-contracts.md`: market data, strategy, evaluation, signal, and
  strategy-material contracts.
- `docs/strategy-lifecycle-contracts.md`: strategy lifecycle state, policy,
  material, downstream, and Codex-boundary contracts.
- `docs/derivatives-market-contracts.md`: derivatives and
  market-structure data, context, material, and Codex-boundary contracts.
- `docs/macro-calendar-contracts.md`: macro and scheduled-event data, context,
  material, and Codex-boundary contracts.
- `docs/onchain-flow-contracts.md`: on-chain and exchange-flow data, context,
  material, and Codex-boundary contracts.
- `docs/feature-factor-contracts.md`: feature, factor, multi-source signal,
  material, and Codex-boundary contracts.
- `docs/intelligence-fusion-contracts.md`: fusion artifact, planned material,
  integration, and Codex-boundary contracts.
- `docs/user-state-contracts.md`: optional local user-state,
  personalized-risk, material, privacy, and Codex-boundary contracts.
- `docs/monitoring-contracts.md`: local monitor configuration, cycle,
  alert archive, health, privacy, and Codex-boundary contracts.
- `docs/delivery-workbench-contracts.md`: local delivery and workbench summary,
  index, source-ref, privacy, and Codex-boundary contracts.
- `docs/product-stability-contracts.md`: product validation, run health,
  backup boundary, operational acceptance, privacy, and Codex-boundary
  contracts.
- `docs/logging-standards.md`: local JSON logging levels, event shape,
  privacy boundaries, context fields, and anti-noise rules.
- `docs/dashboard-contracts.md`: local web dashboard, command, job, schedule,
  artifact preview, privacy, and Codex-boundary contracts.
- `docs/research-data-contracts.md`: shared local research data, run index,
  text-event history, and data-quality contracts.
- `docs/event-intelligence-contracts.md`: text event, NLP evidence, topic,
  event signal, confluence, assessment, and event-material contracts.
- `docs/decision-intelligence-contracts.md`: regime, risk, recommendation,
  watch trigger, delta, alert decision, and decision-material contracts.
- `docs/outcome-tracking-contracts.md`: outcome target, evaluation, history,
  material, and Codex-boundary contracts.

## Layer Rules

Halpha keeps complete evidence artifacts inspectable, but Codex input must use
bounded report-facing material.

| Layer | Purpose | Codex input status |
| --- | --- | --- |
| Raw collection | Preserve public source observations exactly enough for audit. | Not embedded by default. Referenced by path and summarized through material. |
| Shared reusable data | Preserve reusable local data such as OHLCV history. | Not embedded. Referenced only through current-run views and bounded material. |
| Intermediate evidence | Preserve deterministic JSON evidence, scores, diagnostics, and links. | Not embedded in full. Referenced by path and summarized through material. |
| Report-facing material | Convert evidence into bounded AI-readable Markdown. | Eligible for embedding in research context. |
| Research context | Combine selected material and generation constraints. | Embedded into Codex context. |
| Codex prompt | Wrap research context with report-generation rules. | Sent to Codex CLI through stdin. |
| Final report | Generated Simplified Chinese Markdown plus deterministic post-processing tables. | Output, not upstream input. |
| Delivery/workbench output | Surface existing evidence and report links as a local delivery snapshot and CLI fallback. | Not embedded by default. Not upstream input. |
| Dashboard control state | Record local web UI jobs, logs, schedule state, and UI control metadata. | Not embedded by default. Not upstream evidence. |
| Manifest | Record lifecycle, artifacts, counts, warnings, errors, and Codex input budget. | Not embedded in full. Used for audit. |

Shared reusable data contracts are defined in
`docs/research-data-contracts.md`. This document owns Codex input admission
rules for those contracts.

## Flow And Artifacts

### Raw Collection

Produced early in a product run:

- `raw/market.json`
- `raw/macro_calendar.json`
- `raw/onchain_flow.json`
- `raw/text_events.json`

These preserve public collection results. They are not Codex context by
themselves.

### Shared Market History

Reusable input data:

- `data/market/ohlcv/`
- `data/market/metadata/ohlcv_schema.json`
- `data/market/metadata/ohlcv_sync_state.json`
- `data/macro/calendar/`
- `data/macro/metadata/macro_calendar_schema.json`
- `data/macro/metadata/macro_calendar_state.json`
- `data/onchain/flow/`
- `data/onchain/metadata/onchain_flow_schema.json`
- `data/onchain/metadata/onchain_flow_state.json`
- `data/research/metadata/research_data_catalog.json`
- `data/research/metadata/text_event_history_state.json`
- `data/research/text_events/`

Shared OHLCV history, reusable text-event history, and the research data
catalog stay outside per-run report directories and must not be embedded into
Codex input.

### Current-Run Data Views

Current-run market windows and storage references:

- `raw/market_data_views.json`
- `raw/derivatives_market_views.json`
- `raw/macro_calendar_views.json`
- `raw/onchain_flow_views.json`

These artifacts record view metadata and bounded current-run windows, not full
raw OHLCV, derivatives history, macro/calendar history, or on-chain flow
history.

### Derivatives And Market-Structure Evidence

Derivatives artifacts:

- `raw/derivatives_market.json`
- `data/market/derivatives/`
- `data/market/metadata/derivatives_market_schema.json`
- `data/market/metadata/derivatives_market_state.json`
- `raw/derivatives_market_views.json`
- `analysis/derivatives_market_context.json`
- `analysis/derivatives_market_material.md`

These artifacts preserve funding, open-interest, premium or basis, bounded
spread or depth, and liquidation-source availability evidence. The implemented
context artifact currently covers deterministic funding, open-interest, premium,
basis, bounded liquidity-depth, and liquidation-availability states. Codex
should consume bounded `analysis/derivatives_market_material.md` instead of
full raw, history, view, or context artifacts.

### Macro And Calendar Evidence

Macro/calendar artifacts:

- `raw/macro_calendar.json`
- `data/macro/calendar/`
- `data/macro/metadata/macro_calendar_schema.json`
- `data/macro/metadata/macro_calendar_state.json`
- `raw/macro_calendar_views.json`
- `analysis/macro_calendar_context.json`
- `analysis/macro_calendar_material.md`

These artifacts preserve configured public macro and scheduled-event
observations such as Federal Reserve FOMC meeting calendar records when enabled.
The reusable history, current-run views, and deterministic context are
source-aware input or analysis data, not Codex context by themselves.
Risk, decision, and watch-trigger artifacts may cite bounded macro/calendar
context records as conservative source-linked evidence. Codex should consume
bounded `analysis/macro_calendar_material.md` instead of raw macro/calendar
artifacts, reusable macro/calendar history, macro/calendar views, or full
macro/calendar context JSON.

### On-Chain And Exchange-Flow Evidence

On-chain flow artifacts:

- `raw/onchain_flow.json`
- `data/onchain/flow/`
- `data/onchain/metadata/onchain_flow_schema.json`
- `data/onchain/metadata/onchain_flow_state.json`
- `raw/onchain_flow_views.json`
- `analysis/onchain_flow_context.json`
- `analysis/onchain_flow_material.md`

`raw/onchain_flow.json` preserves configured public stablecoin supply, broad
chain activity, network congestion, and exchange-flow source-availability
evidence when enabled. Reusable history, current-run views, and deterministic
context are source-aware input or analysis data, not Codex context by
themselves. Codex should consume bounded `analysis/onchain_flow_material.md` instead of
raw on-chain flow artifacts, reusable on-chain flow history, on-chain flow
views, or full on-chain flow context JSON.

### Text Intelligence Evidence

Source-aware event processing artifacts:

- `analysis/text_event_records.json`
- `analysis/text_entity_evidence.json`
- `analysis/text_event_classification_evidence.json`
- `analysis/text_event_topics.json`
- `analysis/text_event_signals.json`

These are complete evidence artifacts. Codex should consume
`analysis/event_intelligence_material.md` and `analysis/text_material.md`
instead of full JSON records.

### Quantitative Evidence

Strategy and signal artifacts:

- `analysis/strategy_benchmark_suite.json`
- `analysis/quant_strategy_runs.json`
- `analysis/strategy_evaluation_summary.json`
- `analysis/strategy_experiment.json`
- `analysis/strategy_effectiveness_gates.json`
- `analysis/market_strategy_signals.json`
- `analysis/market_signals.json`

Codex should consume bounded strategy and signal material instead of full
strategy run, benchmark, or experiment JSON.

### Strategy Lifecycle Evidence

Strategy lifecycle artifacts:

- `analysis/strategy_lifecycle_state.json`
- `analysis/strategy_lifecycle_material.md`

These contracts are defined in `docs/strategy-lifecycle-contracts.md`. The
implemented lifecycle state artifact records deterministic strategy identity,
contract version, parameter version, parameter digest, lifecycle status,
degradation, insufficient-evidence, watchlist, rejection, retirement, policy,
warnings, errors, and source refs from existing strategy and outcome evidence
when quant strategy evidence is enabled.
The lifecycle material artifact is the bounded Codex-facing summary. Codex
should consume bounded lifecycle material instead of full lifecycle JSON,
full strategy runs, full outcome history, or local lifecycle policy input.

### Feature, Factor, And Multi-Source Signal Evidence

Feature/factor artifacts:

- `analysis/feature_snapshots.json`
- `analysis/factor_states.json`
- `analysis/multi_source_signals.json`
- `analysis/factor_signal_material.md`

These contracts are defined in `docs/feature-factor-contracts.md`. Product runs
generate `analysis/feature_snapshots.json`, `analysis/factor_states.json`,
`analysis/multi_source_signals.json`, and bounded
`analysis/factor_signal_material.md`. Feature, factor, and multi-source signal
JSON artifacts are intermediate evidence and should not be embedded in full
Codex input. Codex should consume bounded `analysis/factor_signal_material.md`.

### Intelligence Fusion Evidence

Fusion artifacts:

- `analysis/intelligence_fusion.json`
- `analysis/intelligence_fusion_material.md`

These contracts are defined in `docs/intelligence-fusion-contracts.md`.
Product runs generate `analysis/intelligence_fusion.json`. Fusion JSON remains
intermediate evidence and should not be embedded in full Codex input. Product
runs generate bounded Codex-facing fusion material as
`analysis/intelligence_fusion_material.md`. Product runs also integrate bounded
fusion fields into decision recommendations and alert decisions before research
context is built.

### User State And Personalized Risk Evidence

Personalization contracts:

- `analysis/user_state_context.json`
- `analysis/personalized_risk_constraints.json`
- `analysis/personalized_risk_material.md`

These contracts are defined in `docs/user-state-contracts.md`. Product runs
generate `analysis/user_state_context.json` as optional sanitized local
user-state status and context, and
`analysis/personalized_risk_constraints.json` as deterministic constraints from
sanitized user state plus available current-run intelligence. Constraint JSON is
intermediate evidence and should not be embedded in full Codex input.
Product runs generate bounded Codex-facing personalized-risk material as
`analysis/personalized_risk_material.md`. Raw local user-state files, private
notes, account identifiers, exact holdings, balances, machine paths, full
user-state JSON, and full personalized-risk JSON must not be embedded in Codex
input. Codex should consume bounded `analysis/personalized_risk_material.md`
instead of full user-state or personalized-risk JSON.
Product runs integrate constraints into decision recommendations, watch
triggers, and alert decisions as conservative fields while preserving
pre-personalization values when a record is downgraded or blocked.

### Decision And Risk Evidence

Decision-support artifacts:

- `analysis/market_regime_assessment.json`
- `analysis/risk_assessment.json`
- `analysis/decision_recommendations.json`
- `analysis/watch_triggers.json`
- `analysis/decision_intelligence_delta.json`

Codex should consume `analysis/decision_intelligence_material.md` instead of
full decision JSON.

### Event-Decision Evidence

Event connection and reassessment artifacts:

- `analysis/event_market_confluence.json`
- `analysis/event_intelligence_assessment.json`
- `analysis/alert_decisions.json`

Codex should consume bounded event and alert material. It may explain
Halpha-generated event severity, decision impact, alert priority, downgrade
reasons, and no-alert states, but must not create or revise those fields.

### Data Quality Evidence

Current-run quality artifact:

- `analysis/data_quality_summary.json`
- `analysis/data_quality_material.md`

`analysis/data_quality_summary.json` records deterministic schema, timestamp,
duplicate, shared-store, derivatives, macro/calendar, on-chain flow,
feature/factor, intelligence-fusion, partial-collection, degraded, skipped,
warning, and failed states.
`analysis/data_quality_material.md` is the bounded Codex-facing summary derived
from that JSON. Codex may explain Halpha-generated quality
status, but must not create quality checks, invent validation results, inspect
full shared stores, read SQLite contents, read Parquet tables, or reconstruct
raw archives.

### Outcome Tracking Evidence

Outcome tracking artifacts:

- `analysis/outcome_targets.json`: implemented source-linked targets from the
  latest previous successful run.
- `analysis/outcome_evaluations.json`: implemented market and strategy outcome
  evaluations plus event, alert, decision, and watch follow-through
  evaluations.
- `data/research/outcomes/outcome_history.json`: implemented reusable outcome
  history.
- `data/research/metadata/outcome_history_state.json`: implemented outcome history
  state metadata.

These artifacts record prior research targets, later outcome evaluations, and
reusable outcome history. They are not Codex context by themselves. Codex should
consume bounded `analysis/outcome_tracking_material.md` instead of full target,
evaluation, or history records.

### Local Monitor And Workbench Outputs

Monitor artifacts:

- `runs/monitor/cycles/<cycle_id>/monitor_cycle_manifest.json`
- `runs/monitor/alert_archive.jsonl`
- `runs/monitor/alert_cooldown_state.json`
- `runs/monitor/alert_archive_state.json`
- `runs/monitor/monitor_health_state.json`

Monitor artifacts are local operational state. They are not Codex input by
default.

Workbench delivery artifacts:

- `runs/workbench/latest/workbench_summary.json`
- `runs/workbench/latest/index.md`
- `runs/workbench/latest/index.html`

Workbench artifacts summarize and link to existing deterministic artifacts for
local delivery and CLI inspection or recovery, including bounded
product-validation health when available. They are delivery snapshots, not the
primary UI, not replacements for dashboard views, not upstream analysis inputs,
decision artifacts, alert-priority sources, strategy-gate inputs, validation
authorities, or Codex context by default. Codex should continue to consume
bounded report-facing material rather than full workbench summaries or
generated indexes.

### Local Dashboard Control State

Dashboard contracts are defined in `docs/dashboard-contracts.md`. Dashboard
state records local web UI control metadata such as dashboard service state,
dashboard-triggered jobs, bounded logs, schedule state, and linked source refs.
It is control and delivery state, not upstream research evidence, validation
authority, decision input, alert-priority source, strategy-gate input, or Codex
context by default.

Implemented dashboard control artifacts include:

- `runs/dashboard/service_state.json`
- `runs/dashboard/jobs/index.json`
- `runs/dashboard/jobs/<job_id>/job.json`
- `runs/dashboard/jobs/<job_id>/stdout.log`
- `runs/dashboard/jobs/<job_id>/stderr.log`
- `runs/dashboard/schedules/daily_report_schedule.json`

### Report-Facing Material

Eligible Codex input:

- `analysis/market_material.md`
- `analysis/text_material.md`
- `analysis/market_signal_material.md`
- `analysis/strategy_evaluation_material.md`
- `analysis/strategy_experiment_material.md`
- `analysis/strategy_lifecycle_material.md`
- `analysis/derivatives_market_material.md`
- `analysis/macro_calendar_material.md`
- `analysis/onchain_flow_material.md`
- `analysis/factor_signal_material.md`
- `analysis/personalized_risk_material.md`
- `analysis/decision_intelligence_material.md`
- `analysis/alert_decision_material.md`
- `analysis/event_intelligence_material.md`
- `analysis/data_quality_material.md`
- `analysis/outcome_tracking_material.md`

Material files must stay bounded, source-aware, and explicit about what Codex
may explain versus what Codex must not generate.

### Codex Input And Report Output

Codex-facing artifacts:

- `analysis/research_context.md`
- `codex_context/context.md`
- `codex_context/prompt.md`

Generated output:

- `report/report.md`

Audit artifact:

- `run_manifest.json`

`run_manifest.json` records `codex_input` metadata, including material inclusion
status, character counts, budgets, over-budget flags, and warnings.

Product-stability artifact:

- `analysis/product_contract_validation.json`

This artifact is defined in `docs/product-stability-contracts.md`. It records
deterministic product contract validation, run health, artifact contract checks,
privacy boundaries, Codex boundaries, and operational diagnostics.

## Codex Input Policy

Codex input policy:

- Embed bounded report-facing material only.
- Preserve complete evidence artifacts outside Codex input.
- Do not embed full raw streams.
- Do not embed full intermediate JSON evidence.
- Do not embed full shared OHLCV history.
- Do not embed full reusable outcome history.
- Do not embed full strategy lifecycle JSON or local lifecycle policy input.
- Do not embed full workbench summaries or generated workbench indexes.
- Do not embed full dashboard service state, job histories, logs, or schedule
  state by default.
- Do not embed full product contract validation artifacts by default.
- Do not embed full reusable on-chain flow history.
- Do not embed full feature snapshots, factor states, or multi-source signal
  JSON.
- Do not embed full local user-state files, private notes, account identifiers,
  machine paths, or full personalized-risk JSON.
- Do not embed full run manifests.
- Prefer high-signal decision, risk, alert, event, strategy, gate, outcome, and quality evidence.
- Prefer high-signal derivatives and market-structure context.
- Prefer scheduled-catalyst, no-event, and source-availability macro/calendar context.
- Prefer high-signal on-chain flow context.
- Prefer conflicting, cautionary, degraded, and high-confidence feature/factor
  evidence when factor signal material exists.
- Prefer degraded, retired, watchlisted, rejected, insufficient-evidence, and
  high-confidence strategy lifecycle records when lifecycle material exists.
- Summarize or omit low-priority records with explicit counts and reasons.

Default size budgets:

| Input | Budget |
| --- | ---: |
| Each material block | 12,000 characters |
| Combined material blocks in research context | 120,000 characters |
| `analysis/research_context.md` | 140,000 characters |
| `codex_context/context.md` | 150,000 characters |
| `codex_context/prompt.md` | 170,000 characters |

Material blocks above the per-block budget are compressed into explicit
head-and-tail excerpts in Codex input. The budget records are safeguards and
audit metadata. They do not remove the complete evidence artifacts from disk.
When combined material blocks exceed the research-context material target,
lower-priority material may be compressed again to preserve the full Codex
context and prompt budgets. `run_manifest.json` records this as
`material_compressed_for_context_budget`.

## Material Selection

Report-facing material should preserve high-signal records before low-signal
records.

Alert decision material:

- Retain P0, P1, and P2 records first.
- Sample P3, `no_alert`, and `unknown` records after high-priority records.
- Record selected counts, omitted counts, omitted priority counts, and omission
  reasons in the material and manifest.

Event intelligence material:

- Retain accepted event signals first.
- Sample unknown, low-confidence, skipped, degraded, stale, duplicate, and
  insufficient-evidence records after accepted records.
- Record selected counts, omitted counts, omitted status counts, and omission
  reasons in the material and manifest.

Strategy and decision material:

- Prefer current gate outcomes, decision state, risk state, invalidation
  conditions, watch conditions, uncertainty, and source artifacts.
- Avoid row dumps when a deterministic post-processed table will be inserted
  after Codex stdout validation.

Derivatives market material:

- Prefer high-severity funding, open-interest, premium or basis, liquidity, and
  liquidation-availability records first.
- Summarize neutral, skipped, unavailable, stale, partial, degraded, or
  low-severity records with counts and representative examples only when useful.
- Record unavailable source classes explicitly so missing derivatives evidence
  is not treated as neutral.
- Do not embed full raw derivatives payloads, reusable derivatives history,
  full order-book snapshots, or full context JSON.

Macro calendar material:

- Prefer high-importance scheduled catalysts, recent catalysts, no-event
  windows, and unavailable, stale, degraded, partial, or failed source states.
- Summarize low-signal macro/calendar records with counts and representative
  examples.
- Record source availability explicitly so missing macro/calendar evidence is
  not treated as neutral.
- Distinguish scheduled catalyst timing risk from confirmed realized market
  impact.
- Do not embed full raw macro/calendar payloads, reusable macro/calendar
  history, current-run views, or full context JSON.

On-chain flow material:

- Prefer high-severity stablecoin liquidity, chain activity, network
  congestion, and exchange-flow source-availability records first.
- Summarize normal, skipped, unavailable, stale, partial, degraded, and
  low-severity records with counts and representative examples only when useful.
- Record unavailable source classes explicitly so missing exchange-flow evidence
  is not treated as neutral.
- Do not embed full raw on-chain flow payloads, address-level records, reusable
  on-chain flow history, current-run views, or full context JSON.

Feature/factor material:

- Prefer conflicting, cautionary, degraded, failed, and
  insufficient-evidence factor or signal records before neutral records.
- Preserve high-confidence supportive factor states only when they materially
  explain the current context.
- Summarize omitted low-priority features, factors, and signals with counts and
  reasons.
- Do not embed full raw streams, reusable histories, current-run views,
  `analysis/feature_snapshots.json`, `analysis/factor_states.json`, or
  `analysis/multi_source_signals.json`.

Personalized-risk material:

- Prefer disabled-asset blocks, risk-limit downgrades, and timeframe mismatches
  before low-impact watchlist or strategy preference annotations.
- Preserve whether output is general or personalized.
- Summarize omitted private values with counts only.
- Do not embed full local user-state files, private notes, account identifiers,
  exact holdings, balances, machine paths, `analysis/user_state_context.json`,
  or `analysis/personalized_risk_constraints.json`.

## Validation

Automated validation:

```bash
python -m pytest
```

Real-source no-Codex product validation:

```bash
python -m halpha run --config config.example.yaml --no-codex
```

Focused Codex-input validation:

```bash
python -m halpha run --config config.example.yaml --until build_codex_context
```

Inspect:

- `run_manifest.json` `codex_input`
- `analysis/research_context.md`
- `codex_context/context.md`
- `codex_context/prompt.md`
- `analysis/alert_decision_material.md`
- `analysis/event_intelligence_material.md`
- `analysis/derivatives_market_material.md`
- `analysis/macro_calendar_material.md`
- `analysis/onchain_flow_material.md`
- `analysis/strategy_lifecycle_material.md`
- `analysis/factor_signal_material.md`

Validation should confirm that full intermediate JSON records are referenced by
path, not embedded wholesale, and that low-priority material is summarized or
omitted with explicit counts.
