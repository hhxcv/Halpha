# Monitoring Contracts

This document defines Halpha's local monitoring contract. It is a durable
implementation contract, not a milestone plan.

## Purpose

The monitor path turns repeated manual research runs into explicit local cycles.
It must remain observable, bounded, and local-first:

- no hidden or dashboard-owned background service;
- no hosted scheduler or dashboard assumption;
- no trading execution, account access, position sizing, or order placement;
- no Codex execution unless a command explicitly asks for a full report path;
- no private user-state values in public artifacts, logs, issues, PRs, or docs.

The current command surface validates monitor configuration, runs one bounded
local monitor cycle or finite diagnostic loop, starts one resident Monitor
service, writes immutable cycle manifests, persists alert archive, cooldown,
cycle, and service-health state in `.halpha/state.sqlite`, and exposes
read-only monitor health inspection.

The resident Monitor service is one of exactly three supported resident Halpha
process roles: `dashboard`, `monitor`, and `schedule`. It is explicit, unique
within one runtime root, and managed through the shared lifecycle contract in
`docs/dashboard-contracts.md` and `docs/artifact-governance.md`.

Target Monitor responsibility:

- remain the single continuous information-refresh and alert-reassessment
  service for one runtime root;
- keep running through ordinary source, network, and collection failures by
  recording warnings or errors and retrying on the next cadence;
- avoid Codex and report generation during resident cycles;
- temporarily run whole monitor cycles through the configured target stage until
  the source-cadence fast path replaces that bridge;
- update source groups by configured cadence and pass changed scope to
  downstream work after that planned behavior is implemented;
- never trade, access accounts, access wallets, place orders, or compute
  position sizing.

The resident Monitor must not be owned by Dashboard, Schedule, a hidden
supervisor, a broker, a worker pool, or a fourth resident Halpha process.

## Configuration

The optional `monitor` config section supports these fields:

| Field | Default | Contract |
| --- | --- | --- |
| `enabled` | `false` | Local monitor feature gate. It does not start a hidden process by itself. |
| `interval_seconds` | `300` | Positive integer interval between successful resident cycles and finite-loop diagnostic cycles. |
| `max_cycles` | `1` | Positive integer cycle limit for the diagnostic finite-loop command only. It is not a resident-service termination rule. |
| `failure_backoff_max_seconds` | `3600` | Positive integer cap for resident Monitor retry backoff after recoverable cycle failures. |
| `cooldown_seconds` | `3600` | Positive integer duplicate-alert cooldown window. |
| `output_dir` | `runs/monitor` | Local monitor artifact directory. |
| `target_stage` | `build_materials` | Pipeline stage boundary for default monitor reassessment. |
| `no_codex` | `true` | Default monitor runs stop before Codex report generation. |

Relative `output_dir` values resolve from the current working directory, not
from the config file location.

Current implemented validation command:

```bash
python -m halpha monitor run --config config.example.yaml --dry-run
```

This command prints the effective monitor config and records
`cycle_execution: not_run`. It must not collect data, run pipeline stages, write
monitor artifacts, or invoke Codex CLI.

Current implemented one-cycle command:

```bash
python -m halpha monitor run --config config.example.yaml --once
```

This command runs exactly one bounded cycle through the configured product
pipeline target stage and writes one monitor cycle manifest. The default
`no_codex: true` setting keeps the monitor path before Codex report generation.
When generated `analysis/alert_decisions.json` exists, the cycle commits alert
archive records, suppression results, cooldown updates, and the monitor cycle
index to `.halpha/state.sqlite`.

Current implemented resident-service commands:

```bash
python -m halpha monitor start --config config.example.yaml
python -m halpha monitor status --config config.example.yaml
python -m halpha monitor stop --config config.example.yaml
python -m halpha monitor restart --config config.example.yaml
```

The resident Monitor service is unique per runtime root through the shared
service lifecycle controller. It runs no-Codex monitor cycles continuously
until explicit stop, records heartbeat and terminal lifecycle state, persists
current service health in `.halpha/state.sqlite`, and retries recoverable cycle
failures with bounded exponential backoff.

Current implemented diagnostic finite-loop command:

```bash
python -m halpha monitor run --config config.example.yaml --max-cycles 3 --interval-seconds 300
```

This command runs a finite local loop. It stops after the requested maximum
cycle count or after the first failed cycle. It is a diagnostic path, not the
resident Monitor service, daemon, cron job, scheduler, or notification worker.

Current implemented read-only health command:

```bash
python -m halpha monitor inspect --config config.example.yaml
```

This command reads local monitor state, resident service health, and cycle
manifest refs only from `.halpha/state.sqlite`. It must not collect network
data, run processors, run pipeline stages, invoke Codex CLI, repair archives,
export raw alert records, deliver notifications, trade, or access accounts.

## Cycle Manifest

Monitor runtime writes one manifest per cycle under the configured monitor
output directory. The path shape is:

```text
runs/monitor/cycles/<cycle_id>/monitor_cycle_manifest.json
```

Required manifest fields:

- `artifact_type`: `monitor_cycle_manifest`.
- `cycle_id`: deterministic local cycle identifier.
- `status`: `succeeded`, `failed`, or `partial`.
- `started_at`, `finished_at`: UTC timestamps measured around actual work.
- `config_ref`: local config path reference, never embedded secrets.
- `target_stage`: requested pipeline stage boundary.
- `no_codex`: boolean Codex boundary state.
- `exit_code`: terminal monitor command exit code.
- `run_id`: linked product run id when a run was created.
- `run_dir`: linked product run directory when a run was created.
- `run_manifest`: linked product run manifest path when available.
- `product_run`: bounded linked product-run summary.
- `source_artifacts`: linked product-run artifact refs when available.
- `warnings`, `errors`: bounded actionable strings.

The cycle manifest stores references and counts. It must not embed full raw
streams, full reusable stores, full Codex context, raw user-state files, or
private local values.

## Alert Archive

The local alert archive records emitted and suppressed alert decisions. The
authoritative mutable state path is:

```text
.halpha/state.sqlite
```

Legacy no-new-write state files are:

```text
runs/monitor/alert_archive.jsonl
runs/monitor/alert_cooldown_state.json
runs/monitor/alert_archive_state.json
```

Each alert archive record must include:

- `artifact_type`: `monitor_alert_archive_record`.
- `record_id`: deterministic record id.
- `alert_key`: deterministic duplicate key.
- `cycle_id`: producing monitor cycle.
- `decision_id`: source alert decision id when available.
- `symbol`, `timeframe`, `priority`, `attention_decision`.
- `status`: `emitted`, `suppressed_duplicate`, `suppressed_cooldown`,
  `suppressed_no_alert`, or `skipped`.
- `suppression_reasons`: reason codes for suppressed records.
- `cooldown_until`: UTC timestamp when cooldown applies.
- `source_artifacts`: bounded path refs to source evidence.
- `personalized_context`: boolean presence plus bounded constraint id, state,
  and action only when present.
- `source_run`: linked product run id and run manifest ref.
- `created_at`: UTC timestamp.

Duplicate keys must be deterministic and source-aware. Repeated equivalent
alerts during cooldown are archived as suppressed records instead of emitted
again.

Cycle index, alert records, suppression status, and cooldown updates must be
committed transactionally for one terminal monitor cycle. Retrying persistence
for the same cycle id must not duplicate alert records or extend an existing
cooldown merely because the write was retried.

The archive must not store raw user-state files, private notes, account
identifiers, holdings, balances, allocations, position sizes, private endpoints,
or personalized evidence text.

## Health Summary

Monitor inspection reads local monitor state and reports bounded health
information:

- latest cycle id, status, and linked run refs;
- recent failure count;
- emitted, suppressed, duplicate, and cooldown counts;
- latest warning and error summaries;
- state-store and evidence refs.

Inspection is read-only. It must not collect network data, run processors, run
pipeline stages, invoke Codex CLI, repair archives, or dump raw alert records.

The local health state path is:

```text
.halpha/state.sqlite
```

It records monitor-cycle indexes, bounded alert archive records, cooldown
records, warning and error counts, and latest finite-loop metadata. It must not
store raw user-state files, private notes, account identifiers, holdings,
balances, allocations, position sizes, private endpoints, or unbounded evidence
text.

Missing cycle manifests or linked run artifacts referenced by the state store
must be surfaced as stale or degraded diagnostics. The monitor read model must
not silently delete the database record or report the missing evidence as
healthy.

## Codex Boundary

Monitor artifacts are local operational state. They are not Codex input by
default. Codex may explain monitor evidence only when a future explicit report
path includes bounded monitor material. Codex must not generate alert priority,
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
python -m halpha monitor run --config config.example.yaml --dry-run
python -m halpha monitor run --config config.example.yaml --once
python -m halpha monitor run --config config.example.yaml --max-cycles <n> --interval-seconds <seconds>
python -m halpha monitor inspect --config config.example.yaml
```

`--dry-run` validates configuration only. `--once` validates one bounded cycle,
cycle manifest, state-store alert archive records, cooldown state, and health
state. `--max-cycles` validates finite loop behavior. `monitor inspect`
validates read-only aggregate health output.

Full product validation with Codex is required only when a monitor change alters
Codex context, report generation, or final report content. The implemented
monitor artifacts are not Codex input by default.
