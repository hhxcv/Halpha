# Product Stability Contracts

This document defines Halpha's local product-stability contract. It is a
durable contract for validation, run health, local backup boundaries, recovery
inspection, and operational acceptance. It is not a milestone plan.

## Implementation Status

- Product-stability contracts are defined here.
- `analysis/product_contract_validation.json` is planned for M19 and is not
  implemented yet.
- A read-only `validate` command is planned for M19 and is not implemented yet.
- Data inspection and workbench surfacing for product validation are planned
  for M19 and are not implemented yet.
- Existing validation paths remain `python -m pytest`, `python -m halpha run`,
  `python -m halpha data inspect`, `python -m halpha monitor inspect`, and
  `python -m halpha workbench inspect`.

## Related Docs

- `docs/artifact-governance.md`: artifact layers and Codex input policy.
- `docs/research-data-contracts.md`: reusable local stores and run index.
- `docs/delivery-workbench-contracts.md`: local delivery and workbench output.
- `docs/monitoring-contracts.md`: monitor cycle and alert archive state.
- `docs/strategy-lifecycle-contracts.md`: strategy lifecycle state and
  downstream boundaries.

## Product-Stability Goal

M19 stabilization should make the local product answer three questions quickly:

- Did the run produce the implemented artifacts it claims to have produced?
- Are missing, failed, skipped, degraded, stale, partial, over-budget, or
  not-run states explicit and actionable?
- What should be backed up, restored, inspected, or rerun without exposing
  local private values?

Stability validation must be deterministic. Codex or another LLM must not
create validation results, run health, backup decisions, recovery decisions,
contract pass/fail states, forecasts, or trading advice.

## Pipeline Position

Planned product validation sits after implemented product artifacts exist:

```text
collectors, shared stores, analysis stages, Codex context, report generation
-> run manifest
-> product contract validation
-> data inspection and workbench visibility
```

Validation is an audit and operational layer. It must not become an upstream
source for strategy gates, risk assessment, intelligence fusion, decisions,
alert priorities, personalized constraints, lifecycle state, Codex prompts, or
trading actions.

## analysis/product_contract_validation.json

Planned artifact path:

```text
analysis/product_contract_validation.json
```

Purpose:

- summarize product run health against implemented contracts;
- validate recorded artifact refs without embedding raw records;
- preserve source refs and actionable diagnostics for local acceptance;
- make no-Codex and full-Codex product runs auditable through one bounded
  artifact.

Planned top-level shape:

```json
{
  "schema_version": 1,
  "artifact_type": "product_contract_validation",
  "run_id": "20260620T000000Z",
  "created_at": "2026-06-20T00:00:00Z",
  "status": "ok|warning|degraded|failed|skipped",
  "mode": "product_run|read_only",
  "counts": {
    "checks": 0,
    "ok": 0,
    "warning": 0,
    "degraded": 0,
    "failed": 0,
    "skipped": 0,
    "errors": 0,
    "warnings": 0
  },
  "checks": [],
  "source_artifacts": [],
  "omitted": {
    "raw_artifact_contents_embedded": false,
    "full_run_manifest_embedded": false,
    "raw_local_user_state_embedded": false
  },
  "privacy_boundary": {
    "local_config_values_embedded": false,
    "machine_local_paths_embedded": false,
    "credentials_embedded": false
  },
  "codex_boundary": {
    "codex_generated_validation": false,
    "codex_input_by_default": false
  },
  "warnings": [],
  "errors": []
}
```

Planned check record shape:

```json
{
  "check_id": "artifact_ref:analysis/risk_assessment.json",
  "category": "manifest|artifact|stage|codex_input|report|workbench|privacy|backup_boundary",
  "status": "ok|warning|degraded|failed|skipped",
  "severity": "info|warning|error",
  "message": "bounded actionable diagnostic",
  "source_artifacts": ["run_manifest.json"],
  "expected": "bounded expected state",
  "observed": "bounded observed state",
  "recovery_hint": "bounded local next step"
}
```

Validation records must not include full raw artifacts, full intermediate JSON,
full reusable histories, full run manifests, full workbench summaries, local
config contents, proxy values, credentials, account identifiers, private user
notes, or exact private holdings.

## Planned Validation Checks

Manifest checks:

- `run_manifest.json` exists, is a JSON object, and records `run_id`, `status`,
  `stage_order`, `stages`, `artifacts`, `counts`, `warnings`, and `errors`
  where applicable.
- Stage records use explicit status values and preserve failure reasons.
- Failed, skipped, not-run, degraded, stale, partial, and warning states are
  visible instead of treated as success.

Artifact checks:

- Each artifact ref recorded in the manifest points to an existing file unless
  its producer was skipped, not run, or not applicable.
- JSON artifacts are JSON objects.
- JSON artifact `artifact_type` matches the implemented artifact contract when
  the type is known.
- Markdown material artifacts exist when their manifest refs claim they exist.
- Count fields are bounded aggregate metadata, not raw record dumps.

Codex and report checks:

- No-Codex runs may omit `report/report.md`, but must record the Codex skip
  state explicitly.
- Completed Codex runs should record a report artifact and the report file
  should exist.
- Codex input metadata should record included material refs, character counts,
  budget status, and over-budget warnings.
- Codex must not be treated as the source of deterministic validation results.

Workbench checks:

- Workbench outputs remain delivery artifacts and are not upstream decision
  inputs.
- Workbench summaries and indexes are not embedded into Codex input by default.

Privacy checks:

- Validation output must use repo-relative refs where practical.
- Validation output must not print local config values, proxy values,
  credentials, tokens, cookies, machine-local paths, user-state private notes,
  account identifiers, exact balances, exact holdings, allocations, or position
  sizes.

## Planned Read-Only Validate Command

Planned command:

```bash
python -m halpha validate --config config.example.yaml
python -m halpha validate --config config.example.yaml --run-dir runs/<run_id>
```

Planned behavior:

- select the latest indexed run or the explicit run directory;
- evaluate product contract validation in read-only mode;
- print bounded status, counts, failed check names, source refs, and recovery
  hints;
- exit nonzero only when validation itself fails or the inspected run has
  failed contract checks that should block acceptance.

The command must not:

- collect network data;
- run processors;
- run pipeline stages;
- run Codex CLI;
- generate reports;
- mutate decisions, alerts, lifecycle state, workbench outputs, stores, or run
  archives;
- repair files;
- dump raw records or local private values.

## Backup And Restore Boundaries

Local backup scope should be explicit and user-controlled.

Recommended backup groups:

- `runs/`: product run archives, reports, Codex context, workbench outputs, and
  monitor state.
- `data/`: reusable local stores, run index, local history state, and research
  data metadata.
- machine-local config files: local validation config, local user-state files,
  and private policy files. These must remain outside public commits and public
  docs.

Restore is a local file operation, not an implemented Halpha command. After
restoring files, users or AI agents should validate with read-only commands
such as data inspection, monitor inspection, workbench inspection, and planned
product validation. Restored local config or user-state files must not be
printed or committed.

Backup and restore are out of scope for automated cloud sync, hosted storage,
database services, account integrations, exchange connections, or trading
execution.

## Operational Acceptance

M19 validation should use the narrowest relevant check first:

- automated tests for changed behavior;
- focused integration tests for touched modules;
- no-Codex product acceptance when report generation is not under review;
- full Codex product acceptance when Codex context or final report behavior is
  changed;
- read-only data inspection for local store and artifact visibility;
- read-only monitor inspection for local monitor health;
- workbench build and inspect for local delivery visibility;
- planned read-only product validation for contract health.

`config.example.yaml` remains public demonstration config. Real local
acceptance should use machine-local config files and must not print or commit
local private values.
