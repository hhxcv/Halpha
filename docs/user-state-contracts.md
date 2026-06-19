# User State Contracts

This document defines Halpha user-state and personalized-risk contracts. It is
durable product documentation, not a milestone plan.

The contracts below are intended for local-first personalization. They do not
create account integration, portfolio automation, position sizing, order
placement, or trading execution.

Until the corresponding pipeline stages are implemented, product runs may not
write every artifact described here. Implementations should update this document
as behavior evolves.

## Scope

User-state personalization lets Halpha distinguish general market intelligence
from constraints that matter to a configured local user.

Supported information classes:

- local watchlist;
- disabled assets;
- risk preference;
- preferred timeframes;
- strategy preferences;
- optional manual exposure notes as local-only input.

Out of scope:

- broker, exchange, wallet, custodian, or account integration;
- automatic holdings import;
- balances, orders, fills, tax lots, PnL, account IDs, or broker IDs;
- portfolio allocation, position sizing, VaR, or stress-test optimization;
- trade execution, order placement, cancellation, or account operations;
- hosted profile services, vector databases, black-box personalization models,
  or hidden user state;
- scheduler, daemon, websocket, push notification, or alert delivery runtime.

## Pipeline Position

```text
optional local user-state input
+ intelligence fusion
+ decision recommendations
+ watch triggers
+ alert decisions
-> analysis/user_state_context.json
-> analysis/personalized_risk_constraints.json
-> decision/watch/alert personalization fields
-> analysis/personalized_risk_material.md
-> research context
-> Codex context
-> Simplified Chinese report
```

The user-state layer is additive. It must preserve existing fusion, decision,
watch, alert, event, risk, strategy, feature, factor, data-quality, and outcome
artifacts.

## Local Input Contract

The product should support omitted user state and configured local user state.
Configuration should be explicit. A disabled or omitted configuration must not
fabricate personalization.

Example public config shape:

```yaml
user_state:
  enabled: false
  path: user_state.local.yaml
```

The example path is a placeholder. Real local paths and files must stay in
gitignored local configuration.

Example local user-state file shape:

```yaml
schema_version: 1
watchlist:
  - symbol: BTCUSDT
    timeframes: [1d, 1h]
    relevance: high
disabled_assets:
  - symbol: EXAMPLEUSDT
    reason_code: disabled_by_user
risk:
  preference: conservative
  max_risk_state: high
  max_action_level: WATCH
  allow_new_exposure: false
preferred_timeframes:
  - 1d
strategy_preferences:
  preferred:
    - breakout_atr_trend
  disabled:
    - example_strategy
manual_exposure_notes:
  - symbol: BTCUSDT
    exposure_state: watch
    private_note: local-only text omitted from report-facing artifacts
```

Allowed high-level input fields:

- `schema_version`
- `watchlist`
- `disabled_assets`
- `risk`
- `preferred_timeframes`
- `strategy_preferences`
- `manual_exposure_notes`

Implementations should reject unknown or invalid field shapes with actionable
errors. Error messages must not print raw private notes, local machine paths,
credentials, account identifiers, or other local privacy values.

## Privacy Rules

Local user-state input may contain private values. Halpha must treat them as
local-only configuration data.

Never write to public docs, public issues, public PRs, examples, logs, Codex
input, or final reports:

- real local file paths;
- usernames, hostnames, ports, proxy URLs, credentials, tokens, cookies, or
  private endpoints;
- account IDs, wallet addresses, broker IDs, exchange account identifiers, or
  payment identifiers;
- raw private notes;
- exact holdings, balances, position sizes, entry prices, or PnL values.

Local artifacts may preserve sanitized user-facing research fields when they are
needed for the report, such as symbol, timeframe, preference category, disabled
state, and risk preference. Private notes should be counted and omitted unless
the user explicitly chooses a future report-safe field.

Path references in artifacts should use privacy-safe source labels such as
`configured_user_state` instead of absolute machine paths.

## analysis/user_state_context.json

Purpose:

- Normalize optional local user state.
- Validate schema and privacy boundaries.
- Provide sanitized user context for deterministic personalization.
- Preserve whether the run is general or personalized.

Contract shape:

```json
{
  "schema_version": 1,
  "artifact_type": "user_state_context",
  "run_id": "20260619T000000Z",
  "created_at": "2026-06-19T00:00:00Z",
  "status": "ok",
  "mode": "personalized",
  "source": {
    "configured": true,
    "source_ref": "configured_user_state",
    "raw_path_embedded": false,
    "raw_file_embedded": false
  },
  "privacy": {
    "private_notes_embedded": false,
    "machine_paths_embedded": false,
    "account_identifiers_embedded": false,
    "omitted_private_values": 1
  },
  "watchlist": [],
  "disabled_assets": [],
  "risk": {},
  "preferred_timeframes": [],
  "strategy_preferences": {},
  "manual_exposure_summary": [],
  "counts": {},
  "warnings": [],
  "errors": [],
  "source_artifacts": []
}
```

Allowed `status` values:

- `ok`
- `warning`
- `degraded`
- `failed`
- `skipped`

Allowed `mode` values:

- `general`: user state is omitted or disabled.
- `personalized`: sanitized user state is available.
- `invalid`: configured user state failed validation.

Required behavior:

- Omitted or disabled user state should produce an explicit skipped/general
  state rather than hidden defaults.
- Valid configured user state should produce sanitized records only.
- Invalid configured user state should fail or degrade the user-state stage
  without printing private values.
- Counts should include watchlist records, disabled assets, preferred
  timeframes, strategy preference records, manual exposure summary records,
  warnings, errors, and omitted private values where relevant.

## analysis/personalized_risk_constraints.json

Purpose:

- Convert sanitized user state plus current intelligence into deterministic
  constraints.
- Explain whether a record remains general or becomes personalized.
- Provide downstream decision, watch, alert, Codex, and report evidence.

Primary inputs:

- `analysis/user_state_context.json`
- `analysis/intelligence_fusion.json`
- `analysis/decision_recommendations.json`
- `analysis/watch_triggers.json`
- `analysis/alert_decisions.json`

Contract shape:

```json
{
  "schema_version": 1,
  "artifact_type": "personalized_risk_constraints",
  "run_id": "20260619T000000Z",
  "created_at": "2026-06-19T00:00:00Z",
  "status": "ok",
  "records": [],
  "coverage": [],
  "counts": {
    "records": 0,
    "state_counts": {},
    "action_counts": {},
    "warnings": 0,
    "errors": 0
  },
  "warnings": [],
  "errors": [],
  "source_artifacts": [
    "analysis/user_state_context.json"
  ]
}
```

Record shape:

```json
{
  "constraint_id": "personalized:BTCUSDT:1d:disabled_asset",
  "scope": {
    "symbol": "BTCUSDT",
    "timeframe": "1d"
  },
  "state": "disabled_asset_blocked",
  "action": "block",
  "severity": "high",
  "reason_codes": ["disabled_asset"],
  "matched_user_state": {
    "watchlist": true,
    "disabled_asset": true,
    "preferred_timeframe": true,
    "strategy_preference": false,
    "manual_exposure_summary": false
  },
  "upstream_records": [],
  "evidence": [],
  "uncertainty": [],
  "warnings": [],
  "errors": [],
  "source_artifacts": [
    "analysis/user_state_context.json",
    "analysis/intelligence_fusion.json"
  ]
}
```

Allowed `state` values:

- `general`
- `watchlist_relevant`
- `disabled_asset_blocked`
- `risk_limit_downgraded`
- `timeframe_mismatch`
- `strategy_preference_note`
- `insufficient_user_state`
- `skipped`
- `degraded`
- `failed`

Allowed `action` values:

- `none`
- `annotate`
- `downgrade`
- `block`
- `skip`

Rules:

- `disabled_asset_blocked` must not upgrade any decision or alert.
- `risk_limit_downgraded` may only make report-facing guidance more
  conservative.
- `timeframe_mismatch` should add uncertainty or downgrade stronger guidance
  when upstream evidence is outside preferred timeframes.
- `watchlist_relevant` may increase report salience but must not create a
  stronger action level by itself.
- Every non-general state must include source artifacts and reason codes.
- The artifact must not contain private notes, account identifiers, exact
  holdings, balances, or machine paths.

## Decision, Watch, And Alert Integration

Downstream artifacts may include personalization fields after constraints are
generated.

Expected fields:

- `personalized_constraint_id`
- `personalized_state`
- `personalized_action`
- `personalized_reason_codes`
- `personalized_evidence`
- `personalized_uncertainty`
- `personalized_source_artifacts`

When personalization changes a record, preserve pre-personalization values such
as:

- `pre_personalized_action_level`
- `pre_personalized_decision_bias`
- `pre_personalized_recommended_actions`
- `pre_personalized_priority`
- `pre_personalized_trigger_state`

Integration must be conservative. It may block, downgrade, annotate, or add
uncertainty. It must not create stronger action levels, higher alert priorities,
position sizes, allocations, or trading instructions.

## analysis/personalized_risk_material.md

Purpose:

- Provide bounded AI-readable personalized-risk material.
- Explain only Halpha-generated personalized constraints.
- Keep raw local user-state files and private values out of Codex input.

Required boundary metadata:

```yaml
artifact_type: analysis_personalized_risk_material
full_user_state_file_embedded: false
private_notes_embedded: false
machine_paths_embedded: false
account_identifiers_embedded: false
full_personalized_risk_constraints_json_embedded: false
codex_may_explain_personalized_constraints: true
codex_may_generate_user_state: false
codex_may_generate_holdings: false
codex_may_generate_allocations: false
codex_may_generate_position_sizing: false
codex_may_generate_action_levels: false
codex_may_generate_price_forecasts: false
financial_advice: false
```

Material should prefer high-impact constraints before low-impact annotations:

1. blocked disabled assets;
2. risk-limit downgrades;
3. timeframe mismatches affecting stronger guidance;
4. watchlist-relevant records;
5. strategy preference notes;
6. general or skipped records summarized by count.

Material should record selected counts, omitted counts, omitted state counts,
omission reasons, warnings, errors, and source artifacts.

## Manifest Expectations

`run_manifest.json` should record:

- artifact paths for user-state context, personalized-risk constraints, and
  personalized-risk material;
- user-state mode and status;
- sanitized record counts;
- omitted private value counts;
- constraint state counts and action counts;
- decision, watch, and alert integration counts;
- warning and error counts;
- Codex input budget metadata for `analysis/personalized_risk_material.md`.

Manifest fields must not contain absolute local paths, raw private notes, exact
holdings, balances, account IDs, or other local privacy values.

## Data Quality And Inspection

Data quality should cover:

- presence and shape of `analysis/user_state_context.json`;
- privacy boundary checks for user-state context;
- presence and shape of `analysis/personalized_risk_constraints.json`;
- state counts, action counts, warning counts, and error counts;
- material boundary metadata and Codex budget state.

`python -m halpha data inspect --config config.example.yaml` should summarize
user-state and personalized-risk status, counts, state counts, integration
counts, warnings, errors, and budget state without dumping raw local user-state
records or private values.

## Codex And Report Boundary

Codex may:

- explain Halpha-generated personalized constraints;
- distinguish general intelligence from personalized constraints;
- cite source artifacts and uncertainty;
- explain why a disabled asset, risk preference, timeframe preference, or
  watchlist match made output more conservative.

Codex must not:

- infer hidden user state;
- create or revise holdings;
- create allocations;
- size positions;
- create action levels or alert priorities;
- generate price forecasts;
- generate trading instructions;
- expose raw local user-state files, private notes, machine paths, credentials,
  account identifiers, balances, or PnL.

Reports may explain personalized constraints conservatively, but structured
personalized states and adjustment reasons must come from Halpha artifacts.

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

- `analysis/user_state_context.json`
- `analysis/personalized_risk_constraints.json`
- `analysis/personalized_risk_material.md`
- personalized fields in `analysis/decision_recommendations.json`
- personalized fields in `analysis/watch_triggers.json`
- personalized fields in `analysis/alert_decisions.json`
- `analysis/data_quality_summary.json`
- `analysis/research_context.md`
- `codex_context/context.md`
- `codex_context/prompt.md`
- `report/report.md` when Codex CLI validation is run
- `run_manifest.json`

Validation should confirm that personalization is explicit, deterministic,
bounded for Codex input, privacy-preserving, and not generated by Codex.
