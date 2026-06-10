# Decision Intelligence Contracts

## Purpose

This document defines Halpha decision-intelligence contracts.

It is a durable implementation contract, not a milestone-only plan and not an implementation record. The contracts may evolve as shipped behavior grows, but agents should update this document instead of creating milestone-numbered successor contract files.

Decision intelligence turns upstream quantitative research artifacts into deterministic research decision support for the report loop. It does not replace quantitative evidence.

Current decision-intelligence flow:

```text
quant strategy run artifacts
  -> market strategy signal artifacts
  -> normalized market signal artifacts
  -> AI-readable quant material
  -> market regime assessment
  -> risk assessment
  -> decision recommendations
  -> watch triggers
  -> previous-run decision delta
  -> AI-readable decision material
  -> research context
  -> Codex context + prompt
  -> Simplified Chinese Markdown report
```

Decision-intelligence outputs are personal research material. They are not trades, orders, account operations, portfolio instructions, position sizing, return promises, or financial advice.

## Contract Status

This file separates stable direction from shipped behavior.

- `contract`: expected durable interface or rule.
- `initial adoption`: first implementation slice for the active milestone.
- `not implemented yet`: allowed future contract detail that must not be described as shipped behavior.

README should describe only user-visible behavior that exists. This file may define intended contracts before implementation when they are needed to guide a focused issue.

## Scope

Define contracts for:

- Upstream quantitative artifact retention.
- Decision-intelligence JSON artifacts.
- AI-readable decision material.
- Missing-upstream and insufficient-data behavior.
- Report-level fusion between quant evidence and decision synthesis.
- Manifest reporting expectations.
- Selected technology boundaries.

## Out of Scope

- Code implementation.
- Dependency installation.
- New market data sources.
- New text event intelligence.
- Real-time monitoring.
- Scheduler, daemon, websocket, polling, or alert delivery runtime.
- Dashboard or workbench UI.
- Database service or state store redesign.
- User profiles, holdings, account state, or exchange account operations.
- Trading execution, order placement, position sizing, or portfolio management.
- Machine learning prediction or ML regime classification.
- LLM-generated action contracts.

## Technology Boundaries

Decision-intelligence contracts are Halpha-owned JSON and Markdown artifacts.

Rules:

- Do not persist third-party framework objects as decision-intelligence artifacts.
- Do not use hidden AI state as a decision-intelligence contract.
- Do not ask Codex or another LLM to generate structured action levels.
- Do not add Pydantic or another schema dependency for the initial contract adoption.
- Use deterministic Halpha logic for regime, risk, action, trigger, and delta fields.
- Preserve source artifact references so every decision record can be traced back to upstream evidence.

## Upstream Quant Evidence Policy

Decision intelligence consumes upstream quantitative artifacts.

The active adoption uses M2-produced quant artifacts as upstream evidence.

Retained upstream artifacts:

```text
analysis/quant_strategy_runs.json
analysis/market_strategy_signals.json
analysis/market_signals.json
analysis/market_signal_material.md
```

Rules:

- Retain upstream quant artifacts in the product path.
- Treat upstream quant artifacts as evidence, not as replaceable intermediate clutter.
- Decision-intelligence artifacts are additive derived artifacts.
- Do not rename, remove, or rewrite upstream quant artifacts as part of decision-intelligence generation.
- Do not embed shared OHLCV history into decision-intelligence material or Codex context.
- Preserve evidence, conflicts, warnings, uncertainty, insufficient-data state, and source artifacts from upstream quant records.

Initial adoption:

- Decision intelligence starts after `analysis/market_signal_material.md` exists.
- Decision-intelligence stages run before `analysis/research_context.md`.
- When `quant.enabled` is false, skip decision intelligence and do not write fake unknown decision artifacts.

## Common JSON Artifact Rules

Each decision-intelligence JSON artifact should use:

```json
{
  "schema_version": 1,
  "artifact_type": "artifact_name",
  "run_id": "20260606T000000Z",
  "created_at": "2026-06-06T00:00:00Z",
  "source_artifacts": [],
  "records": [],
  "warnings": [],
  "errors": []
}
```

Rules:

- `schema_version` starts at `1`.
- `artifact_type` must match the artifact contract name.
- `run_id` must identify the current run.
- `created_at` must be ISO 8601 UTC.
- `source_artifacts` must use repo artifact paths or stable shared-data metadata paths.
- `records` may be empty only when the artifact status and warnings explain why.
- `warnings` record degraded or incomplete evidence.
- `errors` record artifact-specific failures that did not prevent writing a partial artifact.
- Do not fabricate conclusions to avoid empty or unknown output.
- Use deterministic ordering for records and source references.

Record identity:

- Prefer one record per supported source, symbol, and timeframe when upstream artifacts support that scope.
- Use a deterministic record id derived from artifact type, source, symbol, timeframe, and latest candle or run id.
- Include source artifact references on each record.

## Market Regime Assessment

Artifact:

```text
analysis/market_regime_assessment.json
```

Purpose:

- Summarize the current market state before action guidance.

Artifact type:

```text
market_regime_assessment
```

Initial regime taxonomy:

```text
trend_up
trend_down
range_bound
high_volatility
low_volatility
mixed
unknown
```

Record fields:

```json
{
  "record_id": "market_regime:binance:BTCUSDT:1d:2026-06-06T00:00:00Z",
  "source": "binance",
  "symbol": "BTCUSDT",
  "timeframe": "1d",
  "latest_candle_time": "2026-06-06T00:00:00Z",
  "regime": "mixed",
  "confidence": "medium",
  "status": "succeeded",
  "evidence": [],
  "conflicts": [],
  "uncertainty": [],
  "source_artifacts": []
}
```

Rules:

- Derive regime from current quant strategy and market signal artifacts.
- Prefer explainable rule inputs such as direction counts, confidence, volatility notes, latest strategy regimes, conflicts, and insufficient-data state.
- Use `unknown` with warnings when upstream evidence is missing or too weak.
- Use `mixed` when evidence is present but materially conflicting.
- Do not use ML classification.
- Do not read raw OHLCV directly for new calculations unless an existing upstream artifact already exposes the needed bounded value.

## Risk Assessment

Artifact:

```text
analysis/risk_assessment.json
```

Purpose:

- Identify risk state before decision recommendations are generated.

Artifact type:

```text
risk_assessment
```

Initial risk taxonomy:

```text
low
medium
high
extreme
unknown
```

Record fields:

```json
{
  "record_id": "risk_assessment:binance:BTCUSDT:1d:2026-06-06T00:00:00Z",
  "source": "binance",
  "symbol": "BTCUSDT",
  "timeframe": "1d",
  "risk_level": "high",
  "rising_risks": [],
  "blocking_risks": [],
  "data_quality_risks": [],
  "signal_conflict_risks": [],
  "gates": {
    "block_strong_action": true,
    "cap_action_level": "WATCH",
    "requires_invalidation": true
  },
  "evidence": [],
  "warnings": [],
  "errors": [],
  "source_artifacts": []
}
```

Rules:

- Derive risk from upstream strategy warnings, normalized signal conflicts, volatility or risk notes exposed by upstream artifacts, regime uncertainty, and data-quality gaps.
- Missing or weak upstream evidence must not produce unsupported `low` risk.
- High or extreme risk must be machine-readable as a downgrade or blocking condition for decision recommendations.
- Do not include user holdings, account state, portfolio risk, VaR, stress testing, or position sizing.
- Do not use LLM-generated risk conclusions.

## Decision Recommendations

Artifact:

```text
analysis/decision_recommendations.json
```

Purpose:

- State deterministic research decision support: what to do, what not to do, when to wait, and what invalidates the current view.

Artifact type:

```text
decision_recommendations
```

Long-term action taxonomy:

```text
STRONG_DO
DO
TRY_SMALL
WATCH
AVOID
EXIT_OR_REDUCE
HEDGE_OR_PROTECT
NO_ACTION
```

Action taxonomy policy:

- Action levels are research decision-support classifications.
- Action levels may be rendered as report language only when supported by evidence.
- Action levels are not orders, account operations, portfolio instructions, position sizing, automatic trading actions, investment advice, or return promises.
- `EXIT_OR_REDUCE` means the research view indicates elevated risk or invalidation pressure. It does not mean Halpha issued a sell order.
- `HEDGE_OR_PROTECT` means the research view indicates protective consideration. It does not mean Halpha opened or advised a hedge.

Record fields:

```json
{
  "record_id": "decision_recommendation:binance:BTCUSDT:1d:2026-06-06T00:00:00Z",
  "source": "binance",
  "symbol": "BTCUSDT",
  "timeframe": "1d",
  "action_level": "WATCH",
  "decision_bias": "wait_for_confirmation",
  "confidence": "medium",
  "recommended_actions": [],
  "do_not_do": [],
  "risk_conditions": [],
  "invalidation_conditions": [],
  "evidence": [],
  "conflicts": [],
  "warnings": [],
  "source_artifacts": []
}
```

Rules:

- Derive action level from quant evidence, market regime, and risk assessment.
- Evidence insufficient means `WATCH`, `NO_ACTION`, or a non-actionable status.
- High or extreme risk must downgrade or block stronger action levels.
- Major conflicts must cap action strength.
- Every actionable recommendation must include evidence references.
- Every actionable recommendation must include invalidation conditions or be downgraded to a non-actionable or watch state.
- Codex and other LLMs must not generate the structured action level.
- Do not include order placement, position sizing, account actions, automatic trading, or unbounded price targets.

## Watch Triggers

Artifact:

```text
analysis/watch_triggers.json
```

Purpose:

- Tell the report user which future changes would confirm, invalidate, downgrade, or improve the current decision view.

Artifact type:

```text
watch_triggers
```

Trigger types:

```text
confirmation
invalidation
risk_escalation
risk_relief
wait_condition
recheck_next_run
```

Record fields:

```json
{
  "trigger_id": "watch_trigger:binance:BTCUSDT:1d:confirmation:2026-06-06T00:00:00Z",
  "source": "binance",
  "symbol": "BTCUSDT",
  "timeframe": "1d",
  "type": "confirmation",
  "condition": "A supported condition derived from current artifacts.",
  "priority": "medium",
  "expected_decision_impact": "could_upgrade_watch_to_try_small",
  "linked_decision_record_id": "decision_recommendation:binance:BTCUSDT:1d:2026-06-06T00:00:00Z",
  "evidence": [],
  "warnings": [],
  "source_artifacts": []
}
```

Rules:

- Derive triggers from current upstream signals, regime, risk, and decision artifacts.
- Link triggers to decision recommendations when evidence supports the link.
- Missing evidence produces warnings or no-trigger records, not fabricated conditions.
- Static trigger generation does not implement monitoring.
- Do not add scheduler, daemon, websocket, polling, notifications, or alert delivery.

## Previous-Run Decision Delta

Artifact:

```text
analysis/decision_intelligence_delta.json
```

Purpose:

- Compare current decision-intelligence artifacts with the nearest usable previous successful run.

Artifact type:

```text
decision_intelligence_delta
```

Previous successful run definition:

```text
The previous successful run is the nearest run before the current run under the same configured run output directory whose run_manifest.json records a successful main product run and whose decision-intelligence artifacts are present and valid enough for comparison.
```

No previous run:

```json
{
  "status": "no_previous_run",
  "previous_run_id": null,
  "previous_run_path": null,
  "changes": [],
  "warnings": [
    "No previous successful decision-intelligence run found."
  ]
}
```

Changed-field record:

```json
{
  "change_id": "decision_delta:binance:BTCUSDT:1d:risk_level",
  "scope": {
    "source": "binance",
    "symbol": "BTCUSDT",
    "timeframe": "1d"
  },
  "field": "risk_level",
  "from": "medium",
  "to": "high",
  "source_artifacts": []
}
```

Rules:

- Compare at least regime, risk level, action level, decision bias, invalidation status, and major watch triggers when those fields exist.
- Do not compare raw OHLCV history.
- Do not introduce SQLite, a new state store, or a background state service.
- If previous artifacts are missing, invalid, or not decision-intelligence artifacts, record `no_previous_run` or warnings.
- The delta consumes structured JSON artifacts. It does not consume `decision_intelligence_material.md`.

## AI-Readable Decision Material

Artifact:

```text
analysis/decision_intelligence_material.md
```

Purpose:

- Provide compact AI-readable decision material for Codex report generation.

Front matter:

```yaml
artifact_type: analysis_decision_intelligence_material
schema_version: 1
audience: ai
run_id: 20260606T000000Z
source_artifacts:
  - analysis/market_regime_assessment.json
  - analysis/risk_assessment.json
  - analysis/decision_recommendations.json
  - analysis/watch_triggers.json
  - analysis/decision_intelligence_delta.json
```

Required sections:

```text
source_policy
decision_overview
regime
risk
recommendations
do_not_do
invalidation_conditions
watch_triggers
delta_vs_previous_run
evidence_conflicts_uncertainty
report_usage_rules
record: <decision record id>
```

Rules:

- Reference all source decision-intelligence JSON artifacts.
- Include per-source, per-symbol, and per-timeframe summaries when records support them.
- Clearly separate action guidance, evidence, risks, conflicts, uncertainty, invalidation conditions, and deltas.
- State that recommendations are research decision support, not trading execution, account operations, financial advice, or return promises.
- Preserve source artifact references.
- Keep existing `analysis/market_signal_material.md` as the upstream quant evidence material.
- Do not ask Codex to infer action levels from raw strategy artifacts.

## Research Context and Codex Context Integration

Decision-intelligence material may be added to the existing report context when generated.

`analysis/research_context.md` contract additions:

```yaml
market_regime_assessment: analysis/market_regime_assessment.json
risk_assessment: analysis/risk_assessment.json
decision_recommendations: analysis/decision_recommendations.json
watch_triggers: analysis/watch_triggers.json
decision_intelligence_delta: analysis/decision_intelligence_delta.json
decision_intelligence_material: analysis/decision_intelligence_material.md
```

Rules:

- Embed or reference `analysis/decision_intelligence_material.md`.
- Preserve existing market material, text material, and quant signal material.
- Keep upstream quant material as evidence and decision material as synthesis.
- Codex consumes decision material for report language only.
- Codex must not invent action levels, prices, strategy conclusions, signals, trading instructions, or unsupported certainty.

Prompt rules:

- Require supported sections for current decision view, what to do, what not to do, tentative opportunities, wait/watch conditions, risk state, invalidation conditions, changes versus previous run, uncertainty, and method limits when decision material exists.
- Require cautious language for uncertain market conclusions.
- Require evidence and risk conditions near decision guidance.
- Forbid upgrading unsupported or low-confidence material into strong advice.
- Forbid trading instructions, position sizing, account actions, return promises, and investment recommendations.

Report-level fusion rule:

- Use quant material for upstream evidence.
- Use decision material for deterministic decision synthesis.
- When quant evidence and decision synthesis conflict, show the conflict and prefer conservative decision language.
- When decision material is missing, do not ask Codex to recreate decision intelligence from quant artifacts.
- When decision material says `WATCH`, `NO_ACTION`, or non-actionable status, the report must not turn it into `DO` language.

## Run Manifest Expectations

`run_manifest.json` records a `decision_intelligence` section for decision-intelligence status and debugging.

Skipped when quant is disabled:

```json
{
  "decision_intelligence": {
    "enabled": false,
    "status": "skipped",
    "reason": "quant_disabled",
    "artifacts": {},
    "counts": {
      "regime_records": 0,
      "risk_records": 0,
      "decision_recommendations": 0,
      "watch_triggers": 0,
      "changed_delta_records": 0
    },
    "previous_run": {
      "status": "not_checked",
      "run_id": null,
      "path": null
    },
    "warnings": [],
    "errors": []
  }
}
```

Succeeded or partially succeeded:

```json
{
  "decision_intelligence": {
    "enabled": true,
    "status": "succeeded",
    "artifacts": {
      "market_regime_assessment": "analysis/market_regime_assessment.json",
      "risk_assessment": "analysis/risk_assessment.json",
      "decision_recommendations": "analysis/decision_recommendations.json",
      "watch_triggers": "analysis/watch_triggers.json",
      "decision_intelligence_delta": "analysis/decision_intelligence_delta.json",
      "decision_intelligence_material": "analysis/decision_intelligence_material.md"
    },
    "counts": {
      "regime_records": 4,
      "risk_records": 4,
      "decision_recommendations": 4,
      "watch_triggers": 12,
      "changed_delta_records": 3
    },
    "previous_run": {
      "status": "compared",
      "run_id": "20260605T000000Z",
      "path": "runs/20260605T000000Z"
    },
    "warnings": [],
    "errors": []
  }
}
```

Rules:

- Record enabled and status fields.
- Record all produced decision-intelligence artifact paths.
- Record counts for regime records, risk records, decision recommendations, watch triggers, and changed delta records.
- Record previous-run comparison status and previous run id or path when available.
- Record warnings and errors.
- Handle partial failure without silently reporting success.
- Do not embed full decision artifacts into the manifest.

## Pipeline Stage Contract

Intended stage order addition:

```text
build_market_signal_material
build_market_regime_assessment
build_risk_assessment
build_decision_recommendations
build_watch_triggers
build_decision_intelligence_delta
build_decision_intelligence_material
build_research_context
```

Rules:

- Use one pipeline stage per decision-intelligence artifact.
- Place decision-intelligence stages after market signal material generation and before research context generation.
- `build_decision_intelligence_delta` runs after current regime, risk, decision, and watch artifacts exist.
- `build_decision_intelligence_material` consumes the delta artifact.
- Failure handling should preserve artifacts from completed stages and record actionable errors.
- Do not write fake artifacts to make downstream stages appear complete.

## Missing-Upstream and Insufficient-Data Behavior

Decision intelligence distinguishes disabled, missing, insufficient, and partial evidence states.

| Situation | Behavior |
| --- | --- |
| `quant.enabled: false` | Skip decision intelligence. Do not write decision-intelligence JSON or Markdown artifacts. Record skipped and zero counts in the manifest. |
| `quant.enabled: true`, required upstream quant artifact missing | Write an error or fail the producing stage according to existing pipeline error policy. Do not fabricate evidence. |
| `quant.enabled: true`, upstream record has insufficient data | Write decision-intelligence artifacts with `unknown`, `WATCH`, `NO_ACTION`, warnings, or non-actionable status as appropriate. |
| Partial upstream evidence exists | Preserve usable evidence, record warnings for missing pieces, and avoid unsupported conclusions. |
| Conflicting upstream evidence exists | Record conflicts and cap or downgrade decision strength. |

Rules:

- Unknown output is valid only when quant is enabled but upstream evidence is missing, insufficient, conflicting, or weak.
- Unknown output is not a substitute for skipped behavior when quant is disabled.
- Missing evidence should be visible in warnings, errors, uncertainty, or non-actionable decision status.
- Do not silently rewrite missing evidence into conclusions.

## Acceptance Trace

- Decision-intelligence JSON and Markdown artifact contracts are defined above.
- Upstream quant artifacts are retained and used as evidence.
- Decision-intelligence artifacts are additive derived artifacts, not replacements for quant artifacts.
- Missing-upstream, insufficient-data, skipped, partial, and conflict behavior are defined.
- Action recommendations must come from deterministic Halpha logic, not Codex or another LLM.
- Action taxonomy is research decision-support language only.
- The intended pipeline position is after market signal material and before research context.
