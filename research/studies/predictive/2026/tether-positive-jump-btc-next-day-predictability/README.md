# Tether positive jumps and next-day BTC perpetual returns

This predictive study tests whether a published stablecoin-to-Bitcoin jump-spillover
result survives a fully post-publication sample and an operational transfer to the
BTCUSDT perpetual used by Halpha. It does not create a product strategy, modify core
trading code, authorize trading, or claim durable profitability.

## Question

After a complete UTC day in which the Bitfinex USDT/USD price has both a statistically
significant positive BNS jump and a positive daily return, is the next 24-hour Binance
BTCUSDT perpetual return negative after a 15-minute action delay? Is the interaction
between the positive-jump indicator and USDT return incrementally negative after raw
USDT return, the jump indicator, prior BTC return and BTC realized variance?

## Why this question was selected

The current basic-data frontier has tested many adjacent transformations of OHLCV,
funding and cross-sectional BTC relationships without producing a qualified candidate.
This question adds a different economic mechanism: demand for a dollar-like settlement
asset may reveal BTC selling pressure before stop-loss or inventory adjustment completes.

Three stablecoin directions were screened before selection:

1. **Stablecoin issuance growth -> crypto returns** was rejected for now. Published
   event evidence is positive, but other primary work finds no return causality and
   issuance is endogenous to demand. Reliable multi-chain supply normalization adds
   complexity without resolving the causal ambiguity.
2. **Severe downward USDT depeg -> next-day rebound** was deferred. A 2026 peer-reviewed
   study reports the pattern, but severe events are rare; a genuinely fresh confirmation
   set would take too long for the current small-capital, quick-validation priority.
3. **Positive intraday USDT jump -> next-day BTC weakness** was selected. The source
   sample ends in 2021-06, leaving about five years of post-source data. Inputs are two
   small public price series, the output maps to one liquid BTC perpetual leg, and a UTC
   day decision is manually actionable at 08:00 China time.

Selection reflects project decision value, independence from exhausted directions,
falsifiability, public data availability, realistic implementation cost and expected
research cost. Novelty or a visually attractive backtest was not a selection criterion.

## Scope and interpretation

- The primary source uses hourly Bitfinex BTC/USD and USDT/USD data from 2018-11 to
  2021-06. This study uses Bitfinex USDT/USD only for the signal and Binance BTCUSDT
  perpetual for the delayed target. It is an operational transfer, not a numerical
  replication.
- All three windows start after the source sample. They remain sequentially sealed to
  prevent adapting the question to later outcomes.
- The event portfolio is only an economic feasibility screen. Even three predictive
  passes cannot qualify a strategy: a separate strategy-candidate study must bind
  actual funding, vectorbt replay, order semantics and framework-neutral handoff.
- BNS inference with only 24 hourly returns per day and a price near a one-dollar peg is
  a material finite-sample and tick-size limitation. Data-quality gates and a fixed
  threshold diagnostic expose but cannot eliminate that limitation.
- A profitable historical result would be evidence within the frozen sample, not proof
  of alpha, causality, future profitability, or a long-lived edge.

## Fixed project baseline

- Git commit: `0bdfeffa616260cebd2d2188ddc8deb9e85c77f4`
- Formal comparison context: `ONE_SHOT_DONCHIAN_ATR_BREAKOUT` `1.0.1`,
  `BTCUSDT-PERP`
- Research kind: `PREDICTIVE`
- Product effect: none

## Reproduction

```powershell
research/.venv/Scripts/python.exe research/studies/predictive/2026/tether-positive-jump-btc-next-day-predictability/study.py checkpoint
research/.venv/Scripts/python.exe research/studies/predictive/2026/tether-positive-jump-btc-next-day-predictability/study.py selftest
research/.venv/Scripts/python.exe research/studies/predictive/2026/tether-positive-jump-btc-next-day-predictability/study.py fetch --stage development
research/.venv/Scripts/python.exe research/studies/predictive/2026/tether-positive-jump-btc-next-day-predictability/study.py inspect --stage development
research/.venv/Scripts/python.exe research/studies/predictive/2026/tether-positive-jump-btc-next-day-predictability/study.py analyze --stage development
research/.venv/Scripts/python.exe research/studies/predictive/2026/tether-positive-jump-btc-next-day-predictability/study.py gate --stage development
research/.venv/Scripts/python.exe research/studies/predictive/2026/tether-positive-jump-btc-next-day-predictability/study.py conclude
research/.venv/Scripts/python.exe research/studies/predictive/2026/tether-positive-jump-btc-next-day-predictability/study.py validate
```

Evaluation and confirmation commands are identical with `--stage evaluation` or
`--stage confirmation`, but the script refuses to open them until the preceding gate
passes. Raw API responses and Binance zip files live outside Git at the exact path and
identity recorded in each source manifest.

