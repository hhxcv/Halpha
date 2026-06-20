# Intelligence Fusion Contracts

This document defines Halpha intelligence fusion contracts. It is durable
project documentation, not a milestone plan.

Implementation status:

- `analysis/intelligence_fusion.json` is implemented in product runs.
- Decision recommendation and alert decision fusion integration is implemented
  in product runs.
- `analysis/intelligence_fusion_material.md` is implemented in product runs.
- Fusion artifacts must remain additive. They must not replace strategy
  evaluation, feature/factor, event intelligence, risk assessment, decision
  recommendations, alert decisions, data quality, outcome tracking, or final
  reports.

## Related Docs

- `docs/artifact-governance.md`: artifact layers and Codex input policy.
- `docs/quant-contracts.md`: strategy, evaluation, and market signal
  contracts.
- `docs/feature-factor-contracts.md`: feature, factor, multi-source signal,
  and factor material contracts.
- `docs/event-intelligence-contracts.md`: event intelligence and alert
  contracts.
- `docs/decision-intelligence-contracts.md`: regime, risk, recommendation,
  watch, and decision material contracts.
- `docs/outcome-tracking-contracts.md`: outcome accountability contracts.
- `docs/research-data-contracts.md`: shared local research data and
  data-quality contracts.

## Purpose

The intelligence fusion layer converts already implemented current-run
evidence into deterministic decision-grade context. It answers whether
independent evidence supports, conflicts with, weakens, or blocks a possible
decision or alert interpretation.

Target flow:

```text
strategy evidence
+ strategy lifecycle state
+ feature/factor states
+ multi-source signals
+ event intelligence
+ risk and regime assessment
+ alert decisions
+ outcome tracking
+ data quality
-> analysis/intelligence_fusion.json
-> decision and alert fusion context
-> analysis/intelligence_fusion_material.md
-> research context, Codex context, and reports
```

The layer is research material. It is not trading execution, investment advice,
position sizing, account automation, or a forecasting guarantee.

## Sources

Fusion may use implemented current-run artifacts when present:

- `analysis/market_signals.json`
- `analysis/strategy_evaluation_summary.json`
- `analysis/strategy_effectiveness_gates.json`
- `analysis/strategy_lifecycle_state.json`
- `analysis/market_regime_assessment.json`
- `analysis/risk_assessment.json`
- `analysis/feature_snapshots.json`
- `analysis/factor_states.json`
- `analysis/multi_source_signals.json`
- `analysis/event_intelligence_assessment.json`
- `analysis/alert_decisions.json`
- `analysis/outcome_evaluations.json`
- `analysis/data_quality_summary.json`

Rules:

- Use current-run bounded artifacts and source refs.
- Do not read full shared OHLCV history for Codex-facing fusion.
- Do not embed full reusable derivatives, macro/calendar, on-chain, text-event,
  or outcome history.
- Missing optional upstream artifacts should produce explicit skipped,
  unavailable, or insufficient-evidence states where material.
- Do not fabricate support, conflict, risk override, event override, or outcome
  feedback for unavailable sources.
- Do not call Codex, another LLM, or a hidden model to generate fusion states.

## analysis/intelligence_fusion.json

Purpose:

- Record deterministic cross-source intelligence for each supported market
  scope.
- Preserve source-specific evidence and traceability.
- Distinguish confluence, conflict, independence, risk override, event
  override, outcome feedback, insufficient evidence, degraded evidence, and
  skipped inputs.

Required top-level fields:

```json
{
  "schema_version": 1,
  "artifact_type": "intelligence_fusion",
  "run_id": "<run_id>",
  "created_at": "<UTC ISO timestamp>",
  "status": "ok|warning|degraded|failed|skipped",
  "records": [],
  "coverage": [],
  "counts": {},
  "warnings": [],
  "errors": [],
  "source_artifacts": []
}
```

Record contract:

```json
{
  "fusion_record_id": "fusion:<scope_key>",
  "scope": {
    "symbol": "BTCUSDT",
    "timeframe": "1d",
    "asset": null,
    "region": null
  },
  "state": "supportive|cautionary|conflicting|risk_blocked|event_overridden|insufficient_evidence|degraded|failed|neutral",
  "direction": "bullish|bearish|mixed|neutral|unknown",
  "confidence": "high|medium|low|unknown",
  "confluence": {
    "state": "aligned|partial|none|unknown",
    "supporting_sources": 0,
    "independent_sources": 0
  },
  "conflict": {
    "state": "none|minor|material|severe|unknown",
    "conflicting_sources": 0
  },
  "risk_override": {
    "state": "none|downgrade|block|unknown",
    "risk_level": "low|medium|high|extreme|unknown",
    "reasons": []
  },
  "event_override": {
    "state": "none|watch|downgrade|block|unknown",
    "severity": "low|medium|high|critical|unknown",
    "reasons": []
  },
  "outcome_feedback": {
    "state": "supportive|cautionary|mixed|insufficient_evidence|unknown",
    "source_records": 0
  },
  "evidence": [],
  "uncertainty": [],
  "warnings": [],
  "errors": [],
  "source_artifacts": [],
  "source_record_refs": []
}
```

Allowed `state` values:

- `supportive`: independent source groups broadly agree and no blocking risk is
  present.
- `cautionary`: some support exists, but quality, risk, event, or outcome
  evidence weakens confidence.
- `conflicting`: material source groups disagree.
- `risk_blocked`: risk assessment says the view should be blocked or
  downgraded.
- `event_overridden`: event intelligence changes the interpretation enough to
  require a watch-only or downgraded stance.
- `insufficient_evidence`: required inputs are missing, stale, skipped, or too
  weak.
- `degraded`: upstream evidence exists but data-quality or source warnings
  materially limit use.
- `failed`: required fusion inputs are invalid or internally inconsistent.
- `neutral`: evidence exists but does not support a directional interpretation.

Rules:

- Records must be deterministic and sorted by stable scope keys.
- Every non-neutral state must include source artifact refs.
- Every conflict, risk override, event override, or outcome feedback state must
  include evidence and uncertainty.
- Fusion may summarize upstream evidence. It must not copy full upstream JSON
  records into each fusion record.
- Fusion must preserve Halpha-owned upstream states instead of reclassifying
  them through AI.

## Coverage

Coverage records describe whether each input class was used, skipped,
unavailable, degraded, failed, or insufficient.

Required fields:

```json
{
  "source_layer": "strategy|strategy_evaluation|strategy_gate|strategy_lifecycle|factor|event|risk|regime|alert|outcome|data_quality",
  "source_artifact": "analysis/factor_states.json",
  "status": "used|skipped|missing|unavailable|degraded|failed",
  "records": 0,
  "warnings": [],
  "errors": []
}
```

Coverage must be visible enough that a user can tell whether a weak fusion
state comes from real conflict or missing evidence.

## analysis/intelligence_fusion_material.md

Purpose:

- Provide bounded AI-readable fusion context for Codex and final report
  generation.
- Preserve high-signal fusion records and summarize omitted records.
- Explain source availability, confluence, conflict, risk override, event
  override, outcome feedback, and uncertainty.

Required boundaries:

```yaml
codex_may_explain_intelligence_fusion: true
codex_may_generate_fusion_states: false
codex_may_generate_risk_overrides: false
codex_may_generate_alert_priorities: false
codex_may_generate_action_levels: false
codex_may_generate_price_forecasts: false
codex_may_create_trading_instructions: false
full_intelligence_fusion_json_embedded: false
full_upstream_intermediate_json_embedded: false
full_raw_streams_embedded: false
full_reusable_histories_embedded: false
selected_records_only: true
```

Material selection rules:

- Prefer conflicting, risk-blocked, event-overridden, degraded, failed, and
  high-confidence supportive records before neutral records.
- Preserve strategy lifecycle source refs when degraded, retired, watchlisted,
  rejected, or insufficient-evidence lifecycle states qualify strategy
  evidence.
- Preserve representative supportive records when they explain current
  decision or alert context.
- Summarize omitted low-priority records with counts and reasons.
- Keep source artifact paths visible.
- Do not embed full raw streams, reusable histories, current-run views, full
  run manifests, or full intermediate JSON.

## Decision And Alert Integration

Product runs integrate fusion evidence into decision recommendations and alert
decisions by adding bounded fusion context fields such as:

- `fusion_record_id`
- `fusion_state`
- `fusion_conflict_state`
- `fusion_risk_override_state`
- `fusion_event_override_state`
- `fusion_outcome_feedback_state`
- `fusion_evidence`
- `fusion_uncertainty`
- `fusion_source_artifacts`

Integration rules:

- Preserve original deterministic decision and alert source evidence.
- Preserve pre-fusion action levels or priorities when integration changes a
  record.
- Do not remove upstream downgrade reasons, warnings, uncertainty, or source
  refs.
- Conservative decision downgrades are allowed only when fusion records include
  source-backed blocking risk, event override, severe conflict, degraded
  evidence, or insufficient evidence.
- Degraded or retired strategy lifecycle evidence should qualify or downgrade
  otherwise-supportive strategy language through fusion conflict or degraded
  context, while preserving original gate outcomes and lifecycle source refs.
- Conservative alert attention downgrades are allowed only for severe conflict,
  degraded evidence, or insufficient evidence. Blocking risk and event override
  require reassessment annotations instead of hidden priority upgrades.
- Integration must be visible in material artifacts before research context is
  built.

## Manifest Expectations

`run_manifest.json` should record:

- intelligence fusion artifact paths;
- fusion record counts;
- confluence, conflict, risk override, event override, outcome feedback, and
  insufficient-evidence counts;
- warning and error counts;
- decision and alert fusion integration counts;
- Codex input budget metadata for `analysis/intelligence_fusion_material.md`.

## Data Quality And Inspection

Data quality and inspection should cover:

- `analysis/intelligence_fusion.json` presence, shape, status, counts,
  warnings, errors, source coverage, and degraded states;
- `analysis/intelligence_fusion_material.md` Codex boundaries and budget state;
- decision and alert fusion integration counts.

`python -m halpha data inspect --config config.example.yaml` should summarize
fusion status without dumping fusion records or full upstream records.

## Codex And Report Boundary

Codex may:

- explain Halpha-generated fusion evidence;
- cite source artifacts and uncertainty;
- describe agreement, conflict, risk override, event override, outcome feedback,
  missing evidence, stale evidence, and degraded state using generated
  material.

Codex must not:

- create or revise fusion states;
- create or revise risk overrides;
- create or revise alert priorities;
- create or revise action levels;
- generate price forecasts;
- generate trading instructions;
- infer missing upstream data;
- treat fusion evidence as a guarantee.

Reports may explain fusion evidence conservatively, but structured fusion state
must come from Halpha artifacts.

## Validation

Minimum validation once implemented:

```bash
python -m pytest
python -m halpha run --config config.example.yaml --no-codex
python -m halpha run --config config.example.yaml --until build_codex_context
python -m halpha data inspect --config config.example.yaml --run-dir runs/<run_id>
```

Full report validation when Codex CLI use is intended:

```bash
python -m halpha run --config config.example.yaml
```

Acceptance should inspect:

- `analysis/intelligence_fusion.json`
- `analysis/intelligence_fusion_material.md`
- `analysis/decision_recommendations.json`
- `analysis/alert_decisions.json`
- `analysis/data_quality_summary.json`
- `analysis/research_context.md`
- `codex_context/context.md`
- `codex_context/prompt.md`
- `report/report.md` when Codex CLI validation is run
- `run_manifest.json`

Validation should confirm that fusion is source-backed, bounded for Codex
input, visible in data-quality and inspection output, cited from bounded fusion
material in final reports, and not generated by Codex.
