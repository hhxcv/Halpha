# Derivatives Market Contracts

This document defines Halpha's derivatives and market-structure data contracts.
It is a durable implementation contract, not a milestone-only plan and not an
implementation record.

Derivatives and market-structure evidence is market context. It does not replace
spot OHLCV evidence, strategy evidence, event intelligence, decision
intelligence, alert decisions, outcome tracking, or report generation.

Derivatives and market-structure outputs are personal research material. They
are not trades, orders, account operations, portfolio instructions, position
sizing, forecasts, or financial advice.

## Related Docs

- `README.md`: project overview, implemented commands, and validation.
- `AGENTS.md`: AI-agent rules, artifact expectations, and validation rules.
- `docs/artifact-governance.md`: artifact layers, Codex input policy, and
  documentation index.
- `docs/research-data-contracts.md`: shared local research data, run index,
  text-event history, data-quality, and local-store contracts.
- `docs/quant-contracts.md`: market data, strategy, evaluation, signal, and
  strategy-material contracts.
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
- `not implemented yet`: allowed future contract detail that must not be
  described as shipped behavior.

README should describe only user-visible behavior that exists. This file may
define intended contracts before implementation when they are needed to guide a
focused issue.

Planned contract set:

| Contract | Status | Producer | Consumer |
| --- | --- | --- | --- |
| Raw derivatives market artifact | not implemented yet | derivatives collection stage | reusable history, data quality |
| Shared derivatives market history | not implemented yet | derivatives history writer | current-run views, data inspection |
| Derivatives current-run views | not implemented yet | derivatives view builder | context, data quality |
| Derivatives market context | not implemented yet | context builder | regime, risk, decisions, alerts, outcomes, material |
| Derivatives market material | not implemented yet | material builder | research context, Codex context, report |

## Scope

Define contracts for:

- funding rate evidence;
- open interest and open-interest change evidence;
- mark or index premium evidence;
- futures basis evidence;
- bounded spread and depth summaries;
- liquidation-summary source availability and evidence when reliable;
- reusable local derivatives history;
- current-run derivatives views;
- deterministic derivatives context records;
- data-quality, manifest, and inspection expectations;
- Codex and report boundaries.

## Out of Scope

- Code implementation.
- Dependency installation.
- Authenticated endpoints.
- Exchange account access.
- Balances, orders, positions, margin state, or liquidation of user accounts.
- Trading execution, order placement, portfolio automation, or position sizing.
- Websocket streaming, tick storage, high-frequency order-book replay, or
  execution-grade market microstructure.
- Scheduler, daemon, alert delivery runtime, or notification channels.
- Macro data, on-chain data, user-state personalization, or dashboard UI.
- ML prediction, automatic strategy optimization, or LLM-generated derivatives
  conclusions.

## Technology Boundaries

Derivatives source access must use public unauthenticated market-data endpoints.

Rules:

- Do not require credentials, tokens, cookies, exchange accounts, balances,
  orders, positions, or margin permissions.
- Do not persist third-party client objects as Halpha contracts.
- Do not embed full raw endpoint payloads or reusable derivatives history in
  Codex input.
- Use Halpha-owned JSON, Markdown, Parquet, or plain metadata artifacts as the
  stable downstream contract.
- Treat endpoint limitations as source availability evidence, not as neutral
  market evidence.

Initial public-source adoption may use a configured stable derivatives market
source such as Binance USD-M futures public REST market-data endpoints. The
contract does not require multi-exchange abstraction before one source is
working end to end.

## Planned Pipeline Position

Planned product flow:

```text
configured public derivatives source
  -> raw derivatives market artifact
  -> shared derivatives market history
  -> derivatives current-run views
  -> derivatives market context
  -> regime, risk, decision, watch, alert, outcome, and strategy interpretation
  -> derivatives market material
  -> research context
  -> Codex context + prompt
  -> Simplified Chinese Markdown report
```

Pipeline insertion should preserve the existing product command:

```bash
python -m halpha run --config config.example.yaml
```

No derivatives stage should fabricate skipped downstream artifacts to make later
stages appear complete.

## Common State Rules

Derivatives artifacts must distinguish these states where applicable:

```text
succeeded
ok
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
  periodic product-run input for the class.
- `stale` means the latest usable record is older than the configured freshness
  window.
- `partial` means some configured symbols, periods, or endpoint classes
  succeeded while others failed or were unavailable.
- `degraded` means evidence exists but has quality limitations.
- Missing, skipped, unavailable, stale, partial, or degraded evidence must not
  be interpreted as neutral or low risk.
- Codex may explain these states only from Halpha-generated material.

## Data Class Contract

Planned data classes:

| Data class | Purpose | Required source state |
| --- | --- | --- |
| `funding_rate` | Identify funding pressure and potential crowded long or short pressure. | Implement when reliable public historical or latest funding endpoint exists. |
| `open_interest` | Identify leverage expansion, contraction, or crowding context. | Implement when reliable current or historical public OI endpoint exists. |
| `premium_index` | Identify mark/index premium stress or discount state. | Implement when reliable public mark/index premium endpoint exists. |
| `basis` | Identify futures premium, discount, or annualized basis stress. | Implement when reliable public basis endpoint exists. |
| `spread_depth` | Summarize bounded top-of-book spread and depth imbalance. | Implement only from bounded public snapshots; otherwise record unavailable or degraded. |
| `liquidation_summary` | Summarize public liquidation pressure when a reliable periodic source exists. | Implement if reliable; otherwise record unavailable with source limitations. |

Rules:

- A data class may be absent only when disabled or not configured.
- A configured but unsupported data class must produce `unavailable` or
  `degraded` source-state evidence.
- Liquidation coverage must not be silently deferred. If the source only offers
  real-time streams or unsuitable periodic data, artifacts should record that
  limitation.
- Spread and depth summaries must be bounded summaries, not full order-book
  dumps.

## Raw Derivatives Market Artifact

Planned artifact:

```text
raw/derivatives_market.json
```

Purpose:

- preserve current-run public derivatives and market-structure observations;
- keep source endpoint identity and parsing warnings inspectable;
- provide input to reusable history and current-run views.

Top-level contract:

```json
{
  "schema_version": 1,
  "artifact_type": "derivatives_market_raw",
  "collector": "derivatives_market",
  "collection_method": "public_http",
  "source": {
    "name": "binance_usdm",
    "url": "https://fapi.binance.com"
  },
  "collected_at": "2026-06-18T00:00:00Z",
  "items": [],
  "availability": [],
  "warnings": [],
  "errors": []
}
```

Required item fields:

```json
{
  "item_id": "derivatives_market:funding_rate:binance_usdm:BTCUSDT:2026-06-18T00:00:00Z",
  "data_class": "funding_rate",
  "source": "binance_usdm",
  "market_type": "usd_m_futures",
  "symbol": "BTCUSDT",
  "period": "8h",
  "as_of": "2026-06-18T00:00:00Z",
  "endpoint": "funding_rate_history",
  "metrics": {},
  "units": {},
  "raw_fields": {},
  "warnings": [],
  "errors": []
}
```

Rules:

- `item_id` must be deterministic.
- `data_class`, `source`, `symbol`, `as_of`, `metrics`, and `source endpoint`
  identity are required.
- `raw_fields` may preserve bounded source fields needed for audit, but must not
  store credentials, local proxy values, or private endpoints.
- Endpoint failures should be represented in `errors` or `availability`, not by
  fabricating neutral records.

## Shared Derivatives Market History

Planned reusable storage:

```text
data/market/derivatives/
data/market/metadata/derivatives_market_schema.json
data/market/metadata/derivatives_market_state.json
```

Purpose:

- preserve reusable derivatives observations outside per-run report
  directories;
- provide bounded current-run views for context generation;
- support data inspection and quality checks.

Required record identity:

```text
source + market_type + data_class + symbol + period + as_of
```

Required behavior:

- append or merge deterministic records from raw derivatives artifacts;
- warn on conflicting duplicates instead of silently replacing source evidence;
- preserve source endpoint and source artifact references;
- keep full reusable history outside Codex input;
- record implemented, skipped, unavailable, stale, partial, degraded, and failed
  data classes in state metadata.

## Derivatives Current-Run Views

Planned artifact:

```text
raw/derivatives_market_views.json
```

Purpose:

- expose bounded current-run derivatives windows and storage refs;
- avoid embedding full reusable history into analysis or Codex context.

Record fields:

```json
{
  "view_id": "derivatives_view:funding_rate:binance_usdm:BTCUSDT:8h:2026-06-18T00:00:00Z",
  "data_class": "funding_rate",
  "source": "binance_usdm",
  "market_type": "usd_m_futures",
  "symbol": "BTCUSDT",
  "period": "8h",
  "input_window_start": "2026-06-17T00:00:00Z",
  "input_window_end": "2026-06-18T00:00:00Z",
  "latest_observation_time": "2026-06-18T00:00:00Z",
  "row_count": 4,
  "status": "succeeded",
  "storage_ref": "data/market/derivatives/source=binance_usdm/data_class=funding_rate/symbol=BTCUSDT",
  "warnings": [],
  "errors": [],
  "source_artifacts": []
}
```

Rules:

- Views record metadata and selected bounded rows or summaries only when needed.
- Large reusable histories must be referenced by `storage_ref`, not embedded.
- Missing or stale windows must produce explicit status and warnings.

## Derivatives Market Context

Planned artifact:

```text
analysis/derivatives_market_context.json
```

Purpose:

- turn derivatives views into deterministic context states;
- expose conservative evidence for regime, risk, decision, alert, outcome, and
  report consumers.

Top-level contract:

```json
{
  "schema_version": 1,
  "artifact_type": "derivatives_market_context",
  "run_id": "20260618T000000Z",
  "created_at": "2026-06-18T00:00:00Z",
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
  "context_id": "derivatives_context:funding_pressure:binance_usdm:BTCUSDT:8h:2026-06-18T00:00:00Z",
  "context_type": "funding_pressure",
  "data_class": "funding_rate",
  "source": "binance_usdm",
  "market_type": "usd_m_futures",
  "symbol": "BTCUSDT",
  "period": "8h",
  "as_of": "2026-06-18T00:00:00Z",
  "status": "succeeded",
  "state": "neutral",
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
funding_pressure
open_interest_pressure
premium_basis_state
liquidity_depth_state
liquidation_availability
```

Rules:

- Context states are generated by deterministic Halpha logic.
- Funding and open-interest stress may raise or qualify risk; they must not
  generate trade direction by themselves.
- Premium or basis stress may indicate derivatives pressure; it must not
  create price targets.
- Spread or depth summaries may indicate liquidity degradation; they must not
  become execution-grade slippage models.
- Liquidation availability records must state whether reliable periodic
  liquidation summaries are implemented, unavailable, real-time-only, stale, or
  degraded.

## Downstream Consumer Rules

Market regime and risk:

- May cite derivatives context as evidence, conflict, uncertainty, or risk
  escalation.
- Missing or unavailable derivatives context must not lower risk.
- Derivatives stress may cap confidence or raise blocking risks.

Decision recommendations and watch triggers:

- May cite derivatives context as risk conditions, downgrade reasons,
  invalidation pressure, risk-relief triggers, or recheck triggers.
- Must not create account actions, orders, position sizing, hedging
  instructions, or trading execution.

Alert decisions:

- May cite derivatives context only when event, risk, decision, or watch
  evidence supports relevance.
- Must not create alert delivery or monitoring runtime.

Outcome tracking:

- May record later follow-through for previous derivatives context records when
  those records exist.
- Must use as-of timestamps and no-lookahead windows.

Strategy interpretation:

- May explain whether derivatives context supports, conflicts with, or limits
  current strategy evidence.
- Must not promote or reject strategies solely from derivatives context unless a
  later strategy gate explicitly supports that behavior.

## Derivatives Market Material

Planned artifact:

```text
analysis/derivatives_market_material.md
```

Purpose:

- provide bounded AI-readable derivatives context for Codex report generation;
- avoid embedding raw endpoint payloads or full reusable derivatives history.

Required sections:

```text
source_policy
derivatives_overview
funding_and_leverage
premium_and_basis
liquidity_and_depth
liquidation_source_availability
data_quality
downstream_implications
report_usage_rules
record: <context id>
```

Rules:

- Include high-severity context records first.
- Summarize neutral, skipped, unavailable, stale, partial, and degraded records
  with counts and representative examples only when useful.
- Preserve source artifacts and source limitations.
- State that derivatives context is research context, not trading instruction
  or forecast.

## Codex Boundary

Codex may:

- explain Halpha-generated derivatives context states;
- describe source availability and data-quality limitations;
- explain whether derivatives context confirms, conflicts with, or does not
  affect current Halpha decision evidence.

Codex must not:

- create derivatives records, states, severities, risk levels, or signals;
- infer missing market-structure data;
- inspect reusable derivatives stores, raw endpoint payloads, SQLite indexes, or
  Parquet tables;
- calculate funding pressure, open-interest changes, premium, basis, spread,
  depth imbalance, or liquidation summaries from raw data;
- generate trading instructions, position sizing, account actions, price
  forecasts, or return promises.

## Manifest Expectations

When implemented, `run_manifest.json` should record:

- raw derivatives artifact path and counts;
- reusable derivatives history state and store counts;
- derivatives current-run view counts and unavailable classes;
- derivatives context counts by context type, state, severity, status, warning,
  and error;
- derivatives material path and Codex input budget metadata;
- source availability for liquidation and spread or depth summaries.

Do not embed full raw derivatives artifacts, reusable history, or context
records into the manifest.

## Data Quality Expectations

Data quality should cover:

- raw derivatives artifact presence and schema;
- endpoint partial failures;
- malformed values;
- missing symbols, periods, or data classes;
- stale timestamps;
- duplicate or conflicting records;
- reusable history status;
- current-run view coverage;
- unavailable liquidation, spread, or depth source states;
- Codex input boundaries for derivatives material.

Rules:

- Quality warnings should remain visible.
- Data quality should not repair or rewrite source evidence.
- Unavailable source classes should be explicit and should not imply neutral
  derivatives risk.

## Validation Rules

Automated validation should cover:

- config validation;
- source payload parsing;
- skipped and disabled derivatives config;
- missing, stale, partial, unavailable, degraded, and failed data states;
- funding and open-interest context classification;
- premium and basis context classification;
- spread and depth bounded summaries;
- liquidation-source availability behavior;
- data-quality and inspection output;
- Codex material boundaries.

Real-source validation should use existing product commands and inspect
generated artifacts. Full report validation sends generated local research
context to Codex CLI.
