# Feature, Factor, and Multi-Source Signal Contracts

This document defines Halpha feature, factor, multi-source signal, and factor
signal material contracts. It is durable project documentation, not a milestone
plan.

Implementation status:

- `analysis/feature_snapshots.json` is implemented in product runs.
- `analysis/factor_states.json` is implemented in product runs.
- `analysis/multi_source_signals.json` is implemented in product runs.
- `analysis/factor_signal_material.md` is implemented in product runs.
- These artifacts remain additive. They do not replace market
  signals, strategy evaluation, derivatives context, macro/calendar context,
  on-chain flow context, event intelligence, decision intelligence, alert
  decisions, data quality, outcome tracking, or final reports.

## Related Docs

- `docs/artifact-governance.md`: artifact layers and Codex input policy.
- `docs/quant-contracts.md`: strategy, evaluation, and market signal
  contracts.
- `docs/derivatives-market-contracts.md`: derivatives context contracts.
- `docs/macro-calendar-contracts.md`: macro/calendar context contracts.
- `docs/onchain-flow-contracts.md`: on-chain flow context contracts.
- `docs/event-intelligence-contracts.md`: event intelligence contracts.
- `docs/decision-intelligence-contracts.md`: downstream risk, decision, watch,
  and alert contracts.
- `docs/outcome-tracking-contracts.md`: outcome accountability contracts.

## Purpose

The feature/factor layer converts heterogeneous current-run evidence into a
common deterministic surface that later consumers can inspect without parsing
every source-specific artifact.

Target flow:

```text
bounded current-run inputs
-> analysis/feature_snapshots.json
-> analysis/factor_states.json
-> analysis/multi_source_signals.json
-> analysis/factor_signal_material.md
-> research context, Codex context, and reports
```

The layer is research material. It is not trading execution, investment advice,
position sizing, account automation, or a forecasting guarantee.

## Sources

Feature extraction may use implemented current-run artifacts when present:

- `raw/market.json`
- `raw/market_data_views.json`
- `analysis/market_signals.json`
- `analysis/strategy_evaluation_summary.json`
- `analysis/strategy_effectiveness_gates.json`
- `analysis/derivatives_market_context.json`
- `analysis/macro_calendar_context.json`
- `analysis/onchain_flow_context.json`
- `analysis/text_event_signals.json`
- `analysis/event_intelligence_assessment.json`
- `analysis/outcome_targets.json`
- `analysis/outcome_evaluations.json`
- `analysis/data_quality_summary.json`

Rules:

- Use current-run bounded artifacts and source refs.
- Do not read full shared OHLCV history for Codex-facing features.
- Do not embed full reusable derivatives, macro/calendar, on-chain, text-event,
  or outcome history.
- Missing optional upstream artifacts should produce explicit coverage,
  skipped, unavailable, or insufficient-evidence state where material.
- Do not fabricate feature values for unavailable sources.

## analysis/feature_snapshots.json

Purpose:

- Normalize source-specific evidence into feature records.
- Preserve source refs, scope, timestamps, values, units, status, warnings, and
  errors before factor scoring.

Artifact shape:

```json
{
  "schema_version": 1,
  "artifact_type": "feature_snapshots",
  "run_id": "run-id",
  "created_at": "2026-06-19T00:00:00Z",
  "status": "ok",
  "records": [],
  "counts": {
    "records": 0,
    "coverage_records": 0,
    "features_by_type": {},
    "features_by_source_layer": {},
    "status_counts": {},
    "source_status_counts": {},
    "warnings": 0,
    "errors": 0
  },
  "coverage": [],
  "warnings": [],
  "errors": [],
  "source_artifacts": []
}
```

Feature record shape:

```json
{
  "feature_id": "feature:trend:BTCUSDT:1d:source-record",
  "feature_type": "price_trend",
  "factor_family": "trend",
  "source_layer": "market",
  "source_artifact": "raw/market_data_views.json",
  "source_record_id": "optional-source-record-id",
  "scope": {
    "symbol": "BTCUSDT",
    "timeframe": "1d",
    "asset": "BTC",
    "chain": null,
    "region": null
  },
  "observed_at": "2026-06-19T00:00:00Z",
  "calculation_window": {
    "start": "2026-06-12T00:00:00Z",
    "end": "2026-06-19T00:00:00Z",
    "row_count": 8
  },
  "value": 0.12,
  "value_unit": "ratio",
  "direction_hint": "supportive",
  "status": "available",
  "confidence": "medium",
  "evidence": [],
  "uncertainty": [],
  "warnings": [],
  "errors": []
}
```

Allowed `status` values:

- `available`
- `neutral`
- `missing`
- `stale`
- `partial`
- `degraded`
- `insufficient_evidence`
- `conflicting`
- `failed`

Allowed `direction_hint` values:

- `supportive`
- `cautionary`
- `neutral`
- `conflicting`
- `unknown`

Initial feature types:

| Feature type | Factor family | Typical source |
| --- | --- | --- |
| `price_trend` | `trend` | market views, market signals |
| `price_volatility` | `volatility` | market views, strategy diagnostics |
| `strategy_direction` | `trend` | market signals, strategy gates |
| `strategy_reliability` | `evidence_quality` | strategy evaluation, gates, outcomes |
| `derivatives_leverage_pressure` | `leverage` | derivatives context |
| `derivatives_liquidity_pressure` | `liquidity` | derivatives context |
| `macro_calendar_pressure` | `macro_risk` | macro/calendar context |
| `onchain_liquidity_context` | `liquidity` | on-chain flow context |
| `onchain_activity_context` | `onchain_flow` | on-chain flow context |
| `event_pressure` | `event_pressure` | event intelligence assessment |
| `outcome_feedback` | `evidence_quality` | outcome evaluations |
| `source_quality` | `evidence_quality` | data quality summary |

## analysis/factor_states.json

Purpose:

- Convert feature snapshots into deterministic factor states.
- Provide a compact source-aware surface for normalized signals and later
  fusion.

Artifact shape:

```json
{
  "schema_version": 1,
  "artifact_type": "factor_states",
  "run_id": "run-id",
  "created_at": "2026-06-19T00:00:00Z",
  "status": "ok",
  "records": [],
  "counts": {
    "records": 0,
    "factors_by_type": {},
    "direction_counts": {},
    "state_counts": {},
    "confidence_counts": {},
    "warnings": 0,
    "errors": 0
  },
  "warnings": [],
  "errors": [],
  "source_artifacts": ["analysis/feature_snapshots.json"]
}
```

Factor record shape:

```json
{
  "factor_id": "factor:trend:BTCUSDT:1d",
  "factor_type": "trend",
  "scope": {
    "symbol": "BTCUSDT",
    "timeframe": "1d",
    "asset": "BTC",
    "chain": null,
    "region": null
  },
  "state": "supportive",
  "direction": "supportive",
  "score": 0.45,
  "score_unit": "bounded_-1_to_1",
  "confidence": "medium",
  "calculation_window": {
    "start": "2026-06-12T00:00:00Z",
    "end": "2026-06-19T00:00:00Z",
    "feature_count": 3
  },
  "input_feature_ids": [],
  "evidence": [],
  "uncertainty": [],
  "warnings": [],
  "errors": [],
  "source_artifacts": ["analysis/feature_snapshots.json"]
}
```

Initial factor taxonomy:

| Factor type | Purpose | Positive score means |
| --- | --- | --- |
| `trend` | Price and strategy direction context. | Directional evidence is supportive. |
| `volatility` | Volatility expansion or compression context. | Volatility backdrop is favorable or controlled. |
| `liquidity` | Spot, derivatives, stablecoin, and source liquidity context. | Liquidity context is supportive. |
| `leverage` | Funding, open interest, basis, and crowdedness context. | Leverage pressure is favorable or not stressed. |
| `macro_risk` | Scheduled or recent macro/calendar context. | Macro risk is low or non-blocking. |
| `event_pressure` | Public event pressure and decision impact context. | Event pressure supports attention or thesis. |
| `onchain_flow` | Broad chain activity and network congestion context. | On-chain context is supportive or not stressed. |
| `evidence_quality` | Data quality, source availability, and outcome reliability. | Evidence quality is usable. |

Scoring rules:

- `score` must be deterministic and bounded from `-1.0` to `1.0`.
- `score` must not be a probability.
- `score` must not be a price forecast or expected return.
- `direction` must be one of `supportive`, `cautionary`, `neutral`,
  `conflicting`, or `unknown`.
- `state` may be more specific, such as `supportive`, `cautionary`,
  `neutral`, `conflicting`, `insufficient_evidence`, `stale`, `degraded`, or
  `failed`.
- `confidence` must be one of `high`, `medium`, `low`, or `unknown`.

## analysis/multi_source_signals.json

Purpose:

- Normalize factor states into conservative research signals.
- Make cross-source agreement, conflict, missing evidence, and degraded
  evidence inspectable.

Artifact shape:

```json
{
  "schema_version": 1,
  "artifact_type": "multi_source_signals",
  "run_id": "run-id",
  "created_at": "2026-06-19T00:00:00Z",
  "status": "ok",
  "records": [],
  "counts": {
    "records": 0,
    "state_counts": {},
    "direction_counts": {},
    "conflicting": 0,
    "warnings": 0,
    "errors": 0
  },
  "warnings": [],
  "errors": [],
  "source_artifacts": ["analysis/factor_states.json"]
}
```

Signal record shape:

```json
{
  "signal_id": "multi_source_signal:BTCUSDT:1d:current",
  "signal_type": "multi_source_market_context",
  "scope": {
    "symbol": "BTCUSDT",
    "timeframe": "1d",
    "asset": "BTC"
  },
  "state": "conflicting",
  "direction": "unknown",
  "score": 0.05,
  "confidence": "low",
  "contributing_factor_ids": [],
  "supportive_factor_ids": [],
  "cautionary_factor_ids": [],
  "neutral_factor_ids": [],
  "conflicting_factor_ids": [],
  "evidence": [],
  "uncertainty": [],
  "warnings": [],
  "errors": [],
  "source_artifacts": ["analysis/factor_states.json"]
}
```

Allowed `state` values:

- `supportive`
- `cautionary`
- `neutral`
- `conflicting`
- `insufficient_evidence`
- `degraded`
- `failed`

Rules:

- Multi-source signals are research context, not trading instructions.
- Do not create or replace `action_level`, `decision_bias`, alert priority, or
  position sizing.
- Do not replace `analysis/market_signals.json`; remain additive.

## analysis/factor_signal_material.md

Purpose:

- Provide bounded AI-readable material from feature, factor, and multi-source
  signal artifacts.
- Let Codex explain generated factor evidence without generating structured
  factor outputs.

Required sections:

- `source_policy`
- `factor_signal_overview`
- `taxonomy`
- `selected_factor_states`
- `selected_multi_source_signals`
- `data_quality`
- `report_usage_rules`
- `omissions`

Required boundaries:

```yaml
codex_may_explain_factor_signal_material: true
codex_may_generate_feature_records: false
codex_may_generate_factor_scores: false
codex_may_generate_signal_states: false
codex_may_generate_action_levels: false
codex_may_generate_price_forecasts: false
codex_may_create_trading_instructions: false
full_raw_streams_embedded: false
full_reusable_histories_embedded: false
full_feature_snapshots_json_embedded: false
full_factor_states_json_embedded: false
full_multi_source_signals_json_embedded: false
selected_records_only: true
```

Material selection rules:

- Prefer conflicting, cautionary, degraded, failed, and insufficient-evidence
  records before neutral records.
- Preserve high-confidence supportive records when they materially explain the
  current context.
- Summarize omitted low-priority records with counts and reasons.
- Keep source artifact paths visible.
- Do not embed full raw streams, reusable histories, full current-run views, or
  full intermediate JSON.

## Manifest Expectations

`run_manifest.json` records:

- feature, factor, multi-source signal, and factor/signal material artifact
  paths;
- feature, factor, multi-source signal, and material record counts;
- status counts, conflict counts, warning counts, and error counts;
- Codex input budget metadata for `analysis/factor_signal_material.md`;
- source coverage for the implemented upstream artifacts.

## Data Quality And Inspection

Data-quality and inspection should cover:

- `analysis/feature_snapshots.json` presence, shape, counts, and source
  coverage;
- `analysis/factor_states.json` status, score bounds, missing inputs,
  conflicts, warnings, and errors;
- `analysis/multi_source_signals.json` agreement, conflict, insufficient
  evidence, degraded, warning, and error states;
- `analysis/factor_signal_material.md` Codex boundaries and budget state.

`python -m halpha data inspect --config config.example.yaml` should summarize
feature/factor artifact status without dumping feature, factor, or signal
records.

## Codex And Report Boundary

Codex may:

- explain Halpha-generated feature, factor, and multi-source signal material;
- cite source artifacts and uncertainty;
- describe agreement, conflict, missing evidence, stale evidence, and degraded
  state using generated material.

Codex must not:

- generate feature records;
- generate or revise factor scores;
- generate or revise signal states;
- create action levels, alert priorities, risk levels, price forecasts,
  position sizing, trading instructions, wallet actions, or account actions;
- infer missing raw data, shared stores, reusable histories, current-run views,
  or full intermediate JSON;
- treat missing optional evidence as neutral unless Halpha generated that state.

## Validation Rules

Automated tests should cover:

- artifact shape;
- feature extraction from available sources;
- missing optional inputs;
- stale, degraded, conflicting, insufficient-evidence, and failed states;
- factor score bounds;
- multi-source agreement and conflict;
- material selection and omission counts;
- Codex boundary strings;
- data-quality and inspection summaries.

Product validation should use:

```bash
python -m pytest
python -m halpha run --config config.example.yaml --no-codex
python -m halpha run --config config.example.yaml
```

Full report runs require public network access, configured public sources, and a
working Codex CLI.
