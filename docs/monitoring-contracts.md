# Monitoring Contracts

This document defines Halpha's local Monitor contract. It is a durable
implementation contract, not a milestone plan.

## Purpose

The current user-facing Monitor surface is a local System Monitor health
service. Its job is to keep Core liveness observable for one runtime root and to
attempt Core start or recovery when Core state is stale or terminal.

Monitor is not the continuous intelligence workflow. Live owns user-facing
continuous market intelligence, source refresh state, trigger decisions,
trigger-created jobs, report dispatch visibility, and alert history. Core owns
scheduled job dispatch and command-job execution. Dashboard reads these states
but does not own background work.

Monitor must remain local-first and bounded:

- no hidden dashboard-owned background service;
- no hosted scheduler, broker, worker pool, or remote-control assumption;
- no data collection, source-cadence refresh, report scheduling, trigger
  decisions, command-job creation, product pipeline work, or Codex execution
  inside the resident Monitor process;
- no trading execution, account access, wallet access, order placement,
  forecasts, or position sizing;
- no private user-state values in public artifacts, logs, issues, PRs, or docs.

The resident Monitor service is one of exactly two supported resident Halpha
process roles: `core` and `monitor`. It is explicit, unique within one runtime
root, and managed through the shared lifecycle contract in
`docs/dashboard-contracts.md` and `docs/artifact-governance.md`.

## Responsibilities

Monitor responsibility:

- check Core health from local runtime state;
- start or retry Core when lifecycle state requires it;
- record resident Monitor heartbeat and terminal lifecycle state;
- persist bounded health, warning, and error state in `.halpha/state.sqlite`;
- keep running through recoverable Core health/start failures with bounded
  retry backoff.

Core and Live responsibility:

- claim due daily report schedule occurrences;
- create visible command jobs for scheduled or trigger-created runs;
- run source refresh, data collection, trigger evaluation, report dispatch, and
  product pipeline work;
- expose read models for Live state, trigger decisions, report artifacts, and
  command jobs.

The resident Monitor must not be owned by Dashboard UI, a schedule process, a
hidden supervisor, a broker, a worker pool, or another resident Halpha process.

## Configuration

The primary `monitor` config section supports these fields:

| Field | Default | Contract |
| --- | --- | --- |
| `enabled` | `false` | Local Monitor service feature gate. It does not start a hidden process by itself. |
| `interval_seconds` | `300` | Positive integer delay between resident Core-health checks. |
| `failure_backoff_max_seconds` | `3600` | Positive integer cap for resident Monitor retry backoff after recoverable Core health/start failures. |
| `output_dir` | `runs/monitor` | Local legacy or diagnostic monitor artifact directory when such artifacts are explicitly produced. |

Relative `output_dir` values resolve from the current working directory, not
from the config file location.

These legacy monitor-cycle keys are not part of the primary user-facing
configuration and must not appear in primary config examples:

- `max_cycles`;
- `cooldown_seconds`;
- `source_cadence_seconds`;
- `target_stage`;
- `no_codex`.

They may still appear in historical state, legacy migration tests, or internal
diagnostic contracts. When surfaced to users, label them as legacy or
diagnostic state, not as current Monitor ownership of source refresh, pipeline
stages, or report scheduling.

## Commands

Current resident-service commands:

```bash
python -m halpha monitor start --config config.example.yaml
python -m halpha monitor status --config config.example.yaml
python -m halpha monitor stop --config config.example.yaml
python -m halpha monitor restart --config config.example.yaml
```

Current read-only inspection command:

```bash
python -m halpha monitor inspect --config config.example.yaml
```

`monitor inspect` reads local Monitor health state and lifecycle refs only from
`.halpha/state.sqlite`. It must not collect network data, run processors, run
pipeline stages, invoke Codex CLI, repair archives, export raw alert records,
deliver notifications, trade, or access accounts.

There is no current user-facing `monitor run` workflow. Mutating product work
must use Core command jobs or explicit product commands such as
`python -m halpha run`.

## State

The authoritative local Monitor health state path is:

```text
.halpha/state.sqlite
```

The Monitor read model may include:

- resident Monitor service status;
- Core service status and heartbeat;
- latest Monitor heartbeat and terminal lifecycle state;
- bounded warning and error summaries;
- retry or backoff state needed to explain current health.

Missing or stale state must be surfaced as unavailable, stale, degraded, or
failed. The Monitor read model must not silently delete state-store records or
report missing evidence as healthy.

## Legacy Diagnostic State

Earlier Halpha versions exposed monitor-cycle reassessment paths that wrote
cycle manifests and alert archive state. Current primary Monitor behavior no
longer owns that workflow. Existing legacy artifacts and state tables remain
inspectable for migration, regression tests, and bounded diagnostics.

Legacy file paths include:

```text
runs/monitor/cycles/<cycle_id>/monitor_cycle_manifest.json
runs/monitor/alert_archive.jsonl
runs/monitor/alert_cooldown_state.json
runs/monitor/alert_archive_state.json
runs/monitor/monitor_health_state.json
```

Only explicit legacy migration or diagnostic code may read these files for
import or compatibility checks. Normal Monitor service and inspection paths
must not use them as fallback authorities for current health.

Legacy cycle manifests and alert archives must remain bounded and
source-aware. They must not embed full raw streams, full reusable stores, full
Codex context, raw user-state files, private notes, account identifiers,
holdings, balances, allocations, position sizes, private endpoints, or
unbounded evidence text.

## Codex Boundary

Monitor artifacts are local operational state. They are not Codex input by
default. Codex may explain Monitor evidence only when an explicit report path
includes bounded Monitor material. Codex must not generate alert priority,
duplicate decisions, cooldown decisions, forecasts, trading advice, position
sizing, or account actions.

## Validation

Monitor validation should use the narrowest command that proves the changed
behavior:

```bash
python -m pytest
python -m halpha monitor status --config config.example.yaml
python -m halpha monitor start --config config.example.yaml
python -m halpha monitor stop --config config.example.yaml
python -m halpha monitor inspect --config config.example.yaml
```

Use `python -m halpha run --config config.example.yaml --no-codex` or a
command-job path when validating product pipeline work. Full product validation
with Codex is required only when a change alters Codex context, report
generation, or final report content.
