# Storage Contracts

This document defines Halpha's M21 storage contract for run archives, shared
data, runtime state, and derived artifacts. It is a durable implementation
contract for humans and AI agents. It is not a milestone plan and not a claim
that every producer already satisfies the target rule.

M21 reliability work requires run history, Monitor state, shared data state,
and cleanup decisions to be explicit. The goal is simple:

- product runs stay inspectable but disposable;
- reusable facts stay outside per-run archives;
- mutable operational state has one runtime authority;
- rebuildable summaries do not become hidden authorities.

## Related Docs

- `docs/artifact-governance.md`: artifact layers, runtime state authority, and
  Codex input policy.
- `docs/research-data-contracts.md`: implemented shared research data stores,
  run-index projection, catalog fields, and data-quality contracts.
- `docs/monitoring-contracts.md`: Monitor service, cycle, source-cadence,
  alert archive, and health contracts.
- `docs/dashboard-contracts.md`: Dashboard command jobs, service lifecycle,
  artifact preview, and local API contracts.
- `docs/product-stability-contracts.md`: product validation, workflow
  stability, run health, backup boundary, and operational acceptance.

## Storage Categories

Halpha storage belongs to exactly one current category.

| Category | Current root | Authority |
| --- | --- | --- |
| Run archive | `runs/<run_id>/` | One decision, report, reassessment, validation, stage-rerun, or failed-run-resume execution archive. |
| Shared data | `data/` or explicit configured shared-data root | Durable reusable facts and store metadata. |
| Runtime state | `.halpha/state.sqlite` and bounded `.halpha/` operational files | Mutable operational state, service state, command jobs, schedules, Monitor state, cooldowns, and indexes. |
| Derived artifact/cache | Rebuildable delivery or read-model outputs | Summaries produced from run archives, shared data, and runtime state. |

No file should be interpreted through two category contracts at once. If a file
is a run-local artifact, it is not shared data. If a value is runtime state, it
is not research evidence. If an output is derived, it must be rebuildable from
authoritative sources or explicitly marked as unavailable.

## Run Archives

A run archive is one top-level execution archive under `runs/<run_id>/`.

Run archives may contain:

- `run_manifest.json`;
- current-run raw source snapshots under `raw/`;
- current-run deterministic evidence under `analysis/`;
- bounded Codex context under `codex_context/`;
- report output under `report/`;
- copied upstream run-local artifacts for a derived stage rerun.

Run archives must not contain:

- durable shared OHLCV, text-event, outcome, derivatives, macro/calendar, or
  on-chain history;
- `.halpha/state.sqlite` or runtime state side files;
- command-job stdout or stderr logs;
- hidden source-polling state;
- private local config values, proxy values, credentials, cookies, account
  identifiers, or raw local user-state files;
- durable cleanup approval state.

Run archive names may remain timestamp-based. New product run directory names
use the configured display timezone because they are user-visible report
archive labels. Directory names are not the authority for the run timestamp or
why a run exists. `run_manifest.json` must carry UTC lifecycle timestamps and
the bounded classification metadata described below.

### Allowed Run Archive Creators

Only these operations may create a top-level product run archive:

- explicit user product run, such as `python -m halpha run ...`;
- Dashboard command job that explicitly starts a product run;
- scheduled daily report dispatch that actually starts a product run;
- decision-producing Monitor reassessment after source evidence actually
  changed;
- derived stage rerun from a completed successful parent run;
- failed-run resume in place from the recorded failed stage;
- product validation path only when it intentionally produces a run artifact.

These operations must not create a product run archive:

- source polling by itself;
- no-due Monitor cycle;
- no-change source refresh;
- all-source no-change Monitor cycle;
- Monitor, Dashboard, or Schedule health check;
- read-only inspection command;
- read-only validation command;
- schedule tick that does not dispatch a due report;
- Dashboard page load, API read model, artifact preview, or settings read.

Source polling, no-due cycles, no-change refreshes, health checks, inspections,
and schedule ticks are runtime-state events. They may update bounded runtime
state, but they must not create `runs/<run_id>/`, `run_manifest.json`, `raw/`,
`analysis/`, `codex_context/`, or `report/`.

### Run Manifest Classification

New run archives are expected to record these minimum fields in
`run_manifest.json`:

- `run_kind`: finite run kind, such as `product_report`,
  `scheduled_report`, `monitor_reassessment`, `stage_rerun`,
  `validation_run`, `standalone_backtest`, `standalone_experiment`, or
  `unknown`.
- `trigger`: bounded trigger object with `source` and `intent`.
- `trigger.job_id`: command job id when a Dashboard command job created the
  run.
- `trigger.schedule_id`: schedule id when Schedule dispatched the run.
- `trigger.monitor_cycle_id`: Monitor cycle id when a Monitor reassessment
  created the run.
- `trigger.source_keys`: bounded changed source keys for Monitor
  reassessments.
- `trigger.parent_run_id`: parent run id when a derived stage rerun creates a new
  archive.
- `trigger.requested_stage`: requested stage for derived stage reruns and
  failed-run resume-in-place requests.
- `disposal_class`: cleanup classification, such as `report_archive`,
  `monitor_reassessment_archive`, `derived_archive`, `validation_archive`,
  `standalone_archive`, or `legacy_archive`.

Trigger metadata must be source-aware and bounded. It must not embed raw config
contents, absolute machine-local paths, proxy URLs, credentials, account ids,
private endpoints, user names, or raw user-state values.

Legacy manifests without these fields are not classified archives. Readers
must show them as `unknown` or `legacy`, not crash and not silently treat them
as safe cleanup candidates.

## Public Path References

Public artifacts, Dashboard payloads, Workbench output, command-job records,
report-visible evidence, and user-facing diagnostics use bounded local refs.
Runtime-root-local files serialize as stable relative refs such as
`runs/<run_id>/run_manifest.json` or `analysis/risk_assessment.json`.
Absolute external paths, Windows-shaped absolute paths, traversal-like refs,
and unrelated paths serialize as `<external-artifact>` unless the field has a
more specific placeholder such as `<external-config>`.

This contract applies only to public serialization. Internal `Path` values may
still point at configured external stores when Halpha must read or write those
stores. The public ref must not include drive letters, usernames, home
directories, hostnames, private endpoint details, or absolute machine-local
directory names.

## Shared Data

Shared data is durable reusable input data. It lives outside per-run report
directories and is summarized through store metadata, current-run views, and
bounded material.

Current implemented or initially adopted shared stores are:

- OHLCV history under `data/market/ohlcv/`;
- derivatives market history under `data/market/derivatives/`;
- macro/calendar history under `data/macro/calendar/`;
- on-chain flow history under `data/onchain/flow/`;
- text-event history under `data/research/text_events/`;
- outcome history under `data/research/outcomes/outcome_history.json`;
- research data catalog under `data/research/metadata/research_data_catalog.json`.

Shared data may contain:

- durable public-source records or normalized reusable records;
- store-local schema metadata;
- store-local state metadata;
- storage refs, counts, warnings, errors, and consumer metadata;
- migration metadata for the implemented store.

Shared data must not contain:

- per-run Codex context;
- generated report prose;
- Dashboard command-job lifecycle rows;
- Monitor service health rows;
- schedule dispatch claims;
- runtime mutation leases;
- private local user-state files;
- cleanup approval for run archive deletion.

### Shared Data Layout

Implemented shared stores follow these layout rules:

- store category uses `data/<domain>/...` unless a config field explicitly
  selects a local shared-data root;
- domain roots match the current implemented domain, such as `data/market/`,
  `data/macro/`, `data/onchain/`, or `data/research/`;
- source identity is part of the path, state metadata, or record identity when
  the store is source-specific;
- symbol and timeframe are part of the path, state metadata, or record identity
  when the store is market-series data;
- time partition fields are recorded when the current store supports
  time-based retrieval;
- schema version is recorded in schema metadata;
- state metadata records stored ranges, latest update or revision, duplicate
  handling, conflicts, warnings, and errors where the producer implements
  them;
- migration metadata records applied schema version, available compatibility or
  migration path, last migration time when one ran, and migration warnings or
  errors.

The current shared data catalog must describe implemented stores only. It must
not invent store entries for unimplemented future storage systems.

Cataloged shared store `storage_path` values must be runtime-root-relative
shared-data paths or safe external refs. They must not point under `runs/`.
Run archives may appear only as source artifact refs or current-run views, not
as durable shared store roots.

Run archives may reference shared data through bounded refs and current-run
views. Run archives must not become the durable store required to query shared
data.

## Runtime State

Runtime state is mutable operational state under `.halpha/state.sqlite` within
one runtime root. It records references and bounded status, not artifact
contents.

Runtime state may contain:

- schema migration state for the runtime store;
- mutation lease and resident service lifecycle state;
- run-index projection and latest-run derived views;
- Dashboard command-job lifecycle metadata;
- bounded command-job parameter/result refs;
- daily report schedule configuration, due dispatch claims, and dispatch
  history refs;
- Monitor source state, latest attempt, latest success, next attempt, latest
  revision, changed or no-change status, failure count, and last error;
- Monitor cycle index, alert archive records, cooldown state, finite-loop
  summary, and service health query state;
- Dashboard UI preferences.

Runtime state must not contain:

- full raw streams;
- full reusable histories;
- full run manifests or artifact bodies;
- full Codex context;
- full report prose;
- unbounded stdout or stderr;
- private secrets or raw local user-state values.

Deleting a run archive must not delete runtime state. Runtime run-index
projections may be rebuilt from authoritative `run_manifest.json` files where
the contract supports rebuilding. Runtime state rows that reference deleted or
missing archives are diagnostics until rebuilt or otherwise repaired by an
explicit command.

## Derived Artifacts And Caches

Derived artifacts and caches are rebuildable outputs produced from run
archives, shared data, and runtime state.

Examples include:

- `runs/workbench/latest/workbench_summary.json`;
- `runs/workbench/latest/index.md`;
- `runs/workbench/latest/index.html`;
- Dashboard read models and artifact previews;
- latest-run selections derived from runtime indexes;
- bounded local diagnostic summaries.

Derived outputs may contain bounded summaries, source refs, counts, warnings,
and errors. They must not contain full raw histories, full reusable stores,
full Codex context, raw private user state, credentials, or cleanup authority.

Derived outputs must be safe to rebuild or mark stale. They must not be the
only owner of a fact that belongs to run archives, shared data, or runtime
state.

## Deletion Semantics

Deleting a run archive means deleting only the selected `runs/<run_id>/`
directory and run-local files beneath it.

Run archive deletion must not delete:

- `data/`;
- `.halpha/state.sqlite`;
- `.halpha/state.sqlite-wal`;
- `.halpha/state.sqlite-shm`;
- machine-local config files;
- command-job logs outside the selected run archive;
- shared data catalog files;
- derived outputs outside the selected run archive unless a cleanup command
  explicitly owns that derived output.

Deleting shared data requires explicit user action scoped to shared data. It
must not happen through normal run cleanup, Monitor polling, Dashboard read
models, schedule ticks, or product-run cleanup.

Deleting runtime state requires explicit local maintenance or migration work.
Normal run archive cleanup must not delete runtime state. Runtime indexes may
be rebuilt from authoritative run manifests and shared metadata when the
contract supports rebuilding.

Malformed, missing, dangling, unknown, or legacy run archives are diagnostics.
They require review unless a later cleanup contract defines a safe explicit
heuristic. They are not automatic deletion approval.

## Cleanup Boundary

Cleanup planning may classify run archives by `run_kind`, `trigger`,
`disposal_class`, report presence, latest-index references, manifest health,
and source refs. Cleanup planning must be dry-run first unless a user invokes
an explicit apply command with selected candidates.

The implemented CLI path is:

```bash
python -m halpha data cleanup-runs --config <config>
python -m halpha data cleanup-runs --config <config> --apply --run-id <run_id>
```

The dry-run plan reports candidate counts, approximate deletable size, run IDs,
run kinds, bounded trigger summaries, report presence, latest-index references,
and deletion reasons. Apply mode deletes only explicitly selected candidates
from the approved plan, then rebuilds the run-index projection from remaining
run manifests so deleted archives do not remain healthy latest or report
selections.

Report-bearing archives require stronger confirmation than disposable
reassessment or validation archives:

```bash
python -m halpha data cleanup-runs --config <config> --apply --run-id <run_id> --include-report-runs --confirm-report-runs "DELETE REPORT RUNS"
```

Shared data and runtime state remain out of scope for run archive cleanup.

## Current Implementation Follow-Ups

The implementation issues tied to this storage boundary are:

- #691 stops no-change Monitor source refreshes from creating product run
  archives.
- #692 stores routine Monitor polling in runtime state instead of unbounded
  cycle directories.
- #693 adds run classification metadata to new manifests and readers.
- #694 adds explicit cleanup planning for disposable run archives.
- #695 hardens shared data catalog and migration metadata.
