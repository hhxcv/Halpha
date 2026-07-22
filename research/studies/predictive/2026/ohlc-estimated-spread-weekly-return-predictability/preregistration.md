# Preregistration

## Identity and fixed question

- Kind: `PREDICTIVE`.
- Predictor ID: `RESEARCH_CHL28_HIGH_NEXT_WEEK_V1`.
- Baseline commit: `0bdfeffa616260cebd2d2188ddc8deb9e85c77f4`.
- Formal-strategy background only:
  `ONE_SHOT_DONCHIAN_ATR_BREAKOUT 1.0.1 / BTCUSDT-PERP`.

Question: among the fixed mature-perpetual universe, does a high trailing 28-pair
two-day-corrected Abdi-Ranaldo CHL estimate predict higher next-week returns than
a low estimate, with positive rank IC and positive controlled slope after Amihud
illiquidity, volatility, MAX, momentum, market beta, and volume? Does it beat the
two fixed simple explanations and retain enough single-leg net margin to authorize
a separate strategy-candidate question?

This study itself cannot qualify a strategy, create a handoff, or make a long-term
profitability claim.

## Fixed universe and data

`1000XECUSDT, AAVEUSDT, AVAXUSDT, BCHUSDT, BNBUSDT, CRVUSDT,
DASHUSDT, ENSUSDT, ETCUSDT, HBARUSDT, KAVAUSDT, LINKUSDT, LTCUSDT,
NEARUSDT, RUNEUSDT, SNXUSDT, SOLUSDT, TRXUSDT, UNIUSDT, VETUSDT,
XLMUSDT, XMRUSDT, XRPUSDT, ZECUSDT, ZILUSDT`.

- Daily UTC Binance USD-M klines: 2022-01-01 through 2026-07-21.
- Current exchange metadata is quality context only; it must not dynamically
  change the list.
- Parent raw cache and manifest are fixed by path, byte length, and SHA-256.
- RepOD V1 factor returns are fixed as external reference data; they never enter a
  stage gate or the Halpha return panel.
- No product data, account data, database, credentials, or runtime configuration.
- Each decision requires complete warm-up and target endpoints. After the fixed
  10m USDT median-volume floor, at least 20 symbols must remain rankable.

The universe is a current-survivor list, not point-in-time market history. Results
must not be generalized to delisted coins, new listings, microcaps, all venues, or
the source paper's 565-asset spot universe.

## Signal and leakage-safe timeline

For decision Saturday `t` and pair count `W`:

1. `eta_d = (log(high_d) + log(low_d)) / 2`.
2. `moment_d = (log(close_d) - eta_d) * (log(close_d) - eta_(d+1))`.
3. `s_d = sqrt(max(4 * moment_d, 0))`.
4. `CHL_i,t(W) = mean(s_d)` for `d = t-(W+1)` through `t-2` inclusive.
   Thus `eta_(d+1)` ends at Friday `t-1`; Saturday's unfinished high/low/close is
   never used.
5. Primary score is `CHL_i,t(28)`. Ascending symbol order breaks exact ties.
6. Low and high groups are the bottom and top `ceil(20% * N)` scores. Main spread
   is equal-weight high minus equal-weight low next-week return.
7. Controls, all known at `t`: 28-day log Amihud, 56-day leave-one-out market beta,
   7- and 28-day momentum, 28-day return volatility, 28-day maximum daily return,
   and log median quote volume over the preceding 30 bars.
8. Entry proxy: Monday `t+2d` open. Exit: following Monday `t+9d` open. No same-day
   entry and no intervening information may affect the frozen rank.

Primary formation is 28 two-day pairs. Fixed non-selectable diagnostics are 14 and
56 pairs. A monthly-corrected 28-pair CHL ranking is another fixed robustness
diagnostic. None can replace or reverse a failed primary result.

## Stages and sealing

- development: decisions 2023-03-04 through 2024-02-24 (52 weeks);
- evaluation: 2024-03-02 through 2025-02-22 (52 weeks), opened only after
  development PASS;
- confirmation: 2025-03-01 through 2026-07-11 (72 weeks), opened only after
  evaluation PASS.

The selected factor-zoo source ends in 2024, so development and part of evaluation
overlap its calendar even though Halpha data and instruments are independent.
Confirmation contains later calendar evidence but is opened only through the
sequential gates. Broad crypto paths were visible in earlier Halpha work; this is
not a fully researcher-blind experiment.

## Statistics, simple explanations, and feasibility proxy

For every opened stage and window retain full symbol panel, weekly aggregates, and
selected-proxy rows.

- Four-week circular-block bootstrap, 5,000 repetitions, seed `20260722`.
- HAC/Newey-West intercept or weekly Fama-MacBeth mean tests with four lags.
- Weekly Spearman rank IC between CHL and next-week return.
- Weekly cross-sectional controlled slope on standardized CHL plus every fixed
  control, including log Amihud.
- Fixed simple explanations: high-minus-low 28-day Amihud and high-minus-low
  28-day volatility. The primary CHL spread must have a higher mean than both.
- Monthly-corrected CHL is a robustness diagnostic only.
- Single-leg feasibility proxy: select the highest trailing-volume member inside
  the high-CHL quintile; use 25% full-plan notional, subtract 52 bp from the
  underlying round trip, then subtract a 4% annual full-plan hurdle.

The 52 bp stress includes fees plus execution allowance, but actual settled
funding is omitted. Even a PASS can only open a separate strategy-candidate study,
which must add funding, executable-cost stress, risk paths, plan semantics, and a
framework-independent decision trace.

## Mandatory gate for each stage

All checks must pass:

1. data quality PASS, every expected action week present, median rankable count at
   least 20;
2. primary high-minus-low mean positive, block-bootstrap 95% lower bound positive,
   and at least 55% of weekly spreads positive;
3. mean rank IC positive with one-sided HAC p < 0.10;
4. controlled CHL slope positive with one-sided HAC p < 0.10;
5. primary mean exceeds both fixed Amihud and volatility high-minus-low means;
6. feasibility-proxy mean and bootstrap lower bound positive after stress cost and
   hurdle;
7. spread and proxy means are positive in both chronological halves;
8. 14- and 56-pair primary-form diagnostic spreads and the monthly-corrected
   28-pair spread are nonnegative;
9. proxy selects at least 10 symbols, at least half of selected symbols have
   positive mean proxy return, and no symbol supplies more than 40% of aggregate
   positive contribution;
10. median absolute weekly rank correlation between CHL and any fixed control
    remains below 0.90.

A negative primary spread, negative feasibility mean, or nonpositive incremental
mean versus either fixed explanation is `DOES_NOT_SUPPORT`. Positive incremental
means with failed statistical, stability, distinctness, breadth, or coverage
gates are `INSUFFICIENT_EVIDENCE`. Unreliable inputs or an implementation that
cannot be resolved without changing the question are `CANNOT_DETERMINE`. Only
three sequential PASS stages can be `SUPPORTS_WITHIN_SCOPE`.

## Family stop

After a failed stage, do not reverse the sort, change estimator, correction,
window, quantiles, universe, volume floor, weekday, entry gap, holding period,
cost, hurdle, controls, selected symbol, or favorable regime. Do not promote the
Amihud, volatility, monthly-corrected, 14-pair, or 56-pair diagnostic as a strategy.
A future question must have a genuinely independent mechanism and a new
preregistration.

## Known omissions and invalidation

- No actual funding, bid/ask quote, depth, market impact, queue, partial fill,
  account fee tier, margin, liquidation, ADL, tax, or manual-delay model.
- CHL is an estimator, not the executable spread of a 24/7 perpetual contract.
- Quote volume is not market capitalization and cannot fully control size.
- Survivor-fixed symbols can materially overstate broad-universe persistence.
- A diversified broad-spot factor can exist while a single mature-perpetual leg is
  unusable; that is a legitimate negative result, not a reason to relax the gate.
- A positive backtest supports only a scoped predictive relation; it does not
  prove alpha or guarantee long-term profitability.
