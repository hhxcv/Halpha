# Delivery Workbench Contracts

This document defines Halpha's local delivery and workbench contract. It is a
durable implementation contract, not a milestone plan.

## Purpose

The dashboard is Halpha's primary local user entry point. The delivery
workbench is a local delivery snapshot and CLI inspection or recovery fallback
for current intelligence without changing the research pipeline:

- summarize existing deterministic artifacts;
- link to reports, source artifacts, monitor state, alerts, outcomes, and
  strategy state;
- show complete, partial, missing, stale, degraded, and failed states
  explicitly;
- avoid raw record dumps and duplicated full artifacts;
- remain local-first and inspectable;
- avoid replacing dashboard views;
- never become the source of decision, strategy, alert, risk, forecast, or
  trading logic.

Workbench outputs are delivery artifacts. They are not upstream evidence,
analysis inputs, Codex context, product state authority, primary UI, or
dashboard replacements.

## Output Layers

The workbench layer has three implemented output types:

| Output | Purpose | Consumer |
| --- | --- | --- |
| Workbench summary JSON | Machine-readable bounded summary of existing local artifacts. | CLI inspection, recovery checks, local index rendering, human audit. |
| Workbench Markdown index | Human-readable local index for reports and current state. | User and AI-agent local inspection fallback. |
| Workbench static HTML index | Browser-readable local index generated from the same summary. | User local inspection fallback. |

All workbench outputs must be reproducible from existing artifacts. They must
not trigger network collection, analysis stages, monitor cycles, Codex CLI, or
report generation by themselves.

Current implemented commands:

```bash
python -m halpha workbench build --config config.example.yaml
python -m halpha workbench build --config config.example.yaml --run-dir runs/<run_id>
python -m halpha workbench inspect --config config.example.yaml
```

`workbench build` writes:

```text
runs/workbench/latest/workbench_summary.json
runs/workbench/latest/index.md
runs/workbench/latest/index.html
```

`workbench inspect` is read-only and prints a bounded summary of the latest
workbench state.

## Summary JSON Contract

The workbench summary should record bounded references and status fields rather
than full source payloads.

Required top-level fields:

- `artifact_type`: stable type identifier.
- `generated_at`: UTC timestamp measured when the workbench artifact is built.
- `source_selection`: latest-run or explicit-run selection metadata.
- `latest_run`: bounded run id, status, manifest ref, and report ref when
  available.
- `decision_state`: bounded refs and short summaries from decision, risk, and
  watch-trigger artifacts.
- `alert_state`: bounded alert archive and alert-decision refs, counts, latest
  status, warnings, and errors.
- `monitor_state`: bounded monitor health and latest cycle refs when available.
- `outcome_state`: bounded outcome target, evaluation, and history-state refs
  when available.
- `strategy_state`: bounded strategy gate, strategy evaluation, experiment,
  strategy-lifecycle artifact status, lifecycle status counts, degradation
  counts, retirement counts, warnings, and errors when available.
- `product_validation_state`: bounded product contract validation status,
  check counts, failed/degraded/warning counts, and source refs when available.
- `data_quality_state`: bounded data-quality refs, quality level, warnings, and
  errors when available.
- `index_outputs`: generated Markdown or HTML index refs when available.
- `source_artifacts`: bounded grouped path refs to source artifacts.
- `omitted`: counts or reasons for omitted records, sections, or unavailable
  details.
- `warnings`: bounded actionable warning strings.
- `errors`: bounded actionable error strings.

Status values should distinguish:

- `available`;
- `partial`;
- `missing`;
- `stale`;
- `degraded`;
- `failed`;
- `skipped`;
- `not_applicable`.

Absent source evidence must not be represented as neutral evidence.

## Index Contract

Human-readable indexes should use the summary JSON as their source of truth.
They may display:

- latest report link and run status;
- decision, risk, and watch-trigger summaries;
- alert archive counts and latest alert status;
- monitor health status;
- outcome tracking status;
- strategy gate, experiment, and bounded strategy-lifecycle status;
- product contract validation status and bounded check counts;
- data-quality status;
- source artifact links;
- warnings, errors, and omitted-section counts.

Indexes must not display:

- raw full alert records;
- raw local user-state files;
- private notes;
- account identifiers;
- exact holdings, balances, allocations, or position sizes;
- credentials, tokens, cookies, private endpoints, proxy values, or machine-local
  privacy values;
- full reusable histories, full intermediate JSON evidence, SQLite contents,
  Parquet tables, or full run manifests by default.

## Source References

Workbench outputs should use repo-relative artifact refs whenever practical.
References should point to existing source artifacts rather than copying their
full contents into the delivery layer.

If a referenced artifact is missing or unreadable, the workbench output should
record the section as `missing`, `partial`, or `failed` with a bounded warning
or error.

## Codex Boundary

Workbench artifacts are delivery snapshots. They are not upstream evidence,
analysis inputs, dashboard replacements, or Codex input by default.

Codex may use bounded report-facing material such as decision, alert, strategy,
event, data-quality, and outcome material according to
`docs/artifact-governance.md`. Codex must not receive full workbench summaries
or generated indexes as raw context by default, and it must not generate
workbench state, decision state, alert priority, strategy status, forecasts, or
trading advice.

## Privacy Boundary

Workbench generation must preserve local privacy:

- do not print or persist local private config values;
- do not embed raw local user-state files;
- summarize personalized-risk presence and bounded public-facing state only;
- use counts for omitted private values;
- keep local path refs bounded to repo artifact refs where practical;
- never write credentials, tokens, cookies, account identifiers, private
  endpoints, proxy values, or machine-local privacy values.

## Validation

Workbench validation should prove:

- complete source artifacts produce a bounded summary and index;
- partial or missing artifacts produce explicit states and warnings;
- inspect commands are read-only;
- generated indexes are deterministic from the summary;
- output does not expose raw private user-state values;
- workbench artifacts are not admitted into Codex context by default;
- workbench artifacts remain delivery snapshots and CLI fallbacks, not the
  primary UI.

Current command validation:

```bash
python -m halpha workbench build --config config.example.yaml
python -m halpha workbench build --config config.example.yaml --run-dir runs/<run_id>
python -m halpha workbench inspect --config config.example.yaml
python -m halpha data inspect --config config.example.yaml
```

Full product validation with Codex is required only when a workbench change
alters Codex context, report generation, or final report content.
