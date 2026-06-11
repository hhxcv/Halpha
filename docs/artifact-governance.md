# Artifact Governance

This document defines how Halpha artifacts are layered, consumed, and admitted
into Codex input. It is a durable contract for humans and AI agents. It is not a
milestone plan.

## Related Docs

- `README.md`: project overview, commands, and product validation.
- `AGENTS.md`: AI-agent rules, artifact expectations, and validation rules.
- `docs/quant-contracts.md`: market data, strategy, evaluation, signal, and
  strategy-material contracts.
- `docs/research-data-contracts.md`: shared local research data, run index,
  text-event history, and data-quality contracts.
- `docs/event-intelligence-contracts.md`: text event, NLP evidence, topic,
  event signal, confluence, assessment, and event-material contracts.
- `docs/decision-intelligence-contracts.md`: regime, risk, recommendation,
  watch trigger, delta, alert decision, and decision-material contracts.
- `docs/outcome-tracking-contracts.md`: planned outcome target, evaluation,
  history, material, and Codex-boundary contracts.

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
| Manifest | Record lifecycle, artifacts, counts, warnings, errors, and Codex input budget. | Not embedded in full. Used for audit. |

Shared reusable data contracts are defined in
`docs/research-data-contracts.md`. This document owns Codex input admission
rules for those contracts.

## Flow And Artifacts

### Raw Collection

Produced early in a product run:

- `raw/market.json`
- `raw/text_events.json`

These preserve public collection results. They are not Codex context by
themselves.

### Shared Market History

Reusable input data:

- `data/market/ohlcv/`
- `data/market/metadata/ohlcv_schema.json`
- `data/market/metadata/ohlcv_sync_state.json`
- `data/research/metadata/research_data_catalog.json`
- `data/research/metadata/text_event_history_state.json`
- `data/research/text_events/`

Shared OHLCV history, reusable text-event history, and the research data
catalog stay outside per-run report directories and must not be embedded into
Codex input.

### Current-Run Data Views

Current-run market windows and storage references:

- `raw/market_data_views.json`

This artifact records view metadata, not full raw OHLCV history.

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
duplicate, shared-store, partial-collection, degraded, skipped, warning, and
failed states. `analysis/data_quality_material.md` is the bounded Codex-facing
summary derived from that JSON. Codex may explain Halpha-generated quality
status, but must not create quality checks, invent validation results, inspect
full shared stores, read SQLite contents, read Parquet tables, or reconstruct
raw archives.

### Outcome Tracking Evidence

Outcome tracking artifacts:

- `analysis/outcome_targets.json`: implemented source-linked targets from the
  latest previous successful run.
- `analysis/outcome_evaluations.json`: implemented market and strategy outcome
  evaluations; event, alert, and decision follow-through expansion is planned.
- `data/research/outcomes/`: planned reusable outcome history.
- `data/research/metadata/outcome_history_state.json`: planned outcome history
  state metadata.

These artifacts record prior research targets, later outcome evaluations, and
reusable outcome history. They are not Codex context by themselves. Once
implemented, Codex should consume bounded `analysis/outcome_tracking_material.md`
instead of full target, evaluation, or history records.

### Report-Facing Material

Eligible Codex input:

- `analysis/market_material.md`
- `analysis/text_material.md`
- `analysis/market_signal_material.md`
- `analysis/strategy_evaluation_material.md`
- `analysis/strategy_experiment_material.md`
- `analysis/decision_intelligence_material.md`
- `analysis/alert_decision_material.md`
- `analysis/event_intelligence_material.md`
- `analysis/data_quality_material.md`
- `analysis/outcome_tracking_material.md` when implemented

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

## Codex Input Policy

Codex input policy:

- Embed bounded report-facing material only.
- Preserve complete evidence artifacts outside Codex input.
- Do not embed full raw streams.
- Do not embed full intermediate JSON evidence.
- Do not embed full shared OHLCV history.
- Do not embed full run manifests.
- Prefer high-signal decision, risk, alert, event, strategy, gate, and quality evidence.
- Summarize or omit low-priority records with explicit counts and reasons.

Default size budgets:

| Input | Budget |
| --- | ---: |
| Each material block | 16,000 characters |
| `analysis/research_context.md` | 140,000 characters |
| `codex_context/context.md` | 150,000 characters |
| `codex_context/prompt.md` | 170,000 characters |

Material blocks above the per-block budget are compressed into explicit
head-and-tail excerpts in Codex input. The budget records are safeguards and
audit metadata. They do not remove the complete evidence artifacts from disk.

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

Validation should confirm that full intermediate JSON records are referenced by
path, not embedded wholesale, and that low-priority material is summarized or
omitted with explicit counts.
