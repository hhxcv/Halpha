# Monitoring Contracts

This document defines Halpha's local monitoring contract. It is a durable
implementation contract, not a milestone plan.

## Purpose

The monitor path turns repeated manual research runs into explicit local cycles.
It must remain observable, bounded, and local-first:

- no hidden background service;
- no hosted scheduler or dashboard assumption;
- no trading execution, account access, position sizing, or order placement;
- no Codex execution unless a command explicitly asks for a full report path;
- no private user-state values in public artifacts, logs, issues, PRs, or docs.

The current command surface only validates monitor configuration and help text.
Cycle execution, alert archive writes, duplicate suppression, cooldown, and
health inspection are defined here as contracts and are implemented by later
monitor runtime changes.

## Configuration

The optional `monitor` config section supports these fields:

| Field | Default | Contract |
| --- | --- | --- |
| `enabled` | `false` | Local monitor feature gate. It does not start a hidden process by itself. |
| `interval_seconds` | `300` | Positive integer interval between finite-loop cycles. |
| `max_cycles` | `1` | Positive integer cycle limit. Monitor loops must stop after this limit. |
| `cooldown_seconds` | `3600` | Positive integer duplicate-alert cooldown window. |
| `output_dir` | `runs/monitor` | Local monitor artifact directory. |
| `target_stage` | `build_personalized_risk_material` | Pipeline stage boundary for default monitor reassessment. |
| `no_codex` | `true` | Default monitor runs stop before Codex report generation. |

Current implemented validation command:

```bash
python -m halpha monitor run --config config.example.yaml --dry-run
```

This command prints the effective monitor config and records
`cycle_execution: not_run`. It must not collect data, run pipeline stages, write
monitor artifacts, or invoke Codex CLI.

## Cycle Manifest

Monitor runtime writes one manifest per cycle under the configured monitor
output directory. The intended path shape is:

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
- `run_dir`: linked product run directory when a run was created.
- `run_manifest`: linked product run manifest path when available.
- `alert_decisions`: linked alert decision artifact refs when available.
- `emitted_alerts`, `suppressed_alerts`: counts and archive refs.
- `warnings`, `errors`: bounded actionable strings.

The cycle manifest stores references and counts. It must not embed full raw
streams, full reusable stores, full Codex context, raw user-state files, or
private local values.

## Alert Archive

The local alert archive records emitted and suppressed alert decisions. The
intended local state paths are:

```text
runs/monitor/alert_archive.jsonl
runs/monitor/alert_cooldown_state.json
```

Each alert archive record must include:

- `record_id`: deterministic record id.
- `alert_key`: deterministic duplicate key.
- `cycle_id`: producing monitor cycle.
- `decision_id`: source alert decision id when available.
- `symbol`, `timeframe`, `priority`, `attention_decision`.
- `status`: `emitted` or `suppressed`.
- `suppression_reasons`: reason codes for suppressed records.
- `cooldown_until`: UTC timestamp when cooldown applies.
- `source_artifacts`: bounded path refs to source evidence.
- `personalized_context_present`: boolean only, not private user-state values.
- `created_at`: UTC timestamp.

Duplicate keys must be deterministic and source-aware. Repeated equivalent
alerts during cooldown are archived as suppressed records instead of emitted
again.

## Health Summary

Monitor inspection reads local monitor state and reports bounded health
information:

- latest cycle id, status, and linked run refs;
- recent failure count;
- emitted, suppressed, duplicate, and cooldown counts;
- latest warning and error summaries;
- archive path refs;
- data availability status.

Inspection is read-only. It must not collect network data, run processors, run
pipeline stages, invoke Codex CLI, repair archives, or dump raw alert records.

## Codex Boundary

Monitor artifacts are local operational state. They are not Codex input by
default. Codex may explain monitor evidence only when a future explicit report
path includes bounded monitor material. Codex must not generate alert priority,
duplicate decisions, cooldown decisions, forecasts, trading advice, position
sizing, or account actions.
