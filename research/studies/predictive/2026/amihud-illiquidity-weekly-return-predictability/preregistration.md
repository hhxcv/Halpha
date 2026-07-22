# Preregistration

## Identity and fixed question

- Kind: `PREDICTIVE`.
- Predictor ID: `RESEARCH_AMIHUD28_HIGH_NEXT_WEEK_V1`.
- Baseline commit: `0bdfeffa616260cebd2d2188ddc8deb9e85c77f4`.
- Formal-strategy background only:
  `ONE_SHOT_DONCHIAN_ATR_BREAKOUT 1.0.1 / BTCUSDT-PERP`.

Question: among the fixed mature-perpetual universe, does high 28-day Amihud
illiquidity predict higher next-week returns than low illiquidity, with positive
rank IC and positive controlled slope after volatility, MAX, momentum, market beta,
and volume? Does a conservative single-leg feasibility proxy retain enough net
margin to authorize a separate strategy-candidate question?

This study itself cannot qualify a strategy, create a handoff, or make a long-term
profitability claim.

## Fixed universe and data

`1000XECUSDT, AAVEUSDT, AVAXUSDT, BCHUSDT, BNBUSDT, CRVUSDT,
DASHUSDT, ENSUSDT, ETCUSDT, HBARUSDT, KAVAUSDT, LINKUSDT, LTCUSDT,
NEARUSDT, RUNEUSDT, SNXUSDT, SOLUSDT, TRXUSDT, UNIUSDT, VETUSDT,
XLMUSDT, XMRUSDT, XRPUSDT, ZECUSDT, ZILUSDT`.

- Daily UTC Binance USD-M klines: 2022-01-01 through 2026-07-21.
- Current exchange metadata is quality context only; it must not dynamically change
  the list.
- Parent raw cache and manifest are fixed by path, byte length, and SHA-256. No
  product data, account data, database, credentials, or runtime configuration.
- Each decision requires all 25 symbols' complete warm-up and target endpoints;
  after the fixed 10m USDT median-volume floor, at least 20 must remain rankable.

The universe is a current-survivor list, not point-in-time market history. Results
must not be generalized to delisted coins, new listings, microcaps, or all venues.

## Signal and timeline

For decision Saturday `t` and formation window `W`:

1. For daily bar `d`, use simple open-to-next-open return
   `r_i,d = open_i,d+1 / open_i,d - 1`; pair it with the quote volume reported for
   the bar that begins at `d`.
2. `ILLIQ_i,t(W) = mean(|r_i,d| / quote_volume_i,d)` over exactly the `W`
   complete bars ending at Saturday `t`.
3. Primary score is `log(ILLIQ_i,t(28))`. Ascending symbol order breaks exact ties.
4. Low and high groups are the bottom and top `ceil(20% * N)` scores. Main spread
   is equal-weight high minus equal-weight low next-week return.
5. Controls, all known by `t`: 56-day leave-one-out market beta, 7- and 28-day
   momentum, 28-day return volatility, 28-day maximum daily return, and log median
   quote volume over the preceding 30 bars.
6. Entry proxy: Monday `t+2d` open. Exit: following Monday `t+9d` open. No same-day
   entry and no intervening information may affect the frozen rank.

Primary formation is 28 days. Fixed non-selectable diagnostics are 14 and 56 days.
They can refute robustness but cannot replace the primary result.

## Stages and sealing

- development: decisions 2023-03-04 through 2024-02-24 (52 weeks);
- evaluation: 2024-03-02 through 2025-02-22 (52 weeks), opened only after
  development PASS;
- confirmation: 2025-03-01 through 2026-07-11 (72 weeks), opened only after
  evaluation PASS.

All dates are after the 2014–2022 source samples used by the most recent selected
paper. They are not fully researcher-blind because broad crypto paths were visible
in other Halpha studies. The stage-specific ranks and outcomes are frozen only by
this question's checkpoint and sequential gates.

## Statistics and feasibility proxy

For every stage and window retain full symbol panel, weekly aggregates, and
selected-proxy rows.

- Four-week circular-block bootstrap, 5,000 repetitions, seed `20260722`.
- HAC/Newey-West intercept or Fama-MacBeth mean tests with four lags.
- Weekly Spearman rank IC between log Amihud and next-week return.
- Weekly cross-sectional controlled slope on standardized log Amihud plus all fixed
  controls.
- Weekly high-vol-minus-low-vol and low-volume-minus-high-volume spreads are simple
  explanation diagnostics, never replacement strategies.
- Single-leg feasibility proxy: select the highest trailing-volume member inside
  the high-illiquidity quintile; use 25% full-plan notional, subtract 52 bp from the
  underlying round trip, then subtract a 4% annual full-plan hurdle. Funding is
  omitted, so the proxy cannot qualify trading.

## Mandatory gate for each stage

All checks must pass:

1. data quality PASS, every expected action week present, median rankable count at
   least 20;
2. primary high-minus-low mean positive, block-bootstrap 95% lower bound positive,
   and at least 55% of weekly spreads positive;
3. mean rank IC positive with one-sided HAC p < 0.10;
4. controlled Amihud slope positive with one-sided HAC p < 0.10;
5. feasibility-proxy mean and bootstrap lower bound positive after stress cost and
   hurdle;
6. spread and proxy means are positive in both chronological halves;
7. 14- and 56-day diagnostic spread means are nonnegative;
8. proxy selects at least 10 symbols, at least half of selected symbols have
   positive mean proxy return, and no symbol supplies more than 40% of aggregate
   positive contribution;
9. median absolute weekly rank correlation between the Amihud score and any one
   fixed control remains below 0.90.

A negative primary spread or negative proxy mean is `DOES_NOT_SUPPORT`. Positive
means with failed statistical, stability, distinctness, breadth, or coverage gates
are `INSUFFICIENT_EVIDENCE`. Unreliable inputs or implementation that cannot be
resolved without changing the question are `CANNOT_DETERMINE`. Only three
sequential PASS stages can be `SUPPORTS_WITHIN_SCOPE`, which authorizes only a new
actual-funding strategy-candidate study.

## Family stop

After a failed stage, do not reverse the sort, change window, quantiles, universe,
volume floor, weekday, entry gap, holding period, cost, hurdle, controls, symbol,
or favorable regime. Do not open a low-volume or volatility rule from the
diagnostics. A future question must have a genuinely independent mechanism and a
new preregistration.

## Known omissions and invalidation

- No actual funding, bid/ask spread, depth, market impact, queue, partial fill,
  account fee tier, margin, liquidation, ADL, tax, or manual-delay model.
- Quote volume is not market capitalization and cannot fully control size.
- Daily Amihud is not actual trade impact and may combine volatility, volume
  measurement error, and exchange-specific activity.
- A later strategy study would require actual settled funding, executable cost
  stress, risk path, plan semantics, and framework-independent decision traces.
