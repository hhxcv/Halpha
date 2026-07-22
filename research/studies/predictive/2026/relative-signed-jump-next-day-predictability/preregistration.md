# Preregistration

Frozen before downloading or inspecting exact development RSJ outcomes.

## Hypothesis

Higher RSJ predicts lower next-day returns. The primary spread is therefore the
equal-weight return of the lowest RSJ quintile minus the highest RSJ quintile and is
expected to be positive; rank IC and controlled slope are expected to be negative.

## Universe, data and stages

- Fixed 25 mature Binance USD-M perpetual symbols in `study.py`.
- Signal input: official 15-minute trade-price klines; a signal day must contain all
  96 bars plus the prior close needed for close-to-close returns.
- Daily controls: the already bound official daily public cache; no duplicate download.
- Development decisions: `[2022-03-26, 2023-07-01)`.
- Evaluation: `[2023-07-01, 2025-01-01)`.
- Confirmation: `[2025-01-01, 2026-07-20)`.
- Development is later than the source sample. Stages still open sequentially because
  the broad market path has been exposed in other Halpha studies.

## Frozen score and target

For each symbol and each complete UTC signal day ending at decision time `t`:

1. Compute close-to-close log returns from 15-minute closes.
2. `RV+ = sum(r_j^2 for r_j > 0)`, `RV- = sum(r_j^2 for r_j < 0)`,
   `RV = RV+ + RV-`, `RSJ15 = (RV+ - RV-) / RV`.
3. At least 20 symbols must be rankable and each must have trailing 30-day median
   daily quote volume of at least 10 million USDT.
4. Sort cross-sectionally; bottom/top 20% form the low/high RSJ portfolios.
5. Enter at `t + 15 minutes` using that bar's open and exit exactly 24 hours later
   using the corresponding bar open. No same-close execution is allowed.

Derived 30-minute and one-hour scores use the same complete 15-minute source day
and last close in each non-overlapping bucket. They are diagnostics only.

## Controls and simple explanations

The weekly Fama–MacBeth-style cross-sectional coefficient series controls for:

- previous one-day open-to-open return (short-term reversal);
- same-day 15-minute realized variance;
- trailing MOM14, beta84 to the leave-one-out market, total volatility28, MAX28 and
  log median quote volume30.

Simple baselines:

- prior-day loser minus winner next-day spread;
- equal-weight market return;
- highest-volume member of the prior-day loser quintile under identical delay, cost,
  notional and hurdle.

The RSJ one-leg proxy chooses the highest-volume member of the low-RSJ quintile,
uses 25% full-plan notional, subtracts 52 bp underlying round-trip cost and a 4%
annual full-plan capital hurdle. This can reject feasibility but cannot prove net
profitability because funding and exact fills are absent.

## Development gate

All checks must pass:

- bound data quality `PASS`, at least 440 eligible development days, at least 95%
  of expected decision days represented, and median rankable count at least 20;
- low-minus-high RSJ spread mean > 0, circular seven-day block-bootstrap 95% lower
  bound > 0, positive on at least 52% of days, and positive in both halves;
- mean daily rank IC < 0 with one-sided HAC p < 5%;
- mean controlled RSJ slope < 0 with one-sided HAC p < 5%;
- RSJ spread exceeds the simple one-day reversal spread on average;
- RSJ one-leg proxy mean and seven-day block-bootstrap lower bound > 0, both halves
  > 0, at least 10 selected symbols, at least half positive by symbol, and no symbol
  contributes more than 40% of positive proxy P&L;
- RSJ one-leg proxy exceeds the identically costed reversal proxy on average;
- 30-minute and one-hour diagnostic low-minus-high spreads are nonnegative;
- maximum median absolute RSJ/control Spearman correlation < 0.90.

Evaluation and confirmation repeat the same checks without changes.

## Stop rules

Any stage failure seals later stages. A primary economic sign failure yields
`DOES_NOT_SUPPORT`; otherwise the conclusion is `INSUFFICIENT_EVIDENCE`. Do not
switch to 5-minute data, reverse the trade, choose a different delay, day boundary,
tail, universe, control, cost, target, notional or sampling interval after results.
Any 5-minute question would need new authorization and a fresh independent rationale,
not be a rescue attempt for this study.

