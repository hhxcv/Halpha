# Dashboard Contracts

This document defines Halpha's local web dashboard contract. It is a durable
implementation contract, not a milestone plan.

## Purpose

The dashboard is Halpha's primary local user entry point. It lets the user
inspect, run, monitor, and control the local research product without replacing
the existing CLI or artifact contracts.

The dashboard must remain:

- local-first;
- artifact-backed;
- source-aware;
- privacy-preserving;
- explicit about command execution;
- explicit about Codex execution;
- free of trading execution, account operations, wallet operations, portfolio
  automation, position sizing, or order placement.

CLI commands remain automation, validation, debugging, and recovery paths. The
dashboard may call implemented CLI paths through controlled jobs, but it must
not create hidden product behavior outside those contracts.

## Source Of Truth

Dashboard views must read existing Halpha artifacts and local stores. The
dashboard is not the source of research, decision, strategy, alert, risk,
forecast, validation, or report truth.

Primary sources:

- `data/research/index.sqlite`: compact run, stage, artifact, and latest-run
  metadata.
- `runs/<run_id>/run_manifest.json`: per-run lifecycle, stage, artifact, count,
  Codex, warning, and error state.
- `runs/<run_id>/raw/`: current-run public observations and bounded current-run
  views.
- `runs/<run_id>/analysis/`: deterministic evidence, materials, validation,
  strategy, decision, alert, data-quality, outcome, and related artifacts.
- `runs/<run_id>/codex_context/`: generated Codex input context and prompt
  artifacts.
- `runs/<run_id>/report/report.md`: final Simplified Chinese report from Codex
  stdout plus deterministic post-processing.
- `data/market/`, `data/macro/`, `data/onchain/`, and `data/research/`:
  reusable local stores and metadata.
- `runs/monitor/`: monitor cycles, alert archive, cooldown state, archive state,
  and monitor health state.
- `runs/workbench/latest/`: bounded delivery summaries and local indexes.
- `runs/strategy_backtests/`, `runs/strategy_experiments/`, and
  `runs/text_intelligence/`: standalone command outputs.

Dashboard runtime state may record UI-triggered job and schedule state. That
state is control and delivery state only. It must not override or mutate
product artifacts as research evidence.

## View Contract

Dashboard pages should expose the current product shape through bounded views:

- Overview: latest run, latest report, product validation, data quality, monitor
  health, warning and error counts, and recent job state.
- Runs and reports: run history, stage timeline, artifact refs, Codex status,
  warnings, errors, and report previews.
- Artifact explorer: bounded previews for allowed JSON, JSONL, Markdown, text,
  and table-like artifacts.
- Local data: metadata, counts, ranges, freshness, warnings, and source refs for
  implemented reusable stores.
- Strategy lab: pipeline strategy artifacts, standalone backtests, standalone
  experiments, gates, lifecycle state, warnings, and limitations.
- Decision, risk, event, and alert views: deterministic records and bounded
  source refs from existing artifacts.
- Monitor: cycle history, linked runs, alert archive aggregates, cooldown state,
  warnings, and errors.
- Command center: controlled UI triggers for implemented Halpha commands.
- Schedule controls: explicit local daily-report schedule state when
  implemented.

Every view must distinguish available, partial, missing, stale, degraded,
failed, skipped, and not-applicable states where the source artifacts support
those distinctions. Missing evidence must not be displayed as neutral evidence.

## Artifact Preview Rules

Dashboard artifact previews must be bounded by default.

Allowed behavior:

- resolve repo-relative artifact refs from known run, data, monitor, workbench,
  standalone command, and dashboard runtime roots;
- show bounded previews for JSON, JSONL, Markdown, text, and table-like data;
- show metadata for truncation, omitted rows, unsupported formats, unreadable
  files, and missing artifacts;
- link source artifacts instead of copying large payloads into dashboard state.

Default previews must not embed:

- full raw streams;
- full reusable OHLCV, derivatives, macro/calendar, on-chain, text-event, or
  outcome histories;
- full SQLite contents;
- full Parquet tables;
- full intermediate JSON evidence;
- full run manifests;
- full Codex context or prompt artifacts;
- full product validation artifacts by default;
- raw local user-state files;
- private notes;
- credentials, tokens, cookies, account identifiers, proxy values, private
  endpoints, machine-local paths, or other local private values.

## Command And Job Contract

Dashboard-triggered work must run through explicit, allowlisted job intents.
The dashboard must not expose arbitrary shell execution.

Supported job implementations should record:

- job id;
- job kind or command intent;
- structured request parameters;
- config ref;
- status;
- created, started, finished, and updated timestamps;
- process id when applicable;
- exit code;
- bounded stdout and stderr refs;
- linked run, report, monitor, backtest, experiment, text-intelligence, or
  workbench artifacts when available;
- warnings and errors.

Job status values should include:

- `queued`;
- `running`;
- `succeeded`;
- `failed`;
- `cancel_requested`;
- `cancelled`;
- `not_started`;
- `unsupported`;
- `blocked`.

Command requests must validate structured parameters before execution. Stage
names must match implemented pipeline stages. Run directories and artifact
paths must stay within allowed roots. Unsupported arguments must fail before a
process starts.

Codex-capable full report jobs require explicit user confirmation before the
dashboard invokes Codex CLI. No monitor job or read-only inspection job should
invoke Codex unless its command contract explicitly says so.

## Schedule Contract

Daily report scheduling, when implemented, must be explicit dashboard state.

Schedule state should record:

- enabled state;
- schedule kind;
- local timezone or explicit UTC interpretation;
- next run time;
- last run time;
- linked job ids;
- linked report refs when available;
- warnings and errors.

The schedule must not assume a hosted scheduler, OS service, startup task,
cron integration, workflow engine, or hidden daemon. Scheduled work should run
only while the dashboard runtime is active unless a later explicit local service
requirement changes that contract.

## Monitor Boundary

Dashboard monitor controls must preserve `docs/monitoring-contracts.md`:

- no hidden background service;
- no hosted scheduler assumption;
- no alert delivery channel unless implemented by a separate explicit contract;
- no trading execution or account operations;
- no Codex execution by default.

Finite monitor loops started from the dashboard must remain visible as jobs and
must expose stop, cancel, completion, failure, and bounded log state.

## Privacy Boundary

Dashboard APIs, UI, job records, logs, previews, and docs must not expose local
private values.

Local private values include:

- proxy URLs;
- ports and hostnames that reveal private endpoints;
- credentials, tokens, cookies, and account identifiers;
- machine-local paths, usernames, private endpoints, and local-only config
  values;
- raw local user-state files;
- private notes;
- account identifiers, exact holdings, balances, allocations, or position
  sizes.

Use bounded public-facing summaries, sanitized refs, omitted-value counts, and
explicit warnings instead of copying private source content into dashboard
responses.

## Codex Boundary

The dashboard may display Codex-related artifact metadata and report outputs.
It must not make Codex the source of deterministic Halpha states.

Codex must not generate:

- market data;
- derivatives states;
- macro/calendar events or states;
- on-chain records or labels;
- feature records or factor scores;
- fusion states;
- user state or personalized constraints;
- strategy lifecycle states;
- data-quality checks;
- alert priority;
- action levels;
- forecasts;
- trading instructions;
- position sizing.

The dashboard must preserve the existing rule that Codex receives bounded
report-facing material, not full raw artifacts, reusable histories, private
user-state files, full workbench summaries, full dashboard job histories, or
full dashboard schedule state by default.

## Validation

Dashboard changes should use the narrowest validation that proves the touched
behavior:

- `python -m pytest` for automated behavior.
- Dashboard API tests for read models, path allowlists, previews, job intents,
  redaction, and schedule state.
- Local browser smoke checks for UI changes.
- `python -m halpha validate --config config.example.yaml` when product
  validation behavior or surfaced validation state changes.
- `python -m halpha monitor inspect --config config.example.yaml` when monitor
  surfacing changes.
- Full local product runs with Codex only when Codex context, report generation,
  or UI-triggered full report behavior changes.

Production dashboard behavior must use real artifacts and real command flow.
Fake data, fake runners, fake artifacts, and mock dashboards are test-only.
