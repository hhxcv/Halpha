# Halpha

Halpha is a personal market research pipeline. It collects public market data and
public text sources, builds source-aware research artifacts, prepares local
context for Codex CLI, and writes a Simplified Chinese Markdown research report.

The project is designed for reviewable research, not trading execution. It keeps
raw data, deterministic analysis material, Codex context, generated reports, and
run manifests as plain files so each run can be inspected after it finishes.

## What It Does

- Collects public Binance ticker data for configured symbols.
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
- Builds research context and Codex prompt artifacts.
- Runs Codex CLI to generate a Simplified Chinese report.
- Inserts deterministic strategy output and strategy effectiveness tables into the final report.
- Records lifecycle status, artifacts, counts, warnings, errors, and Codex status in `run_manifest.json`.

Halpha does not implement account access, exchange trading, order placement,
portfolio automation, real-time alerts, dashboards, or hosted services.

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

Run one configured strategy backtest from shared local OHLCV history:

```bash
python -m halpha backtest --config config.example.yaml --strategy tsmom_vol_scaled --symbol BTCUSDT --timeframe 1d
```

Standalone backtests write inspectable artifacts under
`runs/strategy_backtests/` by default. Use `--output-dir <dir>` to choose a
different local output directory. This command does not run the report pipeline
or Codex CLI.

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
build_analysis_materials
build_research_context
build_codex_context
run_codex_report
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
- `raw/text_events.json`: public RSS text events.
- `analysis/text_event_records.json`: normalized source-aware text event records.
- `analysis/text_entity_evidence.json`: entity and configured-asset relevance evidence.
- `analysis/text_event_classification_evidence.json`: event category candidates and financial tone evidence.
- `analysis/text_event_topics.json`: duplicate, same-topic, related-context, and distinct event grouping evidence.
- `analysis/text_event_signals.json`: deterministic report-facing text event signals.
- `raw/market_data_views.json`: current-run OHLCV input window metadata.
- `data/market/ohlcv/`: shared finalized OHLCV history.
- `data/market/metadata/ohlcv_schema.json`: shared OHLCV schema metadata.
- `data/market/metadata/ohlcv_sync_state.json`: shared OHLCV stored-range metadata.
- `analysis/strategy_benchmark_suite.json`: fixed strategy benchmark window metadata.
- `analysis/quant_strategy_runs.json`: configured strategy run outputs.
- `analysis/strategy_evaluation_summary.json`: strategy evaluation summaries.
- `analysis/strategy_evaluation_material.md`: AI-readable strategy evaluation material.
- `analysis/strategy_experiment.json`: current-run strategy experiment output.
- `analysis/strategy_effectiveness_gates.json`: deterministic strategy gate output.
- `analysis/strategy_experiment_material.md`: AI-readable strategy experiment and gate material.
- `analysis/market_strategy_signals.json`: strategy signal outputs.
- `analysis/market_signals.json`: normalized report-facing market signals.
- `analysis/market_signal_material.md`: AI-readable market signal material.
- `analysis/market_regime_assessment.json`: deterministic market regime assessment.
- `analysis/risk_assessment.json`: deterministic risk assessment.
- `analysis/decision_recommendations.json`: deterministic decision-support recommendations.
- `analysis/watch_triggers.json`: deterministic watch triggers.
- `analysis/event_market_confluence.json`: deterministic event-quant and event-decision relationship records.
- `analysis/event_intelligence_assessment.json`: deterministic event relevance, severity, market response, and decision-impact assessment records.
- `analysis/alert_decisions.json`: deterministic event attention-priority decisions, not alert delivery.
- `analysis/alert_decision_material.md`: AI-readable alert priority, downgrade, suppression, and uncertainty material.
- `analysis/event_intelligence_material.md`: AI-readable event evidence, topic, signal, and confluence material.
- `analysis/decision_intelligence_delta.json`: previous-run decision-intelligence changes.
- `analysis/decision_intelligence_material.md`: AI-readable decision material.
- `analysis/market_material.md`: AI-readable market material.
- `analysis/text_material.md`: AI-readable text material.
- `analysis/research_context.md`: structured local research context.
- `codex_context/context.md`: Codex-readable context artifact.
- `codex_context/prompt.md`: prompt sent to Codex CLI.
- `report/report.md`: Simplified Chinese Markdown report from Codex stdout.
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

Failed runs preserve artifacts created before the failure and record errors in
`run_manifest.json`. The product command must not emit fake raw data, fake
analysis, or placeholder reports.

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
AI-readable strategy evaluation material carries those deterministic evaluation
fields into research context and report generation without asking Codex to
calculate new metrics.

## Codex Report Generation

Codex consumes generated research context and prompt artifacts. It does not
generate action levels, strategy signals, structured decision artifacts, event
categories, event impacts, event-market relationships, or price forecasts.
Those are produced deterministically before report generation.

Codex input is governed by `docs/artifact-governance.md`: complete evidence
artifacts stay inspectable on disk, while Codex receives bounded report-facing
material plus explicit budget metadata in `run_manifest.json`.

The final report is generated from Codex stdout. When strategy run artifacts are
available, Halpha inserts the complete strategy output table after Codex output
validation so Codex does not need to recreate every row. When strategy gate
artifacts are available, Halpha also inserts a deterministic strategy
effectiveness table from `analysis/strategy_effectiveness_gates.json`.

## Validation

Run automated tests:

```bash
python -m pytest
```

Run real-source product acceptance without Codex CLI:

```bash
python -m halpha run --config config.example.yaml --no-codex
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
wholesale.

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
  - `docs/event-intelligence-contracts.md`: event intelligence contracts.
  - `docs/decision-intelligence-contracts.md`: decision intelligence contracts.
- `src/halpha/`: Python package.
- `tests/`: automated tests.
- `runs/`: per-run artifact area; generated contents are ignored by git.

## Disclaimer

Halpha is a personal research project. It does not provide financial advice,
investment recommendations, trading instructions, or trading signals.
