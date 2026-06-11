# Outcome Tracking Contracts

This document defines Halpha outcome tracking contracts. Outcome tracking
compares earlier research targets with later observable evidence so reports can
carry accountability evidence. It is a durable implementation contract, not a
milestone-only plan and not an implementation record.

Outcome tracking is incremental. Contracts marked planned describe intended
behavior and must not be described as shipped product behavior until producers
are implemented.

Outcome tracking outputs are personal research material. They are not trades,
orders, account operations, portfolio instructions, position sizing, return
promises, price forecasts, or financial advice.

## Related Docs

- `README.md`: project overview, implemented commands, and validation.
- `AGENTS.md`: AI-agent rules, artifact expectations, and validation rules.
- `docs/artifact-governance.md`: artifact layers, Codex input policy, and
  documentation index.
- `docs/research-data-contracts.md`: shared local research data, run index,
  text-event history, and data-quality contracts.
- `docs/quant-contracts.md`: upstream market, strategy, evaluation, signal, and
  strategy-material contracts.
- `docs/event-intelligence-contracts.md`: upstream text event, NLP evidence,
  topic, signal, confluence, and assessment contracts.
- `docs/decision-intelligence-contracts.md`: upstream regime, risk,
  recommendation, watch trigger, delta, alert decision, and decision-material
  contracts.

## Contract Status

| Contract | Status | Producer | Consumer |
| --- | --- | --- | --- |
| Outcome targets | Implemented | outcome target extraction stage | outcome evaluation, outcome material |
| Outcome evaluations | Implemented | outcome evaluation stage | outcome history, outcome material |
| Outcome history | Implemented | outcome history writer | later runs, data inspection, outcome material |
| Outcome tracking material | Planned | outcome material stage | research context, Codex context, report |

README should describe only user-visible behavior that exists. This file may
define intended contracts before implementation when they are needed to guide a
focused issue.

## Scope

Define contracts for:

- target extraction from earlier Halpha artifacts;
- market and strategy outcome evaluation from later OHLCV evidence;
- event, alert, decision, and watch follow-through evaluation from later
  Halpha artifacts;
- reusable outcome history;
- AI-readable outcome material;
- manifest, catalog, and Codex-boundary rules;
- no-lookahead and maturity-horizon behavior.

## Out Of Scope

- Code implementation.
- Dependency installation.
- New market or text sources.
- Model training or ML prediction.
- Strategy promotion, best-parameter selection, or capital allocation.
- Real-time monitoring, alert delivery, scheduler, daemon, or hosted service.
- Trading execution, order placement, account operations, or portfolio
  automation.
- Codex-generated outcome labels, target extraction, or evaluation scoring.

## Outcome Tracking Flow

Planned flow:

```text
previous run artifacts
  -> outcome target extraction
  -> outcome target artifact
  -> maturity horizon check
  -> current and shared evidence lookup
  -> deterministic outcome evaluation
  -> reusable outcome history
  -> bounded outcome tracking material
  -> research context
  -> Codex context + prompt
  -> Simplified Chinese Markdown report
```

Outcome tracking uses earlier run artifacts as targets and later evidence as
observations. It must never evaluate a target with evidence that existed before
the target's as-of timestamp.

## Common Rules

Common JSON top-level fields:

```json
{
  "schema_version": 1,
  "artifact_type": "artifact_name",
  "run_id": "20260611T000000Z",
  "created_at": "2026-06-11T00:00:00Z",
  "status": "ok",
  "source_artifacts": [],
  "counts": {},
  "warnings": [],
  "errors": []
}
```

Rules:

- `schema_version` starts at `1`.
- `artifact_type` must match the artifact contract name.
- `run_id` identifies the current run that produced the artifact.
- `created_at` is ISO 8601 UTC.
- `status` uses `ok`, `warning`, `degraded`, `skipped`, or `failed`.
- `source_artifacts` uses repo artifact paths or stable shared-data metadata
  paths.
- Record ordering is deterministic.
- Empty records require a status, warning, or error that explains why.
- Missing optional inputs produce `skipped` or `degraded`, not fabricated
  outcomes.

## No-Lookahead Rules

No-lookahead is a hard contract.

Each target must record:

- the source run id;
- the source artifact path;
- the source record id when available;
- the source record created or as-of timestamp;
- the target horizon and maturity rule.

Each evaluation must:

- use only observations strictly after the target as-of timestamp;
- record the observation window start and end;
- record source artifacts and shared-store references used for evidence;
- mark the record `pending` when the maturity horizon has not elapsed;
- mark the record `insufficient_data` when the horizon elapsed but required
  evidence is missing or too sparse;
- mark the record `stale` when the target is too old for the configured
  evaluation policy;
- mark the record `skipped` when the target type is unsupported or disabled;
- avoid deriving any target field from the later observation window.

If a no-lookahead violation is detected, the affected evaluation must be
`failed` or omitted with an artifact-level error. It must not be silently
accepted.

## Maturity Horizons

Targets use explicit maturity horizons. A horizon defines when later evidence is
allowed to be judged.

Required horizon fields:

- `horizon_id`
- `horizon_kind`
- `duration`
- `start_at`
- `matures_at`
- `expires_at`
- `observation_window_start`
- `observation_window_end`

Allowed `horizon_kind` values:

- `next_candle`
- `fixed_duration`
- `next_run`
- `event_follow_through`
- `decision_follow_through`

Maturity status values:

- `pending`: horizon has not matured.
- `matured`: horizon matured and can be evaluated.
- `evaluated`: evaluation has been written.
- `insufficient_data`: required later evidence is missing or too sparse.
- `skipped`: disabled or unsupported target.
- `stale`: horizon expired before sufficient evidence was available.
- `failed`: evaluation failed due to an implementation or contract error.

## Outcome Target Artifact

Implemented current-run artifact:

```text
analysis/outcome_targets.json
```

Purpose:

- extract bounded, traceable targets from prior Halpha research artifacts;
- preserve what was knowable at the target as-of time;
- provide deterministic inputs for later evaluation.

Required top-level fields:

- `schema_version`
- `artifact_type`
- `run_id`
- `created_at`
- `status`
- `previous_run`
- `target_policy`
- `targets`
- `skipped_records`
- `counts`
- `source_artifacts`
- `warnings`
- `errors`

Required target fields:

- `target_id`
- `target_kind`
- `source_run_id`
- `source_artifact`
- `source_record_id`
- `source_record_type`
- `source_created_at`
- `source_as_of`
- `source`
- `asset`
- `symbol`
- `timeframe`
- `horizon`
- `maturity_status`
- `expected_observation`
- `evidence`
- `uncertainty`
- `warnings`
- `errors`

Allowed `target_kind` values:

- `market_signal`
- `strategy_gate`
- `event_assessment`
- `alert_decision`
- `decision_recommendation`
- `watch_trigger`

`expected_observation` must be descriptive and evaluable. It may include fields
such as direction, threshold, category, state change, or follow-through
condition. It must not contain trading instructions.

Missing previous successful runs produce a `skipped` artifact with
`previous_run.status` set to `no_previous_run`. Skipped source records must
preserve source artifact, source record type, source record id when available,
reason, and missing fields when relevant.

## Outcome Evaluation Artifact

Implemented current-run artifact for market, strategy, event, alert, decision,
and watch targets.

```text
analysis/outcome_evaluations.json
```

Purpose:

- evaluate matured targets against later observable evidence;
- record pending, skipped, stale, insufficient-data, degraded, and failed
  states explicitly;
- preserve enough evidence for report use without embedding full stores into
  Codex context.

Required top-level fields:

- `schema_version`
- `artifact_type`
- `run_id`
- `created_at`
- `status`
- `evaluation_policy`
- `evaluations`
- `counts`
- `source_artifacts`
- `warnings`
- `errors`

Required evaluation fields:

- `outcome_id`
- `target_id`
- `source_run_id`
- `evaluation_run_id`
- `evaluated_at`
- `evaluation_status`
- `outcome_state`
- `observation_window`
- `metrics`
- `evidence`
- `source_artifacts`
- `warnings`
- `errors`

Current implementation rules:

- market and strategy targets are evaluated from shared OHLCV history;
- observation rows must be strictly after `source_as_of`;
- the anchor row at or before `source_as_of` is source-state context, not an
  observation row;
- event, alert, decision, and watch targets are evaluated from later Halpha
  artifacts and reusable text-event history;
- ambiguous later follow-through stays `unresolved`;
- missing later follow-through evidence stays `insufficient_data`;
- unsupported target kinds remain visible as `skipped`.

Allowed `evaluation_status` values:

- `pending`
- `matured`
- `evaluated`
- `skipped`
- `stale`
- `insufficient_data`
- `degraded`
- `failed`

Allowed `outcome_state` values:

- `aligned`
- `not_aligned`
- `confirmed`
- `contradicted`
- `unresolved`
- `no_change`
- `skipped`
- `stale`
- `insufficient_data`
- `failed`

Market and strategy evaluations should record:

- observation start and end timestamps;
- start and end close values where available;
- return percentage;
- maximum favorable excursion percentage;
- maximum adverse excursion percentage;
- threshold hit state when a threshold exists;
- sample count and coverage warnings;
- source OHLCV view or shared-store references.

Event, alert, decision, and watch follow-through evaluations should record:

- later artifacts inspected;
- confirming evidence count;
- contradicting evidence count;
- unresolved reason when no clear follow-through exists;
- downgrade, stale, duplicate, and insufficient-evidence state where relevant.

## Reusable Outcome History

Implemented reusable store root:

```text
data/research/outcomes/
```

Implemented history artifact:

```text
data/research/outcomes/outcome_history.json
```

Implemented state metadata:

```text
data/research/metadata/outcome_history_state.json
```

Purpose:

- preserve cross-run target and evaluation records;
- make prior targets discoverable without scanning every run directory;
- support later data inspection and report accountability material.

Required history fields:

- `stable_outcome_key`
- `outcome_id`
- `target_id`
- `target_kind`
- `source_run_id`
- `evaluation_run_ids`
- `first_evaluation_run_id`
- `latest_evaluation_run_id`
- `first_evaluated_at`
- `latest_evaluated_at`
- `source_as_of`
- `horizon_end`
- `evaluation_status`
- `outcome_state`
- `observation_start`
- `observation_end`
- `sample_rows`
- `metrics`
- `evidence`
- `uncertainty`
- `source_artifacts`
- `content_hash`
- `status`
- `warnings`
- `errors`

Required state metadata fields:

- `schema_version`
- `artifact_type`
- `updated_at`
- `status`
- `storage_path`
- `history_path`
- `state_path`
- `totals`
- `sources`
- `target_kinds`
- `outcome_states`
- `evaluation_statuses`
- `source_artifacts`
- `warnings`
- `errors`

Rules:

- store reusable history outside per-run report directories;
- use deterministic unique keys;
- make repeated writes idempotent;
- warn on conflicting duplicates instead of silently replacing evidence;
- keep full outcome history out of Codex input.

## Outcome Tracking Material

Planned current-run artifact:

```text
analysis/outcome_tracking_material.md
```

Purpose:

- provide bounded AI-readable accountability evidence;
- summarize high-signal target and outcome records;
- keep complete target, evaluation, and history artifacts inspectable outside
  Codex input.

Material must include boundary flags:

```text
codex_may_explain_outcome_states: true
codex_may_generate_outcome_labels: false
codex_may_score_prior_recommendations: false
full_outcome_history_embedded: false
```

Rules:

- include selected high-signal evaluated, contradicted, unresolved, and failed
  records before low-signal pending records;
- summarize omitted records with counts and reasons;
- cite source run ids and artifact paths;
- distinguish target evidence from later observation evidence;
- avoid embedding full outcome history, raw streams, shared OHLCV rows, SQLite
  contents, Parquet tables, or complete intermediate JSON.

## Manifest And Catalog Rules

Product runs record:

- `analysis/outcome_targets.json` path, status, target count, warning count,
  and error count;
- outcome target skipped record count and skipped reason counts;
- `analysis/outcome_evaluations.json` path, status, evaluated count, pending
  count, insufficient-data count, warning count, and error count;

When implemented, product runs should also record:

- `analysis/outcome_tracking_material.md` path and Codex input budget metadata;
- reusable outcome history state path and write status;
- run index references for outcome artifacts.

The research data catalog should include only implemented outcome stores. It
should summarize storage metadata and counts, not row dumps.

## Codex Boundary

Codex may:

- explain Halpha-generated target and outcome states;
- compare evaluated outcomes with current evidence visible in bounded material;
- discuss uncertainty and data-quality limitations recorded by Halpha.

Codex must not:

- generate target ids, target kinds, maturity states, evaluation labels, or
  outcome scores;
- infer outcomes from omitted raw data or stores;
- inspect full shared stores unless the material explicitly includes bounded
  excerpts;
- promote, select, or optimize strategies;
- produce trading instructions, position sizing, or price forecasts.

Codex context may include `analysis/outcome_tracking_material.md` after the
artifact is implemented. It must not embed full target, evaluation, or reusable
history records by default.

## Validation Rules

Automated validation should cover:

- deterministic target ids and evaluation ids;
- relative path references;
- no-lookahead enforcement;
- pending, matured, evaluated, skipped, stale, insufficient-data, degraded, and
  failed states;
- market directional alignment and threshold behavior;
- favorable and adverse excursion calculations;
- event, alert, decision, and watch follow-through state rules;
- duplicate and conflicting history writes;
- manifest and catalog references;
- Codex input boundaries and material budgets.

Real-source validation should use existing product commands and inspect the
generated artifacts once producers are implemented. Full report validation sends
generated local research context to Codex CLI.
