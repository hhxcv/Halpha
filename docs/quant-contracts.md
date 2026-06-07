# Quant Contracts

## Purpose

This document defines Halpha quantitative research contracts.

It is a durable implementation contract, not a milestone-only plan and not an implementation record. The contracts may evolve as shipped behavior grows, but agents should update this document instead of creating parallel milestone-numbered contract files.

Initial adoption implemented the smallest useful slice of this contract for historical OHLCV data, deterministic data views, quantitative signal artifacts, and report-context integration.

Current shipped quant signal flow:

```text
configured market source
  -> historical OHLCV sync
  -> reusable local OHLCV store
  -> deterministic OHLCV data views
  -> quantitative signal evaluation
  -> structured market signal artifacts
  -> AI-readable market signal material
  -> research context
  -> Codex context + prompt
  -> Simplified Chinese Markdown report
```

Strategy research flow contract:

```text
configured market source
  -> historical OHLCV sync
  -> reusable local OHLCV store
  -> deterministic OHLCV data views
  -> strategy run evaluation
  -> quant strategy run artifacts
  -> market strategy signal artifacts
  -> normalized market signal artifacts
  -> AI-readable quant material
  -> research context
  -> Codex context + prompt
  -> Simplified Chinese Markdown report
```

Strategy inputs use raw OHLCV-style data. AI context uses strategy conclusions, normalized signal conclusions, key evidence, bounded input-window context, diagnostics summaries, warnings, and uncertainty notes.

Quant strategy outputs and signals are personal research material. They are not trades, positions, portfolio advice, return forecasts, or financial advice.

## Contract Status

This file separates stable direction from shipped behavior.

- `contract`: expected durable interface or rule.
- `initial adoption`: first implementation slice for the active milestone.
- `not implemented yet`: allowed future contract detail that must not be described as shipped behavior.

README should describe only user-visible behavior that exists. This file may define intended contracts before implementation when they are needed to guide a focused issue.

## Scope

Define contracts for:

- Quant configuration.
- OHLCV schema.
- Shared OHLCV storage layout.
- Strategy data view records.
- Strategy research run artifacts.
- Bounded strategy diagnostics.
- Market strategy signal artifacts.
- Normalized market signal artifacts.
- AI-readable market signal material.
- Research context and Codex context integration.
- Selected technology boundaries.

## Out of Scope

- Code implementation.
- Dependency installation.
- Network fetching.
- Exchange account access.
- Trading execution.
- Order simulation.
- Position records.
- Portfolio automation.
- Backtesting product flow.
- Strategy parameter optimization.
- Machine learning prediction.
- Text event signal processing.
- Real-time market monitoring.
- Database service design.
- Hosted service design.

## Technology Boundaries

Selected tools are implementation aids, not product architecture boundaries.

| Area | Boundary |
| --- | --- |
| Market data access | CCXT may be used only for public OHLCV data. No authenticated endpoints, account state, balances, orders, or trading operations. |
| Strategy calculation | vectorbt may be used for indicators, signal calculation, and bounded research diagnostics. Vectorbt objects are internal implementation details and must not be persisted as stable Halpha artifacts or embedded into AI context. |
| History storage | Hive-style partitioned Parquet may be used as the reusable OHLCV fact store. It is not AI context. |
| Query and cropping | DuckDB may be used to read and crop local Parquet windows. It is not a database service or hosted dependency. |
| Report interface | Halpha-owned strategy run, signal JSON, and Markdown contracts are the stable report-loop interface. |

Do not add a dependency until the current implementation step requires it.

## Dependency Contract

Runtime dependencies should serve the current quant flow. They must not introduce account operations, trading execution, hosted services, dashboard behavior, or unrelated quant frameworks into the product path.

| Dependency | Purpose | Boundary |
| --- | --- | --- |
| `ccxt` | Public OHLCV market data access. | Public market endpoints only. No credentials, balances, orders, or trading operations. |
| `pandas` | In-memory OHLCV data frames for strategy inputs. | Local tabular preparation only. No hidden network or persistence role. |
| `pyarrow` | Parquet read/write support for the shared OHLCV fact store. | File format support only. Not an AI context input. |
| `duckdb` | Local query and cropping layer over stored OHLCV data. | In-process local querying only. No database service assumption. |
| `vectorbt` | Strategy indicator, signal calculation, and bounded research diagnostic support. | Internal implementation helper only. Do not expose vectorbt objects as Halpha artifact contracts or AI context. No portfolio automation, order execution, or trading product flow. |

## Configuration Contract

Quant configuration extends the existing source-based config. The product command remains:

```bash
python -m halpha run --config config.example.yaml
```

Current shipped signal config shape:

```yaml
market:
  enabled: true
  source: binance
  proxy:
    enabled: false
  symbols:
    - BTCUSDT
    - ETHUSDT
  ohlcv:
    storage_dir: data/market/ohlcv
    timeframes:
      - 1d
      - 1h
    lookback:
      1d: 500
      1h: 720

quant:
  enabled: true
  signals:
    - trend
    - momentum
    - volatility
    - volume_anomaly
```

Strategy config contract:

```yaml
quant:
  enabled: true
  engine: vectorbt
  strategies:
    - name: tsmom_vol_scaled
      enabled: true
      params:
        return_window: 20
        volatility_window: 20
        target_volatility: 0.2
      backtest:
        enabled: true
        fees_bps: 10
        slippage_bps: 5
        mode: long_flat
  parameter_diagnostics:
    enabled: false
    max_combinations: 50
```

Validation contract:

- `market.enabled` is required.
- `market.source` is required when `market.enabled` is true.
- `market.source` must be a supported OHLCV market source when `market.ohlcv` exists or `quant.enabled` is true.
- `market.proxy` may be omitted when direct public source access works.
- `market.proxy.enabled` is required when `market.proxy` exists.
- `market.proxy.url` is required when `market.proxy.enabled` is true.
- `market.proxy.url` must be an `http` or `https` proxy URL without embedded credentials.
- Machine-local proxy values must stay in gitignored local config files, not committed examples or docs.
- `market.symbols` must be a non-empty list when `market.enabled` is true.
- `market.ohlcv` may be omitted when quant is not configured.
- `market.ohlcv.storage_dir` is required when `market.ohlcv` exists or `quant.enabled` is true.
- `market.ohlcv.storage_dir` must be outside `run.output_dir`.
- `market.ohlcv.timeframes` must be a non-empty list when `market.ohlcv` exists or `quant.enabled` is true.
- `market.ohlcv.lookback` must define a positive integer for each configured timeframe when `market.ohlcv` exists or `quant.enabled` is true.
- `quant` may be omitted when the report path does not use quant signals.
- `quant.enabled` is required when `quant` exists.
- Current shipped signal config uses `quant.signals`.
- Strategy adoption uses `quant.strategies`.
- `quant.signals` must be a non-empty list when current shipped quant signal config is enabled.
- `quant.strategies` must be a non-empty list when strategy config is enabled.
- Supported signal and strategy names are narrow and explicit. Unknown names fail with an actionable error.
- Strategy records may include per-strategy `params`, `backtest`, and enabled state.
- Strategy-level `backtest` and global `parameter_diagnostics` are optional, bounded research diagnostics, not trading or return-forecast settings.
- Quant config must not require credentials, account settings, trading settings, portfolio settings, or hosted service settings.

Proxy configuration:

Public examples should leave proxy access disabled:

```yaml
market:
  proxy:
    enabled: false
```

Local-only configs may enable proxy access when direct public source access is unavailable:

```yaml
market:
  proxy:
    enabled: true
    url: http://proxy.example:8080
```

Rules:

- Keep real local proxy URLs, ports, hostnames, and private endpoints in gitignored local config files.
- Use placeholder proxy values in docs, tests, issues, PRs, comments, and examples.
- Do not embed proxy credentials in `market.proxy.url`.
- Omit `market.proxy` or set `market.proxy.enabled: false` when direct public source access works.

Initial adoption:

- Add only the config fields required for historical OHLCV sync and basic signal evaluation.
- Keep the existing run command.
- Do not add alternate product commands.

Strategy adoption:

- Keep the existing run command.
- Use `quant.strategies` for strategy-centered quant runs.
- Retire M1 demo signal names from the product strategy path instead of migrating them into strategy aliases.
- Do not provide compatibility aliases for `trend`, `momentum`, `volatility`, or `volume_anomaly` as strategy names.
- Do not add credentials, account operations, trading execution, position sizing, or portfolio automation settings.

## OHLCV Schema Contract

OHLCV rows represent finalized candles from a configured public market source.

Required fields:

| Field | Type | Rule |
| --- | --- | --- |
| `source` | string | Configured public market source name. |
| `symbol` | string | Configured market symbol. |
| `timeframe` | string | Configured candle timeframe. |
| `open_time` | string | Candle open time as ISO 8601 UTC. |
| `open` | number | Candle open price. |
| `high` | number | Candle high price. |
| `low` | number | Candle low price. |
| `close` | number | Candle close price. |
| `volume` | number | Candle volume. |
| `fetched_at` | string | Fetch time as ISO 8601 UTC. |

Uniqueness rule:

```text
source + symbol + timeframe + open_time
```

Ordering rule:

```text
source ASC, symbol ASC, timeframe ASC, open_time ASC
```

Closed-candle rule:

- Store only candles considered closed for their timeframe.
- Exclude the current in-progress candle.
- If source timing is uncertain, mark the uncertainty in sync metadata and signal artifacts.

Data quality rule:

- Do not fabricate missing candles.
- Do not fill prices or volume with synthetic values.
- Deduplicate by the uniqueness rule.
- If duplicate records disagree, keep a deterministic record and preserve the conflict in metadata or pipeline-stage errors.

## Shared OHLCV Storage Contract

Shared OHLCV data lives outside per-run report directories.

Logical layout:

```text
data/
  market/
    ohlcv/
      source=<source>/
        symbol=<symbol>/
          timeframe=<timeframe>/
            year=<yyyy>/
              month=<mm>/
                part-*.parquet
    metadata/
      ohlcv_schema.json
      ohlcv_sync_state.json
```

Storage rules:

- The Parquet dataset stores OHLCV facts only.
- The dataset is reusable across runs.
- The dataset is not embedded into Codex context.
- Partition keys must match row values.
- Writes must preserve deterministic ordering and the OHLCV uniqueness rule.
- Incremental sync must update to the latest available closed candle.

`data/market/metadata/ohlcv_schema.json` contract:

```json
{
  "schema_version": 1,
  "artifact_type": "ohlcv_schema",
  "required_fields": [
    "source",
    "symbol",
    "timeframe",
    "open_time",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "fetched_at"
  ],
  "unique_key": ["source", "symbol", "timeframe", "open_time"],
  "time_format": "iso8601_utc"
}
```

`data/market/metadata/ohlcv_sync_state.json` contract:

```json
{
  "schema_version": 1,
  "artifact_type": "ohlcv_sync_state",
  "updated_at": "2026-06-06T00:00:00Z",
  "items": [
    {
      "source": "binance",
      "symbol": "BTCUSDT",
      "timeframe": "1d",
      "earliest_open_time": "2025-01-22T00:00:00Z",
      "latest_open_time": "2026-06-05T00:00:00Z",
      "row_count": 500,
      "storage_ref": "data/market/ohlcv/source=binance/symbol=BTCUSDT/timeframe=1d",
      "warnings": []
    }
  ]
}
```

Initial adoption:

- Use the shared store for historical OHLCV reuse.
- Keep raw OHLCV history out of Codex context.
- Implement only the fields required by this schema.

## Strategy Data View Contract

Each run records the deterministic OHLCV windows used for signal calculation.

Artifact:

```text
runs/<run_id>/raw/market_data_views.json
```

Top-level contract:

```json
{
  "schema_version": 1,
  "artifact_type": "market_data_views",
  "created_at": "2026-06-06T00:00:00Z",
  "source_artifacts": [
    "data/market/metadata/ohlcv_sync_state.json"
  ],
  "views": []
}
```

View record contract:

```json
{
  "view_id": "ohlcv_view:binance:BTCUSDT:1d:2026-06-05T00:00:00Z",
  "source": "binance",
  "symbol": "BTCUSDT",
  "timeframe": "1d",
  "requested_lookback": 500,
  "input_window_start": "2025-01-22T00:00:00Z",
  "input_window_end": "2026-06-05T00:00:00Z",
  "latest_candle_time": "2026-06-05T00:00:00Z",
  "row_count": 500,
  "storage_ref": "data/market/ohlcv/source=binance/symbol=BTCUSDT/timeframe=1d",
  "included_columns": [
    "open_time",
    "open",
    "high",
    "low",
    "close",
    "volume"
  ],
  "insufficient_data": false,
  "warnings": []
}
```

Rules:

- The view artifact records windows and storage references, not full OHLCV history.
- `input_window_start`, `input_window_end`, and `latest_candle_time` must come from actual stored rows.
- `row_count` must reflect rows available to the evaluator.
- Configured lookback defines the current-run data view window, not the shared storage retention policy.
- Shared storage may retain more historical rows than the configured lookback so later runs can reuse history.
- If data is insufficient, record `insufficient_data: true` and an actionable warning.

## Strategy Research Run Artifact Contract

Strategy run artifacts are the primary quantitative research output for strategy-centered quant flow.

Artifact:

```text
runs/<run_id>/analysis/quant_strategy_runs.json
```

Top-level contract:

```json
{
  "schema_version": 1,
  "artifact_type": "quant_strategy_runs",
  "created_at": "2026-06-06T00:00:00Z",
  "engine": {
    "name": "vectorbt",
    "version": "0.28.0",
    "objects_exposed": false
  },
  "source_artifacts": [
    "raw/market_data_views.json"
  ],
  "runs": []
}
```

Run record contract:

```json
{
  "strategy_run_id": "quant_strategy_run:tsmom_vol_scaled:binance:BTCUSDT:1d:2026-06-05T00:00:00Z",
  "status": "succeeded",
  "strategy_name": "tsmom_vol_scaled",
  "strategy_version": 1,
  "engine": {
    "name": "vectorbt",
    "version": "0.28.0"
  },
  "source": "binance",
  "symbol": "BTCUSDT",
  "timeframe": "1d",
  "input_view_id": "ohlcv_view:binance:BTCUSDT:1d:2026-06-05T00:00:00Z",
  "input_window_start": "2025-01-22T00:00:00Z",
  "input_window_end": "2026-06-05T00:00:00Z",
  "latest_candle_time": "2026-06-05T00:00:00Z",
  "params": {
    "return_window": 20,
    "volatility_window": 20,
    "target_volatility": 0.2
  },
  "data_quality": {
    "row_count": 500,
    "requested_lookback": 500,
    "minimum_required_rows": 40,
    "sufficient_data": true,
    "missing_row_policy": "do_not_fabricate",
    "warnings": []
  },
  "indicators": {
    "return_window_pct": 7.25,
    "realized_volatility_pct": 31.4,
    "volatility_scaled_exposure": 0.64
  },
  "signals": {
    "latest_regime": "risk_on_momentum",
    "entry_count": 12,
    "exit_count": 11,
    "latest_entry": false,
    "latest_exit": false
  },
  "backtest_diagnostic": {
    "enabled": true,
    "status": "succeeded",
    "assumptions": {
      "fees_bps": 10,
      "slippage_bps": 5,
      "mode": "long_flat",
      "price_source": "close",
      "execution_timing": "research_close_to_close"
    },
    "window": {
      "start": "2025-01-22T00:00:00Z",
      "end": "2026-06-05T00:00:00Z",
      "rows": 500
    },
    "metrics": {
      "total_return_pct": 12.4,
      "max_drawdown_pct": -18.2,
      "trade_count": 23,
      "exposure_pct": 56.0,
      "final_equity": 11240.0
    },
    "warnings": [
      "Backtest diagnostic is historical research material, not a return forecast."
    ]
  },
  "parameter_diagnostic": {
    "enabled": false,
    "status": "disabled"
  },
  "assessment": {
    "direction": "bullish",
    "strength": "medium",
    "confidence": "medium",
    "summary": "Positive time-series momentum is present, but realized volatility keeps confidence bounded.",
    "evidence": [
      "return_window_pct is positive over the configured window.",
      "volatility_scaled_exposure is below full exposure because realized volatility is elevated."
    ],
    "uncertainty": [
      "Strategy uses OHLCV price history only and excludes text events.",
      "Historical diagnostic does not predict future returns."
    ]
  },
  "warnings": [],
  "error": null,
  "source_artifacts": [
    "raw/market_data_views.json"
  ],
  "created_at": "2026-06-06T00:00:00Z"
}
```

Required run fields:

| Field | Rule |
| --- | --- |
| `strategy_run_id` | Deterministic for strategy name, source, symbol, timeframe, latest candle, and relevant parameter identity. |
| `status` | One of `succeeded`, `insufficient_data`, `failed`, `skipped`, or `disabled`. |
| `strategy_name` | Explicit built-in strategy name. Not a free-form user label. |
| `strategy_version` | Halpha-owned strategy contract version, not a dependency version. |
| `engine` | Engine metadata only. Do not persist engine objects. |
| `source`, `symbol`, `timeframe` | Must match the input data view and source rows. |
| `input_view_id`, `input_window_start`, `input_window_end`, `latest_candle_time` | Must come from `raw/market_data_views.json`. |
| `params` | Effective strategy parameters used for this run. Defaults must be materialized. |
| `data_quality` | Row counts, sufficiency, minimum requirements, missing-row policy, and warnings. |
| `indicators` | Bounded calculated values needed to inspect the strategy result. Do not dump full indicator series. |
| `signals` | Bounded signal summary such as latest regime, entry or exit counts, and latest signal flags. These are not orders. |
| `backtest_diagnostic` | Optional bounded historical diagnostic with assumptions and limits. |
| `parameter_diagnostic` | Optional bounded sensitivity diagnostic with limits and assumptions. |
| `assessment` | Report-facing direction, strength, confidence, evidence, and uncertainty. |
| `warnings` | Actionable data, method, parameter, risk, or conflict warnings. |
| `error` | Null for successful runs. Required for `failed` runs. |
| `source_artifacts` | Must include the data view artifact and any generated upstream artifact references. |
| `created_at` | ISO 8601 UTC timestamp. |

Run status rules:

- `succeeded`: Strategy calculated indicators, signals, and assessment from sufficient data.
- `insufficient_data`: Strategy did not have enough input rows or required fields. Preserve input metadata. Do not fabricate indicators, signals, or diagnostics.
- `failed`: Strategy execution raised an actionable error. Preserve strategy name, input view, params, and a bounded error summary.
- `skipped`: Strategy was not run because an upstream stage was unavailable or disabled.
- `disabled`: Strategy existed in config but was disabled before execution.

Insufficient data representation:

```json
{
  "status": "insufficient_data",
  "data_quality": {
    "row_count": 12,
    "requested_lookback": 500,
    "minimum_required_rows": 40,
    "sufficient_data": false,
    "missing_row_policy": "do_not_fabricate",
    "warnings": [
      "Only 12 rows are available; tsmom_vol_scaled requires at least 40 rows."
    ]
  },
  "indicators": {},
  "signals": {},
  "backtest_diagnostic": {
    "enabled": true,
    "status": "skipped",
    "warnings": [
      "Backtest diagnostic skipped because input data is insufficient."
    ]
  },
  "assessment": {
    "direction": "unknown",
    "strength": "unknown",
    "confidence": "low",
    "summary": "Strategy result is unavailable because input data is insufficient.",
    "evidence": [
      "input view has 12 OHLCV rows."
    ],
    "uncertainty": [
      "Insufficient data prevents strategy assessment."
    ]
  }
}
```

Failure representation:

```json
{
  "status": "failed",
  "error": {
    "error_type": "StrategyExecutionError",
    "message": "return_window must be lower than available row count.",
    "stage": "evaluate_quant_strategies"
  },
  "assessment": {
    "direction": "unknown",
    "strength": "unknown",
    "confidence": "low",
    "summary": "Strategy run failed before assessment.",
    "evidence": [],
    "uncertainty": [
      "No strategy conclusion is available because execution failed."
    ]
  }
}
```

Warning contract:

```json
{
  "severity": "warning",
  "code": "high_realized_volatility",
  "message": "Realized volatility is elevated relative to the target volatility assumption.",
  "source": "strategy"
}
```

Warning rules:

- `severity` is one of `info`, `warning`, or `error`.
- `code` is stable enough for tests and downstream summaries.
- `message` must be actionable and must not include secrets or local privacy values.
- `source` identifies the emitting layer, such as `data_quality`, `strategy`, `backtest_diagnostic`, or `parameter_diagnostic`.

Vectorbt boundary rules:

- Vectorbt may calculate indicators, signals, and bounded diagnostics.
- Vectorbt objects are internal implementation details.
- Halpha-owned JSON and Markdown artifacts are the stable downstream interface.
- Do not persist vectorbt objects, repr strings, internal class names, or raw portfolio objects as artifact fields.
- Do not embed vectorbt objects or large raw OHLCV series in AI-readable material.

Bounded backtest diagnostic rules:

- Backtest diagnostics are historical research material, not return forecasts.
- Diagnostics must record assumptions before metrics.
- Required assumptions include fees, slippage, mode, price source, execution timing, and input data window.
- Metrics must stay narrow and reviewable. Suggested metrics are `total_return_pct`, `max_drawdown_pct`, `trade_count`, `exposure_pct`, and `final_equity`.
- Diagnostics must not emit trading instructions, live orders, position sizing, account actions, or guaranteed outcomes.
- Diagnostics may be `disabled`, `skipped`, `succeeded`, or `failed`.

Parameter diagnostic rules:

- Parameter diagnostics are optional and disabled unless configured.
- Diagnostics must record tested ranges, tested count, valid count, invalid count, max-combinations limit, assumptions, and stability notes.
- Diagnostics must summarize sensitivity and fragility, not select trading parameters automatically.
- Diagnostics must not create a strategy leaderboard or investment recommendation.

Strategy names:

- Strategy-centered flow uses explicit built-in strategy names such as `tsmom_vol_scaled`, `breakout_atr_trend`, and `bollinger_rsi_reversion`.
- Initial implemented strategy-centered flow supports `tsmom_vol_scaled`.
- The M1 demo signal names `trend`, `momentum`, `volatility`, and `volume_anomaly` are retired from the strategy-centered product path.
- Retired demo names are not migrated into strategy aliases.
- If an old demo name is requested after strategy adoption, config validation should fail with an actionable error.

Downstream consumers:

| Consumer | Input | Rule |
| --- | --- | --- |
| `analysis/market_strategy_signals.json` | `analysis/quant_strategy_runs.json` | Maps strategy run assessments into report-loop strategy signals. Preserve strategy name, input window, evidence, uncertainty, insufficient-data state, warnings, and source artifacts. |
| `analysis/market_signals.json` | `analysis/market_strategy_signals.json` | Normalizes strategy signals into the existing report interface. |
| `analysis/market_signal_material.md` | Strategy runs and normalized market signals | Summarizes strategy conclusions, diagnostics, conflicts, risks, and uncertainty without embedding large OHLCV history. |
| `analysis/research_context.md` | AI-readable quant material | Adds bounded quant material to the report context. |
| `codex_context/context.md` and `codex_context/prompt.md` | Research context and prompt rules | Require Codex CLI to use upstream strategy conclusions and not derive new quant conclusions from raw OHLCV. |
| `run_manifest.json` | Strategy run artifacts and pipeline statuses | Records artifact paths, counts, failures, insufficient-data runs, enabled strategies, disabled strategies, and assumptions summaries. |

## Market Strategy Signal Artifact Contract

Strategy signal artifacts store quantitative output before report-loop normalization.

Current shipped signal flow writes these records directly from initial evaluators. Strategy-centered flow writes these records from `analysis/quant_strategy_runs.json` assessments.

Artifact:

```text
runs/<run_id>/analysis/market_strategy_signals.json
```

Top-level contract:

```json
{
  "schema_version": 1,
  "artifact_type": "market_strategy_signals",
  "created_at": "2026-06-06T00:00:00Z",
  "source_artifacts": [
    "analysis/quant_strategy_runs.json",
    "raw/market_data_views.json"
  ],
  "signals": []
}
```

Signal record contract:

```json
{
  "strategy_signal_id": "strategy_signal:trend:binance:BTCUSDT:1d:2026-06-05T00:00:00Z",
  "strategy_name": "trend",
  "source": "binance",
  "symbol": "BTCUSDT",
  "timeframe": "1d",
  "input_view_id": "ohlcv_view:binance:BTCUSDT:1d:2026-06-05T00:00:00Z",
  "input_window_start": "2025-01-22T00:00:00Z",
  "input_window_end": "2026-06-05T00:00:00Z",
  "latest_candle_time": "2026-06-05T00:00:00Z",
  "direction": "bullish",
  "strength": "medium",
  "confidence": "medium",
  "key_values": {
    "latest_close": 104000.0,
    "moving_average_short": 101000.0,
    "moving_average_long": 97000.0
  },
  "evidence": [
    "latest_close is above moving_average_short",
    "moving_average_short is above moving_average_long"
  ],
  "uncertainty": [
    "Signal uses price history only and does not include text events."
  ],
  "insufficient_data": false,
  "source_artifacts": [
    "raw/market_data_views.json"
  ],
  "created_at": "2026-06-06T00:00:00Z"
}
```

Strategy run mapping rules:

| Market strategy signal field | Strategy run source |
| --- | --- |
| `strategy_signal_id` | Deterministic ID derived from strategy name, source, symbol, timeframe, and latest candle. |
| `strategy_name` | `strategy_run.strategy_name`. |
| `source`, `symbol`, `timeframe` | Strategy run market identity fields. |
| `input_view_id`, `input_window_start`, `input_window_end`, `latest_candle_time` | Strategy run input view fields. |
| `direction`, `strength`, `confidence` | `strategy_run.assessment` values. |
| `key_values` | Bounded values selected from strategy run `indicators`, `signals`, and diagnostics summaries. |
| `evidence` | `strategy_run.assessment.evidence`. |
| `uncertainty` | `strategy_run.assessment.uncertainty` plus relevant warning messages. |
| `insufficient_data` | True when strategy run status is `insufficient_data`. |
| `source_artifacts` | Must include `analysis/quant_strategy_runs.json` and `raw/market_data_views.json`. |

Mapping rules:

- Current shipped direct evaluator flow may use `raw/market_data_views.json` as the only source artifact.
- Strategy-centered flow must include `analysis/quant_strategy_runs.json` and `raw/market_data_views.json` as source artifacts.
- Do not expose vectorbt objects or raw indicator series.
- Do not convert backtest metrics into forecasts.
- Preserve failed and insufficient-data strategy runs as low-confidence `unknown` signals when downstream material needs to explain missing conclusions.
- Preserve warnings that affect report interpretation.
- A strategy signal remains research material, not a trade, position, or investment recommendation.

Allowed direction values:

```text
bullish
bearish
neutral
mixed
unknown
```

Allowed strength values:

```text
low
medium
high
unknown
```

Allowed confidence values:

```text
low
medium
high
unknown
```

Current shipped initial signal names are explicit and narrow:

```text
trend
momentum
volatility
volume_anomaly
```

Strategy-centered signal names are produced from strategy run names. Initial strategy contract names include:

```text
tsmom_vol_scaled
breakout_atr_trend
bollinger_rsi_reversion
```

Rules:

- Evidence must refer to calculated values or actual input-window facts.
- Uncertainty must be explicit when data is thin, stale, missing, or method-limited.
- Volatility signals should include close-to-close variation and candle range values where OHLCV high/low data is available.
- Volume anomaly signals should compare the latest volume with the previous input-window average.
- If an unimplemented strategy request reaches signal evaluation, emit an explicit low-confidence `insufficient_data: true` record instead of fabricating values or silently dropping it.
- A strategy signal must not include trade entries, exits, position sizing, expected returns, or backtest performance.
- `insufficient_data: true` is a valid evaluator output and must not be hidden.

## Normalized Market Signal Artifact Contract

Normalized market signals are the Halpha-owned interface for report generation.

In strategy-centered flow, normalized market signals summarize strategy-run-derived market strategy signals. They keep the report interface stable while allowing the quant layer to evolve.

Artifact:

```text
runs/<run_id>/analysis/market_signals.json
```

Top-level contract:

```json
{
  "schema_version": 1,
  "artifact_type": "market_signals",
  "created_at": "2026-06-06T00:00:00Z",
  "source_artifacts": [
    "analysis/market_strategy_signals.json",
    "analysis/quant_strategy_runs.json"
  ],
  "signals": []
}
```

Signal record contract:

```json
{
  "signal_id": "market_signal:trend:binance:BTCUSDT:1d:2026-06-05T00:00:00Z",
  "strategy_name": "trend",
  "source": "binance",
  "symbol": "BTCUSDT",
  "timeframe": "1d",
  "input_window_start": "2025-01-22T00:00:00Z",
  "input_window_end": "2026-06-05T00:00:00Z",
  "latest_candle_time": "2026-06-05T00:00:00Z",
  "direction": "bullish",
  "strength": "medium",
  "confidence": "medium",
  "key_values": {
    "latest_close": 104000.0,
    "moving_average_short": 101000.0,
    "moving_average_long": 97000.0
  },
  "evidence": [
    "latest_close is above moving_average_short",
    "moving_average_short is above moving_average_long"
  ],
  "uncertainty": [
    "Signal uses price history only and does not include text events."
  ],
  "insufficient_data": false,
  "source_artifacts": [
    "analysis/market_strategy_signals.json",
    "raw/market_data_views.json"
  ],
  "created_at": "2026-06-06T00:00:00Z"
}
```

Rules:

- `signal_id` must be deterministic for the same source, symbol, timeframe, strategy, and latest candle.
- Normalization may drop evaluator-specific fields that are not useful for report generation.
- Normalization must preserve source, input window, key values, evidence, uncertainty, and insufficient-data state.
- Normalization must preserve source artifact references to `analysis/quant_strategy_runs.json` when strategy runs are the upstream source.
- Diagnostics may be summarized through bounded `key_values`, `evidence`, or `uncertainty`. Do not copy full diagnostics when they would make AI context large or misleading.
- Failed strategy runs that become market signals must use `direction: unknown`, `strength: unknown`, and low confidence.
- Normalized signals remain research material, not trading instructions.

## AI-Readable Market Signal Material Contract

AI-readable market signal material is the bounded signal context for Codex CLI.

Artifact:

```text
runs/<run_id>/analysis/market_signal_material.md
```

Strategy-centered material rules:

- Include strategy conclusions from `analysis/quant_strategy_runs.json` only as bounded summaries.
- Include normalized market signals from `analysis/market_signals.json`.
- Include strategy name, version, params summary, input window, latest candle, direction, strength, confidence, key evidence, warnings, and uncertainty when available.
- Include bounded backtest diagnostic summaries only with assumptions and research-material disclaimers.
- Identify confluence when multiple strategies support the same direction for the same source, symbol, and timeframe.
- Identify conflicts when strategies disagree, when confidence is low, when diagnostics conflict with latest-state signals, or when data is insufficient.
- Identify risk and uncertainty near the related strategy conclusion.
- Preserve source artifact references.
- Do not embed large raw OHLCV history.
- Do not embed vectorbt objects or internal dependency objects.
- Do not ask Codex CLI to infer new strategy conclusions from raw OHLCV.
- Do not include trading instructions, position sizing, account actions, return promises, or investment recommendations.

Recommended format:

````markdown
---
artifact_type: analysis_market_signal_material
schema_version: 1
audience: ai
source_artifacts:
  - analysis/quant_strategy_runs.json
  - analysis/market_signals.json
  - raw/market_data_views.json
---

# market_signal_material

## source_policy

```yaml
signal_material_is_financial_advice: false
trading_instructions_allowed: false
raw_ohlcv_history_embedded: false
vectorbt_objects_embedded: false
backtest_diagnostics_are_forecasts: false
allowed_basis:
  - quant_strategy_runs
  - normalized_market_signals
  - bounded_input_window_metadata
  - bounded_diagnostic_summaries
  - key_values
  - evidence
  - uncertainty
```

## record: market_signal:trend:binance:BTCUSDT:1d:2026-06-05T00:00:00Z

```yaml
record_type: market_signal
signal_id: market_signal:trend:binance:BTCUSDT:1d:2026-06-05T00:00:00Z
strategy_name: trend
source: binance
symbol: BTCUSDT
timeframe: 1d
input_window_start: 2025-01-22T00:00:00Z
input_window_end: 2026-06-05T00:00:00Z
latest_candle_time: 2026-06-05T00:00:00Z
direction: bullish
strength: medium
confidence: medium
key_values:
  latest_close: 104000.0
  moving_average_short: 101000.0
  moving_average_long: 97000.0
evidence:
  - latest_close is above moving_average_short
  - moving_average_short is above moving_average_long
uncertainty:
  - Signal uses price history only and does not include text events.
insufficient_data: false
source_artifacts:
  - analysis/market_signals.json
  - raw/market_data_views.json
```
````

Rules:

- Include signal conclusions, key values, evidence, input-window metadata, and uncertainty.
- Include strategy conclusions, diagnostics summaries, conflict notes, risk notes, and warnings when strategy run artifacts exist.
- Do not embed large OHLCV history.
- Do not embed vectorbt objects.
- Do not ask Codex CLI to derive quantitative conclusions from raw OHLCV history.
- Do not present historical diagnostics as forecasts.
- Do not include trades, positions, expected returns, trading instructions, position sizing, account actions, or investment advice.

## Research Context and Codex Context Integration

Quant signal material may be added to the existing report context when signal artifacts exist.

`analysis/research_context.md` contract additions:

```yaml
quant_strategy_runs: analysis/quant_strategy_runs.json
market_signal_material: analysis/market_signal_material.md
market_signals: analysis/market_signals.json
market_data_views: raw/market_data_views.json
```

Research context rules:

- Embed or reference `analysis/market_signal_material.md`.
- Preserve existing market and text material.
- Keep the source policy explicit.
- State that market signals are research material, not financial advice.
- State that strategy diagnostics are historical research material, not forecasts.
- State when quantitative signals do not include text-event signal processing.

`codex_context/context.md` contract additions:

```yaml
quant_strategy_runs: analysis/quant_strategy_runs.json
market_signal_material: analysis/market_signal_material.md
market_signals: analysis/market_signals.json
market_data_views: raw/market_data_views.json
```

Codex prompt rules:

- Require a Simplified Chinese Markdown report.
- Require quantitative strategy conclusions when strategy material exists.
- Require evidence and uncertainty near strategy conclusions.
- Require conflict notes, watch points, and risk notes.
- Require backtest diagnostics to be described as historical research material when cited.
- Forbid fabricated prices, sources, strategy conclusions, signals, or certainty.
- Forbid trading instructions, position sizing, account actions, and investment recommendations.
- Forbid return promises or deterministic investment claims.
- Do not direct Codex CLI to inspect shared OHLCV storage.

## Run Manifest Contract Additions

When OHLCV sync runs, `run_manifest.json` records the sync result.

OHLCV sync keys:

```json
{
  "artifacts": {
    "ohlcv_schema": "data/market/metadata/ohlcv_schema.json",
    "ohlcv_sync_state": "data/market/metadata/ohlcv_sync_state.json"
  },
  "counts": {
    "ohlcv_sync_items": 4,
    "ohlcv_records_fetched": 12,
    "ohlcv_records_stored": 8,
    "ohlcv_records_skipped": 4,
    "ohlcv_sync_errors": 0
  },
  "ohlcv_sync": {
    "schema_version": 1,
    "artifact_type": "ohlcv_sync",
    "status": "succeeded",
    "source": "binance",
    "storage_dir": "data/market/ohlcv",
    "metadata": {
      "ohlcv_schema": "data/market/metadata/ohlcv_schema.json",
      "ohlcv_sync_state": "data/market/metadata/ohlcv_sync_state.json"
    },
    "items": [
      {
        "status": "succeeded",
        "mode": "incremental",
        "source": "binance",
        "symbol": "BTCUSDT",
        "timeframe": "1d",
        "configured_lookback": 500,
        "existing_count": 499,
        "requested_since_open_time": "2026-06-05T00:00:00Z",
        "requested_limit": 501,
        "fetched_count": 1,
        "stored_count": 1,
        "skipped_count": 0,
        "stored_range": {
          "earliest_open_time": "2025-01-22T00:00:00Z",
          "latest_open_time": "2026-06-05T00:00:00Z",
          "row_count": 500
        },
        "latest_closed_candle": "2026-06-05T00:00:00Z",
        "warnings": [],
        "errors": []
      }
    ],
    "totals": {
      "items": 4,
      "fetched_count": 12,
      "stored_count": 8,
      "skipped_count": 4,
      "error_count": 0
    },
    "warnings": [],
    "errors": []
  }
}
```

OHLCV sync rules:

- Omit network OHLCV fetching when `market.ohlcv` is not configured.
- Initial backfill stores only finalized candles and trims to the configured lookback.
- Incremental sync requests from the next missing candle when existing shared history is present.
- Merge writes must keep shared history deduplicated and deterministically ordered.
- Sync failures must leave existing shared history inspectable and record actionable errors.
- Product sync must not emit fake OHLCV records.

When data views are created, `run_manifest.json` should record them:

```json
{
  "artifacts": {
    "market_data_views": "raw/market_data_views.json"
  },
  "counts": {
    "market_data_views": 4,
    "market_data_views_insufficient_data": 0
  }
}
```

When strategy runs are created, `run_manifest.json` should record them.

Artifact keys:

```json
{
  "artifacts": {
    "quant_strategy_runs": "analysis/quant_strategy_runs.json"
  },
  "counts": {
    "quant_strategy_runs": 8,
    "quant_strategy_runs_succeeded": 6,
    "quant_strategy_runs_failed": 1,
    "quant_strategy_runs_insufficient_data": 1,
    "quant_strategy_runs_skipped": 0,
    "quant_strategy_runs_disabled": 0
  },
  "quant_strategies": {
    "engine": {
      "name": "vectorbt",
      "version": "0.28.0"
    },
    "enabled": [
      "tsmom_vol_scaled"
    ],
    "disabled": [],
    "backtest_diagnostics_enabled": true,
    "parameter_diagnostics_enabled": false,
    "failures": [
      {
        "strategy_name": "tsmom_vol_scaled",
        "source": "binance",
        "symbol": "BTCUSDT",
        "timeframe": "1d",
        "input_view_id": "ohlcv_view:binance:BTCUSDT:1d:2026-06-05T00:00:00Z",
        "message": "return_window must be lower than available row count."
      }
    ],
    "insufficient_data": [
      {
        "strategy_name": "tsmom_vol_scaled",
        "source": "binance",
        "symbol": "ETHUSDT",
        "timeframe": "1h",
        "input_view_id": "ohlcv_view:binance:ETHUSDT:1h:2026-06-05T00:00:00Z",
        "row_count": 12,
        "minimum_required_rows": 40
      }
    ]
  }
}
```

Manifest strategy rules:

- Record artifact paths and counts without embedding the full strategy run artifact.
- Count insufficient-data runs separately from failed runs.
- Record enabled and disabled strategy names.
- Record bounded engine metadata when available.
- Record failure summaries with strategy name, source, symbol, timeframe, input view, and actionable message.
- Do not record stack traces, secrets, local proxy values, local paths outside repo artifacts, credentials, tokens, cookies, account IDs, or private endpoints.

When implementation creates signal artifacts, `run_manifest.json` should record them.

Artifact keys:

```json
{
  "artifacts": {
    "market_data_views": "raw/market_data_views.json",
    "quant_strategy_runs": "analysis/quant_strategy_runs.json",
    "market_strategy_signals": "analysis/market_strategy_signals.json",
    "market_signals": "analysis/market_signals.json",
    "market_signal_material": "analysis/market_signal_material.md"
  },
  "counts": {
    "market_data_views": 4,
    "quant_strategy_runs": 16,
    "quant_strategy_runs_succeeded": 16,
    "market_strategy_signals": 16,
    "market_strategy_signals_insufficient_data": 0,
    "market_signals": 16,
    "market_signals_insufficient_data": 0,
    "market_signal_material_records": 16
  }
}
```

Pipeline stage names:

```text
sync_ohlcv
build_market_data_views
evaluate_quant_strategies
evaluate_market_strategy_signals
build_market_signals
build_market_signal_material
```

Failure rules:

- Preserve artifacts from completed pipeline stages.
- Record failed pipeline stage and actionable error.
- Do not write fake signal artifacts to make downstream pipeline stages appear complete.

## Acceptance Trace

- A focused quant contract document exists: this file.
- Config, OHLCV, data view, strategy run, strategy signal, market signal, and AI-readable material contracts are defined above.
- Strategy inputs use raw OHLCV-style data; AI context uses strategy conclusions, normalized signal conclusions, diagnostics summaries, warnings, and bounded market context.
- Quant signals and strategy diagnostics are research material, not trades, positions, return forecasts, or financial advice.
- `analysis/quant_strategy_runs.json` fields and downstream consumers are defined above.
- Vectorbt objects are internal implementation details and are not stable artifact fields or AI context.
- Backtest diagnostics are bounded historical research material, not return forecasts.
- Insufficient data, strategy failure, and warnings have explicit artifact representation rules.
- M1 demo signal names are retired from strategy-centered flow instead of migrated into strategy aliases.
- This document states initial adoption scope without making the contract milestone-only.
- This document separates current signal contracts from not-yet-implemented extensions.
