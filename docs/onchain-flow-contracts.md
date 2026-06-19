# On-Chain Flow Contracts

This document defines Halpha's on-chain and exchange-flow context contracts. It
is a durable implementation contract, not a milestone-only plan and not an
implementation record.

On-chain and exchange-flow evidence is crypto-specific liquidity, network
activity, network congestion, and source-availability context. It does not
replace spot OHLCV evidence, derivatives evidence, macro/calendar evidence,
strategy evidence, event intelligence, decision intelligence, alert decisions,
outcome tracking, or report generation.

On-chain and exchange-flow outputs are personal research material. They are not
trades, orders, account operations, deposits, withdrawals, wallet instructions,
portfolio instructions, position sizing, forecasts, or financial advice.

## Related Docs

- `README.md`: project overview, implemented commands, and validation.
- `AGENTS.md`: AI-agent rules, artifact expectations, and validation rules.
- `docs/artifact-governance.md`: artifact layers, Codex input policy, and
  documentation index.
- `docs/research-data-contracts.md`: shared local research data, run index,
  text-event history, data-quality, and local-store contracts.
- `docs/quant-contracts.md`: market data, strategy, evaluation, signal, and
  strategy-material contracts.
- `docs/derivatives-market-contracts.md`: derivatives and market-structure
  data, context, material, and Codex-boundary contracts.
- `docs/macro-calendar-contracts.md`: macro and scheduled-event data, context,
  material, and Codex-boundary contracts.
- `docs/event-intelligence-contracts.md`: event evidence, confluence,
  assessment, alert-adjacent event contracts, and event material.
- `docs/decision-intelligence-contracts.md`: regime, risk, recommendation,
  watch trigger, delta, alert decision, and decision-material contracts.
- `docs/outcome-tracking-contracts.md`: outcome target, evaluation, history,
  material, and Codex-boundary contracts.

## Contract Status

This file separates stable direction from shipped behavior.

- `contract`: expected durable interface or rule.
- `initial adoption`: first implementation slice.
- `planned`: intended contract whose producer is not implemented yet.
- `not implemented yet`: allowed future contract detail that must not be
  described as shipped behavior.

README should describe only user-visible behavior that exists. This file may
define intended contracts before implementation when they are needed to guide a
focused issue.

Contract set:

| Contract | Status | Producer | Consumer |
| --- | --- | --- | --- |
| Raw on-chain flow artifact | initial adoption | on-chain flow collection stage | reusable history, data quality |
| Shared on-chain flow history | initial adoption | on-chain flow history writer | current-run views, data inspection |
| On-chain flow current-run views | initial adoption | on-chain flow view builder | context, data quality |
| On-chain flow context | initial adoption | context builder | regime, risk, decisions, watches, alerts, outcomes, material |
| On-chain flow material | initial adoption | material builder | research context, Codex context, report |

## Scope

Define contracts for:

- stablecoin supply and stablecoin market-cap observations;
- broad BTC or configured chain activity observations where stable public
  sources exist;
- network congestion observations such as mempool size, fee pressure, or
  equivalent bounded public metrics where stable public sources exist;
- exchange-flow source availability when reliable unauthenticated periodic
  exchange netflow is not available;
- reusable local on-chain flow history;
- current-run on-chain flow views;
- deterministic on-chain flow context records;
- downstream risk, decision, watch, event, alert, outcome, and report
  consumers;
- data-quality, manifest, inspection, and Codex-boundary expectations.

## Out of Scope

- Code implementation.
- Dependency installation.
- Authenticated APIs.
- Paid data vendors.
- Exchange account access, balances, orders, deposits, withdrawals, or margin
  state.
- User wallet access, private keys, wallet signatures, account-specific data,
  or portfolio automation.
- Wallet clustering, address labeling, entity attribution, token transfer graph
  analysis, chain forensics, or exchange reserve proof.
- Reliable exchange netflow when only paid, account-bound, proprietary, or
  non-periodic sources are available.
- Websocket streaming, mempool monitoring runtime, scheduler, daemon, alert
  delivery runtime, push notifications, or dashboard.
- Trading execution, order placement, position sizing, broker integration, or
  exchange account operations.
- On-chain predictive models, price prediction, or LLM-generated flow
  conclusions.

## Technology Boundaries

On-chain and exchange-flow source access must use configured public
unauthenticated sources unless a later explicit requirement changes this
boundary.

Rules:

- Do not require credentials, tokens, cookies, user accounts, exchange accounts,
  trading accounts, private keys, wallet signatures, or paid terminal sessions.
- Do not persist third-party client objects as Halpha contracts.
- Do not embed full raw chain streams, address-level records, or reusable
  on-chain flow history in Codex input.
- Use Halpha-owned JSON, Markdown, Parquet, or plain metadata artifacts as the
  stable downstream contract.
- Treat missing exchange-flow coverage as source availability evidence, not as
  neutral market evidence.

Initial adoption should prefer a small number of stable public sources over
broad but fragile coverage. Suitable initial public-source classes include
stablecoin supply from a free public analytics API and broad BTC network
activity or congestion metrics from a public charts API. The contract does not
require address-level analytics or reliable exchange netflow before one
source-backed path is working end to end.

## Pipeline Position

Intended product flow:

```text
configured public on-chain or flow source
  -> raw on-chain flow artifact [initial adoption]
  -> shared on-chain flow history [initial adoption]
  -> on-chain flow current-run views [initial adoption]
  -> on-chain flow context [initial adoption]
  -> regime, risk, decision, watch, alert, outcome, and strategy interpretation
  -> on-chain flow material [initial adoption]
  -> research context
  -> Codex context + prompt
  -> Simplified Chinese Markdown report
```

Pipeline insertion should preserve the existing product command:

```bash
python -m halpha run --config config.example.yaml
```

No on-chain flow stage should fabricate skipped downstream artifacts to make
later stages appear complete.

## Common State Rules

On-chain flow artifacts must distinguish these states where applicable:

```text
succeeded
ok
normal
abnormal
warning
degraded
skipped
unavailable
stale
partial
insufficient_data
failed
```

Rules:

- `skipped` means the class is disabled or not configured.
- `unavailable` means the configured source does not provide a reliable
  product-run input for the class.
- `stale` means the latest usable record is older than the configured
  freshness window.
- `partial` means some configured assets, chains, classes, or source windows
  succeeded while others failed or were unavailable.
- `degraded` means evidence exists but has quality limitations such as missing
  units, sparse history, unstable source timestamps, or bounded coverage.
- `normal` and `abnormal` are deterministic Halpha context states, not trading
  instructions.
- Missing, skipped, unavailable, stale, partial, degraded, or
  insufficient-data evidence must not be interpreted as neutral or low risk.
- Codex may explain these states only from Halpha-generated material.

## Data Class Contract

Planned data classes:

| Data class | Purpose | Required source state |
| --- | --- | --- |
| `stablecoin_supply` | Identify broad stablecoin liquidity expansion, contraction, or source limitations. | Implement when a stable public unauthenticated source exposes timestamped stablecoin supply or market-cap observations. |
| `chain_activity` | Identify broad configured-chain activity changes such as transaction count or transfer volume where available. | Implement when a stable public unauthenticated source exposes timestamped activity observations. |
| `network_congestion` | Identify network congestion or fee-pressure context from bounded public metrics such as mempool or fee observations. | Implement when a stable public unauthenticated source exposes timestamped congestion observations. |
| `exchange_flow_availability` | Record whether reliable periodic unauthenticated exchange inflow, outflow, or netflow evidence is available. | Implement as explicit availability evidence even when no suitable public periodic source exists. |

Rules:

- A data class may be absent only when disabled or not configured.
- A configured but unsupported class must produce `unavailable` or `degraded`
  source-state evidence.
- Stablecoin supply is liquidity context, not a direct price signal.
- Chain activity and network congestion are context inputs, not trade direction
  by themselves.
- Exchange-flow availability must not fabricate inflow, outflow, or netflow
  values when a reliable public source is missing.
- Data classes should be expanded only when a downstream consumer is ready to
  use the evidence conservatively.

## Raw On-Chain Flow Artifact

Implemented artifact:

```text
raw/onchain_flow.json
```

Purpose:

- preserve current-run public on-chain and flow observations;
- keep source endpoint identity and parsing warnings inspectable;
- provide input to reusable history and current-run views.

Top-level contract:

```json
{
  "schema_version": 1,
  "artifact_type": "onchain_flow_raw",
  "collector": "onchain_flow",
  "collection_method": "public_http",
  "source": {
    "name": "example_public_onchain_source",
    "url": "https://example.invalid"
  },
  "collected_at": "2026-06-19T00:00:00Z",
  "items": [],
  "availability": [],
  "warnings": [],
  "errors": []
}
```

Required item fields:

```json
{
  "item_id": "onchain_flow:stablecoin_supply:example:all:2026-06-19T00:00:00Z",
  "data_class": "stablecoin_supply",
  "source": "example_public_onchain_source",
  "asset": "ALL_STABLECOINS",
  "chain": "all",
  "as_of": "2026-06-19T00:00:00Z",
  "endpoint": "stablecoincharts_all",
  "metrics": {},
  "units": {},
  "raw_fields": {},
  "warnings": [],
  "errors": []
}
```

Rules:

- `item_id` must be deterministic.
- `data_class`, `source`, `as_of`, `metrics`, and source endpoint identity are
  required.
- `asset` or `chain` should be present when the source scope supports it.
- `raw_fields` may preserve bounded source fields needed for audit, but must
  not store credentials, private endpoints, local proxy values, wallet
  addresses, account identifiers, or large raw pages.
- Endpoint failures should be represented in `errors` or `availability`, not by
  fabricating neutral records.

## Shared On-Chain Flow History

Implemented reusable storage:

```text
data/onchain/flow/
data/onchain/metadata/onchain_flow_schema.json
data/onchain/metadata/onchain_flow_state.json
```

Purpose:

- preserve reusable on-chain flow observations outside per-run report
  directories;
- provide bounded current-run views for context generation;
- support data inspection and quality checks.

Required record identity:

```text
source + data_class + asset_or_chain_scope + as_of
```

Required behavior:

- append or merge deterministic records from raw on-chain flow artifacts;
- warn on conflicting duplicates instead of silently replacing source evidence;
- preserve source endpoint and source artifact references;
- keep full reusable history outside Codex input;
- record implemented, skipped, unavailable, stale, partial, degraded,
  insufficient-data, and failed data classes in state metadata.

## On-Chain Flow Current-Run Views

Implemented artifact:

```text
raw/onchain_flow_views.json
```

Purpose:

- expose bounded current-run on-chain flow windows and storage refs;
- avoid embedding full reusable history into analysis or Codex context.

Record fields:

```json
{
  "view_id": "onchain_flow_view:stablecoin_supply:example:all:2026-06-19T00:00:00Z",
  "data_class": "stablecoin_supply",
  "source": "example_public_onchain_source",
  "asset": "ALL_STABLECOINS",
  "chain": "all",
  "input_window_start": "2026-06-12T00:00:00Z",
  "input_window_end": "2026-06-19T00:00:00Z",
  "latest_observation_time": "2026-06-19T00:00:00Z",
  "row_count": 8,
  "status": "succeeded",
  "storage_ref": "data/onchain/flow/source=example_public_onchain_source/data_class=stablecoin_supply",
  "warnings": [],
  "errors": [],
  "source_artifacts": []
}
```

Rules:

- Views record metadata and selected bounded rows or summaries only when needed.
- Large reusable histories must be referenced by `storage_ref`, not embedded.
- Missing or stale windows must produce explicit status and warnings.

## On-Chain Flow Context

Implemented artifact:

```text
analysis/onchain_flow_context.json
```

Purpose:

- turn on-chain flow views into deterministic context states;
- expose conservative evidence for regime, risk, decision, alert, outcome, and
  report consumers.

Top-level contract:

```json
{
  "schema_version": 1,
  "artifact_type": "onchain_flow_context",
  "run_id": "20260619T000000Z",
  "created_at": "2026-06-19T00:00:00Z",
  "status": "warning",
  "records": [],
  "counts": {},
  "warnings": [],
  "errors": [],
  "source_artifacts": []
}
```

Record fields:

```json
{
  "context_id": "onchain_flow_context:stablecoin_liquidity:example:all:2026-06-19T00:00:00Z",
  "context_type": "stablecoin_liquidity",
  "data_class": "stablecoin_supply",
  "source": "example_public_onchain_source",
  "asset": "ALL_STABLECOINS",
  "chain": "all",
  "as_of": "2026-06-19T00:00:00Z",
  "status": "succeeded",
  "state": "normal",
  "severity": "low",
  "confidence": "medium",
  "metrics": {},
  "thresholds": {},
  "evidence": [],
  "uncertainty": [],
  "warnings": [],
  "errors": [],
  "source_artifacts": []
}
```

Context types:

```text
stablecoin_liquidity
chain_activity
network_congestion
exchange_flow_source_availability
```

Rules:

- Context states are generated by deterministic Halpha logic.
- Stablecoin liquidity expansion or contraction may raise or qualify risk; it
  must not generate trade direction by itself.
- Chain activity and network congestion may indicate network or liquidity
  pressure; they must not create price targets.
- Exchange-flow availability records must state whether reliable periodic
  exchange inflow, outflow, or netflow evidence is implemented, unavailable,
  stale, degraded, or failed.

## Downstream Consumer Rules

Market regime and risk:

- May cite on-chain flow context as evidence, conflict, uncertainty, or risk
  escalation.
- Missing or unavailable on-chain flow context must not lower risk.
- Abnormal liquidity, activity, congestion, or source-availability limitations
  may cap confidence or raise blocking risks.

Decision recommendations and watch triggers:

- May cite on-chain flow context as risk conditions, downgrade reasons,
  invalidation pressure, risk-relief triggers, or recheck triggers.
- Must not create account actions, orders, wallet actions, position sizing,
  hedging instructions, or trading execution.

Event intelligence and alert decisions:

- May cite on-chain flow context only when event, risk, decision, or watch
  evidence supports relevance.
- Must not create high-priority alerts from unavailable source evidence alone.
- Must preserve low-confidence, no-alert, and downgrade behavior.

Outcome tracking:

- May record later follow-through for previous on-chain flow context records
  when those records exist.
- Must use as-of timestamps and no-lookahead windows.

Strategy interpretation:

- May explain whether on-chain flow context supports, conflicts with, or limits
  current strategy evidence.
- Must not promote or reject strategies solely from on-chain flow context unless
  a later strategy gate explicitly supports that behavior.

## On-Chain Flow Material

Artifact:

```text
analysis/onchain_flow_material.md
```

Purpose:

- provide bounded AI-readable on-chain flow context for Codex report
  generation;
- avoid embedding raw endpoint payloads, address-level records, or full reusable
  on-chain flow history.

Required sections:

```text
source_policy
onchain_flow_overview
material_budget
stablecoin_liquidity
chain_activity
network_congestion
exchange_flow_source_availability
data_quality
downstream_implications
report_usage_rules
selected_records
```

Rules:

- Include high-severity context records first.
- Summarize normal, skipped, unavailable, stale, partial, degraded, and
  low-severity records with counts and representative examples only when useful.
- Preserve source artifacts and source limitations.
- State that on-chain flow context is research context, not trading instruction
  or forecast.
- Include `codex_may_generate_onchain_records: false`,
  `codex_may_generate_flow_states: false`,
  `codex_may_generate_address_labels: false`,
  `codex_may_generate_risk_levels: false`, and
  `full_onchain_flow_context_json_embedded: false`.
- Record selected-record and omitted-record counts in `run_manifest.json` and
  Codex input budget metadata through the standard material budget mechanism.

## Codex Boundary

Codex may:

- explain Halpha-generated on-chain flow context states;
- describe source availability and data-quality limitations;
- explain whether on-chain flow context confirms, conflicts with, or does not
  affect current Halpha decision evidence.

Codex must not:

- create on-chain records, flow states, severities, risk levels, signals, or
  address labels;
- infer missing exchange-flow values, wallet clusters, entity identities, source
  data, or market impact;
- inspect reusable on-chain stores, raw endpoint payloads, SQLite indexes, or
  Parquet tables;
- calculate stablecoin flows, exchange netflows, chain activity, mempool
  pressure, or congestion from raw data unless Halpha has generated the
  corresponding context artifact;
- generate trading instructions, wallet actions, position sizing, account
  actions, price forecasts, or return promises.

Final report post-processing may insert a bounded deterministic on-chain flow
evidence section from `analysis/onchain_flow_context.json` when
`analysis/onchain_flow_material.md` exists. This inserted section must cite the
material artifact and source artifacts, distinguish supported abnormal, normal,
unavailable, stale, degraded, partial, insufficient-data, and failed states, and
must not create new on-chain records, flow states, risk levels, forecasts, or
trading instructions.

## Manifest Expectations

`run_manifest.json` records implemented on-chain flow summaries:

- raw on-chain flow artifact path and counts;
- reusable on-chain flow history state and store counts;
- on-chain flow current-run view counts and unavailable classes;
- on-chain flow context counts by context type, state, severity, status,
  warning, and error;
- on-chain flow material path, selected counts, omitted counts, and Codex input
  budget metadata;
- source availability for configured on-chain and exchange-flow classes.

Do not embed full raw on-chain flow artifacts, reusable history, address-level
records, or context records into the manifest.

## Data Quality Expectations

Data quality should cover:

- raw on-chain flow artifact presence and schema;
- source partial failures;
- malformed values;
- missing assets, chains, scopes, or data classes;
- stale timestamps;
- duplicate or conflicting records;
- reusable history status;
- current-run view coverage;
- unavailable exchange-flow source states;
- Codex input boundaries for on-chain flow material.

Rules:

- Quality warnings should remain visible.
- Data quality should not repair or rewrite source evidence.
- Unavailable source classes should be explicit and should not imply neutral
  on-chain or flow risk.

## Validation Rules

Automated validation should cover:

- config validation;
- source payload parsing;
- skipped and disabled on-chain flow config;
- missing, stale, partial, unavailable, degraded, insufficient-data, and failed
  data states;
- stablecoin supply context classification;
- chain activity context classification;
- network congestion context classification;
- exchange-flow source availability behavior;
- data-quality and inspection output;
- Codex material boundaries.

Real-source validation should use existing product commands and inspect
generated artifacts. Full report validation sends generated local research
context to Codex CLI.
