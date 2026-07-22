# Preregistration

Baseline commit: `0bdfeffa616260cebd2d2188ddc8deb9e85c77f4`.
Formal strategy background: `ONE_SHOT_DONCHIAN_ATR_BREAKOUT@1.0.1` on
`BTCUSDT-PERP`; it is only a fixed comparison context.

## Fixed hypothesis and data

- Research kind: `PREDICTIVE`.
- Universe: the existing fixed 25 mature Binance USD-M targets; BTC is the external
  market proxy and is not ranked.
- Main predictor: 60 daily log returns ending two full UTC days before month-open.
  `down_beta60 = cov(r_i, r_btc | r_btc < 0) / var(r_btc | r_btc < 0)` with at least
  15 negative BTC observations.
- Direction: higher downside beta predicts higher next-month open-to-open return.
- Controls: total beta60, total volatility60, momentum60, maximum daily return28,
  and log median quote volume30.
- Non-selectable diagnostics: downside beta45 and downside beta90.
- Minimum rankable symbols: 20; tails: 20% each; one full-day information gap.

Stages are development 2022–2023, evaluation 2024, and confirmation 2025. Only a
full preceding PASS can open the next stage. Existing market paths have been viewed
in other questions, but this exact predictor and its stage outputs are uncomputed.

## Primary evidence

Per month report high-minus-low next return, Spearman rank IC, high-downside-beta
long proxy, and high-downside-beta return minus high-total-beta and high-total-vol
returns. Run monthly Fama–MacBeth regressions both alone and with all controls; use
HAC lag 3 and three-month circular block-bootstrap intervals.

The 0.25x long proxy is:

`0.25 * (high-tail gross next return - 0.0052) - 0.04 * holding_days / 365`.

It is only an economic floor. Funding and exact order lifecycle must be studied later.

## Frozen development gate

All conditions must pass:

- data quality PASS; at least 21 action months and 20 rankable symbols each;
- high-minus-low mean and bootstrap lower bound positive;
- rank IC mean and bootstrap lower bound positive;
- uncontrolled and controlled downside-beta slopes positive with one-sided HAC
  `p < 0.05`;
- high-tail long proxy mean and bootstrap lower bound positive;
- high-downside-beta tail beats both high-total-beta and high-total-vol tails on
  average, with the high-total-beta incremental bootstrap lower bound positive;
- both calendar years have positive spread, IC, and proxy;
- beta45 and beta90 diagnostics have positive spread, IC, and proxy;
- at least 8 symbols and 3 categories are selected; no single positive selected
  symbol contributes more than 35% of gross positive return.

Any failure seals later stages and prohibits changing direction, beta definition,
lookback, gap, tail, universe, controls, costs, or threshold inside this family.

Conclusion is `SUPPORTS_WITHIN_SCOPE` only after all three stages pass. Development
failure is `DOES_NOT_SUPPORT` when the core signs/economics fail, otherwise
`INSUFFICIENT_EVIDENCE`. A result never changes product, capital, or account state.

