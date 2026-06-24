# Research Data Contracts

This document defines Halpha's durable local research data contracts. It is a
contract for reusable local evidence, run indexes, data-quality summaries, and
their downstream consumers. It is not a milestone plan.

## Related Docs

- `README.md`: project overview, implemented commands, and validation.
- `AGENTS.md`: AI-agent rules, artifact expectations, and validation rules.
- `docs/artifact-governance.md`: runtime state authority, artifact layers,
  Codex input policy, and documentation index.
- `docs/quant-contracts.md`: market data, strategy, evaluation, signal, and
  strategy-material contracts.
- `docs/derivatives-market-contracts.md`: derivatives and
  market-structure data, context, material, and Codex-boundary contracts.
- `docs/macro-calendar-contracts.md`: macro and scheduled-event data, context,
  material, and Codex-boundary contracts.
- `docs/event-intelligence-contracts.md`: text event, NLP evidence, topic,
  event signal, confluence, assessment, and event-material contracts.
- `docs/decision-intelligence-contracts.md`: regime, risk, recommendation,
  watch trigger, delta, alert decision, and decision-material contracts.
- `docs/outcome-tracking-contracts.md`: outcome target, evaluation,
  history, material, and Codex-boundary contracts.

## Contract Status

Shared OHLCV history, research catalog, run index, text event history,
data-quality, and outcome history contracts are implemented. Planned contracts
must stay marked until their producers are added.

| Contract | Status | Producer | Consumer |
| --- | --- | --- | --- |
| Shared OHLCV history | Implemented | OHLCV sync stage | market views, strategy evaluation, standalone backtest, experiments |
| Research data catalog | Implemented | local data catalog writer | manifest, data inspection, data quality summary |
| Current local run index | Implemented | pipeline completion and stage rerun paths | previous-run lookup, data inspection, audit |
| Text event history | Implemented | text event history writer | data quality summary, future event/outcome workflows |
| Data quality summary | Implemented | data quality stage | research context, Codex context, report, manifest |
| Data quality material | Implemented | analysis material stage | research context, Codex context, report |
| Outcome history | Implemented | outcome history writer | later runs, data inspection, outcome material |
| Derivatives market history | Initial adoption | derivatives history writer | derivatives views, data inspection, data quality |
| Macro calendar history | Initial adoption | macro calendar history writer | macro calendar views, data inspection, data quality |

## Layer Boundary

Reusable local history is input data. It is not AI context.

Halpha keeps these layers separate:

| Layer | Role | Codex input rule |
| --- | --- | --- |
| Raw run artifacts | Preserve current-run public observations. | Not embedded by default. |
| Reusable local history | Preserve cross-run market and event evidence. | Not embedded. Summarized by current-run views or quality material. |
| Current-run views | Select bounded windows for current analysis. | Referenced or summarized through report-facing material. |
| Analysis artifacts | Record deterministic evidence, scores, warnings, and decisions. | Not embedded wholesale. |
| Report-facing material | Convert selected evidence into bounded Markdown. | Eligible for research context. |
| Research and Codex context | Carry bounded material plus generation constraints. | Sent to Codex CLI when full report generation runs. |
| Final report | Generated Simplified Chinese Markdown plus deterministic tables. | Output only. |

## Path Rules

Artifacts and stores must use stable references:

- prefer repo-relative paths for files under the repository;
- prefer config-relative paths when a configured data root sits outside the run
  directory;
- do not write machine-local absolute paths into public docs, examples, PRs, or
  issue text;
- do not print proxy URLs, hostnames, ports, credentials, tokens, cookies,
  account IDs, or private endpoints;
- keep raw artifacts and reusable stores inspectable on disk.

## Shared OHLCV History

Implemented reusable market history:

- storage root: `data/market/ohlcv/`
- schema metadata: `data/market/metadata/ohlcv_schema.json`
- sync state: `data/market/metadata/ohlcv_sync_state.json`

Partition fields:

- `source`
- `symbol`
- `timeframe`
- `year`
- `month`

Required record identity:

- `source`
- `symbol`
- `timeframe`
- `timestamp`

Required behavior:

- store finalized OHLCV candles only;
- keep shared history outside per-run report directories;
- expose current-run windows through `raw/market_data_views.json`;
- report stored ranges and update status through metadata;
- reject or warn on conflicting duplicate candles instead of silently replacing
  source evidence;
- avoid embedding full OHLCV history into Codex input.

## Research Data Catalog

Target catalog path:

- `data/research/metadata/research_data_catalog.json`

Purpose:

- make implemented reusable stores discoverable;
- describe schemas, partitions, unique keys, status, warnings, and consumers;
- provide a compact manifest-facing summary without scanning every store.

Required top-level fields:

- `schema_version`
- `generated_at`
- `status`
- `stores`
- `counts`
- `warnings`
- `errors`

Required store fields:

- `name`
- `kind`
- `status`
- `format`
- `storage_path`
- `schema_path`
- `state_path`
- `schema_version`
- `partition_fields`
- `unique_key_fields`
- `source_fields`
- `latest_update_at`
- `record_count`
- `warning_count`
- `consumers`
- `source_artifacts`
- `warnings`

Status values:

- `ok`
- `warning`
- `degraded`
- `skipped`
- `failed`

Rules:

- include only implemented stores;
- preserve deterministic store ordering by `name`;
- use relative path references;
- summarize large stores by metadata, not row dumps;
- record missing optional stores as `skipped`, not fabricated data.

## Local Run Index

Current implemented index path:

- `.halpha/state.sqlite`

Legacy index path:

- `data/research/index.sqlite`

Purpose:

- preserve compact run audit metadata;
- make latest successful runs discoverable without scanning every run directory;
- keep full artifacts in per-run files rather than SQLite blobs.

Authority boundary:

- `run_manifest.json` remains the authoritative lifecycle record for a
  completed run.
- Per-run artifacts remain the authoritative research evidence.
- The index stores references and searchable metadata only.
- `run_latest` is now a derived SQLite view, not a mutable pointer table.
- The unified runtime state store at `.halpha/state.sqlite` owns the current
  mutable run and artifact index projection.
- Query helpers derive latest run, latest successful run, latest report-bearing
  run, and latest previous successful run from indexed records. A report-bearing
  selection requires the recorded report artifact to exist in the local project
  boundary.
- `data/research/index.sqlite` is legacy storage. It must not be written by new
  run completions or stage reruns outside explicit legacy migration or cleanup
  work.

Required tables:

- `runs`
- `run_stages`
- `run_artifacts`
- `run_latest` view

Required `runs` fields:

- `run_id`
- `run_dir`
- `config_path`
- `started_at`
- `finished_at`
- `status`
- `failed_stage`
- `codex_status`
- `warning_count`
- `error_count`
- `manifest_path`

Required `run_stages` fields:

- `run_id`
- `stage_name`
- `status`
- `started_at`
- `finished_at`
- `warning_count`
- `error_count`

Required `run_artifacts` fields:

- `run_id`
- `artifact_key`
- `path`
- `kind`

Rules:

- use standard library SQLite unless a later requirement proves insufficient;
- store metadata and relative references only;
- never store full raw artifacts, full Markdown reports, Parquet rows, or Codex
  prompts in the index;
- make re-indexing the same run idempotent;
- update partial and failed runs with explicit status.
- make any replacement or migration explicit; do not dual-write, auto-migrate,
  or retain fallback authorities without a dedicated migration contract.

## Text Event History

Target storage root:

- `data/research/text_events/`

Target state metadata:

- `data/research/metadata/text_event_history_state.json`

Purpose:

- preserve reusable normalized public text events across runs;
- trace repeated public items without duplicating every observation in Codex
  context;
- support future outcome, retrieval, and monitoring workflows.

Required history fields:

- `stable_event_key`
- `raw_item_id`
- `source`
- `source_type`
- `url`
- `canonical_url`
- `title`
- `published_at`
- `collected_at`
- `normalized_text`
- `content_hash`
- `origin_run_ids`
- `first_seen_run_id`
- `last_seen_run_id`
- `first_seen_at`
- `last_seen_at`
- `duplicate_group_key`
- `status`
- `warnings`
- `source_artifacts`

Required behavior:

- append current-run normalized event records after validation;
- deduplicate by deterministic event identity;
- preserve all run ids that observed a repeated item;
- warn on conflicting duplicates instead of silently overwriting;
- keep full history out of Codex input.

## Data Quality Summary

Target current-run artifact:

- `analysis/data_quality_summary.json`
- `analysis/data_quality_material.md`

Purpose:

- provide one deterministic quality view for current-run evidence;
- let downstream stages and reports distinguish reliable, degraded, skipped, and
  failed inputs without inspecting every raw artifact.
- provide bounded AI-readable quality material for Codex without embedding full
  local stores, raw archives, SQLite tables, Parquet data, or complete quality
  JSON.

Required top-level fields:

- `schema_version`
- `created_at`
- `status`
- `checks`
- `counts`
- `warnings`
- `errors`
- `source_artifacts`

Required check fields:

- `name`
- `status`
- `scope`
- `summary`
- `warning_count`
- `error_count`
- `source_artifacts`
- `details`

Required check coverage:

- raw market artifact presence and schema;
- raw text artifact presence and schema;
- OHLCV store metadata and current-run view coverage;
- derivatives market raw, history, current-run view, and context/material coverage;
- macro/calendar raw, history, current-run view, context, and material coverage;
- timestamp parseability and future timestamp warnings;
- stale source observations where timestamps are available;
- duplicate or conflicting text records where detectable;
- local catalog status when implemented;
- run index status when implemented;
- text event history status when implemented.

Rules:

- use `ok`, `warning`, `degraded`, `skipped`, or `failed`;
- do not repair or rewrite raw evidence;
- make warnings visible but avoid blocking every degraded run by default;
- summarize quality in Codex context only through bounded material or concise
  research-context sections.
- expose Codex-facing quality through `analysis/data_quality_material.md`;
- allow Codex to explain Halpha-generated quality status, not create or revise
  validation results.

## Manifest Rules

When implemented, product runs should record:

- catalog artifact path and store counts;
- run index write status;
- text event history write status and duplicate counts;
- data quality summary path, status, warning count, and error count;
- Codex input budget metadata for any data-quality material.

`run_manifest.json` remains the per-run lifecycle record. Reusable stores and
indexes do not replace it.

After the runtime-state migration, run manifests remain immutable product
records and the runtime state store remains an operational index. Validation,
dashboard, workbench, and inspection paths may query the runtime index for
discovery, but source refs must still point back to the authoritative run
manifest and artifacts.

## Outcome History

Outcome history contracts live in `docs/outcome-tracking-contracts.md`.

Outcome history is reusable local research data. It should stay outside per-run
report directories, preserve references to source runs and artifacts, and avoid
embedding full history into Codex input.

## Derivatives Market History

Derivatives market history contracts live in
`docs/derivatives-market-contracts.md`.

Reusable derivatives history is local market context data. It should
stay outside per-run report directories, preserve source endpoint and timestamp
references, make unavailable data classes explicit, and avoid embedding full
history into Codex input.

## Macro Calendar History

Macro calendar history contracts live in `docs/macro-calendar-contracts.md`.

Reusable macro/calendar history is local scheduled-event input data. It should
stay outside per-run report directories, preserve source endpoint and source
artifact references, make stale or unavailable calendar states explicit, expose
bounded current-run views through `raw/macro_calendar_views.json`, and avoid
embedding full history into Codex input.

## On-Chain Flow History

On-chain flow history contracts live in `docs/onchain-flow-contracts.md`.

Reusable on-chain flow history is local liquidity and network-activity context
data. It should stay outside per-run report directories, preserve source
endpoint and source artifact references, make unavailable or stale data classes
explicit, expose bounded current-run views through `raw/onchain_flow_views.json`,
and avoid embedding full history into Codex input.

## Validation Rules

Automated validation should cover:

- deterministic ordering;
- relative path references;
- missing optional stores;
- malformed timestamps;
- duplicate and conflicting duplicate handling;
- schema drift;
- partial collection failure;
- manifest references;
- Codex input boundaries.

Real-source validation should use existing product commands and inspect the
generated artifacts. Full report validation sends generated local research
context to Codex CLI.
