# Preregistration

Frozen before downloading or inspecting exact development BTC target outcomes.

## Hypotheses

Primary predictive hypothesis:

- `positive_bns_jump * usdt_daily_log_return` has a negative coefficient for the next
  24-hour BTCUSDT perpetual log return after a 15-minute action delay.

Operational event hypothesis:

- on positive BNS jump days, the delayed BTC return is negative, so an event-triggered
  BTC short has positive gross return and survives a deliberately conservative
  one-leg cost/hurdle screen.

The regression hypothesis is closest to the published result. The event portfolio is
a stricter project-relevance screen, not something reported by the source paper.

## Frozen data and stages

- Signal: official Bitfinex `tUSTUSD` one-hour candles.
- Target and BTC controls: official Binance USD-M `BTCUSDT` 15-minute trade-price
  klines.
- Development signal days: `[2021-07-01, 2023-01-01)`.
- Evaluation signal days: `[2023-01-01, 2024-07-01)`.
- Confirmation signal days: `[2024-07-01, 2026-07-20)`.
- Every stage is after the source sample ending 2021-06. Evaluation opens only after a
  development `PASS`; confirmation opens only after an evaluation `PASS`.

## Frozen signal construction

For each UTC signal day `D`:

1. Require the Bitfinex hourly closes at every bar-open timestamp from `D-1 23:00`
   through `D 23:00`, inclusive. No missing-candle imputation is allowed.
2. Compute 24 consecutive log returns from those 25 closes.
3. `RV = sum(r_i^2)`.
4. `BV = (pi/2) * sum(|r_i| |r_(i-1)|)`.
5. `TP = N * N/(N-2) * mu_(4/3)^(-3) *
   sum(|r_i r_(i-1) r_(i-2)|^(4/3))`, where `N=24` and
   `mu_p = 2^(p/2) Gamma((p+1)/2) / Gamma(1/2)`.
6. `z_BNS = sqrt(N) * (RV-BV) / sqrt((pi^2/4 + pi - 5) * TP)`.
7. `positive_bns_jump = 1` only if `z_BNS > 1.9599639845` and the sum of the 24 hourly
   returns is positive. Zero or invalid quarticity is not a jump.
8. The continuous interaction score is
   `positive_bns_jump * usdt_daily_log_return`.

This matches the current CRAN `highfrequency` default linear BNS formula for BV/TP and
the source paper’s 5% classification and return-sign direction. It does not claim to
recreate the source’s unpublished filtering code.

## Frozen target, controls and delay

- Decision time: `D+1 00:00 UTC`, after all signal bars have closed.
- Entry: Binance BTCUSDT perpetual 15-minute bar open at `D+1 00:15 UTC`.
- Exit: the corresponding bar open at `D+2 00:15 UTC`.
- Target: log exit/entry return. No same-close or same-timestamp execution.
- BTC prior return: open at `D+1 00:00` divided by open at `D 00:00`.
- BTC realized variance: squared 15-minute close-to-close log returns for signal day
  `D`, using only bars closed by the decision.

Controlled OLS/HAC regression:

`target ~ const + usdt_return + positive_bns_jump + interaction
        + btc_prior_return + btc_realized_variance`

The primary coefficient is `interaction`; Newey-West/HAC maximum lag is seven days.
A simpler source-near regression omits the two BTC controls and is reported but is not
the primary gate.

## Fixed-threshold diagnostic

The source paper reports a robustness rule of a positive daily USDT return greater than
0.003%. This study fixes `positive_fixed_jump = usdt_daily_log_return > 0.00003` and
reruns the controlled interaction regression. It is diagnostic only and cannot replace
the BNS primary signal.

## Economic feasibility screen

On every eligible calendar day:

- if `positive_bns_jump=1`, take a hypothetical one-day BTC short at 25% of full-plan
  capital and subtract 52 basis points underlying round-trip cost;
- otherwise hold no position;
- subtract a 4% annual full-plan capital hurdle every calendar day.

Thus `daily_plan_pnl = event * 0.25 * (-target - 0.0052) - 0.04/365`.
The 52 bp stress covers fees plus spread/slippage but not funding. Passing cannot qualify
a strategy; actual funding is mandatory in the later strategy-candidate question.

Simple explanations and baselines:

- unconditional scheduled BTC short over identical target windows;
- event days versus non-event days;
- prior BTC daily return and realized variance in the primary regression;
- raw USDT return and the jump dummy separately from their interaction.

## Data-quality gate

All must hold per stage:

- bound source verification `PASS`;
- at least 95% of expected signal days produce complete signal and target rows;
- at least 98% of expected Bitfinex hourly timestamps are present in the fetched
  boundary;
- no duplicate or off-grid timestamps, non-positive prices, or invalid OHLC relations;
- median daily nonzero USDT hourly returns >= 4 and median unique hourly closes >= 4;
- at least 20 positive BNS jump events and events in at least five calendar quarters.

## Predictive and economic gate

All must hold independently in development, evaluation and confirmation:

- controlled interaction coefficient < 0 with one-sided HAC p < 5%;
- source-near interaction coefficient < 0;
- controlled coefficient is negative in both chronological halves;
- mean event short return > 0, positive on at least 52% of events, positive in both
  halves, and a circular 14-day block-bootstrap 95% lower bound > 0;
- mean event short return exceeds the unconditional scheduled-short mean;
- mean full-plan daily feasibility P&L > 0, both halves > 0, and its circular 14-day
  block-bootstrap 95% lower bound > 0;
- no one positive calendar quarter contributes more than 50% of all positive-quarter
  feasibility P&L;
- fixed-threshold controlled interaction coefficient < 0 with one-sided HAC p < 10%.

Bootstrap repetitions: 5,000; deterministic seed `20260722` plus a fixed stage offset.

## Stop and interpretation rules

Any stage failure seals all later stages. No reverse trade, different peg venue, day
boundary, lag, delay, BNS threshold, fixed threshold, cost, target, control set or event
definition may rescue this question.

- If either the controlled coefficient or gross event-short mean has the wrong sign,
  conclude `DOES_NOT_SUPPORT`.
- If signs agree but uncertainty, quality, robustness or economic gates fail, conclude
  `INSUFFICIENT_EVIDENCE`.
- If all three stages pass, conclude `SUPPORTS_WITHIN_SCOPE` for prediction only and
  open a separately frozen strategy-candidate study.
- `CANNOT_DETERMINE` is reserved for unrecoverable source or computation failure.

