# Halpha

Halpha is a personal market research pipeline. It collects public market data and
public text sources, builds source-aware research artifacts, prepares local
context for Codex CLI, and writes a Simplified Chinese Markdown research report.

The project is designed for reviewable research, not trading execution. It keeps
raw data, deterministic analysis material, Codex context, generated reports, and
run manifests as plain files so each run can be inspected after it finishes.

## What It Does

- Collects public Binance ticker data for configured symbols.
- Collects configured public macro/calendar evidence when enabled.
- Collects configured public on-chain flow evidence when enabled.
- Collects public RSS text events from configured sources.
- Normalizes raw text events into source-aware event records for later text intelligence stages.
- Extracts traceable entity evidence and configured-asset relevance from normalized text events.
- Validates optional local text-intelligence model settings and explicit model preparation metadata.
- Syncs reusable OHLCV history into a shared local Parquet store.
- Builds deterministic current-run OHLCV data views.
- Builds fixed strategy benchmark window suites from shared local OHLCV history.
- Evaluates configured quantitative strategies with bounded diagnostics.
- Runs standalone single-strategy backtests from shared local OHLCV history.
- Runs standalone strategy experiments against fixed benchmark suites and deterministic effectiveness gates.
- Writes pipeline strategy evaluation summaries with single-window, bounded walk-forward, parameter-stability, and overfitting-risk evidence.
- Normalizes strategy outputs into market signal artifacts and AI-readable signal material.
- Builds deterministic regime, risk, recommendation, watch trigger, and previous-run delta artifacts.
- Builds event-quant confluence records and deterministic event intelligence assessments.
- Builds deterministic alert decision artifacts for event attention priority.
- Builds bounded AI-readable alert decision material for report generation.
- Builds bounded AI-readable event intelligence material.
- Builds AI-readable decision material from deterministic JSON artifacts.
- Builds bounded AI-readable derivatives market material from deterministic derivatives context.
- Extracts deterministic outcome targets from the latest previous successful run.
- Evaluates matured market, strategy, event, alert, decision, and watch outcome targets.
- Persists reusable local outcome history outside per-run report directories.
- Builds research context and Codex prompt artifacts.
- Runs Codex CLI to generate a Simplified Chinese report.
- Inserts deterministic strategy output and strategy effectiveness tables into the final report.
- Records lifecycle status, artifacts, counts, warnings, errors, and Codex status in `run_manifest.json`.
- Validates product contract health through a deterministic artifact and read-only CLI inspection.
- Validates local monitor configuration without starting hidden background execution.
- Runs one bounded local monitor cycle and writes a monitor cycle manifest.
- Archives emitted and suppressed monitor alert decisions in local plain files.
- Runs a local web dashboard service as the primary local user entry point for
  overview, report review, strategy research, monitor control, intelligence
  review, settings, bounded artifact previews, dashboard jobs, storage cleanup,
  and daily report schedule state.
- Builds local workbench delivery snapshots, Markdown indexes, and static HTML
  index files from existing artifacts as CLI inspection and recovery aids.

Halpha does not implement account access, exchange trading, order placement,
portfolio automation, real-time alert delivery, hosted dashboards, or hosted
services.

## Install

```bash
python -m pip install -e ".[dev]"
```

Python 3.11 or newer is required.

Install optional local NLP model preparation and runtime dependencies only when
text intelligence model preparation is intended:

```bash
python -m pip install -e ".[dev,nlp]"
```

## Run

Run the full report pipeline:

```bash
python -m halpha run --config config.example.yaml
```

Run all pre-Codex steps and skip final Codex report generation:

```bash
python -m halpha run --config config.example.yaml --no-codex
```

Run through a named pipeline stage and mark later stages as not run:

```bash
python -m halpha run --config config.example.yaml --until build_research_context
```

Run one stage against an existing run directory:

```bash
python -m halpha stage build_research_context --config config.example.yaml --run-dir runs/<run_id>
```

Inspect product contract health for the latest indexed run or one selected run
without collection, pipeline stages, report generation, or Codex:

```bash
python -m halpha validate --config config.example.yaml
python -m halpha validate --config config.example.yaml --run-dir runs/<run_id>
```

Run the local web dashboard:

```bash
python -m halpha dashboard --config config.example.yaml
python -m halpha dashboard --config config.example.yaml --host 127.0.0.1 --port 8765
```

The dashboard is the primary local user entry point and is local-only by
default. Open the printed local URL in a browser to inspect overview state, run
history, report previews, local data store metadata, strategy outputs, monitor
health, recent monitor cycles, alert samples, and dashboard-triggered job
history.

Dashboard artifact previews are bounded and allowlisted to local Halpha runtime
roots. Private values such as proxy URLs, credentials, tokens, private notes,
raw user-state files, machine paths, and private endpoints are rejected or
redacted from dashboard responses and job logs where the dashboard can identify
them.

Dashboard command execution is explicit and allowlisted. Product run, stage,
validation, data inspection, outcome inspection, workbench, strategy, text,
monitor, and schedule trigger actions run through dashboard jobs. Codex-capable
report jobs require explicit confirmation before they can start. The dashboard
does not expose arbitrary shell execution.

Daily report schedule state is explicit local dashboard control state under
`runs/dashboard/schedules/`. The implemented schedule API can inspect, enable,
disable, update, and manually trigger daily report jobs through dashboard jobs.
It does not install an OS scheduler, hosted scheduler, startup task, cron job,
workflow engine, or hidden daemon.

Inspect the monitor command surface and validate local monitor configuration
without running collection, pipeline stages, or Codex:

```bash
python -m halpha monitor --help
python -m halpha monitor run --config config.example.yaml --dry-run
```

Run exactly one bounded local monitor cycle:

```bash
python -m halpha monitor run --config config.example.yaml --once
```

Run a finite local monitor loop:

```bash
python -m halpha monitor run --config config.example.yaml --max-cycles 3 --interval-seconds 300
```

Inspect local monitor health without collection, pipeline execution, or Codex:

```bash
python -m halpha monitor inspect --config config.example.yaml
```

The default monitor cycle reuses the configured product pipeline through the
configured monitor target stage and stops before Codex report generation unless
monitor config explicitly changes that boundary. The cycle also updates the
local alert archive and cooldown state from generated alert decisions. Monitor
notification delivery and daemon/service behavior are not implemented by the
current monitor command. Dashboard service behavior is provided by the separate
`dashboard` command.

Inspect local research data and data-quality state without collection or Codex:

```bash
python -m halpha data inspect --config config.example.yaml
python -m halpha data inspect --config config.example.yaml --run-dir runs/<run_id>
```

The inspection command summarizes shared OHLCV, derivatives, macro/calendar,
on-chain flow, text-event, run-index, intelligence-fusion, strategy-lifecycle,
product-validation, and data-quality state, plus workbench output refs when
available, without dumping full reusable histories or raw records.

Inspect outcome tracking artifacts and shared outcome history state without
collection or Codex:

```bash
python -m halpha outcomes inspect --config config.example.yaml
python -m halpha outcomes inspect --config config.example.yaml --run-dir runs/<run_id>
```

Build local workbench delivery snapshot outputs from existing artifacts:

```bash
python -m halpha workbench build --config config.example.yaml
python -m halpha workbench build --config config.example.yaml --run-dir runs/<run_id>
```

Inspect the latest workbench summary as a CLI inspection and recovery fallback
without running collection, pipeline stages, monitor cycles, or Codex:

```bash
python -m halpha workbench inspect --config config.example.yaml
```

Workbench outputs are local delivery snapshot artifacts under
`runs/workbench/latest/`. They summarize and link to existing deterministic
artifacts, including bounded product-validation health when available. They are
not the primary UI, not a replacement for dashboard views, and not upstream
decision inputs or Codex context by default.

Run one configured strategy backtest from shared local OHLCV history:

```bash
python -m halpha backtest --config config.example.yaml --strategy tsmom_vol_scaled --symbol BTCUSDT --timeframe 1d
```

Standalone backtests write inspectable artifacts under
`runs/strategy_backtests/` by default. Use `--output-dir <dir>` to choose a
different local output directory. This command does not run the report pipeline
or Codex CLI. The backtest artifact includes a bounded candlestick
visualization payload for local dashboard review; it does not copy the full
shared OHLCV history into the artifact.

Run enabled strategy candidates against the fixed benchmark suite:

```bash
python -m halpha experiment --config config.example.yaml
```

Use `--strategy <strategy_name>` one or more times to limit candidates, and
`--output-dir <dir>` to choose a different local output directory. Standalone
experiments write inspectable artifacts under `runs/strategy_experiments/` by
default and do not run the report pipeline or Codex CLI.

Prepare configured text-intelligence models explicitly:

```bash
python -m halpha text-models prepare --config config.example.yaml
```

With the portable example config, `allow_model_download: false` records a local
metadata manifest and skips downloads. Actual model downloads require a
gitignored local config that sets `allow_model_download: true`, explicit model
revisions, and the optional `nlp` dependencies.

Run standalone text intelligence processing from configured text sources:

```bash
python -m halpha text-intel --config config.example.yaml
```

Process an existing raw text artifact without collecting public sources:

```bash
python -m halpha text-intel --config config.example.yaml --input runs/<run_id>/raw/text_events.json
```

Use `--output-dir <dir>` to choose the standalone output root. The command
writes implemented text-intelligence artifacts and a manifest under a unique
local subdirectory. It does not run the full report pipeline or Codex CLI.

Supported stage names:

```text
collect_market_data
collect_derivatives_market_data
sync_derivatives_market_history
build_derivatives_market_views
build_derivatives_market_context
collect_macro_calendar_data
sync_macro_calendar_history
build_macro_calendar_views
build_macro_calendar_context
build_macro_calendar_material
collect_onchain_flow_data
sync_onchain_flow_history
build_onchain_flow_views
build_onchain_flow_context
build_onchain_flow_material
collect_text_events
build_text_event_records
build_text_entity_evidence
build_text_event_classification_evidence
build_text_event_topics
build_text_event_signals
sync_ohlcv
build_market_data_views
build_strategy_benchmark_suite
evaluate_quant_strategies
evaluate_strategy_evaluation
build_strategy_experiment_material
evaluate_market_strategy_signals
build_market_signals
build_market_signal_material
build_market_regime_assessment
build_risk_assessment
build_decision_recommendations
build_watch_triggers
build_event_market_confluence
build_event_intelligence_assessment
build_alert_decisions
build_alert_decision_material
build_event_intelligence_material
build_decision_intelligence_delta
build_decision_intelligence_material
build_data_quality_summary
build_outcome_targets
evaluate_outcomes
build_strategy_lifecycle_state
build_strategy_lifecycle_material
build_feature_snapshots
build_factor_states
build_multi_source_signals
build_intelligence_fusion
integrate_intelligence_fusion
build_user_state_context
build_personalized_risk_constraints
integrate_personalized_risk_constraints
build_personalized_risk_material
build_analysis_materials
build_research_context
build_codex_context
run_codex_report
validate_product_contracts
```

## Configuration

`config.example.yaml` is a portable public-source example. It configures:

- Binance public market data.
- Public RSS text sources.
- Optional text-intelligence model roles, revisions, download policy, and thresholds.
- Shared OHLCV history storage under `data/market/`.
- Built-in quantitative strategies:
  `tsmom_vol_scaled`, `breakout_atr_trend`, `sma_cross_trend`, and
  `bollinger_rsi_reversion`.
- Bounded backtest and parameter diagnostics.
- Optional Federal Reserve FOMC public calendar collection.
- Optional public on-chain flow collection.
- Optional deterministic strategy effectiveness gate thresholds.
- Codex CLI command and arguments for final report generation.

Full report runs require public network access, configured public sources, a
working Codex CLI on `PATH`, and Codex CLI authentication outside this
repository. The generated local prompt is sent to Codex CLI through stdin.

If a local proxy is needed, keep it in a gitignored local config file:

```yaml
market:
  proxy:
    enabled: true
    url: http://proxy.example:8080
```

Do not commit machine-local proxy values, credentials, hostnames, ports, paths,
tokens, cookies, or account identifiers.

## Output Artifacts

A successful configured run can write:

- `raw/market.json`: public market observations.
- `raw/derivatives_market.json`: public derivatives and market-structure observations.
- `raw/macro_calendar.json`: public macro and scheduled-event observations when enabled.
- `raw/onchain_flow.json`: public on-chain flow observations when enabled.
- `raw/macro_calendar_views.json`: current-run macro/calendar input window metadata and bounded records.
- `raw/onchain_flow_views.json`: current-run on-chain flow input window metadata and bounded records.
- `analysis/onchain_flow_context.json`: deterministic on-chain flow context when enabled.
- `analysis/onchain_flow_material.md`: bounded AI-readable on-chain flow context for Codex and report generation.
- `analysis/macro_calendar_context.json`: deterministic macro/calendar timing, source-availability, and catalyst context.
- `analysis/macro_calendar_material.md`: bounded AI-readable macro/calendar context for Codex and report generation.
- `raw/text_events.json`: public RSS text events.
- `analysis/text_event_records.json`: normalized source-aware text event records.
- `analysis/text_entity_evidence.json`: entity and configured-asset relevance evidence.
- `analysis/text_event_classification_evidence.json`: event category candidates and financial tone evidence.
- `analysis/text_event_topics.json`: duplicate, same-topic, related-context, and distinct event grouping evidence.
- `analysis/text_event_signals.json`: deterministic report-facing text event signals.
- `raw/market_data_views.json`: current-run OHLCV input window metadata.
- `raw/derivatives_market_views.json`: current-run derivatives input window metadata.
- `data/market/ohlcv/`: shared finalized OHLCV history.
- `data/market/derivatives/`: shared reusable derivatives market history.
- `data/macro/calendar/`: shared reusable macro/calendar history.
- `data/onchain/flow/`: shared reusable on-chain flow history.
- `data/market/metadata/ohlcv_schema.json`: shared OHLCV schema metadata.
- `data/market/metadata/ohlcv_sync_state.json`: shared OHLCV stored-range metadata.
- `data/market/metadata/derivatives_market_schema.json`: shared derivatives history schema metadata.
- `data/market/metadata/derivatives_market_state.json`: shared derivatives history state metadata.
- `data/macro/metadata/macro_calendar_schema.json`: shared macro/calendar history schema metadata.
- `data/macro/metadata/macro_calendar_state.json`: shared macro/calendar history state metadata.
- `data/onchain/metadata/onchain_flow_schema.json`: shared on-chain flow history schema metadata.
- `data/onchain/metadata/onchain_flow_state.json`: shared on-chain flow history state metadata.
- `data/research/metadata/research_data_catalog.json`: shared local research data catalog.
- `data/research/index.sqlite`: local run index with run, stage, artifact, and latest-run metadata.
- `data/research/metadata/text_event_history_state.json`: shared text-event history state metadata.
- `data/research/text_events/`: shared deduplicated text-event history.
- `data/research/metadata/outcome_history_state.json`: shared outcome history state metadata.
- `data/research/outcomes/outcome_history.json`: shared reusable outcome history.
- `analysis/strategy_benchmark_suite.json`: fixed strategy benchmark window metadata.
- `analysis/quant_strategy_runs.json`: configured strategy run outputs.
- `analysis/strategy_evaluation_summary.json`: strategy evaluation summaries.
- `analysis/strategy_evaluation_material.md`: AI-readable strategy evaluation material.
- `analysis/strategy_experiment.json`: current-run strategy experiment output.
- `analysis/strategy_effectiveness_gates.json`: deterministic strategy gate output.
- `analysis/strategy_experiment_material.md`: AI-readable strategy experiment and gate material.
- `analysis/strategy_lifecycle_state.json`: deterministic strategy lifecycle health, degradation, version, and explicit retirement state.
- `analysis/strategy_lifecycle_material.md`: bounded AI-readable strategy lifecycle material for Codex and report generation.
- `analysis/market_strategy_signals.json`: strategy signal outputs.
- `analysis/market_signals.json`: normalized report-facing market signals.
- `analysis/market_signal_material.md`: AI-readable market signal material.
- `analysis/derivatives_market_context.json`: deterministic funding, open-interest, premium, basis, bounded liquidity-depth, and liquidation-availability derivatives context records.
- `analysis/derivatives_market_material.md`: bounded AI-readable derivatives market material for Codex context.
- `analysis/market_regime_assessment.json`: deterministic market regime assessment.
- `analysis/risk_assessment.json`: deterministic risk assessment.
- `analysis/decision_recommendations.json`: deterministic decision-support recommendations with source-aware risk, downgrade, fusion, and optional personalized constraint context.
- `analysis/watch_triggers.json`: deterministic watch triggers, including supported risk escalation, risk relief, and optional personalized constraint conditions.
- `analysis/event_market_confluence.json`: deterministic event-quant and event-decision relationship records.
- `analysis/event_intelligence_assessment.json`: deterministic event relevance, severity, market response, and decision-impact assessment records.
- `analysis/alert_decisions.json`: deterministic event attention-priority decisions with supported derivatives, fusion, and optional personalized constraint context, not alert delivery.
- `analysis/alert_decision_material.md`: AI-readable alert priority, downgrade, suppression, and uncertainty material.
- `analysis/event_intelligence_material.md`: AI-readable event evidence, topic, signal, and confluence material.
- `analysis/decision_intelligence_delta.json`: previous-run decision-intelligence changes.
- `analysis/decision_intelligence_material.md`: AI-readable decision material.
- `analysis/data_quality_summary.json`: current-run market, text, derivatives, macro/calendar, on-chain flow, feature/factor, intelligence-fusion, shared-store, and Codex-boundary quality checks.
- `analysis/data_quality_material.md`: AI-readable data quality status and local store references.
- `analysis/outcome_targets.json`: source-linked outcome target records from the latest previous successful run.
- `analysis/outcome_evaluations.json`: deterministic market, strategy, event, alert, decision, and watch outcome evaluations.
- `analysis/outcome_tracking_material.md`: AI-readable bounded outcome accountability material.
- `analysis/feature_snapshots.json`: normalized source-aware feature records and source coverage from implemented current-run evidence.
- `analysis/factor_states.json`: deterministic factor states, bounded scores, directions, confidence, and degraded-state evidence from feature snapshots.
- `analysis/multi_source_signals.json`: conservative normalized research signals derived from factor states.
- `analysis/intelligence_fusion.json`: deterministic cross-source fusion records for confluence, conflict, risk overrides, event overrides, outcome feedback, uncertainty, and source refs.
- `analysis/intelligence_fusion_material.md`: AI-readable bounded fusion material for Codex/report input.
- `analysis/user_state_context.json`: optional sanitized local user-state context with privacy boundary metadata.
- `analysis/personalized_risk_constraints.json`: deterministic personalized risk constraint records from sanitized user state and current-run intelligence.
- `analysis/personalized_risk_material.md`: bounded AI-readable personalized-risk material for Codex/report input.
- `analysis/market_material.md`: AI-readable market material.
- `analysis/text_material.md`: AI-readable text material.
- `analysis/research_context.md`: structured local research context.
- `codex_context/context.md`: Codex-readable context artifact.
- `codex_context/prompt.md`: prompt sent to Codex CLI.
- `report/report.md`: Simplified Chinese Markdown report from Codex stdout.
- `analysis/product_contract_validation.json`: deterministic product contract validation, manifest health, artifact contract checks, Codex/report boundary checks, and operational diagnostics.
- `run_manifest.json`: run lifecycle, stage status, artifact paths, counts, Codex status, and errors.
- `runs/strategy_backtests/<id>/strategy_backtest.json`: standalone strategy backtest output.
- `runs/strategy_backtests/<id>/manifest.json`: standalone backtest manifest.
- `runs/strategy_experiments/<id>/strategy_experiment.json`: standalone strategy experiment output.
- `runs/strategy_experiments/<id>/strategy_benchmark_suite.json`: benchmark suite used by a standalone experiment.
- `runs/strategy_experiments/<id>/strategy_effectiveness_gates.json`: deterministic strategy gate output.
- `runs/strategy_experiments/<id>/manifest.json`: standalone strategy experiment manifest.
- `runs/text_intelligence/<id>/raw/text_events.json`: standalone text raw artifact.
- `runs/text_intelligence/<id>/analysis/text_event_records.json`: standalone normalized text event records.
- `runs/text_intelligence/<id>/analysis/text_entity_evidence.json`: standalone entity and asset relevance evidence.
- `runs/text_intelligence/<id>/analysis/text_event_classification_evidence.json`: standalone event category and financial tone evidence.
- `runs/text_intelligence/<id>/analysis/text_event_topics.json`: standalone event topic grouping evidence.
- `runs/text_intelligence/<id>/analysis/text_event_signals.json`: standalone text event signals.
- `runs/text_intelligence/<id>/analysis/event_intelligence_material.md`: standalone AI-readable event intelligence material.
- `runs/text_intelligence/<id>/manifest.json`: standalone text intelligence manifest.
- `data/models/text/model_prepare_manifest.json`: local text model preparation metadata when `text-models prepare` is run with the example cache directory.
- `runs/workbench/latest/workbench_summary.json`: bounded local delivery snapshot summary with latest run, report, decision, alert, monitor, outcome, strategy, product-validation, data-quality, source-ref, warning, error, and Codex-boundary metadata.
- `runs/workbench/latest/index.md`: local Markdown workbench index generated from the summary.
- `runs/workbench/latest/index.html`: local static HTML workbench index generated from the summary.

Failed runs preserve artifacts created before the failure and record errors in
`run_manifest.json`. The product command must not emit fake raw data, fake
analysis, or placeholder reports.

Feature, factor, and multi-source signal contracts are defined in
`docs/feature-factor-contracts.md`. Product runs generate
`analysis/feature_snapshots.json`, `analysis/factor_states.json`,
`analysis/multi_source_signals.json`, and bounded
`analysis/factor_signal_material.md` for Codex/report input.

## Quantitative Research

Built-in strategies use vectorbt as an implementation helper for indicator,
signal, and bounded diagnostic calculations. Persisted artifacts contain only
Halpha-owned fields such as strategy name, version, params, source, symbol,
timeframe, input window, data quality, indicators, signals, assessment,
diagnostic assumptions, scalar metrics, warnings, and source artifacts.

Backtest diagnostics are historical research material only. They are not
forecasts, trading instructions, investment advice, or performance guarantees.
Strategy evaluation summaries include cost assumptions, gross and net metrics,
baseline comparison, relative metrics, bounded walk-forward summaries, and
research limitation, parameter-stability, and overfitting-risk warnings.
Strategy benchmark suites define reusable OHLCV windows for later strategy
experiments without embedding raw OHLCV history in AI-readable context.
Standalone strategy experiments evaluate configured strategy candidates across
those windows using the same single-window strategy evaluation semantics as the
main pipeline, add bounded walk-forward summaries, and classify candidates with
deterministic effectiveness gates. Product runs also write bounded strategy
experiment material into the report context so the final report can discuss
effective, watchlisted, rejected, or insufficient-evidence candidates without
asking Codex to generate gate outcomes.
Strategy lifecycle material carries deterministic strategy health,
degradation, watchlist, rejection, retirement, insufficient-evidence, and
source-availability context into report generation without asking Codex to
create lifecycle states or governance decisions.
Downstream fusion can reference lifecycle state to qualify degraded or retired
strategies before decision material and final report context are built.
AI-readable strategy evaluation material carries those deterministic evaluation
fields into research context and report generation without asking Codex to
calculate new metrics.

## Codex Report Generation

Codex consumes generated research context and prompt artifacts. It does not
generate action levels, strategy signals, structured decision artifacts,
derivatives states, macro/calendar states, on-chain records, flow states,
address labels, risk levels, user state, personalized constraints, holdings,
allocations, position sizes, event categories, event impacts, event-market
relationships, strategy lifecycle states, policy records, promotion decisions,
retirement decisions, parameter optimization, strategy selection, or price forecasts. Those are produced
deterministically before report generation.

Codex input is governed by `docs/artifact-governance.md`: complete evidence
artifacts stay inspectable on disk, while Codex receives bounded report-facing
material plus explicit budget metadata in `run_manifest.json`.
Derivatives, macro/calendar, on-chain flow, personalized risk, and data-quality
evidence follow the same rule: Codex receives concise report-facing material
files, not full local histories, raw archives, current-run views, raw
user-state files, private notes, catalog contents, SQLite tables, Parquet data,
full lifecycle JSON, local lifecycle policy input, or full context JSON.

The final report is generated from Codex stdout. When strategy run artifacts are
available, Halpha inserts the complete strategy output table after Codex output
validation so Codex does not need to recreate every row. When strategy gate
artifacts are available, Halpha also inserts a deterministic strategy
effectiveness table from `analysis/strategy_effectiveness_gates.json`.
When derivatives market material exists, Halpha inserts a bounded derivatives
and market-structure evidence section from deterministic artifacts after Codex
output validation. Macro/calendar and on-chain flow material follow the same
pattern with bounded deterministic evidence sections.

## Validation

`config.example.yaml` is a portable public example. Real local acceptance should
use a gitignored machine-local config file and should not print or commit local
proxy values, credentials, machine paths, user-state files, private policy
values, or other local privacy values.

Run automated tests:

```bash
python -m pytest
```

Run the local lint gate used by CI:

```bash
python -m ruff check .
```

For code changes, run the narrowest focused tests that cover the touched module
before or alongside the full suite.

Run real-source product acceptance without Codex CLI:

```bash
python -m halpha run --config <local-config.yaml> --no-codex
```

Inspect product contract health without collection, pipeline execution, report
generation, or Codex CLI:

```bash
python -m halpha validate --config <local-config.yaml>
python -m halpha validate --config <local-config.yaml> --run-dir runs/<run_id>
```

The validate command prints bounded status, check counts, failed check names,
source refs, and recovery hints. It does not write
`analysis/product_contract_validation.json`; product runs write that artifact
as part of the pipeline.

Inspect local data lake state without collection or Codex CLI:

```bash
python -m halpha data inspect --config <local-config.yaml>
python -m halpha data inspect --config <local-config.yaml> --run-dir runs/<run_id>
```

Use this output to check on-chain flow history state, current-run on-chain view
coverage, feature/factor artifact status, intelligence-fusion status,
strategy-lifecycle status, personalized-risk aggregate status,
product-validation status, Codex input budget state, and latest data-quality
counts without exposing reusable record contents, full lifecycle records, policy
values, product validation checks, or raw local user-state values.

Inspect outcome tracking state without collection or Codex CLI:

```bash
python -m halpha outcomes inspect --config <local-config.yaml>
python -m halpha outcomes inspect --config <local-config.yaml> --run-dir runs/<run_id>
```

Build and inspect local workbench delivery snapshots as CLI inspection and
recovery aids without collection, pipeline execution, monitor cycles, or Codex
CLI:

```bash
python -m halpha workbench build --config <local-config.yaml>
python -m halpha workbench build --config <local-config.yaml> --run-dir runs/<run_id>
python -m halpha workbench inspect --config <local-config.yaml>
```

Inspect local monitor health without collection, pipeline execution, or Codex
CLI:

```bash
python -m halpha monitor inspect --config <local-config.yaml>
```

Run full Codex report acceptance only when Codex context, prompt construction,
report generation, report post-processing, or final report content changed:

```bash
python -m halpha run --config <local-config.yaml>
```

Run standalone strategy experiment acceptance:

```bash
python -m halpha experiment --config config.example.yaml
```

Inspect the generated `runs/strategy_experiments/<id>/manifest.json` and
`strategy_effectiveness_gates.json` files for benchmark, experiment, and gate
counts. The portable example config is expected to produce at least three
`effective` research candidates under the deterministic gate policy.

Run text model preparation metadata acceptance without downloads:

```bash
python -m halpha text-models prepare --config config.example.yaml
```

Run standalone text intelligence acceptance:

```bash
python -m halpha text-intel --config config.example.yaml
```

Run standalone text intelligence from an existing raw text artifact:

```bash
python -m halpha text-intel --config config.example.yaml --input runs/<run_id>/raw/text_events.json
```

For event-intelligence review, inspect recent `analysis/text_event_records.json`,
`analysis/text_entity_evidence.json`,
`analysis/text_event_classification_evidence.json`,
`analysis/text_event_topics.json`, `analysis/text_event_signals.json`,
`analysis/event_market_confluence.json`,
`analysis/event_intelligence_assessment.json`,
`analysis/alert_decisions.json`,
`analysis/alert_decision_material.md`, and
`analysis/event_intelligence_material.md` artifacts. High-confidence accepted
outputs should have source references, model or rule evidence, threshold checks,
and conservative unknown or low-confidence states for ambiguous inputs.

For alert-decision review, run through `build_alert_decision_material` when a
bounded check is enough:

```bash
python -m halpha run --config config.example.yaml --until build_alert_decision_material
```

Inspect `analysis/event_intelligence_assessment.json`,
`analysis/alert_decisions.json`, `analysis/alert_decision_material.md`, and
`run_manifest.json`. Alert priority, event severity, decision impact, downgrade
reasons, and no-alert states must come from generated Halpha artifacts. Codex
may explain those fields in the final report, but must not create or revise
them.

For Codex input-budget review, inspect `run_manifest.json` `codex_input`,
`analysis/research_context.md`, `codex_context/context.md`, and
`codex_context/prompt.md`. Complete intermediate JSON artifacts should be
referenced by path and summarized through bounded material, not embedded
wholesale. Personalized risk review should include
`analysis/user_state_context.json`, `analysis/personalized_risk_constraints.json`,
and `analysis/personalized_risk_material.md` while confirming raw local
user-state files, private notes, account identifiers, holdings, allocations,
and position sizes are not embedded in Codex input. For data-quality review, inspect
`analysis/data_quality_summary.json` as the structured evidence and
`analysis/data_quality_material.md` as the bounded Codex-facing summary. When
on-chain flow is enabled, data-quality review should include
`raw/onchain_flow.json`, `data/onchain/metadata/onchain_flow_state.json`,
`raw/onchain_flow_views.json`, `analysis/onchain_flow_context.json`, and
`analysis/onchain_flow_material.md` status checks.
Strategy lifecycle review should include `analysis/strategy_lifecycle_state.json`
as deterministic evidence and `analysis/strategy_lifecycle_material.md` as the
bounded Codex-facing summary.

To rerun only the report-facing alert material after inspecting or regenerating
upstream artifacts:

```bash
python -m halpha stage build_alert_decision_material --config config.example.yaml --run-dir runs/<run_id>
```

Run full report acceptance when Codex CLI use is intended:

```bash
python -m halpha run --config config.example.yaml
```

This sends generated local research context to Codex CLI through stdin and
writes the final report to `report/report.md`.

Mocks, fixtures, and fake Codex subprocesses are useful for automated tests, but
they are not proof of a real-source product run.

## Project Structure

- `AGENTS.md`: root instructions for AI agents.
- `config.example.yaml`: portable public-source configuration.
- `data/`: shared local market history area; generated contents are ignored by git.
- `docs/`: durable project documentation and implementation contracts.
  - `docs/artifact-governance.md`: artifact map, layer rules, Codex input policy, and documentation index.
  - `docs/research-data-contracts.md`: shared local research data, run index, text-event history, and data-quality contracts.
  - `docs/quant-contracts.md`: quantitative research contracts.
  - `docs/strategy-lifecycle-contracts.md`: strategy lifecycle state, policy, material, downstream, and Codex-boundary contracts.
  - `docs/derivatives-market-contracts.md`: derivatives and market-structure data contracts.
  - `docs/macro-calendar-contracts.md`: macro and scheduled-event data contracts.
  - `docs/onchain-flow-contracts.md`: on-chain and exchange-flow data contracts.
  - `docs/feature-factor-contracts.md`: feature, factor, multi-source signal, material, and Codex-boundary contracts.
  - `docs/intelligence-fusion-contracts.md`: fusion artifact, planned material, integration, and Codex-boundary contracts.
  - `docs/user-state-contracts.md`: optional local user-state, personalized-risk, privacy, material, and Codex-boundary contracts.
  - `docs/monitoring-contracts.md`: local monitor configuration, cycle, alert archive, health, privacy, and Codex-boundary contracts.
  - `docs/delivery-workbench-contracts.md`: local delivery snapshot and workbench summary, index, source-ref, privacy, and Codex-boundary contracts.
  - `docs/product-stability-contracts.md`: product validation, run health, backup boundary, operational acceptance, privacy, and Codex-boundary contracts.
  - `docs/logging-standards.md`: local JSON logging levels, event shape, privacy boundaries, context fields, and anti-noise rules.
  - `docs/dashboard-contracts.md`: local web dashboard, command, job, schedule, artifact preview, privacy, and Codex-boundary contracts.
  - `docs/event-intelligence-contracts.md`: event intelligence contracts.
  - `docs/decision-intelligence-contracts.md`: decision intelligence contracts.
  - `docs/outcome-tracking-contracts.md`: outcome target, evaluation, history, material, and Codex-boundary contracts.
- `src/halpha/`: Python package.
- `tests/`: automated tests.
- `runs/`: per-run artifact area; generated contents are ignored by git.

## Disclaimer

Halpha is a personal research project. It does not provide financial advice,
investment recommendations, trading instructions, or trading signals.
