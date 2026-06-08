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
- Initial trend, momentum, volatility/range risk, and volume anomaly signal evaluation from OHLCV data views.
- `analysis/market_strategy_signals.json` artifact creation when `quant.enabled` is true.
- `analysis/market_signals.json` normalized market signal artifact creation when `quant.enabled` is true.
- `analysis/market_signal_material.md` AI-readable market signal material creation when `quant.enabled` is true.
- Strategy-oriented quant config support through `quant.strategies` for `tsmom_vol_scaled`.
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
- Codex prompt requirements for quantitative signal conclusions, evidence, watch points, and risk notes when market signal material exists.
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

`config.example.yaml` uses public source configuration:

- Binance public market data for configured symbols.
- RSS feeds for configured public text sources.
- Codex CLI command and arguments for final report generation.

Required local environment:

- Public network access for configured market and RSS sources.
- A working Codex CLI on `PATH`.
- Codex CLI authentication configured outside this repository.
- Permission for Codex CLI to receive the generated local prompt through stdin.

If a local proxy is needed for public market access, keep it in a gitignored local config file and enable `market.proxy` there:

```yaml
market:
  proxy:
    enabled: true
    url: http://proxy.example:8080
```

Do not commit machine-local proxy values, credentials, hostnames, ports, or paths.

## Quantitative Signal Report Path

When `market.ohlcv` is configured and `quant.enabled` is true, the implemented run command extends the report loop with quantitative market signal material:

```text
configured public market source
-> finalized OHLCV sync
-> shared local OHLCV history
-> deterministic current-run OHLCV data views
-> trend, momentum, volatility, and volume anomaly signal evaluation
-> normalized market signal artifacts
-> AI-readable market signal material
-> research context and Codex prompt
-> Simplified Chinese Markdown report
```

The shared OHLCV store is reusable local input history. It is not AI context. Current-run data views record deterministic input windows and storage references, not full raw OHLCV history. Codex receives market signal material with bounded input-window metadata, key values, evidence, and uncertainty.

Implemented quantitative signal behavior:

- `trend`: compares the latest close and short moving average with the long moving average.
- `momentum`: compares the latest close with the first and previous closes in the selected window.
- `volatility`: measures close-to-close variation and candle range risk.
- `volume_anomaly`: compares latest volume with the previous-window average volume.

Signal artifacts preserve source, symbol, timeframe, input window, direction, strength, confidence, key values, evidence, uncertainty, source artifacts, and insufficient-data state where applicable. Quantitative signals are personal research material. They are not trades, positions, backtest results, forecasts, or financial advice.

## Quant Strategy Foundation Path

When `market.ohlcv` is configured and `quant.enabled` uses `quant.strategies`, the implemented run command can run the first M2 strategy path:

```text
configured public market source
-> finalized OHLCV sync
-> shared local OHLCV history
-> deterministic current-run OHLCV data views
-> tsmom_vol_scaled strategy run evaluation
-> quant_strategy_runs artifact
-> downstream market strategy signal artifacts
-> existing market signal material and report context
```

Implemented strategy behavior:

- `tsmom_vol_scaled`: uses vectorbt `IndicatorFactory` to calculate time-series momentum return and active signals over a configured return window, then records realized volatility, target volatility, volatility-scaled exposure, latest regime, signal counts, assessment, warnings, and bounded diagnostics metadata.

Strategy run artifacts preserve strategy name, version, engine metadata, params, source, symbol, timeframe, input window, data quality, indicators, signals, assessment, diagnostics metadata, warnings, source artifacts, and insufficient-data or failure state. Vectorbt objects are internal implementation details and are not written into Halpha artifacts or Codex context.

Expected result in a properly configured online environment: writes `raw/market.json`, `raw/text_events.json`, `analysis/market_material.md`, `analysis/text_material.md`, `analysis/research_context.md`, `codex_context/context.md`, `codex_context/prompt.md`, `report/report.md`, and `run_manifest.json`. When `market.ohlcv` is configured, the run also updates shared OHLCV history and metadata under the configured storage location and writes `raw/market_data_views.json` for the current run. When `quant.enabled` is true, the run writes `analysis/market_strategy_signals.json`, `analysis/market_signals.json`, and `analysis/market_signal_material.md`. When `quant.strategies` is configured, the run also writes `analysis/quant_strategy_runs.json` before downstream market signal artifacts. If collection, OHLCV sync, data view creation, strategy run evaluation, strategy signal evaluation, market signal material generation, or Codex execution fails, artifacts created before the failure and `run_manifest.json` record the failure without fake records or a placeholder report.

Output artifact roles:

- `raw/market.json`: inspectable market observations from configured public market sources.
- `raw/text_events.json`: inspectable public text events from configured RSS sources.
- `raw/market_data_views.json`: deterministic OHLCV view metadata for current-run signal inputs.
- `data/market/ohlcv/`: shared finalized OHLCV history when configured.
- `data/market/metadata/ohlcv_schema.json`: shared OHLCV storage schema metadata.
- `data/market/metadata/ohlcv_sync_state.json`: shared OHLCV stored-range metadata.
- `analysis/market_strategy_signals.json`: source-aware quantitative strategy signal output with evidence and uncertainty.
- `analysis/quant_strategy_runs.json`: source-aware strategy run artifact with params, input window, data quality, indicators, signals, assessment, diagnostics metadata, warnings, and failure or insufficient-data state.
- `analysis/market_signals.json`: normalized market signal records for report generation.
- `analysis/market_signal_material.md`: AI-readable quantitative signal material with bounded input-window context.
- `analysis/market_material.md`: AI-readable market material derived from raw market data.
- `analysis/text_material.md`: AI-readable text material derived from raw text events.
- `analysis/research_context.md`: structured local research context for report generation.
- `codex_context/context.md`: Codex-readable context artifact with artifact index and embedded research context.
- `codex_context/prompt.md`: prompt sent to Codex CLI through stdin, including quantitative signal report requirements when signal material exists.
- `report/report.md`: Simplified Chinese Markdown report generated from Codex stdout.
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

