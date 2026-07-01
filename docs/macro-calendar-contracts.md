# Macro Calendar Contracts

This document defines Halpha's macro and scheduled-event data contracts. It is a
durable implementation contract, not a milestone-only plan and not an
implementation record.

Macro and calendar evidence is timing and risk context. It does not replace
spot OHLCV evidence, derivatives evidence, strategy evidence, event
intelligence, decision intelligence, alert decisions, outcome tracking, or
report generation.

Macro and calendar outputs are personal research material. They are not trades,
orders, account operations, portfolio instructions, position sizing, forecasts,
economic-release predictions, or financial advice.

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
| Raw macro calendar artifact | initial adoption | macro/calendar collection stage | reusable state, data quality |
| Shared macro calendar state or history | initial adoption | macro/calendar history writer | current-run views, data inspection |
| Macro calendar current-run views | initial adoption | macro/calendar view builder | context, data quality |
| Macro calendar context | initial adoption | context builder | regime, risk, decisions, watches, alerts, outcomes, material |
| Macro calendar material | planned | material builder | research context, Codex context, report |

## Scope

Define contracts for:

- scheduled economic releases;
- central-bank meetings, speeches, statements, and policy events where stable
  public calendar sources exist;
- market holidays or closure windows where they materially affect source
  freshness or liquidity interpretation;
- optional broad macro proxy observations such as dollar, rates, volatility, or
  broad risk proxies when stable unauthenticated public sources are configured;
- reusable local macro/calendar state or history;
- current-run macro/calendar views;
- deterministic macro/calendar context records;
- downstream risk, decision, watch, event, alert, outcome, and report
  consumers;
- data-quality, manifest, inspection, and Codex-boundary expectations.

## Out of Scope

- Code implementation.
- Dependency installation.
- Paid data terminals.
- Authenticated data sources.
- Account-specific data.
- Macro forecasting, economic surprise modeling, nowcasting, policy-rate
  prediction, or asset price prediction.
- Trading execution, order placement, portfolio automation, or position sizing.
- Scheduler, daemon, alert delivery runtime, push notifications, or dashboard.
- On-chain data, user-state personalization, unified feature/factor engine, or
  intelligence-fusion layer.
- LLM-generated macro events, risk levels, watch triggers, alert priorities,
  forecasts, or trading instructions.

## Technology Boundaries

Macro/calendar source access must use configured public unauthenticated sources
unless a later explicit requirement changes this boundary.

Rules:

- Do not require credentials, tokens, cookies, user accounts, broker accounts,
  trading accounts, or paid terminal sessions.
- Do not persist third-party client objects as Halpha contracts.
- Do not embed full raw calendar streams or reusable macro history in Codex
  input.
- Use Halpha-owned JSON, Markdown, Parquet, or plain metadata artifacts as the
  stable downstream contract.
- Treat source limitations, missing calendars, missing time zones, stale
  records, and partial coverage as source availability evidence, not as neutral
  macro risk evidence.

Initial adoption should prefer a small number of stable public calendar sources
over broad but fragile coverage. A configured source may be disabled or
unavailable, but that state must be explicit in artifacts.

Implemented public sources:

| Source | Data class | Endpoint | Notes |
| --- | --- | --- | --- |
| `federal_reserve_fomc` | `central_bank_event` | `fomc_calendars` | Federal Reserve FOMC meeting calendar. Meeting dates are normalized to UTC and warn when the public source lacks exact intraday time. |
| `bea_release_calendar` | `economic_release` | `bea_release_dates_json` | BEA machine-readable release schedule from `https://apps.bea.gov/API/signup/release_dates.json`. Duplicate release times for the same release are deduplicated. |

`macro_calendar.source` configures one source. `macro_calendar.sources`
configures multiple sources. In a multi-source configuration, each implemented
source collects only the configured data classes it supports, so a source is not
marked unavailable merely because another configured source owns a different
data class.

## Pipeline Position

Intended product flow:

```text
configured public macro/calendar source
  -> raw macro calendar artifact [initial adoption]
  -> shared macro calendar state or history [initial adoption]
  -> macro calendar current-run views [initial adoption]
  -> macro calendar context [initial adoption]
  -> regime, risk, decision, watch, alert, outcome, and strategy interpretation
  -> macro calendar material [initial adoption]
  -> research context
  -> Codex context + prompt
  -> Simplified Chinese Markdown report
```

Pipeline insertion should preserve the existing product command:

```bash
python -m halpha run --config config.example.yaml
```

No macro/calendar stage should fabricate skipped downstream artifacts to make
later stages appear complete.

## Common State Rules

Macro/calendar artifacts must distinguish these states where applicable:

```text
succeeded
ok
warning
degraded
skipped
unavailable
stale
partial
no_event
insufficient_data
failed
```

Rules:

- `skipped` means the class is disabled or not configured.
- `unavailable` means the configured source does not provide a reliable
  product-run input for the class.
- `stale` means the latest usable record is older than the configured
  freshness window.
- `partial` means some configured regions, classes, assets, or source windows
  succeeded while others failed or were unavailable.
- `no_event` means a source was checked successfully and no configured
  scheduled catalyst was found in the current run window.
- `degraded` means evidence exists but has quality limitations such as missing
  importance, ambiguous market scope, or source time-zone uncertainty.
- Missing, skipped, unavailable, stale, partial, degraded, or no-event evidence
  must not be interpreted as confirmed low macro risk.
- Codex may explain these states only from Halpha-generated material.

## Data Class Contract

Data classes:

| Data class | Purpose | Required source state |
| --- | --- | --- |
| `economic_release` | Identify scheduled macro releases that may create catalyst risk. | Implemented for `bea_release_calendar` when the source exposes event time, release name, and source timestamp. |
| `central_bank_event` | Identify scheduled policy meetings, statements, speeches, or minutes. | Implemented for `federal_reserve_fomc`; exact intraday timing may be unavailable and must be warned. |
| `market_holiday` | Identify closure or reduced-liquidity windows that may affect interpretation. | Implement when a stable public source covers configured markets. |
| `macro_proxy_observation` | Preserve bounded broad risk proxy observations such as dollar, rates, or volatility when configured. | Implement only when a stable public source provides timestamped observations and units. |

Rules:

- A data class may be absent only when disabled or not configured.
- A configured but unsupported class must produce `unavailable` or `degraded`
  source-state evidence.
- Economic releases and central-bank events are scheduled catalyst evidence,
  not forecasts.
- Macro proxy observations are context inputs, not signals by themselves.
- Data classes should be expanded only when a downstream consumer is ready to
  use the evidence conservatively.

## Raw Macro Calendar Artifact

Implemented artifact:

```text
raw/macro_calendar.json
```

Purpose:

- preserve current-run public macro/calendar observations;
- keep source endpoint identity, source time-zone handling, and parsing warnings
  inspectable;
- provide input to reusable state and current-run views.

Top-level contract:

```json
{
  "schema_version": 1,
  "artifact_type": "macro_calendar_raw",
  "collector": "macro_calendar",
  "collection_method": "public_http",
  "source": {
    "name": "example_public_calendar",
    "url": "https://example.invalid/calendar"
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
  "item_id": "macro_calendar:economic_release:example_public_calendar:US:CPI:2026-06-18T12:30:00Z",
  "data_class": "economic_release",
  "source": "example_public_calendar",
  "event_name": "Consumer Price Index",
  "event_type": "release",
  "region": "US",
  "affected_assets": ["BTCUSDT"],
  "scheduled_at": "2026-06-18T12:30:00Z",
  "source_timezone": "America/New_York",
  "importance": "high",
  "source_published_at": "2026-06-17T00:00:00Z",
  "endpoint": "economic_calendar",
  "metrics": {},
  "units": {},
  "raw_fields": {},
  "warnings": [],
  "errors": []
}
```

Rules:

- `item_id` must be deterministic.
- `data_class`, `source`, `event_name`, `scheduled_at`, and source endpoint
  identity are required for scheduled events.
- `source_timezone` must be preserved when available. If missing, artifacts
  must record a warning and the normalized UTC time must be treated as
  degraded unless the source explicitly uses UTC.
- `affected_assets` are configured relevance hints, not proof that the event
  will move those assets.
- `raw_fields` may preserve bounded source fields needed for audit, but must
  not store credentials, local proxy values, private endpoints, or large raw
  pages.
- Endpoint failures should be represented in `errors` or `availability`, not by
  fabricating neutral records.

## Shared Macro Calendar State Or History

Implemented reusable storage:

```text
data/macro/calendar/
data/macro/metadata/macro_calendar_schema.json
data/macro/metadata/macro_calendar_state.json
```

Purpose:

- preserve reusable scheduled-event observations outside per-run report
  directories;
- deduplicate public calendar entries across runs;
- provide bounded current-run views for context generation;
- support data inspection and quality checks.

Required scheduled-event identity:

```text
source + data_class + region + event_name + scheduled_at
```

Required macro-proxy identity:

```text
source + data_class + symbol_or_name + as_of
```

Required behavior:

- append or merge deterministic records from raw macro/calendar artifacts;
- warn on conflicting duplicates instead of silently replacing source evidence;
- preserve source endpoint and source artifact references;
- keep full reusable state or history outside Codex input;
- record implemented, skipped, unavailable, stale, partial, no-event, degraded,
  and failed data classes in state metadata.

## Macro Calendar Current-Run Views

Implemented artifact:

```text
raw/macro_calendar_views.json
```

Purpose:

- expose bounded current-run lookback and lookahead windows;
- avoid embedding full reusable macro/calendar history into analysis or Codex
  context.

Record fields:

```json
{
  "view_id": "macro_calendar_view:economic_release:example_public_calendar:US:2026-06-18T00:00:00Z",
  "data_class": "economic_release",
  "source": "example_public_calendar",
  "region": "US",
  "input_window_start": "2026-06-17T00:00:00Z",
  "input_window_end": "2026-06-19T00:00:00Z",
  "latest_observation_time": "2026-06-18T00:00:00Z",
  "event_count": 1,
  "included_record_count": 1,
  "omitted_record_count": 0,
  "status": "succeeded",
  "storage_ref": "data/macro/calendar/source=example_public_calendar/data_class=economic_release/region=US",
  "included_columns": ["scheduled_at", "event_name", "event_type", "importance", "affected_assets", "endpoint", "warnings", "errors"],
  "records": [
    {
      "scheduled_at": "2026-06-18T00:00:00Z",
      "event_name": "Example release",
      "event_type": "economic_release",
      "importance": "high",
      "affected_assets": ["BTCUSDT"],
      "endpoint": "example_calendar",
      "warnings": [],
      "errors": []
    }
  ],
  "warnings": [],
  "errors": [],
  "source_artifacts": []
}
```

Rules:

- Views record metadata and selected bounded rows or summaries only when needed.
- Large reusable histories must be referenced by `storage_ref`, not embedded.
- Missing, stale, or no-event windows must produce explicit status and
  warnings where applicable.

## Macro Calendar Context

Implemented artifact:

```text
analysis/macro_calendar_context.json
```

Purpose:

- turn macro/calendar views into deterministic context states;
- expose conservative evidence for regime, risk, decision, alert, outcome, and
  report consumers.

Top-level contract:

```json
{
  "schema_version": 1,
  "artifact_type": "macro_calendar_context",
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
  "context_id": "macro_calendar_context:scheduled_catalyst:example_public_calendar:US:CPI:2026-06-18T12:30:00Z",
  "context_type": "scheduled_catalyst",
  "data_class": "economic_release",
  "source": "example_public_calendar",
  "event_name": "Consumer Price Index",
  "region": "US",
  "scheduled_at": "2026-06-18T12:30:00Z",
  "as_of": "2026-06-18T00:00:00Z",
  "status": "succeeded",
  "state": "upcoming",
  "severity": "medium",
  "confidence": "medium",
  "time_to_event_hours": 12.5,
  "affected_assets": ["BTCUSDT"],
  "evidence": [],
  "uncertainty": [],
  "warnings": [],
  "errors": [],
  "source_artifacts": []
}
```

Context types:

```text
scheduled_catalyst [initial adoption]
recent_catalyst [initial adoption]
no_event_window [initial adoption]
macro_proxy_state [planned]
source_availability [initial adoption]
```

Rules:

- Context states are generated by deterministic Halpha logic.
- `scheduled_catalyst` means the event is known and upcoming or in progress; it
  does not imply a market direction or outcome.
- `recent_catalyst` means the scheduled time is inside the configured lookback
  window; it does not imply confirmed market impact.
- `no_event_window` means checked sources did not return configured events in
  the current window; it does not prove that macro risk is absent.
- `macro_proxy_state` may describe broad proxy observations only when configured
  source evidence exists; it must not become an asset forecast.
- `source_availability` records missing, unavailable, stale, partial, degraded,
  and failed source states.

## Scheduled Versus Realized Impact

Macro/calendar artifacts must explicitly separate:

- scheduled catalyst facts;
- source freshness and source availability;
- Halpha's deterministic risk or watch interpretation;
- realized market response from later market evidence;
- Codex report language.

Rules:

- A scheduled event is not a confirmed market impact.
- Importance is a source or Halpha relevance field, not a forecast.
- Risk escalation or confidence downgrade may reference an upcoming catalyst
  only as uncertainty or event-risk evidence.
- Realized impact requires later market, derivatives, event, or outcome
  evidence from downstream artifacts.
- Codex must not fill missing realized impact when Halpha has not generated it.

## Downstream Consumer Rules

Market regime and risk:

- May cite macro/calendar context as catalyst risk, uncertainty, conflict, or
  risk escalation.
- Missing or unavailable macro/calendar context must not lower risk.
- Upcoming high-importance catalysts may cap confidence or raise blocking
  risks when source quality is sufficient.
- Initial adoption implements risk-assessment citation, source refs, and
  conservative risk gates for scheduled, recent, stale, unavailable, partial,
  degraded, and no-event macro/calendar context states.

Decision recommendations and watch triggers:

- May cite macro/calendar context as risk conditions, downgrade reasons,
  invalidation pressure, recheck triggers, or post-event confirmation windows.
- Must not create account actions, orders, position sizing, hedging
  instructions, or trading execution.
- Initial adoption implements decision risk conditions, downgrade reasons,
  linked context ids, invalidation conditions, watch wait conditions, watch
  post-event confirmation conditions, and source-availability recheck triggers.

Event intelligence and alert decisions:

- May cite macro/calendar proximity when text events, market moves, or alert
  decisions occur near configured catalyst windows.
- Must not escalate high-priority alerts from a scheduled macro event alone.
- Must preserve low-confidence, no-alert, and downgrade behavior.
- Initial adoption implements event-assessment proximity evidence, linked
  macro/calendar context ids, alert-decision macro relevance, and
  source-availability downgrade or suppression reasons.

Outcome tracking:

- May record later follow-through for previous macro/calendar context records
  when those records exist.
- Must use as-of timestamps and no-lookahead windows.

Strategy interpretation:

- May explain whether macro/calendar context supports, conflicts with, or
  limits current strategy evidence.
- Must not promote or reject strategies solely from macro/calendar context
  unless a later strategy gate explicitly supports that behavior.

## Macro Calendar Material

Implemented artifact:

```text
analysis/macro_calendar_material.md
```

Purpose:

- provide bounded AI-readable macro/calendar context for Codex report
  generation;
- avoid embedding raw source payloads or full reusable macro/calendar history.
- preserve selected-record and omitted-record counts for Codex input budgeting
  and report traceability.

Pipeline stage:

```text
build_macro_calendar_material
```

The stage runs inside `build_materials`, after final data-quality summary
publication. It consumes `analysis/macro_calendar_context.json` only.

Required sections:

```text
source_policy
macro_calendar_overview
scheduled_catalysts
recent_catalysts
no_event_and_unavailable_sources
data_quality
downstream_implications
report_usage_rules
selected_records
```

Rules:

- Include high-importance and high-severity context records first.
- Summarize low-importance, no-event, skipped, unavailable, stale, partial, and
  degraded records with counts and representative examples only when useful.
- Preserve source artifacts, source time-zone handling, and source limitations.
- State that macro/calendar context is research context, not a forecast,
  trading instruction, or realized market-impact claim.
- Include `codex_may_generate_macro_events: false`,
  `codex_may_generate_risk_levels: false`,
  `codex_may_generate_watch_triggers: false`,
  `codex_may_generate_alert_priorities: false`, and
  `full_macro_calendar_context_json_embedded: false`.
- Record selected-record and omitted-record counts in `run_manifest.json` and
  Codex input budget metadata through the standard material budget mechanism.

Implemented manifest keys:

- `artifacts.macro_calendar_material`
- `counts.macro_calendar_material_records`
- `counts.macro_calendar_material_omitted_records`
- `macro_calendar_material.status`
- `macro_calendar_material.context_records`
- `macro_calendar_material.selected_records`
- `macro_calendar_material.omitted_records`

## Codex Boundary

Codex may:

- explain Halpha-generated macro/calendar context states;
- describe source availability, source freshness, time-zone, and data-quality
  limitations;
- explain whether macro/calendar context increases uncertainty, adds catalyst
  risk, or has no supported effect on current Halpha decision evidence.

Codex must not:

- create macro/calendar records, states, severities, risk levels, watch
  triggers, alert priorities, or signals;
- infer missing source data, missing event times, missing time zones, or missing
  market impact;
- inspect reusable macro/calendar stores, raw endpoint payloads, SQLite indexes,
  or Parquet tables;
- forecast economic releases, policy outcomes, asset prices, or returns;
- generate trading instructions, position sizing, account actions, or return
  promises.

Final report post-processing may insert a bounded deterministic macro/calendar
evidence section from `analysis/macro_calendar_context.json` when
`analysis/macro_calendar_material.md` exists. This inserted section must cite
the material artifact and source artifacts, distinguish scheduled catalyst,
recent catalyst, no-event, unavailable, stale, degraded, partial, and failed
states, and must not create new macro events, realized market impact, risk
levels, forecasts, or trading instructions.

## Manifest Expectations

`run_manifest.json` should record implemented macro/calendar summaries after
the relevant producers exist:

- raw macro/calendar artifact path and counts;
- reusable macro/calendar state and store counts;
- macro/calendar current-run view counts and unavailable classes;
- macro/calendar context counts by context type, state, severity, status,
  warning, and error;
- macro/calendar material path, selected counts, omitted counts, and Codex input
  budget metadata;
- source availability for configured calendar classes and macro proxy classes.

Do not embed full raw macro/calendar artifacts, reusable history, or context
records into the manifest.

## Data Quality Expectations

Data quality should cover:

- raw macro/calendar artifact presence and schema;
- source partial failures;
- malformed scheduled times;
- missing time zones;
- stale timestamps;
- duplicate or conflicting records;
- missing event names, regions, data classes, or source refs;
- reusable state status;
- current-run view coverage;
- no-event windows and unavailable source states.

Rules:

- Quality warnings should remain visible.
- Data quality should not repair or rewrite source evidence.
- Unavailable source classes and no-event windows should be explicit and should
  not imply neutral macro risk.

## Validation Rules

Automated validation should cover:

- config validation;
- source payload parsing;
- skipped and disabled macro/calendar config;
- missing, stale, partial, unavailable, degraded, no-event, and failed data
  states;
- source time-zone handling;
- duplicate scheduled event handling;
- bounded current-run views;
- scheduled versus realized impact separation;
- risk, watch, event, and alert integration once implemented;
- data-quality and inspection output;
- Codex material boundaries.

Real-source validation should use existing product commands and inspect
generated artifacts. Full report validation sends generated local research
context to Codex CLI.
