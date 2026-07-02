# Live Contracts

This document defines the M24 Live product contract. The current implemented
slice covers Live config parsing, Core-owned source-refresh scheduler ticks,
visible data-collection command jobs, persisted source-refresh state,
deterministic trigger decisions, Dashboard Settings controls for safe Live
configuration, and the bounded `/api/live` read model.

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
| `live scheduler tick` | A Core-owned scheduling decision that may create visible command jobs. It is not a resident process role. |
| `Live trigger` | A deterministic Halpha decision that may explain why a report or attention item should be created. AI/Codex must not decide the trigger fact, severity, cooldown, or source truth. |

## Runtime Boundary

Live is not a third resident process role. The only resident Halpha process
roles remain:

- `core`
- `monitor`

Live source-refresh execution runs inside Core-owned scheduling and command-job
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
remain under the Monitor contract. They are not the Live Dashboard workflow.

## Configuration Contract

The `live` config section is implemented for source-refresh scheduling and
validated deterministically during config load. Unknown Live fields, unknown
data types, unknown trigger ids, and invalid positive-integer windows are
rejected with actionable errors.

| Field | Default or required behavior | Validation expectation |
| --- | --- | --- |
| `live.enabled` | Defaults to `false`. | Boolean only. `false` prevents automatic Live scheduler ticks from creating jobs. |
| `live.tick_seconds` | Defaults to `30`. | Positive integer. Controls how often Core evaluates Live scheduler ticks. |
| `live.collections.<data_type>.enabled` | Defaults to `false` for every supported data type. | Boolean only. Unknown `data_type` keys are unsupported. |
| `live.collections.<data_type>.cadence_seconds` | Required when that collection is enabled unless a future source-specific default is explicitly documented. | Positive integer. Core must not refresh a data type before the cadence has elapsed unless an explicit user action requests it. |
| `live.collections.<data_type>.lookback_seconds` | Required when that collection is enabled unless a future source-specific default is explicitly documented. | Positive integer. Defines the incremental collection window and must not be interpreted as full-history backfill. |
| `live.collections.macro_calendar.lookahead_seconds` | Required when `macro_calendar` Live collection is enabled. | Positive integer. Defines future scheduled-catalyst coverage. |
| `live.streams.ohlcv.enabled` | Defaults to the configured `live.collections.ohlcv.enabled` value. | Boolean only. Enables Core-owned public OHLCV WebSocket ingestion for implemented sources. |
| `live.streams.ohlcv.stale_after_seconds` | Defaults to `180`. | Positive integer. If no WebSocket event is seen within this window, Live treats the stream as stale and schedules REST backfill. |
| `live.streams.ohlcv.reconnect_initial_seconds` | Defaults to `5`. | Positive integer. Initial reconnect delay after WebSocket disconnect or provider shutdown. |
| `live.streams.ohlcv.reconnect_max_seconds` | Defaults to `300`. | Positive integer greater than or equal to `reconnect_initial_seconds`. Caps exponential reconnect delay. |
| `live.reports.daily.enabled` | Defaults to `false`. | Boolean only. Links the existing daily report schedule state into the Live page; it must not create a second daily scheduler authority. |
| `live.reports.triggers.<trigger_id>.enabled` | Defaults to `false` for every supported trigger. | Boolean only. Unknown `trigger_id` keys are unsupported. |
| `live.reports.triggers.<trigger_id>.cooldown_seconds` | Required when that trigger is enabled. | Positive integer. Prevents duplicate report dispatch for equivalent trigger decisions within the cooldown window. |
| `live.reports.triggers.<trigger_id>.job_intent` | Defaults to `run_no_codex`. | Must be `run_no_codex` or `run`. `run` requires valid persisted unattended Live trigger authorization. |
| `live.reports.triggers.<trigger_id>.min_priority` | Optional. | Must be `low`, `medium`, `high`, or `critical` when present. Used only by priority-like trigger evidence. |
| `live.reports.triggers.<trigger_id>.window_seconds` | Optional trigger lookback window. | Positive integer when present. |
| `live.reports.triggers.<trigger_id>.price_change_pct` | Optional major-market-move price threshold. | Positive number when present. |
| `live.reports.triggers.<trigger_id>.volume_change_pct` | Optional major-market-move volume threshold. | Positive number when present. |
| `live.reports.triggers.<trigger_id>.lookahead_seconds` | Optional scheduled-catalyst lookahead window. | Positive integer when present. |
| `live.reports.triggers.<trigger_id>.min_failed_targets` | Optional degraded-data threshold. | Positive integer when present. |
| `live.reports.triggers.<trigger_id>.min_stale_targets` | Optional degraded-data threshold. | Positive integer when present. |
| `live.reports.triggers.<trigger_id>.codex_authorization` | Optional persisted authorization metadata for unattended `run` trigger jobs. | Mapping only. It must match trigger id, trigger revision, config ref, config digest, job intent, and authorization scope before automatic Codex-capable report dispatch is allowed. |

Unsupported Live config fields must not be silently ignored.

Dashboard Settings exposes the common safe Live fields listed above:

- `live.enabled`, `live.tick_seconds`, and `live.reports.daily.enabled`;
- per-data-type collection enabled, cadence, and lookback windows;
- `live.collections.macro_calendar.lookahead_seconds`;
- per-trigger enabled state, cooldown, job intent, and implemented threshold
  parameters.

Dashboard Settings must not expose raw `codex_authorization` mappings, config
digests, local private paths, or credential-like values. It exposes a virtual
`confirm_codex` action for each trigger instead. When a trigger is enabled with
`job_intent: run`, the backend writes authorization metadata only after explicit
confirmation and only for the current trigger id, trigger revision, config ref,
and config digest. Any later trigger config change invalidates that
authorization until the user confirms again.

Live settings are configuration only. They must not start, stop, or mutate the
resident System Monitor process lifecycle.

The implemented Dashboard Settings defaults use source-value-aware refresh
cadences:

- `ohlcv`: 300 seconds;
- `market_anomaly`: 300 seconds;
- `text_event`: 600 seconds;
- `derivatives_market`: 900 seconds;
- `onchain_flow`: 3600 seconds;
- `macro_calendar`: 21600 seconds.

These are default scheduling values only. A configured collection must still
respect provider rate-limit cooldowns before sending public API requests.

## Live OHLCV WebSocket Streams

Live OHLCV WebSocket ingestion is implemented as an internal Core transport,
not as a new resident process role. It writes finalized public kline candles to
the same `data/market/ohlcv` shared store as REST collection and records stream
state in runtime metadata under `live_stream_state`.

Implemented WebSocket sources:

- `binance` and `binance_spot`: public market-data stream endpoint
  `data-stream.binance.vision`;
- `binance_usdm`: USD-M futures market stream endpoint routed through
  Binance's `/market` WebSocket path.

Current stream behavior:

- uses combined stream URLs such as `<symbol>@kline_<interval>`;
- records only closed candles (`k.x == true`) as OHLCV store records;
- updates collection coverage with `coverage_method:
  ohlcv_websocket_stream`;
- marks initial startup, reconnect, or stale-stream gaps as requiring REST
  backfill;
- lets the existing visible `data_collect` command-job path perform REST
  backfill instead of hiding recovery work in the stream loop;
- suppresses periodic OHLCV REST collection while the WebSocket stream is
  fresh and no backfill is required.

Provider rules that shape the implementation:

- Binance spot and USD-M futures WebSocket connections are valid for only 24
  hours and must be expected to disconnect.
- Binance spot sends WebSocket ping frames every 20 seconds and requires prompt
  pong responses.
- Binance USD-M futures sends ping frames every 3 minutes and disconnects if a
  pong is not received within the documented timeout.
- Binance WebSocket control-message limits apply to client messages, so Halpha
  avoids repeated subscribe/unsubscribe calls and uses URL-based combined
  stream subscriptions.
- Binance USD-M futures kline streams belong to the routed `/market` endpoint;
  unrouted URLs are not used for those streams.

Unsupported OHLCV sources remain on REST collection until their public
WebSocket contracts are implemented source by source. Unsupported stream
targets are recorded as stream warnings; they must not be silently treated as
healthy WebSocket coverage.

## Public API Rate Limits

Public HTTP collection must check the runtime rate-limit cooldown state before
sending a request. The implemented cooldown state is stored in
`.halpha/state.sqlite` under the `public_api_rate_limits` runtime metadata key.
It is mutable operational state, not research evidence and not Codex context by
default.

When a public provider returns a rate-limit response such as HTTP `429` or
Binance-style HTTP `418`, Halpha records a source/host cooldown with status
code, bounded retry interval, last-seen time, and a sanitized reason. Full
request URLs, proxy URLs, credentials, local hostnames, and IP addresses must
not be stored. Later requests to the same public API host must be skipped until
the cooldown expires, including after a Core or Dashboard process restart.

## Supported Live Data Types

The current Live source-refresh scheduler can refresh these implemented
shared-data types through visible `data_collect` command jobs:

- `ohlcv`
- `text_event`
- `macro_calendar`
- `onchain_flow`
- `derivatives_market`
- `market_anomaly`

Other data types are unsupported until their shared-store contract and Live
read model are explicitly implemented.

## Trigger Decisions and Report Dispatch

Core evaluates deterministic Live trigger decisions from the Live scheduler
path after collection state reconciliation. Trigger decisions are stored in
`.halpha/state.sqlite` and exposed through the Dashboard Live read model.

- `market_breakout`
- `major_market_move`
- `critical_news`
- `scheduled_catalyst`
- `derivatives_stress`
- `data_quality_degraded`

Supported decision statuses:

- `triggered`
- `suppressed_cooldown`
- `skipped_disabled`
- `skipped_no_match`
- `skipped_insufficient_evidence`
- `blocked_authorization`
- `failed`

Each trigger decision preserves decision id, trigger id, evaluated time, source
data types, source refs, reason codes, threshold params, matched evidence
summary, cooldown state, linked collection job ids, linked job id, reconciled
run/report refs, warnings, and errors.

Trigger-created jobs use the existing command-job manager. `run_no_codex` jobs
may be created without Codex authorization and are no-report deterministic run
jobs unless a later report artifact ref is present. `run` jobs require valid
persisted unattended Live trigger authorization. Missing or invalid
authorization records `blocked_authorization` and does not create a
Codex-capable job.

Live read models must distinguish trigger decisions, trigger-created jobs, and
actual report artifacts. A trigger-created job is a report artifact only when it
has a concrete `report_ref`.

Trigger decisions must not be generated or revised by AI/Codex.

## Current Source-Refresh Read Model

`GET /api/live` exposes a bounded read model for the implemented source-refresh
slice. It does not embed raw streams or full shared stores. Current fields are:

- Live enabled state and scheduler status.
- Source refresh state by data type.
- Last attempt, last success, next attempt, cadence, freshness, consecutive
  failures, and latest job id for each data type.
- Recent collection jobs with bounded terminal status, duration, warning count,
  error count, and linked artifact refs.
- Active Live collection jobs.
- Warnings and errors.

Planned Live read-model expansion may add latest intelligence items, trigger
decisions, daily report schedule state, report dispatch history, and drill-down
links once their deterministic producers exist.

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
