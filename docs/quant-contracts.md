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

Strategy evaluation flow contract:

```text
configured market source
  -> historical OHLCV sync
  -> reusable local OHLCV store
  -> deterministic OHLCV data views
  -> strategy run evaluation
  -> quant strategy run artifacts
  -> strategy evaluation
  -> strategy evaluation summary artifact
  -> AI-readable strategy evaluation material
  -> market signal and decision-intelligence interpretation
  -> research context
  -> Codex context + prompt
  -> Simplified Chinese Markdown report
```

Strategy inputs use raw OHLCV-style data. AI context uses strategy conclusions, normalized signal conclusions, key evidence, bounded input-window context, diagnostics summaries, warnings, and uncertainty notes.

Quant strategy outputs and signals are personal research material. They are not trades, positions, portfolio advice, return forecasts, or financial advice.

Decision-intelligence contracts live in `docs/decision-intelligence-contracts.md`. That layer consumes the quant artifacts defined here as upstream evidence and must not replace or rename them.

## Related Docs

- `docs/artifact-governance.md`: artifact map, layer rules, Codex input policy, and documentation index.
- `docs/research-data-contracts.md`: reusable data-store coverage, query,
  no-lookahead, and export boundaries for shared data consumers.
- `docs/macro-calendar-contracts.md`: macro and scheduled-event data, context, material, and Codex-boundary contracts.
- `docs/decision-intelligence-contracts.md`: downstream regime, risk, decision, watch trigger, delta, and decision material contracts.
- `docs/event-intelligence-contracts.md`: event intelligence and event-quant confluence contracts.
- `docs/outcome-tracking-contracts.md`: planned downstream target, evaluation, history, material, and Codex-boundary contracts.

## Contract Status

This file separates stable direction from shipped behavior.

- `contract`: expected durable interface or rule.
- `initial adoption`: first implementation slice for the active milestone.
- `not implemented yet`: allowed future contract detail that must not be described as shipped behavior.

README should describe only user-visible behavior that exists. This file may define intended contracts before implementation when they are needed to guide a focused issue.

## Scope

Define contracts for:

- Quant configuration.
- Instrument identity and market identity.
- Strategy specs and strategy-family metadata.
- OHLCV schema.
- Shared OHLCV storage layout.
- Strategy data view records.
- Strategy research run artifacts.
- Strategy signal and exposure records.
- Bounded strategy diagnostics.
- Strategy evaluation artifacts.
- Futures-aware cost and funding assumptions.
- Multi-leg strategy evaluation records.
- Strategy optimization artifacts.
- Strategy dashboard read models.
- AI-readable strategy evaluation material.
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
- Automatic production parameter optimization.
- Automatic active-config mutation from optimized parameters.
- Best-parameter selection outside an explicit bounded research artifact.
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
| Strategy evaluation | Halpha-owned evaluation records are the stable interface for backtest summaries, baseline comparison, walk-forward evidence, and evaluation warnings. |
| Strategy optimization | Halpha-owned optimization artifacts are research evidence only. Optimization must not mutate active config, promote strategies, or select production parameters automatically. |
| History storage | Hive-style partitioned Parquet may be used as the reusable OHLCV fact store. It is not AI context. |
| Query and cropping | Current-run OHLCV windows are selected from the local Parquet-backed store. No database service is used. |
| Report interface | Halpha-owned strategy run, signal JSON, and Markdown contracts are the stable report-loop interface. |

Do not add a dependency until the current implementation step requires it.

## Dependency Contract

Runtime dependencies should serve the current quant flow. They must not introduce account operations, trading execution, hosted services, dashboard behavior, or unrelated quant frameworks into the product path.

| Dependency | Purpose | Boundary |
| --- | --- | --- |
| `ccxt` | Public OHLCV market data access. | Public market endpoints only. No credentials, balances, orders, or trading operations. |
| `pandas` | In-memory OHLCV data frames for strategy inputs. | Local tabular preparation only. No hidden network or persistence role. |
| `pyarrow` | Parquet read/write support for the shared OHLCV fact store. | File format support only. Not an AI context input. |
| `vectorbt` | Strategy indicator and signal calculation support. | Internal implementation helper only. Do not expose vectorbt objects as Halpha artifact contracts or AI context. No portfolio automation, order execution, or trading product flow. |

Current `tsmom_vol_scaled` implementation uses vectorbt `IndicatorFactory` for momentum return and signal calculation. Current `signed_tsmom_trend` implementation uses pandas close-to-close momentum to emit signed long, short, and flat research exposure. Current `breakout_atr_trend` implementation uses vectorbt `IndicatorFactory` for rolling breakout levels and ATR context. Current `sma_cross_trend` implementation uses vectorbt `IndicatorFactory` for short/long simple moving-average trend state. Current `sma_cross_long_short` implementation uses pandas rolling means to emit signed long, short, and flat research exposure. Current `bollinger_rsi_reversion` implementation uses vectorbt `IndicatorFactory` for Bollinger-style bands, RSI state, and trend-filter context. Current `bollinger_rsi_long_short` implementation uses pandas rolling Bollinger, RSI, and trend-filter calculations to emit signed long, short, flat, and trend-suppressed research exposure. When configured, bounded historical diagnostics use Halpha-owned canonical next-bar close-to-close evaluators. Persisted artifacts contain only Halpha-owned summary fields, assumptions, scalar metrics, and warnings.

## Instrument Identity Contract

Status: deterministic source/symbol/timeframe instrument identity helpers are
implemented for configured OHLCV sources. Existing OHLCV and strategy artifacts
continue to identify markets by `source`, `symbol`, and `timeframe` until later
integration issues embed normalized identity records in downstream artifacts.

Purpose:

- Make spot, linear perpetual, inverse perpetual, swap, and other public market
  histories explicit instead of treating every symbol string as equivalent.
- Keep futures-aware strategy evaluation account-independent and source-aware.
- Give Strategy Lab and optimization artifacts one stable market-identity
  vocabulary.

Instrument identity fields:

```json
{
  "instrument_identity": {
    "schema_version": 1,
    "source": "binance_usdm",
    "symbol": "BTCUSDT",
    "exchange_symbol": "BTC/USDT:USDT",
    "market_type": "swap",
    "contract_type": "linear_perpetual",
    "base_asset": "BTC",
    "quote_asset": "USDT",
    "settlement_asset": "USDT",
    "price_unit": "quote_asset_per_base_asset",
    "timeframe": "1h",
    "identity_status": "normalized",
    "warnings": []
  }
}
```

Allowed `market_type` values:

- `spot`;
- `perpetual`;
- `swap`;
- `futures`;
- `unknown`.

Allowed `contract_type` values:

- `none`;
- `linear_perpetual`;
- `inverse_perpetual`;
- `linear_futures`;
- `inverse_futures`;
- `spot`;
- `unknown`.

Rules:

- Existing `source`, `symbol`, and `timeframe` fields remain valid current
  identity fields until downstream artifacts embed normalized identity records.
- Normalized identity must be derived from configured sources and source
  metadata, not guessed only from symbol suffixes.
- Unknown source metadata must produce `unknown` identity values and warnings,
  not fabricated contract details.
- Strategy artifacts that support contracts must record `settlement_asset`
  when known and must record an explicit warning when it is unknown.
- Public market identity must not include account identifiers, balances,
  margin mode, position mode, leverage settings, or order information.

## Strategy Spec Contract

Status: Strategy spec records are implemented for the currently supported
strategy registry. Dashboard parameter forms, signed-exposure strategies, and
expanded strategy families are planned downstream consumers.

Purpose:

- Make strategy family, supported market types, parameter schema, required
  inputs, output exposure policy, and optimization space visible to CLI,
  pipeline, Strategy Lab, gates, lifecycle, and tests.
- Prevent dashboard and config code from hardcoding strategy behavior that
  belongs to the strategy registry.

Strategy spec record:

```json
{
  "schema_version": 1,
  "strategy_name": "sma_cross_trend",
  "strategy_family": "moving_average",
  "strategy_contract_version": "1",
  "status": "implemented",
  "description": "Simple moving-average crossover trend research strategy.",
  "supported_market_types": ["spot", "perpetual", "swap"],
  "required_inputs": [
    {
      "input_type": "ohlcv",
      "required": true,
      "time_alignment": "closed_bar_no_lookahead"
    }
  ],
  "output_position_policy": "research_long_flat_target_exposure",
  "default_params": {},
  "parameter_schema": {},
  "optimization_space": {},
  "minimum_rows_policy": {
    "minimum_rows": 60,
    "reason": "indicator warmup and transition evidence"
  },
  "risk_notes": [
    "Historical strategy output is research material, not a forecast."
  ],
  "supported_filters": [],
  "supported_features": []
}
```

Allowed `strategy_family` values:

- `trend`;
- `moving_average`;
- `mean_reversion`;
- `volatility_regime`;
- `statistical_arbitrage`;
- `cross_sectional`;
- `derivatives_aware`;
- `event_driven`;
- `other`.

Allowed `output_position_policy` values:

- `research_long_flat_target_exposure`: implemented current long-flat record
  semantics.
- `research_signed_target_exposure`: implemented single-leg long, short, and
  flat record semantics. Strategy implementations and evaluation integration
  are separate consumers.
- `research_multi_leg_target_exposure`: implemented multi-leg exposure
  semantics for explicit pair/spread and cross-sectional research records.

Rules:

- Strategy specs are metadata and validation contracts. They must not execute
  strategy logic.
- Unknown strategy names must continue to fail with actionable validation.
- Strategy specs must not contain credentials, private account fields, or live
  execution settings.
- Strategy specs may declare reusable optional filter inputs with
  `supported_filters`; implemented filter inputs must include explicit
  parameter names and `closed_bar_no_lookahead` alignment.
- Strategy specs may declare reusable optional non-OHLCV feature inputs with
  `supported_features`; implemented feature inputs must include explicit
  data type, data class, metric, parameter names, and no-lookahead alignment.
- `optimization_space` is a bounded research search space. It is not an
  instruction to optimize active configuration automatically.
- Strategy Lab should prefer strategy spec metadata for controls and hints when
  the spec registry is implemented.

## Strategy Signal And Exposure Contract

Status: current strategy implementations emit long-flat records, signed
single-leg records, explicit multi-leg pair/spread records, and explicit
multi-leg cross-sectional ranking records. Signed-exposure and multi-leg
evaluation cores are implemented for research backtests.

Current single-leg long-flat shape:

```json
{
  "open_time": "2026-06-05T00:00:00Z",
  "close": 104000.0,
  "signal": {
    "active": true
  },
  "position": {
    "target_exposure": 1.0,
    "unit": "fractional_long_exposure"
  }
}
```

Implemented signed single-leg shape:

```json
{
  "schema_version": 2,
  "open_time": "2026-06-05T00:00:00Z",
  "signal_time": "2026-06-05T00:00:00Z",
  "position": {
    "target_exposure": -1.0,
    "unit": "fractional_signed_exposure",
    "position_state": "short"
  },
  "transition": {
    "entry": true,
    "exit": false,
    "long_entry": false,
    "long_exit": false,
    "short_entry": true,
    "short_exit": false
  },
  "evidence": [],
  "warnings": []
}
```

Allowed `position_state` values:

- `long`;
- `short`;
- `flat`;
- `unknown`.

Signed exposure rules:

- `target_exposure` must be finite and bounded to `-1.0 <= value <= 1.0`
  for single-leg research records.
- Positive exposure means long research exposure. Negative exposure means
  short research exposure. Zero means flat.
- Signal records describe target exposure known at the signal timestamp. They
  do not imply same-bar execution.
- Evaluation timing remains controlled by the execution model. The default
  rule is signal at bar close, position from the next bar.
- Direct long-to-short or short-to-long transitions must remain visible in
  transition diagnostics.

Implemented multi-leg signal shape for the evaluation core:

```json
{
  "schema_version": 1,
  "record_type": "multi_leg_signal",
  "signal_time": "2026-06-05T00:00:00Z",
  "strategy_name": "pair_zscore_reversion",
  "legs": [
    {
      "leg_id": "long_leg",
      "instrument_identity": {},
      "target_exposure": 0.5,
      "price_basis": "close"
    },
    {
      "leg_id": "short_leg",
      "instrument_identity": {},
      "target_exposure": -0.5,
      "price_basis": "close"
    }
  ],
  "gross_exposure": 1.0,
  "net_exposure": 0.0,
  "warnings": []
}
```

Multi-leg rules:

- Leg records must preserve source, symbol, timeframe, and normalized
  instrument identity when implemented.
- Multi-leg evaluation aligns legs by observable open time and reports omitted
  or missing rows.
- The first implemented multi-leg evaluator requires all legs to share one
  timeframe. It does not resample mixed-frequency legs.
- Multi-leg target exposure must be finite and bounded to
  `-1.0 <= target_exposure <= 1.0` per leg.
- Leg exposure units are research exposure units, not account allocation or
  margin instructions.
- Multi-leg records must not collapse pair, spread, or basket evidence into a
  single synthetic symbol unless the synthetic construction is separately
  persisted and reviewable.

## Futures Cost And Funding Contract

Status: current evaluation records include fees, slippage, optional
evidence-backed funding cost inputs for signed single-leg evaluations, and
bounded futures diagnostics when an explicit contract-market instrument
identity is available.

Purpose:

- Make public contract strategy evaluation distinguish gross performance,
  trading costs, funding costs, and data-availability limits.
- Keep futures-aware evaluation account-independent.

Implemented funding-cost input shape:

```json
{
  "schema_version": 1,
  "artifact_type": "strategy_funding_cost_input",
  "status": "available",
  "source": "binance_usdm",
  "symbol": "BTCUSDT",
  "data_class": "funding_rate",
  "period": "8h",
  "as_of_boundary": "2026-06-05T00:00:00Z",
  "unit": "fraction_of_notional",
  "sign_convention": "positive_rate_paid_by_longs_received_by_shorts",
  "period_count": 2,
  "matched_record_count": 2,
  "missing_period_count": 0,
  "periods": [
    {
      "period_start": "2026-06-04T00:00:00Z",
      "period_end": "2026-06-05T00:00:00Z",
      "funding_rate": 0.0001,
      "matched_record_count": 1,
      "funding_as_of": ["2026-06-04T08:00:00Z"]
    }
  ],
  "warnings": [],
  "errors": [],
  "source_artifacts": []
}
```

Implemented derivatives strategy feature input shape:

```json
{
  "schema_version": 1,
  "artifact_type": "strategy_derivatives_feature_input",
  "status": "available",
  "feature_id": "derivatives_feature:funding_rate:funding_rate:binance_usdm:BTCUSDT:8h:2026-06-05T00:00:00Z",
  "data_type": "derivatives_market",
  "data_class": "funding_rate",
  "metric": "funding_rate",
  "source": "binance_usdm",
  "symbol": "BTCUSDT",
  "period": "8h",
  "requested_start": "2026-06-01T00:00:00Z",
  "requested_end": "2026-06-05T00:00:00Z",
  "as_of_boundary": "2026-06-05T00:00:00Z",
  "record_count": 1,
  "matched_record_count": 1,
  "skipped_record_count": 0,
  "records": [
    {
      "feature_time": "2026-06-04T08:00:00Z",
      "first_seen_at": "2026-06-04T08:01:00Z",
      "data_class": "funding_rate",
      "metric": "funding_rate",
      "value": 0.0001,
      "unit": "ratio",
      "quality": {
        "status": "available",
        "warnings": [],
        "errors": []
      }
    }
  ],
  "warnings": [],
  "errors": [],
  "source_artifacts": []
}
```

Implemented futures diagnostic shape:

```json
{
  "artifact_type": "futures_strategy_diagnostics",
  "schema_version": 1,
  "status": "succeeded",
  "instrument_identity": {
    "source": "binance_usdm",
    "symbol": "BTCUSDT",
    "timeframe": "1h",
    "market_type": "swap",
    "contract_type": "linear_perpetual",
    "base_asset": "BTC",
    "quote_asset": "USDT",
    "settlement_asset": "USDT",
    "identity_status": "normalized"
  },
  "method": {
    "basis": "account_independent_contract_research_diagnostics",
    "contribution_basis": "additive_period_gross_return_percentage_points",
    "liquidation_model": "not_modeled",
    "margin_model": "not_modeled",
    "account_balance_model": "not_modeled"
  },
  "contribution": {
    "long_gross_contribution_pct": 8.2,
    "short_gross_contribution_pct": 3.1,
    "flat_gross_contribution_pct": 0.0,
    "total_gross_contribution_pct": 11.3
  },
  "exposure": {
    "long_time_pct": 40.0,
    "short_time_pct": 35.0,
    "flat_time_pct": 25.0,
    "average_gross_exposure_pct": 75.0,
    "average_net_exposure_pct": 5.0,
    "average_abs_exposure_pct": 75.0,
    "max_abs_exposure_pct": 100.0
  },
  "turnover": {
    "total_turnover": 12.0,
    "average_turnover": 0.24
  },
  "costs": {
    "total_cost_pct": 0.8,
    "cost_drag_pct": 0.8,
    "additive_cost_pct": 0.8
  },
  "funding": {
    "status": "available",
    "period_count": 50,
    "matched_record_count": 50,
    "missing_period_count": 0,
    "funding_drag_pct": 0.3
  },
  "risk_warnings": [],
  "warnings": []
}
```

Futures evaluation rules:

- Funding adapters must read reusable derivatives history through the
  derivatives event-like query boundary, not direct ad hoc file scans.
- Derivatives feature adapters must preserve explicit unavailable, stale,
  partial, degraded, skipped, and failed states; missing data must not be
  silently converted into neutral factor values.
- Strategy feature adapters must enforce the requested time range, the
  configured `as_of_boundary`, and `first_seen_at` visibility when the reusable
  history records contain first-seen evidence.
- Funding costs may be applied only when source data is available and aligned
  to the evaluated instrument and time range.
- Futures diagnostics are emitted only when market identity has explicit
  contract-market evidence from embedded `instrument_identity`, explicit
  identity fields, or configured source metadata. They must not be enabled from
  symbol suffix guesses alone.
- Funding record visibility must respect the evaluation `as_of` boundary.
- Missing funding data must be recorded as unavailable, stale, partial, or
  insufficient. It must not be treated as zero funding unless a strategy or
  evaluation config explicitly declares a zero-funding assumption.
- Long and short exposure must apply funding with opposite economic signs when
  funding data supports it.
- Evaluation artifacts record funding input status, matched record counts,
  missing period counts, funding warnings, and `funding_drag_pct` where funding
  is applied.
- Leverage-risk or liquidation-proximity warnings are qualitative research
  diagnostics only. They must not model a real exchange liquidation engine or
  account margin state unless a later explicit contract implements that.
- Futures-aware records must continue to include fees, slippage, gross return,
  net return, turnover, exposure, drawdown, and historical-research warnings.
- Futures diagnostics summarize long contribution, short contribution, flat
  time, gross exposure, net exposure, average absolute exposure, turnover, cost
  drag, funding drag when available, and qualitative risk warnings. They must
  not include account balances, margin mode, leverage settings, exchange
  liquidation prices, or position-size recommendations.

## Strategy Optimization Contract

Status: standalone bounded grid optimization and bounded walk-forward
optimization artifacts are implemented.

Parameter diagnostics and optimization are different contracts:

- Parameter diagnostics summarize configured sensitivity grids and fragility.
- Optimization evaluates a bounded search space, records candidate outcomes,
  records failed combinations, applies a declared selection policy, and writes
  a research artifact.
- Neither diagnostics nor optimization may mutate active strategy config or
  promote a strategy automatically.

Standalone optimization artifact:

```text
runs/strategy_optimizations/<id>/strategy_optimization.json
```

Planned pipeline artifact, when optimization is integrated into a product run:

```text
runs/<run_id>/analysis/strategy_optimization.json
```

Standalone command:

```bash
python -m halpha optimize --config config.example.yaml --strategy tsmom_vol_scaled
python -m halpha optimize --config config.example.yaml --strategy tsmom_vol_scaled --grid return_window=10,20 --grid volatility_window=10,20 --max-combinations 8
python -m halpha optimize --config config.example.yaml --strategy tsmom_vol_scaled --walk-forward-train-rows 120 --walk-forward-validation-rows 30 --walk-forward-step-rows 30 --walk-forward-min-windows 4
```

Top-level implemented contract:

```json
{
  "schema_version": 1,
  "artifact_type": "strategy_optimization",
  "created_at": "2026-06-06T00:00:00Z",
  "optimization_id": "20260606T000000Z_tsmom_vol_scaled_optimization",
  "strategy_name": "tsmom_vol_scaled",
  "instrument_identity": {},
  "inputs": {
    "candidate_source": "bounded_grid_search",
    "strategy_source": "configured_quant_strategy",
    "benchmark_suite_artifact": "strategy_benchmark_suite.json"
  },
  "base_params": {},
  "search_space": {
    "source": "strategy_spec_optimization_space|cli_grid_override",
    "strategy_spec_version": "1",
    "grid": {},
    "combination_count": 0,
    "max_combinations": 50
  },
  "constraints": {
    "max_combinations": 50,
    "raw_ohlcv_history_embedded": false,
    "automatic_config_mutation": false
  },
  "selection_policy": {
    "name": "max_mean_net_return_with_drawdown_tiebreak_research_only_v1",
    "metric": "mean_net_return_pct",
    "tie_breakers": ["worst_max_drawdown_pct", "mean_cost_drag_pct", "candidate_id"],
    "automatic_config_mutation": false,
    "research_only": true
  },
  "coverage": {
    "candidate_count": 0,
    "succeeded": 0,
    "failed": 0,
    "insufficient_data": 0
  },
  "candidates": [],
  "failed_candidates": [],
  "selected_candidate": null,
  "walk_forward": {
    "enabled": true,
    "status": "succeeded|insufficient_data|failed",
    "method": {
      "name": "bounded_train_validation_grid_walk_forward_v1",
      "candidate_selection": "max_train_net_return_with_drawdown_tiebreak",
      "validation_policy": "selected_candidate_evaluated_on_next_validation_window",
      "params_optimized_per_window": true,
      "automatic_config_mutation": false
    },
    "policy": {
      "train_rows": 60,
      "validation_rows": 20,
      "step_rows": 20,
      "min_windows": 3
    },
    "summary": {
      "window_count": 0,
      "succeeded_windows": 0,
      "failed_windows": 0,
      "insufficient_data_windows": 0,
      "selected_candidate_counts": {},
      "selected_candidate_variants": 0,
      "mean_train_selected_net_return_pct": null,
      "mean_validation_net_return_pct": null,
      "mean_validation_cost_drag_pct": null,
      "train_validation_gap_pct": null,
      "positive_validation_net_return_window_pct": null,
      "worst_validation_drawdown_pct": null
    },
    "windows": []
  },
  "robustness": {
    "status": "robust|fragile|overfit_risk|insufficient_data|failed",
    "summary": {},
    "warnings": [],
    "errors": []
  },
  "source_artifacts": [],
  "warnings": [],
  "errors": []
}
```

Optimization candidate contract:

```json
{
  "candidate_id": "candidate:0001",
  "params": {},
  "status": "succeeded|failed|insufficient_data|skipped",
  "metrics": {
    "net_return_pct": 0.0,
    "max_drawdown_pct": 0.0,
    "cost_drag_pct": 0.0,
    "turnover": 0.0
  },
  "gate_inputs": {},
  "warnings": [],
  "errors": []
}
```

Optimization rules:

- Candidate enumeration must be deterministic.
- Search spaces must be bounded by explicit max-combination limits.
- Failed and insufficient candidates must remain visible.
- Selection policy must be recorded before selected-candidate interpretation.
- Implemented standalone optimization uses strategy spec optimization spaces
  unless CLI `--grid` overrides are supplied.
- Candidate evaluation reuses Halpha strategy signal records and the canonical
  single-window strategy evaluator.
- Walk-forward optimization is always represented in the standalone artifact.
  If there are not enough rows, it must produce `insufficient_data` evidence
  instead of omitting the section.
- Walk-forward optimization must record deterministic train and validation
  windows, per-window train candidate outcomes, selected candidate, validation
  metrics, failed windows, data coverage, cost-drag evidence, and warnings.
- Robustness status must be deterministic and limited to `robust`, `fragile`,
  `overfit_risk`, `insufficient_data`, or `failed`. Parameter instability and
  material train-validation performance gaps must produce explicit overfit-risk
  warnings.
- Optimization results are historical research evidence only. They are not
  trading instructions, return forecasts, or active configuration changes.
- Optimization must not rewrite `quant.strategies`, lifecycle policy, active
  strategy parameters, or local config files.

## Strategy Dashboard Read Model Contract

Status: current Strategy Lab exposes OHLCV shared-store review and existing
strategy artifacts. Expanded workbench, optimization, and advanced evaluation
read models are planned.

Purpose:

- Give Dashboard bounded, API-backed read models for strategy workbench
  controls and visual review.
- Keep UI and CLI on the same internal service contracts.

Read-model rules:

- Strategy Lab metadata should come from config, instrument identity, and
  strategy specs when implemented.
- Backtest, experiment, optimization, and comparison actions should return
  job or service status, progress, bounded logs, warnings, errors, and source
  artifact refs.
- The K-line chart remains the OHLCV viewer when no strategy artifact is
  selected.
- When a strategy artifact is selected, markers must be artifact-derived and
  aligned to the matching source, symbol, and timeframe.
- Dashboard read models must bound bars, markers, equity points, candidates,
  warnings, logs, and source refs.
- Dashboard read models must not embed full reusable OHLCV history, vectorbt
  objects, full optimization candidate tables, account state, or trading
  instructions by default.

## Configuration Contract

Quant configuration extends the existing source-based config. The product command remains:

```bash
python -m halpha run --config config.example.yaml
```

Current shipped strategy config shape:

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
    sources:
      - binance
      - binance_spot
      - binance_usdm
      - okx_spot
      - okx_swap
    timeframes:
      - 1m
      - 5m
      - 15m
      - 1h
      - 4h
      - 1d
      - 1w
      - 1month
    lookback:
      1m: 1440
      5m: 2016
      15m: 2016
      1h: 720
      4h: 720
      1d: 500
      1w: 260
      1month: 120

quant:
  enabled: true
  engine: vectorbt
  effectiveness_gates:
    min_positive_net_return_benchmark_pct: 25.0
    max_cost_drag_pct: 6.0
    require_walk_forward_stable: false
    min_walk_forward_positive_net_return_window_pct: 0.0
  strategies:
    - name: tsmom_vol_scaled
      enabled: true
      params:
        return_window: 120
        volatility_window: 60
        target_volatility: 0.2
      backtest:
        enabled: true
        initial_cash: 10000
        fees_bps: 10
        slippage_bps: 5
        mode: long_flat
    - name: signed_tsmom_trend
      enabled: true
      params:
        return_window: 120
        deadband_pct: 1.0
      backtest:
        enabled: true
        initial_cash: 10000
        fees_bps: 10
        slippage_bps: 5
    - name: breakout_atr_trend
      enabled: true
      params:
        breakout_window: 120
        exit_window: 20
        atr_window: 14
      backtest:
        enabled: true
        initial_cash: 10000
        fees_bps: 10
        slippage_bps: 5
        mode: long_flat
    - name: sma_cross_trend
      enabled: true
      params:
        short_window: 20
        long_window: 30
      backtest:
        enabled: true
        initial_cash: 10000
        fees_bps: 10
        slippage_bps: 5
        mode: long_flat
    - name: sma_cross_long_short
      enabled: true
      params:
        short_window: 20
        long_window: 30
        neutral_band_pct: 0.5
      backtest:
        enabled: true
        initial_cash: 10000
        fees_bps: 10
        slippage_bps: 5
    - name: bollinger_rsi_reversion
      enabled: true
      params:
        bollinger_window: 20
        band_std: 2.0
        rsi_window: 14
        rsi_oversold: 30
        rsi_overbought: 70
        trend_window: 100
        trend_filter_pct: 10.0
      backtest:
        enabled: true
        initial_cash: 10000
        fees_bps: 10
        slippage_bps: 5
        mode: long_flat
    - name: bollinger_rsi_long_short
      enabled: true
      params:
        bollinger_window: 20
        band_std: 2.0
        rsi_window: 14
        rsi_oversold: 30
        rsi_overbought: 70
        trend_window: 100
        trend_filter_pct: 10.0
      backtest:
        enabled: true
        initial_cash: 10000
        fees_bps: 10
        slippage_bps: 5
  parameter_diagnostics:
    enabled: true
    max_combinations: 16
    grids:
      tsmom_vol_scaled:
        return_window:
          - 80
          - 120
        volatility_window:
          - 60
          - 120
        target_volatility:
          - 0.15
          - 0.2
      signed_tsmom_trend:
        return_window:
          - 80
          - 120
        deadband_pct:
          - 0.5
          - 1.0
      breakout_atr_trend:
        breakout_window:
          - 80
          - 120
        exit_window:
          - 10
          - 20
        atr_window:
          - 14
      sma_cross_trend:
        short_window:
          - 10
          - 20
        long_window:
          - 30
          - 50
      sma_cross_long_short:
        short_window:
          - 10
          - 20
        long_window:
          - 30
          - 50
        neutral_band_pct:
          - 0.0
          - 0.5
      bollinger_rsi_reversion:
        bollinger_window:
          - 20
        band_std:
          - 2.0
          - 2.5
        rsi_window:
          - 14
        rsi_oversold:
          - 25
          - 30
        rsi_overbought:
          - 70
          - 75
        trend_window:
          - 50
          - 100
        trend_filter_pct:
          - 10.0
      bollinger_rsi_long_short:
        bollinger_window:
          - 20
        band_std:
          - 2.0
          - 2.5
        rsi_window:
          - 14
        rsi_oversold:
          - 25
          - 30
        rsi_overbought:
          - 70
          - 75
        trend_window:
          - 50
          - 100
        trend_filter_pct:
          - 10.0
```

Validation contract:

- `market.enabled` is required.
- `market.source` is required when `market.enabled` is true.
- `market.source` is the current-run market snapshot source and remains
  separate from optional OHLCV collection source choices.
- `market.source` must be a supported market snapshot source when
  `market.ohlcv` exists or `quant.enabled` is true.
- `market.proxy` may be omitted when direct public source access works.
- `market.proxy.enabled` is required when `market.proxy` exists.
- `market.proxy.url` is required when `market.proxy.enabled` is true.
- `market.proxy.url` must be an `http` or `https` proxy URL without embedded credentials.
- Machine-local proxy values must stay in gitignored local config files, not committed examples or docs.
- `market.symbols` must be a non-empty list when `market.enabled` is true.
- `market.ohlcv` may be omitted when quant is not configured.
- `market.ohlcv.storage_dir` is required when `market.ohlcv` exists or `quant.enabled` is true.
- `market.ohlcv.storage_dir` must be outside the runtime-resolved
  `run.output_dir`.
- Relative `market.ohlcv.storage_dir` and `run.output_dir` values resolve from
  the runtime root. Absolute paths remain explicit local overrides.
- `market.ohlcv.timeframes` must be a non-empty list when `market.ohlcv` exists or `quant.enabled` is true.
- Supported OHLCV timeframes are `1m`, `5m`, `15m`, `1h`, `4h`, `1d`,
  `1w`, and `1month`.
- `market.ohlcv.sources` may list explicit public OHLCV collection sources for
  CLI and Dashboard collection. If omitted, explicit collection may use the
  built-in supported OHLCV sources. Product OHLCV sync still uses
  `market.source` unless a later contract changes sync selection.
- `market.ohlcv.lookback` must define a positive integer for each configured timeframe when `market.ohlcv` exists or `quant.enabled` is true.
- `quant` may be omitted when the report path does not use quant strategies.
- `quant.enabled` is required when `quant` exists.
- Current shipped quant config uses `quant.strategies`.
- `quant.signals` is retired and must fail with an actionable validation error when `quant.enabled` is true.
- `quant.strategies` must be a non-empty list when quant is enabled.
- Supported strategy names are narrow and explicit. Unknown names fail with an actionable error.
- Strategy records may include per-strategy `params`, `targeted_params`,
  `backtest`, and enabled state.
- `quant.strategies[].targeted_params` is an optional list of exact
  source/symbol/timeframe parameter overrides. Each item must include
  non-empty `source`, `symbol`, `timeframe`, and a `params` mapping that passes
  the same strategy parameter validation as base `params`.
- Targeted parameter overrides merge over base `params` only for matching
  `source + symbol + timeframe`. Non-matching backtests, experiments, and
  optimizations continue using base params.
- Optimization artifacts may emit `recommended_targeted_params` for the selected
  target candidate. This is research evidence and a copyable config fragment,
  not an automatic active-config mutation.
- Strategy-level `backtest` and global `parameter_diagnostics` are optional, bounded research diagnostics, not trading or return-forecast settings.
- `quant.parameter_diagnostics` may be omitted. If present, `quant.parameter_diagnostics.enabled` must be a boolean.
- `quant.parameter_diagnostics.max_combinations` must be a positive integer when present and is required when parameter diagnostics are enabled.
- `quant.parameter_diagnostics.grids` must be a non-empty mapping when parameter diagnostics are enabled.
- `quant.parameter_diagnostics.grids.<strategy_name>` keys must be supported strategy names.
- Parameter grid field names must be supported params for that strategy.
- Parameter grid field values must be non-empty lists, and each item must pass the same scalar type and value checks as strategy params.
- The product of grid value counts for each configured strategy must be less than or equal to `quant.parameter_diagnostics.max_combinations`.
- Parameter diagnostics may record runtime-invalid combinations, such as combinations with insufficient input data, without failing the whole strategy run.
- `quant.effectiveness_gates` may be omitted. If present, it must be a mapping of deterministic gate threshold overrides.
- `quant.effectiveness_gates` supports only explicit threshold fields for benchmark coverage, performance, baseline comparison, drawdown, cost drag, turnover, funding drag, gross exposure, trade count, sample rows, walk-forward evidence, parameter performance-stability requirement, and overfitting-risk downgrade behavior.
- Unknown `quant.effectiveness_gates` fields must fail config validation so gate threshold typos are not silently ignored.
- Strategy-level `backtest.initial_cash` must be a positive number when present.
- Strategy-level `backtest.fees_bps` and `backtest.slippage_bps` must be non-negative numbers when present.
- Strategy-level `backtest.mode` must be one of `long_flat` or `long_only` when present.
- `tsmom_vol_scaled` params `return_window` and `volatility_window` must be positive integers when present.
- `tsmom_vol_scaled` param `target_volatility` must be a positive number when present.
- `signed_tsmom_trend` param `return_window` must be a positive integer when present.
- `signed_tsmom_trend` param `deadband_pct` must be a number between 0 and 100 when present.
- `signed_tsmom_trend` optional `volatility_filter_enabled` param must be a boolean when present.
- `signed_tsmom_trend` optional `volatility_filter_window` param must be a positive integer when present.
- `signed_tsmom_trend` optional `max_realized_volatility_pct` param must be a positive number when present.
- `breakout_atr_trend` params `breakout_window`, `exit_window`, and `atr_window` must be positive integers when present.
- `sma_cross_trend` params `short_window` and `long_window` must be positive integers when present.
- Effective `sma_cross_trend` `short_window` must be lower than effective `long_window`.
- `sma_cross_long_short` params `short_window` and `long_window` must be positive integers when present.
- `sma_cross_long_short` param `neutral_band_pct` must be a number between 0 and 100 when present.
- Effective `sma_cross_long_short` `short_window` must be lower than effective `long_window`.
- `bollinger_rsi_reversion` params `bollinger_window`, `rsi_window`, and `trend_window` must be positive integers when present.
- `bollinger_rsi_reversion` params `band_std` and `trend_filter_pct` must be positive numbers when present.
- `bollinger_rsi_reversion` params `rsi_oversold` and `rsi_overbought` must be numbers greater than 0 and lower than 100 when present.
- Effective `bollinger_rsi_reversion` `rsi_oversold` must be lower than effective `rsi_overbought`.
- `bollinger_rsi_long_short` params `bollinger_window`, `rsi_window`, and `trend_window` must be positive integers when present.
- `bollinger_rsi_long_short` params `band_std` and `trend_filter_pct` must be positive numbers when present.
- `bollinger_rsi_long_short` params `rsi_oversold` and `rsi_overbought` must be numbers greater than 0 and lower than 100 when present.
- Effective `bollinger_rsi_long_short` `rsi_oversold` must be lower than effective `rsi_overbought`.
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

## No-Lookahead Data Access Contract

Quantitative consumers must read reusable data through bounded query semantics
when evaluating a historical window. A backtest or benchmark window must not
silently use records that would not have been available at the requested point
in time.

OHLCV query inputs:

- `source`;
- `symbol`;
- `timeframe`;
- `start`;
- `end`;
- optional `as_of`.

Implemented adapter:

- `halpha.market.ohlcv_query.query_ohlcv_records` for explicit ranges.
- `halpha.market.ohlcv_query.query_latest_ohlcv_records` for configured or
  explicit latest-lookback windows.

OHLCV query rules:

- Filter by `open_time` and closed-candle eligibility.
- Do not return rows after the requested `end`.
- Do not return rows that violate the requested `as_of` boundary. A candle is
  eligible at `as_of` only when `open_time + timeframe_duration <= as_of`.
- Preserve deterministic ordering by `open_time`.
- Return missing-candle and coverage diagnostics when the store can derive
  them.
- The default explicit range is half-open (`start <= open_time < end`).
  Existing benchmark windows may request an inclusive `open_time` end to keep
  the established `input_window_end` meaning as the latest returned candle
  `open_time`.

Event-like query rules for future quant consumers:

- Text, macro/calendar, on-chain flow, and derivatives records must use the
  shared query contract in `docs/research-data-contracts.md`.
- Text events must not be available to a backtest before the relevant
  `published_at`, `collected_at`, or `first_seen_at` boundary.
- Empty event-like results must carry coverage diagnostics so quantitative code
  can distinguish `no_data` from `not_collected`, `partial`, `failed`, or
  unknown coverage.
- Query output may be converted into DataFrame-like structures for local
  research tools, but that conversion must not drop coverage warnings or source
  refs.

Implemented event strategy feature input:

```json
{
  "schema_version": 1,
  "artifact_type": "strategy_event_feature_input",
  "feature_source": "strategy_event_features",
  "data_type": "market_anomaly",
  "status": "available",
  "requested_start": "2026-06-01T00:00:00Z",
  "requested_end": "2026-06-08T00:00:00Z",
  "as_of_boundary": "2026-06-08T00:00:00Z",
  "matched_record_count": 8,
  "filtered_out_record_count": 0,
  "records": [
    {
      "schema_version": 1,
      "record_type": "strategy_event_feature_record",
      "data_type": "market_anomaly",
      "event_time": "2026-06-06T12:00:00Z",
      "published_at": "2026-06-06T12:00:00Z",
      "first_seen_at": "2026-06-06T12:01:00Z",
      "collected_at": "2026-06-06T12:01:00Z",
      "source": "halpha_monitor_rules",
      "category": "volume_spike",
      "severity": "medium",
      "symbol": "BTCUSDT",
      "title": "BTCUSDT 1m volume spike 3.2x",
      "quality": {
        "status": "warning",
        "warnings": [],
        "errors": []
      }
    }
  ],
  "warnings": [],
  "errors": [],
  "source_artifacts": []
}
```

Event strategy feature rules:

- Strategy event features are bounded local inputs, not Codex-generated event
  impact, forecasts, or trading instructions.
- Event feature builders must use the event-like query boundary and must carry
  `published_at`, `first_seen_at`, and `collected_at` visibility fields when the
  source store provides them.
- Backtests and strategy simulations must not expose a record before the signal
  time can see its event time and visibility timestamps.
- Scheduled-event lookahead windows may include future `event_time` records only
  when publication or first-seen evidence proves that the event schedule was
  already visible before the signal time.
- Missing, unknown, partial, degraded, and failed coverage must stay explicit in
  the feature input and in downstream strategy diagnostics.
- Strategy-facing event windows must stay bounded. They may expose counts and a
  small ordered sample of records; they must not embed full raw histories.

Strategy benchmark suite and strategy experiment benchmark-row loading use the
OHLCV query adapter instead of independently slicing full reusable OHLCV
history. Exports for quantitative research must use the same query boundary.
They must not read full reusable store files directly to bypass range, `as_of`,
or coverage rules.

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
  "status": "succeeded",
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
  "quality_status": "ok",
  "quality": {
    "status": "ok",
    "timeframe_duration_seconds": 86400,
    "range_start": "2025-01-22T00:00:00Z",
    "range_end": "2026-06-05T00:00:00Z",
    "duplicate_open_time_count": 0,
    "duplicate_open_time_samples": [],
    "missing_interval_count": 0,
    "missing_interval_samples": [],
    "stale_latest_candle": false,
    "freshness_reference_time": "2026-06-06T00:00:00Z",
    "stale_after_open_time": "2026-06-07T00:00:00Z",
    "stale_tolerance_seconds": 172800
  },
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
- Views validate supported OHLCV timeframe continuity and freshness for
  configured OHLCV timeframes, including minute, hourly, daily, weekly, and
  monthly candles.
- Missing intervals, duplicate `open_time` values, or stale latest candles set `quality_status: degraded`.
- Degraded OHLCV quality must keep `insufficient_data: true` so downstream strategy runs do not report ordinary success from degraded input.
- Quality samples are bounded and diagnostic; views must not fill missing candles or rewrite raw evidence.

## Strategy Benchmark Suite Contract

Each run may record fixed strategy benchmark windows from shared local OHLCV history. The benchmark suite is a window inventory for strategy experiments; it does not run strategies or embed raw OHLCV rows.

Artifact:

```text
runs/<run_id>/analysis/strategy_benchmark_suite.json
```

Top-level contract:

```json
{
  "schema_version": 1,
  "artifact_type": "strategy_benchmark_suite",
  "created_at": "2026-06-06T00:00:00Z",
  "selection_policy": {
    "source": "configured_symbols_timeframes_and_windows",
    "raw_ohlcv_history_embedded": false,
    "supported_window_selections": [
      "configured_lookback",
      "date_window",
      "latest_lookback"
    ]
  },
  "source_artifacts": [
    "data/market/metadata/ohlcv_sync_state.json"
  ],
  "coverage": {},
  "benchmarks": [],
  "warnings": [],
  "errors": []
}
```

Benchmark record contract:

```json
{
  "benchmark_id": "strategy_benchmark:binance:BTCUSDT:1d:configured_lookback:2025-01-22T00:00:00Z:2026-06-05T00:00:00Z",
  "status": "succeeded",
  "source": "binance",
  "symbol": "BTCUSDT",
  "timeframe": "1d",
  "window_identity": "configured_lookback",
  "window_selection": "configured_lookback",
  "requested_lookback": 500,
  "minimum_rows": 500,
  "input_window_start": "2025-01-22T00:00:00Z",
  "input_window_end": "2026-06-05T00:00:00Z",
  "latest_candle_time": "2026-06-05T00:00:00Z",
  "row_count": 500,
  "history_row_count": 500,
  "storage_ref": "data/market/ohlcv/source=binance/symbol=BTCUSDT/timeframe=1d",
  "included_columns": [
    "open_time",
    "open",
    "high",
    "low",
    "close",
    "volume"
  ],
  "source_artifacts": [
    "data/market/metadata/ohlcv_sync_state.json"
  ],
  "quality_status": "ok",
  "quality": {
    "status": "ok",
    "timeframe_duration_seconds": 86400,
    "range_start": "2025-01-22T00:00:00Z",
    "range_end": "2026-06-05T00:00:00Z",
    "duplicate_open_time_count": 0,
    "duplicate_open_time_samples": [],
    "missing_interval_count": 0,
    "missing_interval_samples": [],
    "stale_latest_candle": false,
    "freshness_reference_time": null,
    "stale_after_open_time": null,
    "stale_tolerance_seconds": null
  },
  "warnings": [],
  "errors": []
}
```

Rules:

- Benchmark records are metadata and storage references, not full OHLCV history.
- Ordering must be deterministic by source, symbol, timeframe, and window identity.
- Supported window selections are configured lookback, explicit latest lookback, and explicit date window.
- Missing or too-short local history must produce `insufficient_data` with warnings, not fake success.
- Degraded OHLCV quality from `raw/market_data_views.json` must produce `insufficient_data` with warnings, not fake success.
- Benchmark output remains Halpha-owned JSON. Strategy experiments may consume it later without exposing third-party portfolio objects.

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
      "initial_cash": 10000.0,
      "fees_bps": 10,
      "slippage_bps": 5,
      "mode": "long_flat",
      "direction": "long_only",
      "execution_model_id": "close_to_close_next_bar_v1",
      "price_source": "close",
      "signal_timing": "signal_at_bar_close",
      "position_timing": "next_bar",
      "lookahead_policy": "no_same_bar_execution",
      "execution_timing": "research_close_to_close"
    },
    "window": {
      "start": "2025-01-22T00:00:00Z",
      "end": "2026-06-05T00:00:00Z",
      "rows": 500
    },
    "metrics": {
      "calculation_backend": "halpha.strategy_evaluation.evaluate_single_window_backtest",
      "execution_model_id": "close_to_close_next_bar_v1",
      "signal_timing": "signal_at_bar_close",
      "position_timing": "next_bar",
      "lookahead_policy": "no_same_bar_execution",
      "return_metric_basis": "net_after_costs",
      "total_return_pct": 9.8,
      "gross_return_pct": 12.4,
      "net_return_pct": 9.8,
      "total_cost_pct": 2.6,
      "cost_drag_pct": 2.6,
      "max_drawdown_pct": -18.2,
      "trade_count": 23,
      "turnover": 24.0,
      "exposure_pct": 56.0,
      "final_equity": 10980.0,
      "final_equity_multiplier": 1.098
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

Enabled parameter diagnostic contract:

```json
{
  "enabled": true,
  "status": "succeeded",
  "assumptions": {
    "max_combinations": 3,
    "grid_source": "quant.parameter_diagnostics.grids.tsmom_vol_scaled",
    "metric_scope": "latest_state_and_canonical_next_bar_backtest_summary",
    "selection_policy": "diagnostic_only_no_best_parameter_selection",
    "strategy_backtest_enabled": true,
    "execution_model_id": "close_to_close_next_bar_v1",
    "signal_timing": "signal_at_bar_close",
    "position_timing": "next_bar",
    "lookahead_policy": "no_same_bar_execution"
  },
  "grid": {
    "return_window": [10, 20, 30],
    "volatility_window": [20],
    "target_volatility": [0.2]
  },
  "tested_combinations": 3,
  "valid_combinations": 2,
  "invalid_combinations": 1,
  "stability": "sensitive",
  "signal_state_stability": {
    "status": "sensitive",
    "reason_codes": [
      "direction_sensitivity",
      "latest_regime_sensitivity",
      "invalid_combinations_present"
    ],
    "direction_counts": {
      "bullish": 1,
      "bearish": 1
    },
    "latest_regime_counts": {
      "risk_on_momentum": 1,
      "risk_off_negative_momentum": 1
    },
    "valid_combinations": 2,
    "invalid_combinations": 1
  },
  "performance_stability": {
    "status": "partially_stable",
    "reason_codes": [
      "invalid_combinations_present"
    ],
    "reasons": [
      {
        "code": "invalid_combinations_present",
        "message": "Invalid combinations limit performance stability evidence.",
        "value": 1
      }
    ],
    "metric_ranges": {
      "backtest_total_return_pct": {
        "min": 0.8,
        "max": 2.8,
        "range": 2.0,
        "threshold": 10.0,
        "observed_count": 2,
        "valid_combination_count": 2,
        "missing_count": 0
      },
      "backtest_max_drawdown_pct": {
        "min": -4.6,
        "max": -4.5,
        "range": 0.1,
        "threshold": 10.0,
        "observed_count": 2,
        "valid_combination_count": 2,
        "missing_count": 0
      },
      "backtest_trade_count": {
        "min": 1,
        "max": 1,
        "range": 0,
        "threshold": 3.0,
        "observed_count": 2,
        "valid_combination_count": 2,
        "missing_count": 0
      },
      "backtest_exposure_pct": {
        "min": 50.0,
        "max": 75.0,
        "range": 25.0,
        "threshold": 25.0,
        "observed_count": 2,
        "valid_combination_count": 2,
        "missing_count": 0
      }
    },
    "valid_combinations": 2,
    "invalid_combinations": 1,
    "min_valid_combinations": 2
  },
  "summary_metrics": {
    "direction_counts": {
      "bullish": 1,
      "bearish": 1
    },
    "latest_regime_counts": {
      "risk_on_momentum": 1,
      "risk_off_negative_momentum": 1
    }
  },
  "combinations": [
    {
      "combination_index": 1,
      "params": {
        "return_window": 10,
        "volatility_window": 20,
        "target_volatility": 0.2
      },
      "status": "succeeded",
      "metrics": {
        "direction": "bullish",
        "strength": "medium",
        "confidence": "medium",
        "latest_regime": "risk_on_momentum",
        "entry_count": 4,
        "exit_count": 3,
        "backtest_total_return_pct": 2.8,
        "backtest_max_drawdown_pct": -4.5,
        "backtest_trade_count": 1,
        "backtest_exposure_pct": 75.0
      },
      "error": null
    }
  ],
  "notes": [
    "Parameter diagnostics compare configured nearby values and do not choose trading parameters."
  ],
  "warnings": [
    {
      "severity": "warning",
      "code": "parameter_direction_sensitivity",
      "message": "tsmom_vol_scaled parameter grid produced multiple assessment directions.",
      "source": "parameter_diagnostic"
    }
  ]
}
```

Parameter diagnostic rules:

- Disabled or omitted diagnostics must record `{"enabled": false, "status": "disabled"}`.
- Enabled diagnostics must preserve configured grid ranges and max-combination assumptions.
- `tested_combinations`, `valid_combinations`, and `invalid_combinations` must be explicit.
- `combinations` records must contain bounded params, status, selected summary metrics, and a bounded error summary when unavailable.
- `stability` is a compatibility alias for `signal_state_stability.status`; new consumers should read the explicit signal-state and performance fields.
- `signal_state_stability` must classify direction and latest-regime agreement separately from performance evidence.
- `performance_stability.status` must be one of `stable`, `partially_stable`, `sensitive`, `insufficient_evidence`, or `no_valid_combinations`.
- Stable performance requires at least two valid combinations, all required backtest metrics present, no invalid combinations, and metric ranges within thresholds.
- Invalid combinations produce partial performance stability only when the valid performance evidence is otherwise stable; missing metrics or too few valid combinations produce insufficient evidence.
- Sensitive performance must record which return, drawdown, trade-count, or exposure range exceeded its threshold.
- Every performance-stability result must record `metric_ranges` and deterministic reason codes.
- `summary_metrics`, `notes`, and `warnings` should describe signal-state and performance stability or sensitivity. Do not report only a best historical result.
- Parameter diagnostics are sensitivity context only. They must not select trading parameters, rank strategies, or make return promises.

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

- Vectorbt may calculate indicators and signals.
- Vectorbt objects are internal implementation details.
- Halpha-owned JSON and Markdown artifacts are the stable downstream interface.
- Do not persist vectorbt objects, repr strings, internal class names, or raw portfolio objects as artifact fields.
- Do not embed vectorbt objects or large raw OHLCV series in AI-readable material.

Bounded backtest diagnostic rules:

- Backtest diagnostics are historical research material, not return forecasts.
- Diagnostics must record assumptions before metrics.
- Required assumptions include initial cash, fees, slippage, mode, direction, execution model identifier, signal timing, position timing, lookahead policy, price source, execution timing, and input data window.
- Metrics must stay narrow and reviewable. Suggested metrics are `total_return_pct`, `net_return_pct`, `gross_return_pct`, `total_cost_pct`, `cost_drag_pct`, `max_drawdown_pct`, `trade_count`, `turnover`, `exposure_pct`, `final_equity`, and `final_equity_multiplier`.
- Diagnostics must not emit trading instructions, live orders, position sizing, account actions, or guaranteed outcomes.
- Diagnostics may be `disabled`, `skipped`, `succeeded`, or `failed`.

Parameter diagnostic rules:

- Parameter diagnostics are optional and disabled unless configured.
- Diagnostics must record tested ranges, tested count, valid count, invalid count, max-combinations limit, assumptions, and stability notes.
- Diagnostics must summarize sensitivity and fragility, not select trading parameters automatically.
- Diagnostics must not create a strategy leaderboard or investment recommendation.

Strategy names:

- Strategy-centered flow uses explicit built-in strategy names such as `tsmom_vol_scaled`, `signed_tsmom_trend`, `breakout_atr_trend`, `sma_cross_trend`, `sma_cross_long_short`, `bollinger_rsi_reversion`, and `bollinger_rsi_long_short`.
- Initial implemented strategy-centered flow supports `tsmom_vol_scaled`, `signed_tsmom_trend`, `breakout_atr_trend`, `sma_cross_trend`, `sma_cross_long_short`, `bollinger_rsi_reversion`, and `bollinger_rsi_long_short`.
- The M1 demo signal names `trend`, `momentum`, `volatility`, and `volume_anomaly` are retired from the strategy-centered product path.
- Retired demo names are not migrated into strategy aliases.
- If an old demo name is requested after strategy adoption, config validation should fail with an actionable error.

## Strategy Evaluation Contract

Status: reusable single-window core, standalone command, pipeline adapter, AI-readable material, and report-context integration implemented.

Strategy evaluation is the reusable backtest and robustness layer for strategy research. It must be usable from the product pipeline and from a standalone research path without duplicating strategy logic.

Reusable evaluation core boundary:

- Inputs must be explicit data, config, and strategy records.
- Outputs must be Halpha-owned JSON-serializable records.
- The core must not depend on `RunContext`.
- The core must not read or write `runs/` by itself.
- The core must not call Codex.
- The core must not expose vectorbt objects, raw portfolio objects, or dependency internals.
- Pipeline and standalone runners are adapters around the same reusable evaluation core.

Reusable core input contract:

```json
{
  "strategy": {
    "name": "tsmom_vol_scaled",
    "params": {
      "return_window": 30,
      "volatility_window": 30,
      "target_volatility": 0.2
    }
  },
  "market_identity": {
    "source": "binance",
    "symbol": "BTCUSDT",
    "timeframe": "1d"
  },
  "ohlcv_rows": [],
  "signal_records": [],
  "cost_assumptions": {
    "fees_bps": 10.0,
    "slippage_bps": 5.0
  },
  "execution_model": {
    "execution_model_id": "close_to_close_next_bar_v1",
    "price_source": "close",
    "signal_timing": "signal_at_bar_close",
    "position_timing": "next_bar",
    "lookahead_policy": "no_same_bar_execution",
    "execution_timing": "research_close_to_close"
  },
  "evaluation_window": {
    "start": "2025-01-22T00:00:00Z",
    "end": "2026-06-05T00:00:00Z",
    "rows": 500
  }
}
```

Signed single-leg evaluation uses the same no-lookahead timing with a versioned
execution model:

```json
{
  "execution_model_id": "close_to_close_next_bar_signed_v1",
  "price_source": "close",
  "signal_timing": "signal_at_bar_close",
  "position_timing": "next_bar",
  "lookahead_policy": "no_same_bar_execution",
  "execution_timing": "research_close_to_close",
  "direction": "long_short",
  "position_unit": "fractional_signed_exposure"
}
```

Multi-leg evaluation uses the same no-lookahead timing with a separate
versioned execution model:

```json
{
  "execution_model_id": "close_to_close_next_bar_multi_leg_v1",
  "price_source": "close",
  "signal_timing": "signal_at_bar_close",
  "position_timing": "next_bar",
  "lookahead_policy": "no_same_bar_execution",
  "execution_timing": "research_close_to_close",
  "direction": "multi_leg",
  "position_unit": "research_leg_exposure"
}
```

Reusable core output contract:

```json
{
  "status": "succeeded",
  "strategy_name": "tsmom_vol_scaled",
  "source": "binance",
  "symbol": "BTCUSDT",
  "timeframe": "1d",
  "params": {
    "return_window": 30,
    "volatility_window": 30,
    "target_volatility": 0.2
  },
  "sample": {
    "start": "2025-01-22T00:00:00Z",
    "end": "2026-06-05T00:00:00Z",
    "rows": 500
  },
  "execution_model": {
    "execution_model_id": "close_to_close_next_bar_v1",
    "price_source": "close",
    "signal_timing": "signal_at_bar_close",
    "position_timing": "next_bar",
    "lookahead_policy": "no_same_bar_execution"
  },
  "cost_assumptions": {
    "fees_bps": 10.0,
    "slippage_bps": 5.0,
    "total_one_way_bps": 15.0
  },
  "strategy_metrics": {
    "gross_return_pct": 12.4,
    "net_return_pct": 9.8,
    "total_cost_pct": 2.6,
    "cost_drag_pct": 2.6,
    "max_drawdown_pct": -18.2,
    "volatility_pct": 31.4,
    "sharpe": 0.42,
    "sortino": 0.58,
    "final_equity": 1.098
  },
  "baseline_metrics": {
    "buy_and_hold": {
      "net_return_pct": 7.1,
      "max_drawdown_pct": -24.0,
      "volatility_pct": 28.0,
      "final_equity": 1.071
    },
    "cash": {
      "net_return_pct": 0.0,
      "max_drawdown_pct": 0.0,
      "volatility_pct": 0.0,
      "final_equity": 1.0
    }
  },
  "relative_metrics": {
    "excess_return_vs_buy_and_hold_pct": 2.7,
    "drawdown_delta_vs_buy_and_hold_pct": 5.8
  },
  "trade_summary": {
    "trade_count": 23,
    "completed_trade_count": 22,
    "open_trade_count": 1,
    "hit_rate_pct": 48.0,
    "turnover": 12.0,
    "exposure_pct": 56.0,
    "average_holding_bars": 18.0
  },
  "drawdown_summary": {
    "max_drawdown_pct": -18.2,
    "max_drawdown_start": "2025-03-01T00:00:00Z",
    "max_drawdown_end": "2025-04-15T00:00:00Z"
  },
  "equity_curve": [],
  "drawdown_curve": [],
  "visualization": {
    "schema_version": 1,
    "chart_type": "candlestick_backtest",
    "status": "available",
    "bars": [],
    "markers": [],
    "equity_curve": [],
    "limits": {
      "max_bars": 120,
      "max_markers": 80
    },
    "omitted": {
      "bars": 0,
      "equity_points": 0,
      "markers": 0
    },
    "warnings": []
  },
  "warnings": [
    {
      "severity": "warning",
      "code": "historical_research_only",
      "message": "Backtest evaluation is historical research material, not a forecast.",
      "source": "strategy_evaluation"
    },
    {
      "severity": "warning",
      "code": "low_trade_count",
      "message": "Trade count is below the research reliability threshold.",
      "source": "strategy_evaluation"
    }
  ],
  "errors": []
}
```

`trade_summary.trade_count` is the complete evaluation-window trade count.
`visualization.markers` is a bounded chart marker list and is not a complete
per-trade ledger. `visualization.omitted.markers` counts operation markers from
the full evaluation window that are not present in the bounded marker list.

Allowed evaluation statuses:

```text
succeeded
skipped
insufficient_data
failed
```

Evaluation status rules:

- `succeeded`: evaluation metrics were calculated from sufficient real OHLCV rows and strategy signal records.
- `skipped`: evaluation was disabled or upstream strategy runs were not configured.
- `insufficient_data`: input rows, signal records, or evaluation windows are too short for meaningful metrics.
- `failed`: evaluation raised an actionable error. Preserve strategy name, market identity, params, and a bounded error summary.

Execution model rules:

- The default research execution model is close-to-close with no same-bar execution.
- A signal known at bar `t` may affect position from bar `t+1`.
- `long_flat` target exposure follows each signal record; `long_only` keeps target exposure active after the first positive target and does not model exits.
- `close_to_close_next_bar_v1` keeps the current long-flat target exposure
  boundary of `0.0 <= target_exposure <= 1.0`.
- `close_to_close_next_bar_signed_v1` supports signed single-leg target
  exposure in `-1.0 <= target_exposure <= 1.0`; positive exposure is long,
  negative exposure is short, and zero exposure is flat.
- Signed evaluation uses previous-bar signed target exposure for the next
  close-to-close return. A short exposure profits when price falls and loses
  when price rises.
- Turnover is the absolute change in target exposure. A direct long `1.0` to
  short `-1.0` transition has turnover `2.0`.
- `close_to_close_next_bar_multi_leg_v1` aligns legs by inner-joined
  `open_time`, requires one shared timeframe, applies previous-bar leg target
  exposure to each leg's next close-to-close return, and sums leg
  contributions into aggregate gross and net returns.
- Multi-leg outputs record aggregate gross exposure, net exposure, turnover,
  drawdown, per-leg contribution, per-leg turnover, omitted rows, and
  insufficient/degraded alignment warnings.
- Evaluation must record fees and slippage assumptions before net metrics.
- Gross and net metrics must be separate.
- Strategy metrics must include gross return, net return, total cost, cost drag, drawdown, volatility, risk-adjusted metrics, and final equity.
- Trade summaries must include trade count, completed and open trades, hit rate, turnover, exposure, and average holding bars.
- Signed trade summaries additionally include long exposure, short exposure,
  average absolute exposure, long trade count, short trade count, long-to-short
  transition count, short-to-long transition count, and side-flip count.
- Contract-market single-window records may include `futures_diagnostics` when
  explicit instrument identity supports futures-aware interpretation. Spot
  records and identity-unknown records omit this field.
- Baseline metrics must include buy-and-hold and cash or no-position behavior where applicable.
- Relative metrics must compare net strategy behavior with buy-and-hold baseline behavior.
- Research limitation warnings must distinguish method or evidence limitations from strategy conclusions. Current warning codes include `historical_research_only`, `insufficient_sample_length`, `low_trade_count`, `no_strategy_exposure`, `high_turnover`, `high_cost_drag`, `funding_costs_not_provided_for_contract`, and `contract_volatility_exposure_risk`.
- Backtest evaluation remains research material, not a forecast, trading instruction, or return promise.

Pipeline strategy evaluation artifact:

```text
runs/<run_id>/analysis/strategy_evaluation_summary.json
```

Top-level contract:

```json
{
  "schema_version": 1,
  "artifact_type": "strategy_evaluation_summary",
  "created_at": "2026-06-06T00:00:00Z",
  "source_artifacts": [
    "analysis/quant_strategy_runs.json",
    "raw/market_data_views.json"
  ],
  "records": [],
  "warnings": [],
  "errors": []
}
```

Record contract:

```json
{
  "evaluation_id": "strategy_evaluation:tsmom_vol_scaled:binance:BTCUSDT:1d:2026-06-05T00:00:00Z",
  "status": "succeeded",
  "strategy_run_id": "quant_strategy_run:tsmom_vol_scaled:binance:BTCUSDT:1d:2026-06-05T00:00:00Z",
  "strategy_name": "tsmom_vol_scaled",
  "strategy_version": 1,
  "source": "binance",
  "symbol": "BTCUSDT",
  "timeframe": "1d",
  "input_view_id": "ohlcv_view:binance:BTCUSDT:1d:2026-06-05T00:00:00Z",
  "input_window_start": "2025-01-22T00:00:00Z",
  "input_window_end": "2026-06-05T00:00:00Z",
  "latest_candle_time": "2026-06-05T00:00:00Z",
  "params": {},
  "single_window": {},
  "walk_forward": {
    "enabled": true,
    "status": "succeeded",
    "method": {
      "name": "bounded_chronological_walk_forward_fixed_params",
      "params_optimized_per_window": false,
      "state_carryover_between_windows": false,
      "window_overlap": false
    },
    "window_policy": {
      "calibration_rows": 60,
      "window_rows": 60,
      "min_window_rows": 20,
      "min_windows": 3
    },
    "summary": {
      "window_count": 7,
      "succeeded_windows": 7,
      "mean_net_return_pct": 1.2,
      "median_net_return_pct": 0.8,
      "positive_net_return_window_pct": 57.1,
      "mean_excess_return_vs_buy_and_hold_pct": 0.3,
      "positive_excess_return_window_pct": 42.9,
      "worst_max_drawdown_pct": -9.4,
      "mean_turnover": 3.0,
      "mean_cost_drag_pct": 0.4,
      "net_return_range_pct": 16.1,
      "result_stability": "stable"
    },
    "windows": []
  },
  "parameter_stability": {
    "enabled": true,
    "status": "stable",
    "diagnostic_status": "succeeded",
    "selection_policy": "diagnostic_only_no_best_parameter_selection",
    "tested_combinations": 4,
    "valid_combinations": 4,
    "invalid_combinations": 0,
    "stability": "stable",
    "signal_state_status": "stable",
    "performance_status": "stable",
    "signal_state_stability": {
      "status": "stable",
      "reason_codes": [
        "direction_and_regime_agree"
      ],
      "direction_counts": {
        "bullish": 4
      },
      "latest_regime_counts": {
        "risk_on_momentum": 4
      },
      "valid_combinations": 4,
      "invalid_combinations": 0
    },
    "performance_stability": {
      "status": "stable",
      "reason_codes": [
        "metric_ranges_within_thresholds"
      ],
      "metric_ranges": {
        "backtest_total_return_pct": {
          "min": 1.0,
          "max": 3.0,
          "range": 2.0,
          "threshold": 10.0
        }
      },
      "valid_combinations": 4,
      "invalid_combinations": 0,
      "min_valid_combinations": 2
    },
    "region_counts": {
      "stable": 4,
      "fragile": 0,
      "inconsistent": 0,
      "insufficient_data": 0
    },
    "regions": [],
    "warnings": []
  },
  "overfitting_risk": {
    "status": "low",
    "selection_policy": "diagnostic_only_no_best_parameter_selection",
    "evidence": [
      "tested_combinations: 4.",
      "sample rows: 500.",
      "trade_count: 23.",
      "cost_drag_pct: 2.6.",
      "parameter_stability_status: stable.",
      "parameter_signal_state_stability_status: stable.",
      "parameter_performance_stability_status: stable.",
      "walk_forward_result_stability: stable."
    ],
    "warnings": []
  },
  "assessment": {
    "reliability": "unknown",
    "sample_quality": "unknown",
    "cost_sensitivity": "low",
    "overfitting_risk": "low",
    "summary": "Strategy evaluation has not produced enough evidence for reliability judgment.",
    "evidence": [
      "sample rows: 500.",
      "trade_count: 23.",
      "exposure_pct: 56.0.",
      "cost_drag_pct: 2.6.",
      "excess_return_vs_buy_and_hold_pct: 2.7.",
      "walk_forward_status: succeeded.",
      "walk_forward_succeeded_windows: 7.",
      "walk_forward_mean_net_return_pct: 1.2.",
      "walk_forward_positive_net_return_window_pct: 57.1.",
      "parameter_stability_status: stable.",
      "parameter_signal_state_stability_status: stable.",
      "parameter_performance_stability_status: stable.",
      "parameter_tested_combinations: 4.",
      "overfitting_risk_status: low."
    ],
    "uncertainty": []
  },
  "warnings": [],
  "error": null,
  "source_artifacts": [
    "analysis/quant_strategy_runs.json",
    "raw/market_data_views.json"
  ],
  "created_at": "2026-06-06T00:00:00Z"
}
```

Pipeline evaluation rules:

- The pipeline adapter must call the reusable evaluation core.
- Pipeline evaluation must consume existing strategy run records and real OHLCV history.
- Pipeline evaluation must not recalculate market data collection.
- Pipeline evaluation must not run Codex.
- Pipeline evaluation must not fabricate evaluation records for skipped, failed, or insufficient upstream states.
- Failed or insufficient strategy runs may produce skipped or insufficient evaluation records so downstream reports can explain missing evidence.
- Walk-forward evaluation uses fixed configured strategy params and must not optimize per window.
- Walk-forward windows are sequential and non-overlapping, with an initial calibration context and no state carryover between evaluation windows.
- Walk-forward `status` is `insufficient_data` when too few successful windows exist; partial window records may be preserved as evidence but must not be presented as a successful walk-forward result.
- Walk-forward warnings include too few windows, insufficient history, short samples, unstable results, and regime-dependent outcomes.
- Report-facing assessment must distinguish full-window single-window metrics from walk-forward evidence.
- Parameter stability must consume existing bounded parameter diagnostics when configured.
- Evaluation `parameter_stability.status` is a gate-compatible performance summary: `stable`, `fragile`, `inconsistent`, `insufficient_data`, or `disabled`.
- Evaluation records must also preserve `signal_state_stability` and `performance_stability` separately.
- `signal_state_stability` records direction/latest-regime agreement. It must not be used as proof of performance robustness.
- `performance_stability` records return, drawdown, trade-count, exposure, validity, metric ranges, and deterministic reason codes.
- Parameter regions summarize configured diagnostic combinations as stable, fragile, inconsistent, or insufficient-data signal-region evidence without ranking or selecting a best parameter set.
- Overfitting risk warnings must be first-class record warnings when triggered by high trial count, short samples, sensitive or insufficient performance stability, cost sensitivity, low trade count, or unstable walk-forward results.
- Overfitting risk is research context only and must not become automatic parameter selection.

Standalone strategy evaluation output:

Standalone evaluation is a research path for one or more explicitly selected strategy, source, symbol, timeframe, and parameter inputs. It must use the same reusable evaluation core and the same output record contract as pipeline evaluation.

Standalone output rules:

- Standalone evaluation must read configured shared OHLCV history or an explicit local input allowed by the implemented command contract.
- Standalone evaluation must write inspectable local artifacts.
- Standalone evaluation must not run the full report pipeline.
- Standalone evaluation must not execute Codex.
- Standalone evaluation must not mutate shared OHLCV history unless the implemented command explicitly performs a sync step.
- Standalone output must preserve cost assumptions, execution model, sample window, warnings, and errors.
- Standalone backtest output may include a bounded `visualization` block for dashboard review. It contains the backtest input-window candlestick bars, deterministic exposure-change markers, and a bounded equity curve. It must not embed full reusable OHLCV history or vectorbt objects.
- Implemented standalone command:
  `python -m halpha backtest --config <config> --strategy <strategy_name> --symbol <symbol> --timeframe <timeframe>`.
- The optional `--output-dir <dir>` argument overrides the default `runs/strategy_backtests/` output directory.
- Each standalone command run writes `strategy_backtest.json` with the reusable core output contract and `manifest.json` with command inputs, artifact paths, warnings, and errors.
- Each standalone backtest also registers a bounded record in `data/research/strategy_evaluations/strategy_evaluation_history.json` with `execution_source.type: standalone_backtest`. Report-run strategy evaluations register into the same shared history with `execution_source.type: report_run`. Shared history records copy review-critical fields such as strategy identity, input window, status, key metrics, warnings, and bounded visualization data when available, and reference the source artifacts instead of embedding full source histories.

Shared strategy evaluation history:

```text
data/research/strategy_evaluations/strategy_evaluation_history.json
```

Shared history record contract:

```json
{
  "history_id": "strategy_evaluation_history:report_run:<run_id>:<evaluation_id>",
  "record_type": "strategy_evaluation_history_record",
  "execution_source": {
    "type": "report_run",
    "run_id": "<run_id>"
  },
  "strategy_name": "tsmom_vol_scaled",
  "source": "binance",
  "symbol": "BTCUSDT",
  "timeframe": "1d",
  "input_window_start": "2026-06-01T00:00:00Z",
  "input_window_end": "2026-06-05T00:00:00Z",
  "metrics": {},
  "visualization": {},
  "source_artifacts": [
    "runs/<run_id>/analysis/strategy_evaluation_summary.json"
  ]
}
```

Standalone strategy experiment output:

Strategy experiments evaluate configured strategy candidates against fixed benchmark suite records outside the main report run. They must use the same single-window evaluation semantics as pipeline strategy evaluation, add bounded walk-forward summaries for gate evidence, and classify candidates with deterministic effectiveness gates.

Implemented standalone experiment command:

```text
python -m halpha experiment --config <config>
```

Optional arguments:

- `--strategy <strategy_name>` limits candidates and may be repeated.
- `--output-dir <dir>` overrides the default `runs/strategy_experiments/` output directory.

Experiment artifact:

```text
runs/strategy_experiments/<id>/strategy_experiment.json
```

Experiment top-level contract:

```json
{
  "schema_version": 1,
  "artifact_type": "strategy_experiment",
  "created_at": "2026-06-06T00:00:00Z",
  "experiment_id": "20260606T000000Z_strategy_experiment",
  "inputs": {
    "candidate_source": "configured_quant_strategies",
    "strategy_names": [
      "tsmom_vol_scaled"
    ],
    "benchmark_suite_artifact": "strategy_benchmark_suite.json"
  },
  "source_artifacts": [
    "strategy_benchmark_suite.json"
  ],
  "coverage": {
    "strategy_candidates": 1,
    "benchmark_records": 4,
    "benchmark_succeeded": 4,
    "benchmark_insufficient_data": 0,
    "evaluations": 4,
    "evaluations_succeeded": 4,
    "evaluations_insufficient_data": 0,
    "evaluations_failed": 0,
    "evaluations_skipped": 0
  },
  "candidates": [],
  "warnings": [],
  "errors": []
}
```

Strategy effectiveness gate artifact:

```text
runs/strategy_experiments/<id>/strategy_effectiveness_gates.json
```

Gate top-level contract:

```json
{
  "schema_version": 1,
  "artifact_type": "strategy_effectiveness_gates",
  "created_at": "2026-06-06T00:00:00Z",
  "policy": {
    "gate_statuses": [
      "effective",
      "watchlisted",
      "rejected",
      "insufficient_evidence"
    ],
    "single_window_profit_alone_can_be_effective": false,
    "llm_generated_gate_outcomes": false,
    "automatic_parameter_optimization": false,
    "historical_research_material": true
  },
  "source_artifacts": [
    "strategy_experiment.json"
  ],
  "coverage": {
    "strategy_candidates": 1,
    "effective": 0,
    "watchlisted": 0,
    "rejected": 0,
    "insufficient_evidence": 1
  },
  "records": [],
  "warnings": [],
  "errors": []
}
```

Gate record rules:

- One gate record must exist for every evaluated strategy candidate.
- `status` must be one of `effective`, `watchlisted`, `rejected`, or `insufficient_evidence`.
- Gate inputs must preserve benchmark coverage, net performance, buy-and-hold comparison, cost drag, drawdown, trade count, sample quality, bounded walk-forward stability, parameter signal-state stability, parameter performance stability, overfitting risk, position-model evidence, futures risk, multi-leg quality, feature availability, optimization robustness, warnings, and source artifacts.
- Gate reasons must explicitly record pass, block, reject, downgrade, or informational reasons with observed values and thresholds.
- Single-window profit alone must not produce `effective` status.
- Insufficient samples, insufficient benchmarks, insufficient walk-forward evidence, low trade count, misaligned multi-leg evidence, insufficient event or feature evidence, or failed optimization robustness evidence may produce `insufficient_evidence`.
- Weak net performance, weak baseline comparison, or excessive drawdown may produce `rejected`.
- Excessive cost drag, high turnover, excessive funding drag, missing funding evidence, weak short-side contribution, degraded multi-leg alignment, partial event or feature coverage, unstable walk-forward evidence, fragile parameter performance stability, fragile or overfit-risk optimization robustness, or elevated overfitting risk may produce `watchlisted`.
- Gate outcomes must be deterministic and derived from Halpha-owned JSON artifacts, not Codex or another LLM.
- Gate thresholds may be configured under `quant.effectiveness_gates`; omitted fields use conservative defaults.

Experiment manifest:

```text
runs/strategy_experiments/<id>/manifest.json
```

Manifest rules:

- Record command inputs, artifact paths, evaluation counts, gate counts, skipped or insufficient benchmarks, failures, warnings, and errors.
- Standalone experiment outputs stay outside per-run report directories.
- Product runs may generate current-run experiment, gate, and material artifacts under `analysis/` for report context integration.
- Do not run Codex, generate reports, select best parameters, promote strategies, place orders, or claim future performance.
- Failed, skipped, and insufficient benchmark evaluations must remain visible in JSON instead of being dropped.

Standalone experiment acceptance:

- Run `python -m halpha experiment --config <config>` after shared OHLCV history is available.
- Inspect `runs/strategy_experiments/<id>/manifest.json` and `strategy_effectiveness_gates.json` for benchmark, experiment, warning, error, and gate counts.
- Current default strategy acceptance expects at least three `effective` research candidates under deterministic gates.
- `effective` means a research candidate passed the configured historical evidence gates; it is not a trading approval, return forecast, position instruction, or portfolio allocation.

Pipeline strategy experiment artifacts:

```text
runs/<run_id>/analysis/strategy_experiment.json
runs/<run_id>/analysis/strategy_effectiveness_gates.json
runs/<run_id>/analysis/strategy_experiment_material.md
```

Pipeline strategy experiment rules:

- Use the current run's `analysis/strategy_benchmark_suite.json` as benchmark input.
- Use the same strategy experiment and gate semantics as the standalone command.
- Write current-run source artifacts with `analysis/` paths.
- Record experiment, gate, warning, error, and material counts in `run_manifest.json`.
- Do not select best parameters, place trades, generate action levels, or claim future performance.

AI-readable strategy experiment material rules:

- Summarize candidate gate statuses, benchmark coverage, net performance, baseline comparison, cost drag, sample quality, bounded walk-forward evidence, parameter signal-state stability, parameter performance stability, overfitting risk, reasons, warnings, and errors.
- Identify `effective`, `watchlisted`, `rejected`, and `insufficient_evidence` statuses as Halpha-generated deterministic gate outcomes.
- Keep rejected, watchlisted, unstable, or insufficient-evidence candidates visible and conservative.
- Do not embed full OHLCV history, full equity curves, or raw trade-by-trade logs.
- Do not ask Codex CLI to generate gate statuses, metrics, promotion decisions, trading instructions, or return forecasts.

AI-readable strategy evaluation material:

```text
runs/<run_id>/analysis/strategy_evaluation_material.md
```

Material rules:

- Summarize strategy reliability, sample quality, baseline comparison, cost assumptions, drawdown, turnover, exposure, trade count, walk-forward status, parameter signal-state stability, parameter performance stability, and overfitting risk.
- Keep metrics bounded and report-facing.
- Include source artifact references.
- Do not embed full equity curves, full OHLCV history, or raw trade-by-trade logs in AI context.
- Do not upgrade historical evaluation into recommendations, position sizing, or return forecasts.
- Preserve warnings near the strategy they affect.

Recommended material format:

````markdown
---
artifact_type: analysis_strategy_evaluation_material
schema_version: 1
audience: ai
source_artifacts:
  - analysis/strategy_evaluation_summary.json
---

# strategy_evaluation_material

## evaluation_overview

```yaml
material_scope: strategy_evaluation_summary
evaluation_record_count: 4
status_counts:
  succeeded: 4
reliability_counts:
  low: 2
  medium: 2
```

## report_guidance

```yaml
cost_assumptions:
  - Mention fees and slippage assumptions before interpreting net performance.
baseline_comparison:
  - Compare strategy net behavior with buy-and-hold and cash baselines.
sample_limits:
  - Keep sample limits close to any reliability statement.
reliability:
  - Do not upgrade weak, fragile, unstable, or insufficient evidence into stronger action language.
forbidden:
  - Do not generate new metrics.
```

## record: strategy_evaluation:tsmom_vol_scaled:binance:BTCUSDT:1d:2026-06-05T00:00:00Z

```yaml
strategy_name: tsmom_vol_scaled
source: binance
symbol: BTCUSDT
timeframe: 1d
assessment:
  reliability: medium
  overfitting_risk: elevated
single_window:
  net_return_pct: 9.8
  max_drawdown_pct: -18.2
baseline_comparison:
  buy_and_hold_net_return_pct: 7.1
walk_forward:
  status: insufficient_data
parameter_stability:
  status: disabled
  signal_state_status: unknown
  performance_status: unknown
overfitting_risk:
  status: elevated
warnings:
  - Historical evaluation is research material, not a forecast.
```
````

Manifest contract:

```json
{
  "artifacts": {
    "strategy_evaluation_summary": "analysis/strategy_evaluation_summary.json",
    "strategy_evaluation_material": "analysis/strategy_evaluation_material.md"
  },
  "counts": {
    "strategy_evaluation_records": 4,
    "strategy_evaluation_succeeded": 4,
    "strategy_evaluation_failed": 0,
    "strategy_evaluation_insufficient_data": 0,
    "strategy_evaluation_skipped": 0,
    "strategy_evaluation_walk_forward_records": 28,
    "strategy_evaluation_parameter_stability_records": 4,
    "strategy_evaluation_material_records": 4
  },
  "strategy_evaluation": {
    "status": "succeeded",
    "coverage": {
      "quant_strategy_runs": 4,
      "evaluation_records": 4,
      "records_with_single_window": 4,
      "walk_forward_windows": 28,
      "records_with_walk_forward": 4,
      "records_with_parameter_stability": 4
    },
    "warnings": [],
    "errors": []
  }
}
```

Downstream evaluation consumers:

| Consumer | Input | Rule |
| --- | --- | --- |
| `analysis/market_signals.json` | `analysis/quant_strategy_runs.json` | Maps strategy run assessments into report-loop strategy signals. Preserve strategy name, input window, evidence, uncertainty, insufficient-data state, warnings, and source artifacts. |
| `analysis/market_signal_material.md` | Normalized market signals | Remains signal-facing material; report context carries strategy evaluation material separately. |
| `analysis/strategy_experiment.json` | `analysis/strategy_benchmark_suite.json` | Evaluates configured strategy candidates against fixed benchmark records for the current run. |
| `analysis/strategy_effectiveness_gates.json` | `analysis/strategy_experiment.json` | Classifies candidates as effective, watchlisted, rejected, or insufficient-evidence with deterministic gate reasons. |
| `analysis/strategy_experiment_material.md` | `analysis/strategy_experiment.json`, `analysis/strategy_effectiveness_gates.json` | Converts candidate gate outcomes into bounded report-facing material. |
| Decision-intelligence artifacts | Deterministic regime, risk, signal, and delta artifacts | Remain decision-facing material; they must not create action levels from backtest returns alone. |
| `analysis/research_context.md` | AI-readable strategy evaluation material | Adds bounded evaluation context beside signal and decision material for report generation. |
| `codex_context/context.md` and `codex_context/prompt.md` | Research context and prompt rules | Require Codex CLI to treat evaluation as historical research material, not as a forecast. |
| `run_manifest.json` | Strategy evaluation artifacts and pipeline statuses | Records artifact paths, counts, coverage, warnings, and errors. |

Downstream consumers:

| Consumer | Input | Rule |
| --- | --- | --- |
| `analysis/market_signals.json` | `analysis/quant_strategy_runs.json` | Normalizes strategy run assessments into the existing report interface. |
| `analysis/market_signal_material.md` | Strategy runs and normalized market signals | Summarizes strategy conclusions, diagnostics, conflicts, risks, and uncertainty without embedding large OHLCV history. |
| `analysis/research_context.md` | AI-readable quant material | Adds bounded quant material to the report context. |
| `codex_context/context.md` and `codex_context/prompt.md` | Research context and prompt rules | Require Codex CLI to use upstream strategy conclusions and not derive new quant conclusions from raw OHLCV. |
| `run_manifest.json` | Strategy run artifacts and pipeline statuses | Records artifact paths, counts, failures, insufficient-data runs, enabled strategies, disabled strategies, and assumptions summaries. |

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
    "analysis/quant_strategy_runs.json",
    "raw/market_data_views.json"
  ],
  "signals": []
}
```

Signal record contract:

```json
{
  "signal_id": "market_signal:tsmom_vol_scaled:binance:BTCUSDT:1d:2026-06-05T00:00:00Z",
  "strategy_name": "tsmom_vol_scaled",
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
    "return_window_pct": 6.2,
    "realized_volatility_pct": 31.4,
    "volatility_scaled_exposure": 0.64,
    "latest_regime": "risk_limited_momentum"
  },
  "evidence": [
    "return_window_pct is 6.2% over the configured return window.",
    "realized_volatility_pct is 31.4% against target_volatility_pct 20.0%."
  ],
  "uncertainty": [
    "Strategy uses OHLCV close prices only and excludes text events."
  ],
  "insufficient_data": false,
  "source_artifacts": [
    "analysis/quant_strategy_runs.json",
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
- Include bounded parameter diagnostic summaries only as sensitivity context, never as best-parameter selection.
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
backtest_diagnostics_are_historical_research_material: true
backtest_diagnostics_are_forecasts: false
parameter_diagnostics_are_optimization: false
allowed_basis:
  - quant_strategy_runs
  - normalized_market_signals
  - bounded_input_window_metadata
  - bounded_backtest_diagnostic_summaries
  - bounded_parameter_diagnostic_summaries
  - key_values
  - evidence
  - uncertainty
```

## quant_overview

```yaml
material_scope: quant_strategy_signal_summary
normalized_market_signal_artifact: analysis/market_signals.json
quant_strategy_runs_artifact: analysis/quant_strategy_runs.json
signal_count: 4
strategy_count: 3
strategies:
  - breakout_atr_trend
  - bollinger_rsi_reversion
  - tsmom_vol_scaled
direction_counts:
  bullish: 2
  bearish: 1
  unknown: 1
confidence_counts:
  high: 1
  low: 1
  medium: 1
  unknown: 1
insufficient_data_count: 1
strategy_run_status_counts:
  succeeded: 3
  insufficient_data: 1
raw_ohlcv_history_embedded: false
source_artifacts:
  - analysis/market_signals.json
  - analysis/quant_strategy_runs.json
```

## strategy_matrix

```yaml
columns:
  - strategy_name
  - source
  - symbol
  - timeframe
  - direction
  - strength
  - confidence
  - latest_regime
  - diagnostics
  - insufficient_data
signals:
  - strategy_name: tsmom_vol_scaled
    source: binance
    symbol: BTCUSDT
    timeframe: 1d
    direction: bullish
    strength: medium
    confidence: high
    latest_regime: risk_on_momentum
    diagnostics:
      backtest_diagnostic_status: succeeded
      parameter_stability: stable
      parameter_signal_state_stability: stable
      parameter_performance_stability: stable
    insufficient_data: false
```

## confluence_and_conflict

```yaml
group_count: 2
confluence_group_count: 1
conflict_group_count: 1
groups:
  - group: binance:BTCUSDT:1d
    strategies:
      - tsmom_vol_scaled
      - bollinger_rsi_reversion
    direction_counts:
      bullish: 1
      bearish: 1
    confluence_direction: none
    conflict: true
    insufficient_data: false
    report_note: Strategies disagree for this market window; describe the conflict before synthesis.
```

## risk_and_uncertainty

```yaml
low_confidence_signals:
  - market_signal:bollinger_rsi_reversion:binance:BTCUSDT:1d:2026-06-05T00:00:00Z
insufficient_data_signals:
  - market_signal:breakout_atr_trend:binance:SOLUSDT:1d:2026-06-05T00:00:00Z
conflicting_groups:
  - binance:BTCUSDT:1d
uncertainty_notes:
  - Strategy uses OHLCV close prices only and excludes text events.
diagnostic_policy:
  backtest_summaries_are_forecasts: false
  parameter_diagnostics_are_optimization: false
raw_ohlcv_history_embedded: false
```

## report_guidance

```yaml
high_confidence_signals:
  - Use as quantitative evidence when direction is clear and no same-market conflict is present.
low_confidence_signals:
  - Use cautious language and explain why confidence is low.
conflicting_signals:
  - Describe disagreement across strategies before giving any synthesis.
insufficient_data_signals:
  - State that the strategy conclusion is unavailable for the affected market window.
source_rules:
  - Reference normalized market signals and quant strategy run artifacts.
  - Do not calculate new quantitative signals from raw OHLCV history.
```

## record: market_signal:tsmom_vol_scaled:binance:BTCUSDT:1d:2026-06-05T00:00:00Z

```yaml
record_type: market_signal
signal_id: market_signal:tsmom_vol_scaled:binance:BTCUSDT:1d:2026-06-05T00:00:00Z
strategy_name: tsmom_vol_scaled
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
  return_window_pct: 6.2
  realized_volatility_pct: 31.4
  volatility_scaled_exposure: 0.64
  latest_regime: risk_limited_momentum
  backtest_diagnostic_status: succeeded
  backtest_total_return_pct: 12.4
  backtest_max_drawdown_pct: -18.2
  backtest_trade_count: 23
  backtest_exposure_pct: 56.0
  backtest_final_equity: 11240.0
  parameter_diagnostic_status: succeeded
  parameter_tested_combinations: 3
  parameter_valid_combinations: 2
  parameter_invalid_combinations: 1
  parameter_stability: sensitive
  parameter_signal_state_stability: sensitive
  parameter_performance_stability: partially_stable
  parameter_performance_stability_reason_codes:
    - invalid_combinations_present
evidence:
  - return_window_pct is 6.2% over the configured return window.
  - realized_volatility_pct is 31.4% against target_volatility_pct 20.0%.
uncertainty:
  - Strategy uses OHLCV close prices only and excludes text events.
  - Historical backtest diagnostic is research material, not a forecast.
insufficient_data: false
source_artifacts:
  - analysis/market_signals.json
  - raw/market_data_views.json
backtest_diagnostic_policy: historical_research_material_only_not_forecast
parameter_diagnostic_policy: bounded_sensitivity_context_only_not_optimization
```
````

Rules:

- Include signal conclusions, key values, evidence, input-window metadata, and uncertainty.
- Include `quant_overview`, `strategy_matrix`, `confluence_and_conflict`, `risk_and_uncertainty`, and `report_guidance` before per-signal records.
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
strategy_experiment: analysis/strategy_experiment.json
strategy_effectiveness_gates: analysis/strategy_effectiveness_gates.json
strategy_experiment_material: analysis/strategy_experiment_material.md
market_signal_material: analysis/market_signal_material.md
market_signals: analysis/market_signals.json
market_data_views: raw/market_data_views.json
```

Research context rules:

- Embed or reference `analysis/market_signal_material.md`.
- Preserve existing market and text material.
- Keep the source policy explicit.
- State that market signals are bounded research material derived from the provided context.
- State that strategy diagnostics are historical research material, not forecasts.
- State that strategy experiment gates are deterministic research candidate statuses, not trading approvals.
- State when quantitative signals do not include text-event signal processing.

`codex_context/context.md` contract additions:

```yaml
quant_strategy_runs: analysis/quant_strategy_runs.json
strategy_experiment: analysis/strategy_experiment.json
strategy_effectiveness_gates: analysis/strategy_effectiveness_gates.json
strategy_experiment_material: analysis/strategy_experiment_material.md
market_signal_material: analysis/market_signal_material.md
market_signals: analysis/market_signals.json
market_data_views: raw/market_data_views.json
```

Codex prompt rules:

- Require a Simplified Chinese Markdown report.
- Require the first report line to be a single H1 title with the run timestamp rendered in Halpha's configured display timezone.
- Do not require or allow a separate title section.
- Prefer Markdown tables for market data, event calendars, and comparable non-strategy data.
- When multiple symbols or coins appear, organize main sections with symbol-level subheadings.
- Require quantitative strategy conclusions when strategy material exists, but only as interpretation needed for the report.
- Require evidence and uncertainty near strategy conclusions.
- Do not ask Codex CLI to recreate the full strategy run table; Halpha inserts that table after Codex output.
- Require conflict notes and watch points.
- Require risk notes only when they are context-specific, such as upcoming events, conflicting signals, volatility, data limitations, source gaps, or source-specific uncertainty.
- Do not ask Codex CLI to include fixed boilerplate risk disclaimers.
- Require synthesis to explain cross-source implications, conflicts, and assessment-changing conditions instead of repeating prior tables or summaries.
- Require backtest diagnostics to be described as historical research material when cited.
- Require strategy experiment gate statuses to be used as Halpha-generated statuses only.
- Require effective, watchlisted, rejected, and insufficient-evidence candidates to be identified when strategy experiment material exists.
- Require benchmark coverage, costs, sample limits, walk-forward evidence, overfitting checks, and uncertainty near strategy effectiveness statements.
- Forbid fabricated prices, sources, strategy conclusions, signals, or certainty.
- Forbid LLM-generated strategy gate statuses, reasons, metrics, or promotion decisions.
- Forbid trading instructions, position sizing, account actions, and investment recommendations.
- Forbid return promises or deterministic investment claims.
- Do not direct Codex CLI to inspect shared OHLCV storage.

Final report post-processing:

- When `analysis/quant_strategy_runs.json` exists, insert a deterministic Markdown table into `report/report.md` after Codex stdout validation.
- The table is generated by Halpha from strategy run artifacts, not by Codex CLI.
- One row represents one strategy run for one source, symbol, and timeframe.
- Include strategy name, source, symbol, timeframe, input window, status, direction, strength, confidence, and conclusion summary.
- Insert the table before the `综合判断` section when present; otherwise before `风险提示`; otherwise append it to the report.
- Codex CLI should explain and synthesize quantitative conclusions around this table, not reproduce the complete row-level strategy run display.
- When `analysis/strategy_effectiveness_gates.json` exists, insert a deterministic strategy effectiveness table into `report/report.md` after Codex stdout validation.
- The gate table is generated by Halpha from gate artifacts, not by Codex CLI.
- One row represents one strategy candidate gate record.
- Include strategy name, gate status, benchmark coverage, net performance, baseline comparison, cost drag, sample quality, walk-forward summary, overfitting risk, and key reasons.
- Codex CLI should explain and synthesize strategy effectiveness around this table, not invent or revise gate outcomes.

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

When strategy benchmark suites are created, `run_manifest.json` should record them:

```json
{
  "artifacts": {
    "strategy_benchmark_suite": "analysis/strategy_benchmark_suite.json"
  },
  "counts": {
    "strategy_benchmark_records": 4,
    "strategy_benchmark_succeeded": 4,
    "strategy_benchmark_insufficient_data": 0,
    "strategy_benchmark_failed": 0
  },
  "strategy_benchmark_suite": {
    "enabled": true,
    "records": 4,
    "succeeded": 4,
    "insufficient_data": 0,
    "failed": 0,
    "missing_history": 0,
    "source_artifacts": [
      "data/market/metadata/ohlcv_sync_state.json"
    ],
    "warnings": [],
    "errors": []
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
    "quant_strategy_runs_disabled": 0,
    "quant_strategies_enabled": 1,
    "quant_strategies_disabled": 0
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
    "parameter_diagnostics_enabled": true,
    "failures": [
      {
        "strategy_name": "tsmom_vol_scaled",
        "source": "binance",
        "symbol": "BTCUSDT",
        "timeframe": "1d",
        "input_view_id": "ohlcv_view:binance:BTCUSDT:1d:2026-06-05T00:00:00Z",
        "error_type": "ValueError",
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
- Count configured enabled and disabled strategies separately from actual strategy run statuses.
- Record enabled and disabled strategy names.
- Record bounded engine metadata when available.
- Record failure summaries with strategy name, source, symbol, timeframe, input view, error type, and actionable message.
- Do not record stack traces, secrets, local proxy values, local paths outside repo artifacts, credentials, tokens, cookies, account IDs, or private endpoints.

When implementation creates strategy evaluation or signal artifacts, `run_manifest.json` should record them.

Artifact keys:

```json
{
  "artifacts": {
    "market_data_views": "raw/market_data_views.json",
    "strategy_benchmark_suite": "analysis/strategy_benchmark_suite.json",
    "quant_strategy_runs": "analysis/quant_strategy_runs.json",
    "strategy_evaluation_summary": "analysis/strategy_evaluation_summary.json",
    "strategy_evaluation_material": "analysis/strategy_evaluation_material.md",
    "strategy_experiment": "analysis/strategy_experiment.json",
    "strategy_effectiveness_gates": "analysis/strategy_effectiveness_gates.json",
    "strategy_experiment_material": "analysis/strategy_experiment_material.md",
    "market_signals": "analysis/market_signals.json",
    "market_signal_material": "analysis/market_signal_material.md"
  },
  "counts": {
    "market_data_views": 4,
    "strategy_benchmark_records": 4,
    "strategy_benchmark_succeeded": 4,
    "strategy_benchmark_insufficient_data": 0,
    "strategy_benchmark_failed": 0,
    "quant_strategy_runs": 16,
    "quant_strategy_runs_succeeded": 16,
    "strategy_evaluation_records": 16,
    "strategy_evaluation_succeeded": 16,
    "strategy_evaluation_failed": 0,
    "strategy_evaluation_insufficient_data": 0,
    "strategy_evaluation_skipped": 0,
    "strategy_evaluation_material_records": 16,
    "strategy_experiment_candidates": 4,
    "strategy_experiment_evaluations": 16,
    "strategy_experiment_evaluations_succeeded": 16,
    "strategy_gate_candidates": 4,
    "strategy_gate_effective": 3,
    "strategy_gate_watchlisted": 0,
    "strategy_gate_rejected": 1,
    "strategy_gate_insufficient_evidence": 0,
    "strategy_experiment_material_records": 4,
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
build_strategy_benchmark_suite
evaluate_quant_strategies
evaluate_strategy_evaluation
build_strategy_experiment
build_market_signals

build_data_quality_summary
build_strategy_experiment_material
build_market_signal_material
```

The implemented benchmark suite stage is `build_strategy_benchmark_suite`. It sits after `build_market_data_views` and before `evaluate_quant_strategies`.

The implemented strategy evaluation stage is `evaluate_strategy_evaluation`. It sits after `evaluate_quant_strategies` and before current-run strategy experiment JSON.

The implemented strategy experiment JSON stage is `build_strategy_experiment`. It sits after `evaluate_strategy_evaluation` and before downstream market signals.

The implemented strategy experiment material stage is `build_strategy_experiment_material`. It runs in `build_materials`, after final data quality summary publication, and reads `analysis/strategy_experiment.json` plus `analysis/strategy_effectiveness_gates.json`.

Failure rules:

- Preserve artifacts from completed pipeline stages.
- Record failed pipeline stage and actionable error.
- Do not write fake signal artifacts to make downstream pipeline stages appear complete.

## Acceptance Trace

- A focused quant contract document exists: this file.
- Config, OHLCV, data view, strategy run, strategy evaluation, strategy signal, market signal, and AI-readable material contracts are defined above.
- Strategy inputs use raw OHLCV-style data; AI context uses strategy conclusions, normalized signal conclusions, diagnostics summaries, warnings, and bounded market context.
- Quant signals and strategy diagnostics are research material, not trades, positions, return forecasts, or financial advice.
- `analysis/quant_strategy_runs.json` fields and downstream consumers are defined above.
- Reusable strategy evaluation input, output, pipeline artifact, standalone output, material, and manifest contracts are defined above.
- Vectorbt objects are internal implementation details and are not stable artifact fields or AI context.
- Backtest diagnostics and strategy evaluation outputs are bounded historical research material, not return forecasts.
- Insufficient data, strategy failure, and warnings have explicit artifact representation rules.
- M1 demo signal names are retired from strategy-centered flow instead of migrated into strategy aliases.
- This document states initial adoption scope without making the contract milestone-only.
- This document separates current signal contracts from not-yet-implemented extensions.
