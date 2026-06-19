# Strategy Lifecycle Contracts

This document defines Halpha strategy lifecycle contracts. It is durable
project documentation, not a milestone plan.

Implementation status:

- The strategy lifecycle contract is defined here.
- `analysis/strategy_lifecycle_state.json` is planned and not implemented yet.
- `analysis/strategy_lifecycle_material.md` is planned and not implemented
  yet.
- Downstream lifecycle integration is planned and not implemented yet.

## Related Docs

- `docs/artifact-governance.md`: artifact layers and Codex input policy.
- `docs/quant-contracts.md`: strategy, evaluation, experiment, gate, and
  strategy-material contracts.
- `docs/outcome-tracking-contracts.md`: outcome accountability contracts.
- `docs/intelligence-fusion-contracts.md`: downstream fusion contracts.
- `docs/decision-intelligence-contracts.md`: downstream decision material
  contracts.
- `docs/delivery-workbench-contracts.md`: local delivery and workbench output
  contracts.
- `docs/user-state-contracts.md`: local privacy and personalized-risk
  boundaries.

## Purpose

The strategy lifecycle layer turns strategy research outputs into reviewable
strategy health state. It preserves version, parameter, outcome, gate,
degradation, watchlist, rejection, retirement, and insufficient-evidence
context without becoming an execution, allocation, or strategy-selection
engine.

Target flow:

```text
strategy runs
+ strategy evaluation
+ strategy effectiveness gates
+ outcome tracking
+ available market-state or regime evidence
+ explicit lifecycle policy records
-> analysis/strategy_lifecycle_state.json
-> analysis/strategy_lifecycle_material.md
-> gates, fusion, decisions, Codex context, reports, data inspection, workbench
```

The layer is research material. It is not trading execution, investment
advice, account automation, position sizing, portfolio management, return
forecasting, or a guarantee that a strategy will work in the future.

## Sources

Lifecycle state may use implemented current-run artifacts when present:

- `analysis/quant_strategy_runs.json`
- `analysis/strategy_evaluation_summary.json`
- `analysis/strategy_experiment.json`
- `analysis/strategy_effectiveness_gates.json`
- `analysis/outcome_evaluations.json`
- `analysis/market_regime_assessment.json`
- `analysis/risk_assessment.json`
- `analysis/intelligence_fusion.json`
- `analysis/data_quality_summary.json`

Lifecycle state may also use explicit local lifecycle policy records when the
product implements that input. Those records may express review intent such as
promotion, watchlisting, rejection, or retirement. They must not contain
credentials, account identifiers, holdings, balances, allocations, position
sizes, private notes intended only for the user, or exchange operations.

Rules:

- Use current-run bounded artifacts and source refs.
- Do not read full shared OHLCV history for Codex-facing lifecycle state.
- Do not invent strategy returns, strategy versions, parameter values, outcome
  evaluations, degradation evidence, or lifecycle policy records.
- Missing optional upstream artifacts should produce explicit skipped,
  unavailable, insufficient-evidence, or degraded states where material.
- Do not call Codex, another LLM, or a hidden model to generate lifecycle
  states, promotions, retirements, or degradation decisions.

## analysis/strategy_lifecycle_state.json

Purpose:

- Record deterministic lifecycle health for each configured or evaluated
  strategy candidate.
- Preserve strategy identity, version, parameter identity, source evidence, and
  lifecycle status.
- Keep rejected, watchlisted, degraded, insufficient-evidence, and retired
  strategies reviewable instead of silently deleting them.

Required top-level fields:

```json
{
  "schema_version": 1,
  "artifact_type": "strategy_lifecycle_state",
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
  "lifecycle_record_id": "strategy_lifecycle:<strategy_name>:<symbol>:<timeframe>",
  "strategy_name": "breakout_atr_trend",
  "scope": {
    "symbol": "BTCUSDT",
    "timeframe": "1d"
  },
  "strategy_contract_version": "unknown",
  "parameter_version": "unknown",
  "parameter_digest": "unknown",
  "lifecycle_status": "effective|active_candidate|watchlisted|rejected|degraded|retired|insufficient_evidence|skipped|failed",
  "health_state": {
    "state": "healthy|watch|degraded|retired|insufficient_evidence|unknown|failed",
    "confidence": "high|medium|low|unknown",
    "reasons": []
  },
  "degradation": {
    "state": "none|warning|degraded|insufficient_evidence|unknown",
    "reasons": [],
    "source_record_refs": []
  },
  "regime_weakness": {
    "state": "none|watch|weak|insufficient_evidence|unknown",
    "regimes": [],
    "reasons": []
  },
  "promotion": {
    "state": "not_requested|requested|blocked|approved|unknown",
    "policy_refs": []
  },
  "retirement": {
    "state": "not_retired|requested|explicitly_retired|blocked|unknown",
    "policy_refs": []
  },
  "evidence": [],
  "uncertainty": [],
  "warnings": [],
  "errors": [],
  "source_artifacts": [],
  "source_record_refs": []
}
```

Allowed lifecycle statuses:

- `effective`: current deterministic evidence passes configured gates and no
  lifecycle degradation or retirement condition overrides it.
- `active_candidate`: current evidence is usable for review, but not strong
  enough to call effective.
- `watchlisted`: current or explicit lifecycle evidence says the strategy
  should remain visible for review, but not treated as cleanly effective.
- `rejected`: current gates or explicit review records reject the candidate.
- `degraded`: prior or current outcome evidence materially weakens strategy
  confidence.
- `retired`: explicit lifecycle policy retires the strategy from active
  consideration while preserving evidence for review.
- `insufficient_evidence`: required evidence is missing, too short, stale, or
  too weak to classify.
- `skipped`: lifecycle evaluation did not run for a declared reason.
- `failed`: inputs were invalid or internally inconsistent.

Rules:

- Records must be deterministic and sorted by stable strategy, symbol, and
  timeframe keys.
- Every non-skipped record must include source artifact refs.
- Degradation must be evidence-backed. It must not be inferred from report
  prose or Codex output.
- Retired status requires an explicit lifecycle policy record. A weak backtest
  alone may degrade, watchlist, or reject a strategy, but must not silently
  retire it.
- Promotion state must be explicit. Lifecycle code must not silently promote
  strategies into active status without a reviewable policy record.
- Lifecycle state may summarize upstream evidence. It must not copy full
  upstream JSON records into every lifecycle record.

## Lifecycle Policy Records

Lifecycle policy records are explicit local review inputs. They are intended
for controlled strategy governance, not for trading execution.

Planned record shape:

```json
{
  "action": "promote|watchlist|reject|retire",
  "strategy_name": "breakout_atr_trend",
  "strategy_contract_version": "optional",
  "parameter_digest": "optional",
  "scope": {
    "symbol": "BTCUSDT",
    "timeframe": "1d"
  },
  "reason": "short review reason",
  "created_at": "<UTC ISO timestamp>",
  "effective_at": "<UTC ISO timestamp or null>"
}
```

Policy rules:

- Policy input must be explicit and locally configured.
- Policy input must be optional. Omitted policy input should not fail normal
  product runs.
- Policy input must not be printed in full when it could contain private local
  notes.
- Policy input must not include account credentials, balances, holdings,
  allocations, order IDs, wallet addresses, API keys, proxy values, machine
  paths, or private endpoints.
- Policy input may affect lifecycle status only through deterministic code.
  Codex must not create, approve, or modify policy records.

## Coverage

Coverage records describe whether each input class was used, skipped, missing,
unavailable, degraded, failed, or insufficient.

Required fields:

```json
{
  "source_layer": "strategy_run|evaluation|gate|outcome|regime|risk|fusion|data_quality|policy",
  "source_artifact": "analysis/strategy_effectiveness_gates.json",
  "status": "used|skipped|missing|unavailable|degraded|failed|insufficient",
  "records": 0,
  "warnings": [],
  "errors": []
}
```

Coverage must be visible enough that users can tell whether weak lifecycle
state comes from poor strategy evidence, missing upstream evidence, unavailable
policy input, or degraded data quality.

## analysis/strategy_lifecycle_material.md

Purpose:

- Provide bounded AI-readable lifecycle context for Codex and final report
  generation.
- Preserve high-signal lifecycle records and summarize omitted records.
- Explain strategy health, degradation, watchlist, rejection, retirement,
  insufficient evidence, source availability, and uncertainty.

Material rules:

- Include counts for lifecycle statuses, degradation warnings, retired
  strategies, policy records used, and omitted records.
- Include only selected high-signal lifecycle records.
- Prefer records with degraded, retired, watchlisted, rejected,
  insufficient-evidence, or high-confidence effective states.
- Include source artifact refs and source record refs where available.
- Do not embed full strategy run JSON, full outcome history, full lifecycle
  state JSON, full policy input files, private policy notes, account data,
  holdings, allocations, balances, or positions.
- Clearly state that lifecycle records are Halpha-generated deterministic
  research material and not trading instructions.

## Downstream Consumers

Planned consumers:

- Strategy gates or gate overlays may use lifecycle evidence to qualify
  whether a gate-passing strategy is healthy, watchlisted, degraded, or retired.
- Intelligence fusion may use lifecycle evidence as strategy-health context.
- Decision material and final reports may explain lifecycle status as
  deterministic Halpha evidence.
- Data inspection may summarize lifecycle artifact status and counts.
- Workbench output may link and summarize lifecycle status for local review.

Consumer rules:

- Downstream consumers must preserve source refs.
- Downstream consumers must not treat missing lifecycle evidence as positive
  strategy evidence.
- Degraded or retired lifecycle states should prevent downstream language from
  presenting the affected strategy as cleanly effective without qualification.
- Workbench output is a delivery surface only. It must not become upstream
  lifecycle input.

## Codex And Report Boundaries

Codex may:

- explain Halpha-generated lifecycle status;
- explain strategy health, watchlist, rejection, retirement, degradation, and
  insufficient-evidence records from bounded material;
- describe source availability, uncertainty, and omitted-record counts.

Codex must not:

- generate lifecycle states;
- create strategy versions or parameter digests;
- create policy records;
- approve promotions or retirements;
- optimize parameters;
- select strategies with hidden judgment;
- forecast prices, returns, or win rates;
- issue trading instructions, position sizing, order guidance, or account
  actions.

Final reports may include lifecycle explanations derived from
`analysis/strategy_lifecycle_material.md`. Reports should not ask Codex to
recreate the full lifecycle table or structured lifecycle state.

## Validation Expectations

Tests should cover:

- complete lifecycle state generation;
- missing and partial upstream evidence;
- degraded performance;
- regime weakness where regime evidence is available;
- insufficient evidence;
- strategy contract version changes;
- parameter digest changes;
- explicit retirement policy records;
- watchlisted and rejected strategy preservation;
- material bounds and omission counts;
- Codex input boundaries;
- downstream source refs;
- data inspection and workbench summaries when implemented.
