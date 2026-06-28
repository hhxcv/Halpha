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
| Research data catalog | Implemented | local data catalog writer | manifest, data inspection, Dashboard data-store view, data quality summary |
| Current local run index | Implemented | pipeline completion and stage rerun paths | previous-run lookup, data inspection, audit |
| Text event history | Implemented | text event history writer | data quality summary, future event/outcome workflows |
| Data quality summary | Implemented | data quality stage | research context, Codex context, report, manifest |
| Data quality material | Implemented | analysis material stage | research context, Codex context, report |
| Outcome history | Implemented | outcome history writer | later runs, data inspection, outcome material |
| Derivatives market history | Initial adoption | derivatives history writer | derivatives views, data inspection, data quality |
| Market anomaly history | Initial adoption | market anomaly history writer | Dashboard data viewer, data inspection, future monitor/event workflows |
| Macro calendar history | Initial adoption | macro calendar history writer | macro calendar views, data inspection, data quality |
| On-chain flow history | Initial adoption | on-chain flow history writer | on-chain views, data inspection, data quality |
| Collection coverage state | Initial adoption | OHLCV and text-event data collect, coverage state writer | collection planner, data inspection, Dashboard data viewer, data quality |
| Collection plan | Implemented | coverage-aware planner | CLI dry-run, Dashboard dry-run, collection apply paths |
| Shared data query | Initial adoption | OHLCV and event-like query adapters | benchmark backtests; CLI export; Dashboard previews and exports planned |
| Bounded data export | Initial adoption | shared query/export service and CLI export command | external quant tools; Dashboard download planned |

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

- prefer runtime-root-relative paths for files under the runtime root;
- resolve relative configured reusable data roots from the runtime root, not
  from the config file location;
- preserve absolute configured data roots as explicit local overrides while
  exposing them in public-facing metadata only through safe external refs;
- do not write machine-local absolute paths into public docs, examples, PRs, or
  issue text;
- do not print proxy URLs, hostnames, ports, credentials, tokens, cookies,
  account IDs, or private endpoints;
- keep raw artifacts and reusable stores inspectable on disk.

## Collection Coverage State

Collection coverage state records whether a reusable data interval was
collected, empty, partial, failed, stale, or not collected. It is metadata about
collection coverage, not the raw records themselves.

Target state path:

- `data/research/metadata/collection_coverage_state.json`

Coverage applies to implemented reusable stores:

- OHLCV history;
- text-event history;
- derivatives market history;
- market anomaly history;
- macro/calendar history;
- on-chain flow history.

Required coverage fields:

- `schema_version`
- `artifact_type`
- `generated_at` or `updated_at`
- `data_type`
- `source`
- `identity`
- `range_start`
- `range_end`
- `status`
- `record_count`
- `attempt_count`
- `latest_attempt_at`
- `latest_success_at`
- `coverage_method`
- `source_artifacts`
- `warnings`
- `errors`

Coverage status values:

- `collected`: source collection succeeded and reusable records exist for the
  interval.
- `no_data`: source collection succeeded and returned no records for the
  interval.
- `partial`: only part of the requested interval, source set, page set, or data
  class was collected.
- `failed`: collection was attempted and failed.
- `not_collected`: no successful or failed attempt is known for the interval.
- `stale`: coverage exists but does not satisfy the consumer freshness rule.
- `warning`: coverage is present with non-fatal completeness, timestamp, or
  schema warnings.
- `error`: coverage metadata is malformed or cannot be trusted.

Rules:

- `no_data` must come from a successful source response. It must not be inferred
  from missing records or missing coverage.
- `not_collected`, `failed`, `partial`, and unknown coverage must remain
  visible to data inspection, Dashboard views, and query diagnostics.
- Coverage records should preserve bounded source refs and collection attempt
  diagnostics, not raw endpoint payloads or full histories.
- Coverage state should be summarized in the research data catalog when
  implemented.

## Timestamp And No-Lookahead Semantics

Reusable data may carry multiple time fields. Consumers must use the field that
matches the question being asked.

Canonical time fields:

- `open_time`: OHLCV candle open time. Closed-candle rules decide whether a bar
  is eligible for a backtest window.
- `event_time`: time the external event occurred when the source provides it.
- `published_at`: time a text or public-information source says an item was
  published.
- `collected_at`: time Halpha collected the record.
- `first_seen_at`: first time Halpha observed a reusable record.
- `last_seen_at`: latest time Halpha observed a repeated reusable record.
- `as_of`: caller-supplied point-in-time boundary for no-lookahead retrieval.

No-lookahead rules:

- A query with `as_of` must exclude records that were not published, collected,
  or first seen by that boundary when those fields are relevant to the data
  type.
- Text-event retrieval should not expose a record first observed after `as_of`,
  even if the source `published_at` claims an earlier timestamp.
- OHLCV retrieval should not expose open or future bars beyond the requested
  range or closed-candle eligibility.
- Event-like retrieval should return coverage diagnostics with empty results so
  callers can distinguish `no_data` from `not_collected`, `failed`, or unknown
  coverage.

## Collection Plan Contract

Collection planning is a dry-run-friendly decision layer between a requested
range and actual source collection. It reads coverage state before fetches are
attempted.

Required plan fields:

- `schema_version`
- `created_at`
- `data_type`
- `source`
- `identity`
- `requested_start`
- `requested_end`
- `strategy`
- `skipped_ranges`
- `gap_ranges`
- `retry_ranges`
- `planned_fetch_windows`
- `coverage_refs`
- `warnings`
- `errors`

Strategy values:

- `no_work`: requested range is already sufficiently covered.
- `gap_only`: planned fetches target missing or incomplete gaps.
- `merged_gaps`: fragmented gaps are combined to reduce fetch overhead.
- `widened_window`: a wider window is more efficient than exact gap fetches.
- `full_range`: full requested range collection is more efficient or required
  by the source.
- `blocked`: source or configuration cannot satisfy the requested collection.

Rules:

- Complete intervals should be skipped.
- Partial and failed intervals should remain visible and eligible for retry.
- Fragmented gaps should be planned by efficiency, not by blindly issuing one
  request per fragment.
- Unsupported historical collection must produce `blocked` or warnings, not
  fake successful coverage.
- OHLCV `data collect` dry-run reads coverage state and returns a bounded plan
  without source fetches, Parquet writes, coverage writes, catalog writes, run
  archives, monitor cycles, schedules, report generation, or Codex execution.
- OHLCV `data collect --apply` executes planned fetch windows, writes finalized
  candles to the shared OHLCV store, updates collection coverage, and refreshes
  the shared research data catalog snapshot without creating a product run.
- Text-event `data collect` dry-run reads coverage state and returns a bounded
  plan without source fetches, history writes, coverage writes, catalog writes,
  run archives, monitor cycles, schedules, report generation, or Codex
  execution.
- Text-event `data collect --apply` runs the configured text source collection
  path for the selected source name or `all`, normalizes records through the
  same text-event record builder used by the pipeline, writes shared
  text-event history, records `collected`, `no_data`, `partial`, `failed`, or
  `not_collected` coverage, and refreshes the shared research data catalog
  snapshot without creating a product run.
- Current text-event RSS collection is best-effort for configured feeds. A
  source that cannot support the requested historical range must surface a
  blocked plan or incomplete coverage instead of fake success.

## Shared Data Query Contract

Shared data queries provide the common read path for backtests, Dashboard
previews, report-facing material builders, and exports.

Implemented query adapters:

- OHLCV range query: `halpha.market.ohlcv_query.query_ohlcv_records`.
- OHLCV latest-lookback query:
  `halpha.market.ohlcv_query.query_latest_ohlcv_records`.
- Text-event range query:
  `halpha.data.event_like_query.query_text_event_records`.
- Macro/calendar range query:
  `halpha.data.event_like_query.query_macro_calendar_records`.
- On-chain flow range query:
  `halpha.data.event_like_query.query_onchain_flow_records`.
- Derivatives market range query:
  `halpha.data.event_like_query.query_derivatives_market_records`.
- Market anomaly range query:
  `halpha.data.event_like_query.query_market_anomaly_records`.

Required query inputs:

- `data_type`
- source and identity filters
- `start`
- `end`
- optional `as_of`
- optional bounded limit or truncation policy
- optional data-type filters supported by the implemented store

Required query outputs:

- `records`
- `record_count`
- `truncated`
- `time_fields`
- `coverage_diagnostics`
- `warnings`
- `errors`
- `source_artifacts`

Rules:

- Query output ordering must be deterministic.
- Empty query results must carry enough coverage diagnostics to distinguish
  successful `no_data` from `not_collected`, `failed`, `partial`, or unknown
  coverage.
- Query adapters must preserve source names, source refs, schema version,
  timestamps, duplicate status, conflict warnings, and errors where available.
- Query APIs are product data access boundaries, not Codex context.
- OHLCV queries use `open_time` for range filtering. The default range is
  half-open (`start <= open_time < end`), while existing benchmark windows may
  request an inclusive `open_time` end to preserve their current
  `input_window_end` contract.
- OHLCV queries with `as_of` return only candles whose close boundary is at or
  before `as_of`.
- Text-event queries use `published_at` for range filtering, with
  `collected_at` and `first_seen_at` as range fallbacks. With `as_of`, text
  queries exclude records whose `published_at`, `collected_at`, or
  `first_seen_at` is after the boundary.
- Macro/calendar queries use `scheduled_at` for range filtering. With `as_of`,
  they use `source_published_at` and `first_seen_at` as knowledge-boundary
  fields so future scheduled events may be returned only when the source or
  local history had made them visible by the boundary.
- On-chain flow and derivatives market queries use record `as_of` for both
  range filtering and no-lookahead eligibility.
- Market anomaly queries use `observed_at` for range filtering and
  `published_at` plus `first_seen_at` for no-lookahead eligibility.

## Market Anomaly History

Market anomaly history records abnormal market observations from two source
kinds behind one structure:

- external anomaly intelligence imported from configured local source adapters;
- Halpha rule-detected anomalies derived from local reusable market data.

Current artifact paths:

- current-run raw anomaly artifact: `raw/market_anomalies.json`;
- reusable history store: `data/market/anomalies/`;
- schema metadata: `data/market/metadata/market_anomaly_schema.json`;
- state metadata: `data/market/metadata/market_anomaly_state.json`.

Required record fields:

- `history_key`: project-defined canonical identity for exact signal merging;
- `anomaly_id`: source-provided or Halpha-generated item id;
- `dedupe_key`: project-defined dedupe grouping key for related signal work;
- `source_kind`: `external_intel` or `halpha_rule`;
- `source`: configured source name;
- `source_kinds`, `sources`, `source_records`: merged provenance;
- `data_class`: anomaly category such as `price_move` or `volume_spike`;
- `symbol`, `market_type`, `timeframe`;
- `observed_at`: market observation time and primary query time;
- `published_at`, `collected_at`, `first_seen_at`, `last_seen_at`;
- `severity`, `direction`, `metric`, `value`, `threshold`, `unit`;
- `window_start`, `window_end`;
- `title`, `summary`;
- `metrics`, `units`, `raw_fields`;
- `origin_run_ids`, `first_seen_run_id`, `last_seen_run_id`;
- `status`, `warnings`, `errors`, `source_artifacts`.

Identity and no-lookahead rules:

- `history_key` is based on `data_class`, `symbol`, `timeframe`,
  `observed_at`, `metric`, and `direction`; it intentionally excludes source
  so external intelligence and Halpha rules can merge the same anomaly signal.
- `source_records` preserves per-source provenance after merging.
- Conflicting duplicates must be kept with warning status, not silently
  overwritten.
- Backtests and previews must treat an anomaly as visible only when its
  `published_at` and `first_seen_at` are not after the requested `as_of`.

## Bounded Data Export Contract

Exports make reusable data available to local research tools without bypassing
query safety.

Export inputs:

- `data_type`
- source and identity filters
- `start`
- `end`
- optional `as_of`
- output format
- output path or destination managed by the command or Dashboard endpoint

Export rules:

- Exports must call the shared data query contract.
- Exports must not read full store files directly to bypass no-lookahead,
  coverage, range, or truncation behavior.
- OHLCV exports may use CSV or Parquet where the store supports it.
- Event-like exports may use JSON or CSV until the store supports a better
  columnar format.
- Export metadata must include request parameters, row count, truncation state,
  coverage diagnostics, warnings, errors, and source refs.
- Full reusable history export is not the default behavior.

Implemented export boundary:

- Service: `halpha.data.data_export.export_data`.
- CLI command: `halpha data export`.
- Required CLI range inputs: `--start` and `--end`.
- OHLCV identity inputs: `--source`, `--symbol`, and `--timeframe`.
- Event-like identity inputs: optional `--source` plus repeated
  `--identity KEY=VALUE` filters.
- Optional no-lookahead input: `--as-of`.
- Optional query bound: `--limit`.
- CSV and Parquet exports write sidecar metadata to
  `<output>.metadata.json`.
- JSON exports embed `metadata` and `records` in the export artifact.

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
- `open_time`

Required behavior:

- store finalized OHLCV candles only;
- keep shared history outside per-run report directories;
- expose current-run windows through `raw/market_data_views.json`;
- report stored ranges and update status through metadata;
- reject or warn on conflicting duplicate candles instead of silently replacing
  source evidence;
- preserve `source` as part of record identity so spot and perpetual public
  OHLCV histories from multiple supported exchanges remain separate;
- support configured OHLCV timeframes from minute candles through monthly
  candles where the selected public source provides them;
- allow explicit OHLCV range collection and backfill through
  `python -m halpha data collect --data-type ohlcv ...`, with dry-run as the
  safe default and `--apply` required for source fetches and shared-store
  writes;
- expose no-lookahead OHLCV range and latest-lookback reads through the shared
  OHLCV query adapter, including missing-candle and collection-coverage
  diagnostics;
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
- `artifact_type`
- `generated_at`
- `status`
- `stores`
- `counts`
- `warnings`
- `errors`
- `validation`

Required store fields:

- `name`
- `domain`
- `kind`
- `status`
- `format`
- `storage_path`
- `schema_path`
- `state_path`
- `schema_version`
- `schema_metadata_kind`
- `partition_fields`
- `unique_key_fields`
- `source_fields`
- `time_field`
- `latest_update_at`
- `latest_completed_revision`
- `record_count`
- `warning_count`
- `error_count`
- `consumers`
- `source_artifacts`
- `migration_status`
- `migration`
- `warnings`
- `errors`

Planned store extension fields for coverage and query work:

- `coverage_state`
- `query_capability`
- `export_capability`

Required migration fields:

- `status`
- `applied_schema_version`
- `available_migrators`
- `compatibility_readers`
- `last_migration_at`
- `warnings`
- `errors`

Status values:

- `ok`
- `warning`
- `degraded`
- `skipped`
- `failed`

Rules:

- include only implemented stores;
- preserve deterministic store ordering by `name`;
- use runtime-root-relative path references, or safe external refs when a
  configured shared-data root is outside the runtime root;
- fail catalog validation when a store `storage_path` points under `runs/`;
- allow `runs/` paths only as bounded source artifact refs, not as shared store
  storage paths;
- validate missing schema metadata, schema version, time field, and migration
  metadata as warnings unless the storage path violates the run-archive
  boundary;
- summarize large stores by metadata, not row dumps;
- expose catalog field summaries through data inspection and Dashboard
  data-store views without embedding raw shared histories;
- summarize coverage-state availability, query capability, and export
  capability when those are implemented;
- standalone shared-data collection may refresh the catalog from shared store
  metadata and bounded collection diagnostics without a `run_manifest.json`;
- in product runs, build the catalog from prepared shared-state candidates and
  publish the official catalog only after product validation is publishable;
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
- `python -m halpha data migrate-state --config <config> --dry-run` reports
  legacy run-index rows without mutating runtime state.
- `python -m halpha data migrate-state --config <config> --apply` imports
  legacy run-index rows only when the referenced `run_manifest.json` exists and
  validates. Manifest evidence wins over legacy row metadata. Dangling or
  invalid rows remain diagnostics.
- `python -m halpha data rebuild-index --config <config>` clears and rebuilds
  the current run-index projection from current `runs/*/run_manifest.json`
  files only. It does not import mutable legacy Dashboard, Schedule, Monitor,
  job, alert, cooldown, or service state.

Required tables:

- `runs`
- `run_stages`
- `run_tasks`
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
- `run_kind`
- `trigger_source`
- `trigger_intent`
- `disposal_class`
- `trigger_job_id`
- `trigger_schedule_id`
- `trigger_monitor_cycle_id`
- `trigger_source_keys`
- `trigger_parent_run_id`
- `trigger_requested_stage`

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
- after explicit migration, normal runtime readers and writers must use
  `.halpha/state.sqlite` and must not consult `data/research/index.sqlite` as a
  fallback authority.

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
- `same_event_group_id`
- `same_event_group_method`
- `same_event_group_score_bucket`
- `status`
- `warnings`
- `source_artifacts`

Required behavior:

- append current-run normalized event records after validation;
- deduplicate by deterministic event identity;
- preserve all run ids that observed a repeated item;
- warn on conflicting duplicates instead of silently overwriting;
- annotate source-preserving same-event groups where exact duplicate keys or
  deterministic near-duplicate rules identify repeated public coverage;
- keep low-confidence or gate-failed near-duplicate candidates separate in
  state metadata with reasons where practical;
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
- run-index stage-time projection boundary;
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
- text event history write status and duplicate counts;
- outcome history state path and write status when outcome evaluation evidence
  exists;
- data quality summary path, status, warning count, and error count;
- Codex input budget metadata for any data-quality material.

`run_manifest.json` remains the per-run lifecycle record. Reusable stores and
indexes do not replace it.

After the runtime-state migration, run manifests remain immutable product
records and the runtime state store remains an operational index. Validation,
dashboard, workbench, and inspection paths may query the runtime index for
latest-run selection, recovery diagnostics, and discovery, but the run index is
committed after the terminal manifest and is not a manifest authority or
required manifest field. Source refs must still point back to the authoritative
run manifest and artifacts.

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
- collection coverage status vocabulary;
- no-lookahead query filtering;
- bounded export metadata;
- partial collection failure;
- manifest references;
- Codex input boundaries.

Real-source validation should use existing product commands and inspect the
generated artifacts. Full report validation sends generated local research
context to Codex CLI.
