# Preregistration

Frozen before fetching Cboe/Binance bytes or calculating any Halpha VIX-beta rank.

## Identity and scope

- Kind: `PREDICTIVE`
- Predictor: `RESEARCH_INTERMEDIATE_VIX_BETA_36W_NEXT_WEEK_V1`
- Universe: 25 fixed mature Binance USD-M perpetuals listed in `study.py`
- Product baseline: commit `0bdfeffa616260cebd2d2188ddc8deb9e85c77f4`
- Formal comparison only: `ONE_SHOT_DONCHIAN_ATR_BREAKOUT@1.0.1`
- Maximum claim: release or reject a separate strategy-candidate question. No
  strategy object, handoff, capital action, or product change can result here.

## Predictor and target

At each fixed Saturday 00:00 UTC decision time:

1. Select the latest Cboe VIX close dated no later than Friday and no earlier than
   Wednesday. Weekly VIX change is current close minus the preceding week's close.
2. Fit `delta_vix_t = a + b * delta_vix_(t-1)` using only earlier weekly changes,
   expanding from 2019 with at least 52 observations. Current innovation is actual
   minus the strictly prior forecast.
3. For each instrument, over the latest 36 complete Saturday-to-Saturday weeks,
   regress its log return on an intercept, the equal-weight leave-one-out market
   log return, and the VIX innovation. The current VIX coefficient is the signal.
4. Require 30-day median quote volume of at least 10m USDT and at least 20 rankable
   instruments. Sort beta ascending with symbol as deterministic tie-break.
5. Use the middle 20% nearest the cross-sectional median as the predicted-high
   group; the bottom and top 20% are the two extremes. This direction is fixed by
   Han (2024), not selected from Halpha outcomes.
6. Target is Monday 00:00 UTC open to the following Monday open, starting two days
   after the Saturday decision. No Saturday/Sunday target return enters the claim.

Primary response is equal-weight middle minus equal-weight average of low/high
extremes. Supporting responses are rank IC of `1 - 2*abs(beta_percentile-0.5)`, a
weekly controlled cross-sectional slope, and a concave quadratic-beta slope.

## Controls and fixed diagnostics

Controls available at Saturday: leave-one-out market beta, last 7-day and 28-day
momentum, 28-day realized volatility, past-28-day MAX, and log 30-day median quote
volume. Controls are cross-sectionally standardized each week.

The only fixed beta-window diagnostics are 26 and 52 weeks. The highest-volume
member of the middle group is a single-leg feasibility proxy. It is screened at
25% of full-plan capital, 52 bp underlying round-trip friction, and a 4% annual
full-plan capital hurdle. It excludes funding and is not a backtested strategy.

## Sequential evidence

- development: decisions 2023-03-04 through 2024-02-24 (52 weeks)
- evaluation: 2024-03-02 through 2025-02-22 (52 weeks), sealed until development PASS
- confirmation: 2025-03-01 through 2026-07-11 (72 weeks), sealed until evaluation PASS

All stages start after the external sample ended on 2023-02-17. Broad market paths
have been visible in other Halpha questions, so exact-output sequencing is not
claimed as investigator blindness.

## Development gate

Development requires:

- public-source data quality PASS, 52 action weeks, median rankable count at least
  20, and no time-order violation;
- positive middle-minus-extremes mean, four-week block-bootstrap 95% lower bound
  above zero, and at least 55% positive spread weeks;
- positive mean middle-score rank IC with one-sided HAC `p < 0.10`;
- positive controlled middle-score Fama–MacBeth slope with one-sided HAC
  `p < 0.10`, and negative quadratic beta-rank-squared slope with one-sided
  concavity `p < 0.10`;
- positive highest-volume single-leg proxy after 52 bp and full-plan hurdle, with
  block-bootstrap 95% lower bound above zero;
- both chronological halves positive for the spread and proxy;
- 26- and 52-week diagnostic spreads nonnegative;
- at least 10 proxy-selected symbols, at least half positive by selected-symbol
  mean, no symbol above 40% of total positive contribution, and median absolute
  correlation between the score and any control below 0.90.

Later stages use the same economic, sign, half, breadth, neighbor, and inference
gates. Every FAIL seals later stages. No reversal to extremes, window search,
different quantiles, symbol subgroup, VIX level/state, target horizon, entry day,
control removal, or cost repair is allowed inside this family.

## Conclusion

- `SUPPORTS_WITHIN_SCOPE`: all three stages pass; only a new actual-funding
  strategy-candidate question is released.
- `DOES_NOT_SUPPORT`: the main spread or single-leg economic proxy is non-positive.
- `INSUFFICIENT_EVIDENCE`: economic signs are positive but inference, robustness,
  breadth, or independent-stage gates fail.
- `CANNOT_DETERMINE`: source or implementation integrity is not established.

