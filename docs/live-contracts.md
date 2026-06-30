# Live Contracts

This document defines the planned M24 Live product contract. It is a durable
target contract for follow-up implementation work, not a claim that Live UI,
Live config parsing, or a Live scheduler already exists.

## Purpose

Live is Halpha's user-facing continuous market intelligence workflow. It shows
what Halpha is collecting, refreshing, detecting, and reporting while preserving
the local-first research boundary.

Live exists to replace user-facing "Monitor" product language. Monitor is the
resident System Monitor/runtime supervisor for Core liveness and restart
supervision only. The #806 ownership split is the prerequisite: Core owns
automatic schedule and command-job creation, while resident Monitor supervises
Core health.

Live must remain:

- local-first;
- Core-owned;
- backed by visible command jobs and local runtime state;
- source-aware and drill-down friendly;
- bounded in every read model;
- free of trading execution, account access, wallet access, order placement,
  position sizing, hosted service assumptions, and AI-owned trigger decisions.

## Vocabulary

| Term | Meaning |
| --- | --- |
| `core` | The resident backend role that owns Dashboard APIs, allowlisted command-job execution, automatic schedules, Live scheduler ticks, and command-job creation. |
| `monitor` | The resident System Monitor/runtime supervisor that checks Core liveness, starts or retries Core when appropriate, and records bounded service health. It is not a market intelligence product workflow. |
| `live` | The user-facing continuous market intelligence workflow that summarizes source refresh, recent intelligence, deterministic trigger decisions, daily schedule state, report dispatches, warnings, and linked evidence. |
| `live scheduler tick` | A planned Core-owned scheduling decision that may create visible command jobs. It is not a resident process role. |
| `Live trigger` | A deterministic Halpha decision that may explain why a report or attention item should be created. AI/Codex must not decide the trigger fact, severity, cooldown, or source truth. |

## Runtime Boundary

Live is not a third resident process role. The only resident Halpha process
roles remain:

- `core`
- `monitor`

Planned Live execution runs inside Core-owned scheduling and command-job
infrastructure:

- Core evaluates Live scheduler ticks.
- Core creates visible command jobs for Live collection, refresh, and report
  work.
- Command jobs record status, logs, source command intent, warnings, errors,
  linked artifacts, linked runs, and linked reports.
- Resident Monitor must not run Live refresh, Live triggers, data collection,
  report dispatch, source cadence work, or product pipeline work.
- Live must not introduce a broker, worker pool, external scheduler, cron
  integration, Redis, Celery, Prefect, Airflow, Kafka, hosted service, or hidden
  resident process.

Explicit existing Monitor CLI recovery commands and monitor cycle artifacts may
remain under the Monitor contract. They are not the planned Live Dashboard
workflow.

## Planned Configuration Contract

The `live` config section is planned and not implemented yet. Follow-up work
that implements parsing must validate it deterministically and reject unknown
Live fields with actionable errors.

| Field | Default or required behavior | Validation expectation |
| --- | --- | --- |
| `live.enabled` | Defaults to `false`. | Boolean only. `false` prevents automatic Live scheduler ticks from creating jobs. |
| `live.tick_seconds` | Defaults to `30` when Live is implemented. | Positive integer. Controls how often Core evaluates Live scheduler ticks. |
| `live.collections.<data_type>.enabled` | Defaults to `false` for every supported data type. | Boolean only. Unknown `data_type` keys are unsupported. |
| `live.collections.<data_type>.cadence_seconds` | Required when that collection is enabled unless a future source-specific default is explicitly documented. | Positive integer. Core must not refresh a data type before the cadence has elapsed unless an explicit user action requests it. |
| `live.collections.<data_type>.lookback_seconds` | Required when that collection is enabled unless a future source-specific default is explicitly documented. | Positive integer. Defines the incremental collection window and must not be interpreted as full-history backfill. |
| `live.collections.macro_calendar.lookahead_seconds` | Required when `macro_calendar` Live collection is enabled. | Positive integer. Defines future scheduled-catalyst coverage. |
| `live.reports.daily.enabled` | Defaults to `false`. | Boolean only. Links the existing daily report schedule state into the Live page; it must not create a second daily scheduler authority. |
| `live.reports.triggers.<trigger_id>.enabled` | Defaults to `false` for every supported trigger. | Boolean only. Unknown `trigger_id` keys are unsupported. |
| `live.reports.triggers.<trigger_id>.cooldown_seconds` | Required when that trigger is enabled. | Positive integer. Prevents duplicate report dispatch for equivalent trigger decisions within the cooldown window. |

Unsupported Live config fields must not be silently ignored after Live parsing
is implemented. Until implementation lands, shipped example configs should not
include `live` fields as current behavior.

## Supported Live Data Types

The planned M24 Live workflow may refresh these implemented shared-data types:

- `ohlcv`
- `text_event`
- `macro_calendar`
- `onchain_flow`
- `derivatives_market`
- `market_anomaly`

Other data types are unsupported until their shared-store contract and Live
read model are explicitly implemented.

## Initial Trigger IDs

Planned deterministic Live trigger ids:

- `market_breakout`
- `major_market_move`
- `critical_news`
- `scheduled_catalyst`
- `derivatives_stress`
- `data_quality_degraded`

Each trigger decision must preserve source refs, data quality state, cooldown
state, and no-action reasons. Trigger decisions must not be generated or
revised by AI/Codex.

## Planned Read Model

Live Dashboard APIs must expose bounded read models, not raw streams or full
shared stores. The minimum read model fields are:

- Live enabled state and scheduler status.
- Source refresh state by data type.
- Last attempt, last success, next attempt, cadence, freshness, consecutive
  failures, and latest job id for each data type.
- Recent collection jobs with bounded terminal status, duration, warning count,
  error count, and linked artifact refs.
- Latest intelligence items or bounded record refs by data type.
- Trigger decisions with status, reason, source refs, cooldown, linked job id,
  linked run id, and linked report ref.
- Daily report schedule state and dispatch history.
- Warnings and errors.

Live read models must not embed:

- full raw streams;
- full reusable shared stores;
- SQLite contents;
- Parquet tables;
- full intermediate evidence JSON;
- private user-state files;
- credentials, tokens, cookies, proxy URLs, private endpoints, local usernames,
  or machine-local absolute paths;
- trading instructions, account data, wallet data, balances, position sizes, or
  order actions.

## Dashboard Contract

The planned Dashboard primary navigation label for this workflow is `Live`.
`Monitor` may appear only as System Monitor/runtime status language in system
health, settings, or service-control surfaces.

The Live page should use product-oriented read models:

- overview/status cards for what is fresh, stale, delayed, failed, skipped, or
  cooling down;
- source freshness and latency indicators;
- timeline and alert/history surfaces;
- recent intelligence summaries;
- drill-down links to the exact job, source record, run, report, warning, or
  artifact explaining a state.

These surfaces are local Halpha read models, not a hosted observability
product.
