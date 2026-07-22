# Preregistration

Frozen before inspecting the exact score’s development result.

## Question and sign

Does higher standardized 14-day residual momentum predict higher next-week returns
among a fixed liquid perpetual universe? Expected signs are positive for the
high-minus-low spread, rank IC and controlled slope.

## Time and universe

- Symbols: the fixed 25-symbol mature Binance USD-M universe listed in `study.py`.
- Public daily bars: 2022-01-01 through 2026-07-21 inclusive.
- Development decisions: `[2023-03-04, 2024-03-02)`, 52 Saturdays.
- Evaluation decisions: `[2024-03-02, 2025-03-01)`, 52 Saturdays.
- Confirmation decisions: `[2025-03-01, 2026-07-18)`, 72 Saturdays.
- Stages open strictly in that order. A failed gate permanently seals later stages
  for this question.

## Frozen predictor

At each Saturday 00:00 UTC decision and for each eligible symbol:

1. Calculate daily open-to-open simple returns.
2. Construct a leave-one-out equal-weight market return from the other 24 symbols.
3. Estimate `r_i = alpha + beta * r_market + error` over the trailing 84 complete
   daily observations ending at the decision.
4. For the last 14 observations, calculate `r_i - beta * r_market`; intentionally do
   not subtract the fitted alpha.
5. Set `RMOM14 = mean(residual_14) / sample_std(residual_14)`.
6. Require trailing 30-day median quote volume of at least 10 million USDT.
7. Rank at least 20 eligible instruments; the top and bottom 20% define the spread.
8. The target is Monday open to the following Monday open: a two-day action gap and
   seven-day holding interval.

Only one primary configuration is selectable. RMOM7 and RMOM28 are diagnostics;
they cannot replace RMOM14 after observing results.

## Baselines and controls

- Same-week ordinary `MOM14` top-minus-bottom spread.
- Leave-one-out market-beta spread of RMOM tails versus ordinary-momentum tails.
- Unconditional equal-weight market return.
- Controls in the weekly cross-sectional regression: ordinary MOM14, beta84,
  idiosyncratic volatility84, total volatility28, MAX28 and log median volume30.
- One-leg feasibility proxy: choose the highest-volume member of the RMOM top
  quintile, apply 25% plan notional, subtract 52 bp underlying round-trip cost and
  a 4% annual full-plan capital hurdle. This is not a strategy backtest and excludes
  funding; it may only reject economic feasibility, not establish net profitability.

## Development gate

All checks must pass:

- complete data quality, 52 decision weeks and median rankable count at least 20;
- RMOM high-minus-low mean > 0, circular four-week block-bootstrap 95% lower bound
  > 0, positive in at least 55% of weeks, and both half-period means > 0;
- mean weekly rank IC > 0 with one-sided HAC p < 10%;
- mean controlled RMOM slope > 0 with one-sided HAC p < 10%;
- RMOM spread exceeds ordinary MOM14 spread on average;
- median absolute RMOM-tail market-beta spread is below the ordinary-momentum-tail
  value, matching the proposed exposure-reduction mechanism;
- one-leg proxy mean and block-bootstrap lower bound > 0, both halves > 0, at least
  10 selected symbols, at least half profitable on mean, and no symbol contributes
  more than 40% of positive proxy P&L;
- RMOM7 and RMOM28 diagnostic spreads are nonnegative;
- median absolute Spearman correlation between RMOM14 and any control is < 0.90.

Evaluation and confirmation use the same frozen checks and no parameter changes.

## Falsification and family stop

Any gate failure yields `DOES_NOT_SUPPORT` when a primary economic sign fails;
otherwise it yields `INSUFFICIENT_EVIDENCE`. Do not reverse the sign, switch to the
short leg, choose a better residual window, add BTC/sector factors, change the tail,
universe, target, gap, cost or hurdle, or promote a diagnostic. A future question
requires a genuinely new mechanism or new forward data, not a neighboring setting.

