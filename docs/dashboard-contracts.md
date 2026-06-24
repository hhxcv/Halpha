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
workbench CLI remains a delivery snapshot and inspection or recovery fallback,
not a competing primary UI. The dashboard may call implemented CLI paths through
controlled jobs, but it must not create hidden product behavior outside those
contracts.

## Source Of Truth

Dashboard views must read existing Halpha artifacts and local stores. The
dashboard is not the source of research, decision, strategy, alert, risk,
forecast, validation, or report truth.

Primary sources:

- `.halpha/state.sqlite`: implemented runtime-root SQLite state-store
  foundation, current run-index projection, and local command-job
  lifecycle plus daily report schedule configuration, dispatch history,
  Dashboard service lifecycle, Dashboard UI preferences, monitor cycle indexes,
  alert archive records, cooldown state, and monitor service health query state.
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
- `runs/monitor/`: immutable monitor cycle manifests.
- `.halpha/state.sqlite`: run index, local command jobs, daily report schedule
  dispatches, monitor cycle indexes, alert archive records, cooldown state,
  monitor service health query state, Dashboard service lifecycle, and Dashboard UI
  preference state.
- `runs/workbench/latest/`: bounded delivery snapshot summaries and local
  indexes for inspection and recovery fallback, not replacements for dashboard
  views.
- `runs/strategy_backtests/`, `runs/strategy_experiments/`, and
  `runs/text_intelligence/`: standalone command outputs.

Dashboard runtime state may record service lifecycle, selected-config
preference, UI-triggered job, and schedule state. That state is control and
delivery state only. It must not override or mutate product artifacts as
research evidence.

Dashboard read models, overview cards, health summaries, and latest-run
selections are derived views. They must be rebuilt from authoritative run
artifacts, reusable stores, and runtime state. They must not become parallel
authorities for facts already owned elsewhere.

## Implemented Operation

Start the dashboard with:

```bash
python -m halpha dashboard
python -m halpha dashboard start
python -m halpha dashboard status
python -m halpha dashboard stop
python -m halpha dashboard restart
python -m halpha dashboard --config config.example.yaml
python -m halpha dashboard --config config.example.yaml --host 127.0.0.1 --port 8765
```

The dashboard service validates that the bind host is local-only. It is a local
operator UI, not a hosted service.

`--config` is optional for dashboard startup. If omitted, startup loads the
last selected dashboard config from `.halpha/state.sqlite` when that config is
available and valid. If no config is selected or the persisted selection no
longer validates, the dashboard starts in an explicit `unconfigured` state.
Unconfigured data APIs must return no-data payloads instead of guessing a
runtime directory. The Settings view can load or switch the active config; a
successful selection updates the in-process dashboard config and records the
last selected config in runtime UI preference state.

Dashboard startup uses the shared resident-service lifecycle controller in
`.halpha/state.sqlite`; it does not write
`.halpha/dashboard/service_state.json` or `.halpha/dashboard/selected_config.json`.
Before binding, startup checks the requested local endpoint. Duplicate start for
the same endpoint returns the existing matching dashboard instance. A
conflicting endpoint/runtime setting returns an explicit conflict and does not
alter the running service. Restart is an explicit stop plus start. If the port
is occupied by a non-Halpha or unresponsive local service, startup fails with an
actionable error and must not kill the unrelated process.

The dashboard root serves the application shell and loads packaged static
frontend assets from `/assets/dashboard.css`, `/assets/dashboard_shared.js`,
`/assets/dashboard_dialogs.js`, `/assets/dashboard_reports.js`,
`/assets/dashboard_strategy_chart.js`, `/assets/dashboard_monitor.js`, and
`/assets/dashboard.js`.

Dashboard timestamp display uses `dashboard.display_timezone` when configured,
falls back to `run.timezone`, and defaults to `Asia/Shanghai`. This display
setting changes the local UI rendering of ISO timestamps; it must not rewrite
source artifacts or stored UTC timestamps.

Implemented dashboard views expose:

- overview state from latest run, product validation, data quality, monitor,
  and workbench summaries;
- run history, report previews, stage timelines, and artifact refs;
- bounded artifact previews for supported local text-like artifacts;
- local data store metadata and source refs;
- strategy research outputs, standalone backtests, experiments, gates, and
  lifecycle state, including bounded K-line backtest visualizations when the
  standalone backtest artifact records visualization data;
- monitor health, recent cycles, alert counts, cooldown state, alert samples,
  and monitor job history from the shared runtime state store.

Implemented dashboard command controls submit to the shared allowlisted
command-job runner.
The current job runner supports:

- read-only or inspection jobs: `validate`, `data_inspect`,
  `outcomes_inspect`, `workbench_inspect`, and `monitor_inspect`;
- product jobs: `run`, `run_no_codex`, `run_until`, and `stage_rerun`;
- workbench build: `workbench_build`;
- strategy and text jobs: `backtest`, `experiment`,
  `text_models_prepare`, and `text_intel`;
- monitor jobs: `monitor_dry_run`, `monitor_once`, and `monitor_inspect`.

The dashboard UI may expose short monitor validation jobs directly in the
Monitor view. It must not create a resident Monitor loop as a command job.
Other command actions are available through the dashboard jobs API and remain
explicit allowlisted jobs.

The dashboard services API exposes one bounded read model for exactly
`dashboard`, `monitor`, and `schedule`. Monitor and Schedule service controls
delegate start, stop, restart, and status actions to the same shared lifecycle
controller used by the CLI. Repeated starts return the existing matching
instance. Config conflicts are visible and do not replace the running service.

Implemented schedule controls are API-backed runtime state for the daily report
schedule in `.halpha/state.sqlite`. The schedule API can inspect, enable,
disable, update, and manually trigger daily report jobs. Automatic due dispatch
is owned by the independent `schedule` resident service, not the Dashboard
lifespan. The Schedule service checks the persisted daily report schedule,
claims due occurrences, marks older bounded catch-up occurrences as missed, and
creates visible allowlisted command jobs for due runs. It is not a hosted
scheduler, OS scheduler, startup task, cron integration, external workflow
engine, or fourth resident process.

## Target Service Lifecycle

The target lifecycle contract is scoped to one runtime root. Runtime root is the
resolved local root used by CLI and all resident services for `.halpha/`,
`runs/`, `logs/`, and relative data roots. It must be selected explicitly by
the command/config contract and shared by CLI, Dashboard, Monitor, and Schedule.
It must not be inferred independently from the config-file directory or
dashboard port.

The only supported resident Halpha process roles are:

- `dashboard`
- `monitor`
- `schedule`

Each role is unique within one runtime root and independently startable,
stoppable, inspectable, and restartable. CLI commands and Dashboard controls
must address the same Monitor and Schedule instances. Dashboard must not create
a private Monitor process or a private daily-report dispatcher. CLI and
Dashboard controls must not create duplicate Monitor or Schedule processes for
the same runtime root.

Lifecycle state must combine:

- an OS-level exclusive lock scoped to the runtime root and role;
- a persisted instance id;
- process metadata such as pid, host, command, config digest, started time, and
  requested endpoint when applicable;
- heartbeat metadata with timestamp and freshness threshold.

Implemented shared controller state lives in `.halpha/state.sqlite` and records
bounded service role, instance id, PID, config ref, config digest, status,
heartbeat, endpoint metadata, stop request, terminal exit, and bounded error
metadata. It recognizes only `dashboard`, `monitor`, and `schedule`. Ordinary
start reports terminal records; explicit restart requires the previous instance
id.

A persisted `running` status alone must not prove that a process is alive.
Lifecycle inspection must distinguish:

- `running`: lock, process metadata, and heartbeat agree.
- `stale`: persisted state exists but heartbeat or process liveness is stale.
- `stopped`: explicit stop completed and released the lock.
- `crashed`: process ended without a clean stop.
- `conflict`: another live instance or mismatched config owns the role.

Start, stop, force-stop, and restart semantics:

- duplicate start with matching config returns the existing matching instance;
- duplicate start with mismatched config returns an explicit conflict and does
  not replace the process;
- stop requests graceful shutdown and records the terminal state;
- force-stop is explicit and records why graceful stop was not enough;
- restart is explicit stop plus start, not implicit replacement during ordinary
  `start`.

Dashboard only serves UI/API, reads product state, submits bounded jobs, and
sends lifecycle requests. Monitor is the single continuous information-refresh
and alert-reassessment service. Schedule is the single time-trigger service for
report jobs. Halpha must not add a hidden supervisor, broker, worker pool, or
fourth resident process role.

## View Contract

Dashboard pages should expose the current product shape through bounded views:

- Overview: latest report state, system runtime, monitor status, data health,
  warning and error counts, and recent attention items.
- Reports: all generated reports, report metadata, real source refs, rendered
  Markdown previews, report generation, report download, and single-run report
  deletion.
- Strategy lab: pipeline strategy artifacts, standalone backtests, standalone
  experiments, gates, lifecycle state, warnings, and limitations. Standalone
  backtests may render bounded candlestick bars, deterministic exposure
  markers, and an equity curve from the `strategy_backtest.json`
  `visualization` block. The dashboard must not reconstruct charts by dumping
  full reusable OHLCV history by default.
- Monitor: monitor control, configured loop parameters, state-store cycle
  history, linked runs, alert archive aggregates, cooldown state, warnings,
  errors, and explicit daily-report schedule state.
- Intelligence: source-aware non-OHLCV intelligence summaries, including text,
  derivatives, on-chain, macro, outcomes, and data-quality tabs where the
  corresponding artifacts exist.
- Settings: config loading and switching, current config controls, validation,
  backup, and storage maintenance for single-run artifacts and shared stores.

Artifact preview remains an internal bounded API capability used by these
views. It must not reintroduce a top-level Artifacts page. Command controls
must be page-local actions backed by allowlisted command jobs, not a top-level
Command center.

Every view must distinguish available, partial, missing, stale, degraded,
failed, skipped, and not-applicable states where the source artifacts support
those distinctions. Missing evidence must not be displayed as neutral evidence.

## UI Smoke Validation

Dashboard UI validation should cover both source-backed APIs and the HTML shell
that users operate directly. Automated smoke coverage should check:

- navigation targets match implemented view sections;
- primary workflow controls are wired for preview, command, schedule, monitor,
  strategy, and text interactions;
- desktop layout contracts keep the sidebar and content panes nonblank;
- smaller viewport layout contracts collapse major grids to a single column;
- bounded preview panels remain scrollable instead of expanding unbounded
  artifact content.
- configured timestamp display converts ISO timestamps without mutating raw
  artifact values.

When browser tooling can access the local dashboard process, validate at least
one desktop viewport and one smaller viewport by navigating across core views
and opening at least one bounded artifact preview. If the local environment
blocks browser automation against the local-only dashboard bind, record that
limitation in the PR and rely on TestClient shell/API coverage plus static
responsive and interaction-contract tests.

The standard local browser-smoke command is:

```bash
python -m pytest tests/test_dashboard_browser_smoke.py -q
```

By default this runs a deterministic static navigation contract check and skips
the real browser launch. The default check must fail if primary navigation
targets, view section IDs, or the Playwright stuck-loading and console-error
assertions drift out of the dashboard shell.

The opt-in real-browser smoke check is:

```bash
HALPHA_BROWSER_SMOKE=1 python -m pytest tests/test_dashboard_browser_smoke.py -q
```

On Windows PowerShell:

```powershell
$env:HALPHA_BROWSER_SMOKE = "1"
python -m pytest tests\test_dashboard_browser_smoke.py -q
```

Without `HALPHA_BROWSER_SMOKE=1`, only the Playwright launch is skipped so
default unit runs do not download or launch browser tooling. When enabled, the
test starts the local dashboard server, drives the primary views with
Playwright Chromium through `npx`, fails on stuck loading or broken navigation,
and fails on browser console or page errors. Tests that require Playwright are
marked `browser_smoke`.

Static dashboard JavaScript must also pass syntax checks before merge:

```bash
node --check src/halpha/dashboard/static/dashboard_shared.js
node --check src/halpha/dashboard/static/dashboard_dialogs.js
node --check src/halpha/dashboard/static/dashboard_reports.js
node --check src/halpha/dashboard/static/dashboard_strategy_chart.js
node --check src/halpha/dashboard/static/dashboard.js
```

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
- requested-by source;
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

Current command-job lifecycle records are written to `.halpha/state.sqlite`.
They include bounded metadata, safe relative log refs, result refs, warnings,
errors, and transition events. New jobs must not write
`.halpha/dashboard/jobs/index.json` or per-job `job.json`; those files are
legacy storage for `data migrate-state` import or separate cleanup work only.
Normal Dashboard, Schedule, and CLI job readers must not use them as fallback
authorities.

Bounded stdout and stderr logs are written under
`.halpha/command_jobs/job_logs/<job_id>/` below the current working directory by
default. Relative dashboard control-state paths resolve from the current
working directory, not from the config file location or product run output
root. Full job logs are local runtime artifacts and must not be copied into
Codex context by default.

## Schedule Contract

Daily report scheduling is current shared runtime state. The target owner is
the independent `schedule` resident service using the unified runtime state
store. Dashboard schedule APIs should become control and read-model surfaces
for that service, not a dashboard-owned dispatcher.

Schedule state should record:

- enabled state;
- schedule kind;
- local timezone or explicit UTC interpretation;
- next run time;
- last run time;
- linked job ids;
- linked report refs when available;
- Codex authorization metadata for unattended Codex-capable schedules;
- missed, blocked, claimed, and job-linked dispatch records;
- warnings and errors.

Implemented daily report schedule state lives in:

```text
.halpha/state.sqlite
```

The legacy `.halpha/dashboard/schedules/daily_report_schedule.json` path is no
longer written for new schedule state. It remains legacy storage until explicit
`data migrate-state` import or separate cleanup work. Normal Dashboard and
Schedule readers must not use it as a fallback authority.

The schedule API supports:

- `GET /api/schedule/daily-report`;
- `POST /api/schedule/daily-report`;
- `POST /api/schedule/daily-report/enable`;
- `POST /api/schedule/daily-report/disable`;
- `POST /api/schedule/daily-report/trigger`.

Manual schedule triggers create visible command jobs and persisted dispatch
records. The default trigger is the explicit request `job_intent`, then the
persisted schedule mode, then the Codex-capable `run` fallback. Codex-capable
`run` triggers require `confirm_codex: true`.

Enabling a schedule requires an explicit `job_intent`. The dashboard enable
control records `run_no_codex`, which the Schedule service can execute without
Codex. Enabling or changing a Codex-capable `run` schedule requires
`confirm_codex: true` and persists authorization with timestamp, schedule
revision, selected config ref, and config digest. Changing the report mode,
selected config ref, or relevant config digest invalidates unattended Codex
authorization and automatic dispatch records a blocked state until reconfirmed.
No-Codex schedules are labeled as no-report runs.

Automatic dispatch claims a due occurrence transactionally before creating a
job, so repeated due checks for the same scheduled time create at most one
dispatch record and one linked job. After downtime, automatic dispatch claims
at most one latest due occurrence and records older due occurrences as missed
within the bounded catch-up policy. Schedule remains active when Dashboard is
stopped.

## Monitor Boundary

Dashboard monitor controls must preserve `docs/monitoring-contracts.md`:

- no hidden private dashboard-owned monitor service;
- no hosted scheduler assumption;
- no alert delivery channel unless implemented by a separate explicit contract;
- no trading execution or account operations;
- no Codex execution by default.

The Monitor service is an independent resident role addressed through the
shared lifecycle contract. Dashboard service controls start, stop, inspect, or
restart the shared Monitor and Schedule instances. Short validation jobs remain
bounded command jobs. Dashboard controls must not create duplicate Monitor or
Schedule processes, and they must not run the monitor loop inside the Dashboard
process.

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

Artifact previews redact private JSON keys, JSONL records, text key-value
lines, configured private values, and local config-root paths where the
dashboard can identify them. Preview redaction is conservative: source keys
that look like private paths, tokens, proxy values, endpoints, users, accounts,
or credentials may be replaced with `<redacted>`.

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
user-state files, full workbench summaries, full command job histories, or
full dashboard service or schedule state by default.

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
