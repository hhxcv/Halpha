# Halpha

Halpha is an early-stage personal research project focused on market intelligence and quantitative research workflows.

The project explores how market data, public information, and structured reasoning can be organized into a reusable research context for personal analysis and review.

At this stage, Halpha has an implemented core report loop. No stable usage interface or release version is provided yet.

The long-term direction is to build a research assistant that helps transform market signals into clearer, reviewable research materials.

## Status

This repository is currently in the implemented core report loop stage.

Implemented now:

- Python package skeleton.
- `python -m halpha run --config config.example.yaml` entrypoint.
- `python -m halpha run --config config.example.yaml --no-codex` validation mode.
- `python -m halpha run --config config.example.yaml --until <stage_name>` validation mode.
- `python -m halpha stage <stage_name> --config config.example.yaml --run-dir runs/<run_id>` single-stage validation command.
- Run directory creation.
- `run_manifest.json` lifecycle.
- Narrow public Binance market collector.
- `raw/market.json` artifact creation for collected market data or collector errors.
- Narrow public RSS text event collector.
- `raw/text_events.json` artifact creation for collected public text events or collector errors.
- Incremental public OHLCV history sync for configured symbols and timeframes.
- Shared Parquet OHLCV history storage outside per-run report directories.
- OHLCV sync status, counts, stored ranges, warnings, and errors in `run_manifest.json`.
- Deterministic OHLCV data view selection for configured lookback windows.
- `raw/market_data_views.json` artifact creation when `market.ohlcv` is configured.
- `analysis/market_strategy_signals.json` artifact creation when `quant.enabled` is true.
- `analysis/market_signals.json` normalized market signal artifact creation when `quant.enabled` is true.
- `analysis/market_signal_material.md` quant-aware AI-readable market signal material creation when `quant.enabled` is true.
- `analysis/market_regime_assessment.json` deterministic market regime artifact creation when `quant.enabled` is true.
- `analysis/risk_assessment.json` deterministic risk assessment artifact creation when `quant.enabled` is true.
- `analysis/decision_recommendations.json` deterministic decision recommendation artifact creation when `quant.enabled` is true.
- Strategy-oriented quant config support through `quant.strategies` for `tsmom_vol_scaled`, `breakout_atr_trend`, and `bollinger_rsi_reversion`.
- Optional bounded strategy parameter diagnostics through `quant.parameter_diagnostics`.
- `analysis/quant_strategy_runs.json` artifact creation when `quant.strategies` is configured.
- Downstream `analysis/market_strategy_signals.json` generation from strategy run results when `quant.strategies` is configured.
- AI-readable market material generation.
- `analysis/market_material.md` artifact creation from `raw/market.json`.
- AI-readable text material generation.
- `analysis/text_material.md` artifact creation from `raw/text_events.json`.
- Research context generation.
- `analysis/research_context.md` artifact creation from analysis materials.
- Codex context artifact generation.
- `codex_context/context.md` and `codex_context/prompt.md` artifact creation.
- Codex prompt requirements for concise report structure, H1 title generation time, table-first data display, quantitative signal conclusions, evidence, watch points, and context-specific risk notes when market signal material exists.
- Codex CLI report generation from persisted prompt context.
- `report/report.md` artifact creation from Codex stdout when Codex CLI succeeds.
- Codex execution status, exit code, and failure summary recording in `run_manifest.json`.

Not implemented yet:

- Report export formats other than Markdown.

The product command must not emit fake raw data, fake analysis, or a placeholder report.

## Usage

Install the package and development dependencies:

```bash
python -m pip install -e ".[dev]"
```

Run the report loop:

```bash
python -m halpha run --config config.example.yaml
```

Run all pre-Codex stages and skip final Codex report generation:

```bash
python -m halpha run --config config.example.yaml --no-codex
```

Run through a named stage and mark later stages as not run:

```bash
python -m halpha run --config config.example.yaml --until build_research_context
```

Run one stage against an existing run directory:

```bash
python -m halpha stage build_research_context --config config.example.yaml --run-dir runs/<run_id>
```

Supported stage names:

```text
collect_market_data
collect_text_events
sync_ohlcv
build_market_data_views
evaluate_quant_strategies
evaluate_market_strategy_signals
build_market_signals
build_market_signal_material
build_market_regime_assessment
build_risk_assessment
build_decision_recommendations
build_analysis_materials
build_research_context
build_codex_context
run_codex_report
```

`config.example.yaml` uses public source configuration:

- Binance public market data for configured symbols.
- RSS feeds for configured public text sources.
- Full built-in quant strategy configuration with bounded backtest and parameter diagnostics enabled.
- Codex CLI command and arguments for final report generation.

Required local environment:

- Public network access for configured market and RSS sources.
- A working Codex CLI on `PATH` when the run reaches `run_codex_report`.
- Codex CLI authentication configured outside this repository when the run reaches `run_codex_report`.
- Permission for Codex CLI to receive the generated local prompt through stdin when the run reaches `run_codex_report`.

If a local proxy is needed for public market access, keep it in a gitignored local config file and enable `market.proxy` there:

```yaml
market:
  proxy:
    enabled: true
    url: http://proxy.example:8080
```

Do not commit machine-local proxy values, credentials, hostnames, ports, or paths.

Local config files used for real-source validation should preserve the same functional settings as `config.example.yaml` and differ only in machine-local privacy values such as proxy configuration.

## Quant Strategy Report Path

When `market.ohlcv` is configured and `quant.enabled` uses `quant.strategies`, the implemented run command can run the M2 strategy path:

```text
configured public market source
-> finalized OHLCV sync
-> shared local OHLCV history
-> deterministic current-run OHLCV data views
-> configured strategy run evaluation
-> optional bounded parameter diagnostics
-> quant_strategy_runs artifact
-> downstream market strategy signal artifacts
-> existing market signal material and report context
```

The shared OHLCV store is reusable local input history. It is not AI context. Current-run data views record deterministic input windows and storage references, not full raw OHLCV history. Codex receives market signal material with bounded input-window metadata, key values, evidence, and uncertainty.

The M1 `quant.signals` product path is retired. Use `quant.strategies`; the current built-in strategies are `tsmom_vol_scaled`, `breakout_atr_trend`, and `bollinger_rsi_reversion`.

Implemented strategy behavior:

- `tsmom_vol_scaled`: uses vectorbt `IndicatorFactory` to calculate time-series momentum return and active signals over a configured return window, then records realized volatility, target volatility, volatility-scaled exposure, latest regime, signal counts, assessment, warnings, and optional bounded vectorbt `Portfolio.from_signals` backtest diagnostics when enabled.
- `breakout_atr_trend`: uses vectorbt `IndicatorFactory` to calculate recent range breakout levels and ATR context, then records breakout state, ATR risk context, latest regime, entries, exits, assessment, warnings, and optional bounded vectorbt `Portfolio.from_signals` backtest diagnostics when enabled.
- `bollinger_rsi_reversion`: uses vectorbt `IndicatorFactory` to calculate Bollinger-style bands, RSI state, and a trend filter, then records oversold or overbought mean-reversion state, trend-filter warnings, entries, exits, assessment, uncertainty, and optional bounded vectorbt `Portfolio.from_signals` backtest diagnostics when enabled.

Strategy run artifacts preserve strategy name, version, engine metadata, params, source, symbol, timeframe, input window, data quality, indicators, signals, assessment, bounded diagnostic assumptions and scalar metrics, warnings, source artifacts, and insufficient-data or failure state. Vectorbt objects are internal implementation details and are not written into Halpha artifacts or Codex context. Backtest diagnostics are historical research material only, not forecasts, trading instructions, or investment advice.

Optional `quant.parameter_diagnostics` runs bounded configured parameter grids and records tested combinations, valid and invalid combinations, sensitivity notes, warnings, and summary metrics. It does not choose best parameters and is not an optimization platform.

Expected result in a properly configured online environment: writes `raw/market.json`, `raw/text_events.json`, `analysis/market_material.md`, `analysis/text_material.md`, `analysis/research_context.md`, `codex_context/context.md`, `codex_context/prompt.md`, `report/report.md`, and `run_manifest.json`. When `market.ohlcv` is configured, the run also updates shared OHLCV history and metadata under the configured storage location and writes `raw/market_data_views.json` for the current run. When `quant.enabled` is true, the run writes `analysis/market_strategy_signals.json`, `analysis/market_signals.json`, `analysis/market_signal_material.md`, `analysis/market_regime_assessment.json`, `analysis/risk_assessment.json`, and `analysis/decision_recommendations.json`. When `quant.strategies` is configured, the run also writes `analysis/quant_strategy_runs.json` before downstream market signal artifacts. If collection, OHLCV sync, data view creation, strategy run evaluation, strategy signal evaluation, market signal material generation, market regime assessment, risk assessment, decision recommendation generation, or Codex execution fails, artifacts created before the failure and `run_manifest.json` record the failure without fake records or a placeholder report.

With the current public example strategy configuration, a successful full quant run evaluates three enabled strategies across two symbols and two timeframes. The expected quant run shape is 4 current-run OHLCV data views, 12 strategy run records, 12 downstream market strategy signal records, 4 market regime assessment records, 4 risk assessment records, 4 decision recommendation records, and a final report with a deterministic quant strategy output table inserted from `analysis/quant_strategy_runs.json`. These counts follow the configured symbols, timeframes, and enabled strategies.

Output artifact roles:

- `raw/market.json`: inspectable market observations from configured public market sources.
- `raw/text_events.json`: inspectable public text events from configured RSS sources.
- `raw/market_data_views.json`: deterministic OHLCV view metadata for current-run signal inputs.
- `data/market/ohlcv/`: shared finalized OHLCV history when configured.
- `data/market/metadata/ohlcv_schema.json`: shared OHLCV storage schema metadata.
- `data/market/metadata/ohlcv_sync_state.json`: shared OHLCV stored-range metadata.
- `analysis/market_strategy_signals.json`: source-aware quantitative strategy signal output with evidence and uncertainty.
- `analysis/quant_strategy_runs.json`: source-aware strategy run artifact with params, input window, data quality, indicators, signals, assessment, optional bounded backtest and parameter diagnostic summaries, warnings, and failure or insufficient-data state.
- `analysis/market_signals.json`: normalized market signal records for report generation.
- `analysis/market_signal_material.md`: AI-readable quantitative signal material with overview, strategy matrix, confluence and conflict notes, risk and uncertainty notes, report guidance, and bounded input-window context.
- `analysis/market_regime_assessment.json`: deterministic market-state assessment derived from current M2 strategy and market signal artifacts, with regime, confidence, evidence, conflicts, uncertainty, warnings, and source artifacts.
- `analysis/risk_assessment.json`: deterministic risk-state assessment derived from current M2 and market regime artifacts, with risk level, rising risks, blocking risks, data-quality risks, signal-conflict risks, gating fields, evidence, warnings, errors, and source artifacts.
- `analysis/decision_recommendations.json`: deterministic decision-support recommendations derived from current M2, regime, and risk artifacts, with action level, decision bias, confidence, evidence, conflicts, risk conditions, invalidation conditions, do-not-do guidance, warnings, and source artifacts.
- `analysis/market_material.md`: AI-readable market material derived from raw market data.
- `analysis/text_material.md`: AI-readable text material derived from raw text events.
- `analysis/research_context.md`: structured local research context for report generation.
- `codex_context/context.md`: Codex-readable context artifact with artifact index and embedded research context.
- `codex_context/prompt.md`: prompt sent to Codex CLI through stdin, including the fixed run timestamp for the report title and quantitative signal report requirements when signal material exists.
- `report/report.md`: Simplified Chinese Markdown report generated from Codex stdout, with a deterministic quant strategy output table inserted when strategy run artifacts exist.
- `run_manifest.json`: run lifecycle, stage status, artifact paths, counts, Codex status, and errors.

Automated tests use mocks, fixtures, or fake Codex subprocesses only as test behavior. They are not product inputs and are not accepted as proof of a real-source product run.

Run tests:

```bash
python -m pytest
```

## Project Structure

Current structure:

- `AGENTS.md`: root instructions for AI agents.
- `config.example.yaml`: example source-based configuration.
- `data/`: intended shared local market history area; generated contents are ignored by git.
- `docs/`: durable project documentation and reusable implementation contracts.
- `LICENSE`: project license.
- `MILESTONES.md`: active and completed milestones only.
- `pyproject.toml`: Python package metadata and test configuration.
- `README.md`: human-facing overview and structure index.
- `src/halpha/`: Python package.
- `tests/`: focused tests for config, collection, materials, context, Codex runner, and the smoke path.
- `runs/`: intended run artifact area; generated contents are ignored by git.

## Disclaimer

Halpha is a personal research project. It does not provide financial advice, investment recommendations, or trading signals.

