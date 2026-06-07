# Quant Contracts

## Purpose

This document defines Halpha quantitative signal contracts.

It is a durable implementation contract, not a milestone-only plan and not an implementation record. The contracts may evolve as shipped behavior grows, but agents should update this document instead of creating parallel milestone-numbered contract files.

Initial adoption should implement the smallest useful slice of this contract for historical OHLCV data, deterministic data views, quantitative signal artifacts, and report-context integration.

Quant flow:

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

Strategy inputs use raw OHLCV-style data. AI context uses signal conclusions, key evidence, bounded recent market context, and uncertainty notes.

Quant signals are personal research material. They are not trades, positions, portfolio advice, backtest performance claims, or financial advice.

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
| Signal calculation | vectorbt may be used for indicators and basic signal calculation. Do not introduce portfolio or backtest product flow. |
| History storage | Hive-style partitioned Parquet may be used as the reusable OHLCV fact store. It is not AI context. |
| Query and cropping | DuckDB may be used to read and crop local Parquet windows. It is not a database service or hosted dependency. |
| Report interface | Halpha-owned signal JSON and Markdown contracts are the stable report-loop interface. |

Do not add a dependency until the current implementation step requires it.

## Dependency Contract

Runtime dependencies should serve the current quant flow. They must not introduce account operations, trading execution, hosted services, dashboard behavior, or unrelated quant frameworks into the product path.

| Dependency | Purpose | Boundary |
| --- | --- | --- |
| `ccxt` | Public OHLCV market data access. | Public market endpoints only. No credentials, balances, orders, or trading operations. |
| `pandas` | In-memory OHLCV data frames for strategy inputs. | Local tabular preparation only. No hidden network or persistence role. |
| `pyarrow` | Parquet read/write support for the shared OHLCV fact store. | File format support only. Not an AI context input. |
| `duckdb` | Local query and cropping layer over stored OHLCV data. | In-process local querying only. No database service assumption. |
| `vectorbt` | Indicator and basic signal calculation support. | No portfolio automation, order simulation, or backtesting product flow. |

## Configuration Contract

Quant configuration extends the existing source-based config. The product command remains:

```bash
python -m halpha run --config config.example.yaml
```

Contract shape:

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
- `quant.signals` must be a non-empty list when `quant.enabled` is true.
- Supported signal names are narrow and explicit. Unknown signal names fail with an actionable error.
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

## Market Strategy Signal Artifact Contract

Strategy signal artifacts store evaluator output before report-loop normalization.

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

Rules:

- Evidence must refer to calculated values or actual input-window facts.
- Uncertainty must be explicit when data is thin, stale, missing, or method-limited.
- A strategy signal must not include trade entries, exits, position sizing, expected returns, or backtest performance.
- `insufficient_data: true` is a valid evaluator output and must not be hidden.

## Normalized Market Signal Artifact Contract

Normalized market signals are the Halpha-owned interface for report generation.

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
    "analysis/market_strategy_signals.json"
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
- Normalized signals remain research material, not trading instructions.

## AI-Readable Market Signal Material Contract

AI-readable market signal material is the bounded signal context for Codex CLI.

Artifact:

```text
runs/<run_id>/analysis/market_signal_material.md
```

Recommended format:

````markdown
---
artifact_type: analysis_market_signal_material
schema_version: 1
audience: ai
source_artifacts:
  - analysis/market_signals.json
  - raw/market_data_views.json
---

# market_signal_material

## source_policy

```yaml
signal_material_is_financial_advice: false
trading_instructions_allowed: false
raw_ohlcv_history_embedded: false
allowed_basis:
  - normalized_market_signals
  - bounded_input_window_metadata
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
- Do not embed large OHLCV history.
- Do not ask Codex CLI to derive quantitative conclusions from raw OHLCV history.
- Do not include trades, positions, expected returns, backtest metrics, or investment advice.

## Research Context and Codex Context Integration

Quant signal material may be added to the existing report context when signal artifacts exist.

`analysis/research_context.md` contract additions:

```yaml
market_signal_material: analysis/market_signal_material.md
market_signals: analysis/market_signals.json
market_data_views: raw/market_data_views.json
```

Research context rules:

- Embed or reference `analysis/market_signal_material.md`.
- Preserve existing market and text material.
- Keep the source policy explicit.
- State that market signals are research material, not financial advice.
- State when quantitative signals do not include text-event signal processing.

`codex_context/context.md` contract additions:

```yaml
market_signal_material: analysis/market_signal_material.md
market_signals: analysis/market_signals.json
market_data_views: raw/market_data_views.json
```

Codex prompt rules:

- Require a Simplified Chinese Markdown report.
- Require quantitative signal conclusions when market signal material exists.
- Require evidence and uncertainty near signal conclusions.
- Require watch points and risk notes.
- Forbid fabricated prices, sources, signals, or certainty.
- Forbid trading instructions, position sizing, account actions, and investment recommendations.
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

When implementation creates signal artifacts, `run_manifest.json` should record them.

Artifact keys:

```json
{
  "artifacts": {
    "market_data_views": "raw/market_data_views.json",
    "market_strategy_signals": "analysis/market_strategy_signals.json",
    "market_signals": "analysis/market_signals.json",
    "market_signal_material": "analysis/market_signal_material.md"
  },
  "counts": {
    "market_data_views": 4,
    "market_strategy_signals": 16,
    "market_signals": 16,
    "market_signals_insufficient_data": 0
  }
}
```

Pipeline stage names:

```text
sync_ohlcv
build_market_data_views
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
- Config, OHLCV, data view, strategy signal, market signal, and AI-readable material contracts are defined above.
- Strategy inputs use raw OHLCV-style data; AI context uses signal conclusions and bounded market context.
- Quant signals are research material, not trades, positions, or backtest performance claims.
- This document states initial adoption scope without making the contract milestone-only.
- This document does not describe quant behavior as currently implemented.
