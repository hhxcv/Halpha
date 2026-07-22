# Preregistration

Frozen before fetching this study's source pages or calculating any TOM return.

## Identity and claim

- Kind: `STRATEGY_CANDIDATE`
- Instrument: Binance USD-M `BTCUSDT-PERP`, long only
- Identity: `RESEARCH_BTCUSDT_TOM_LAST_TO_DAY4_LONG_0P5X_V1`
- Formal comparison only: `ONE_SHOT_DONCHIAN_ATR_BREAKOUT@1.0.1`
- Claim under test: current economic and operational suitability as a monthly
  semi-automatic timing plan, not proof of structural Alpha.

## Fixed primary rule

For every calendar month whose final day falls inside the evidence stage:

1. The schedule is known before entry and uses no return information.
2. Enter one `BTCUSDT-PERP` long at the UTC open of the final calendar day.
3. Target notional is exactly 0.5 times the user's full-plan capital reference.
4. Exit at the UTC open of calendar day 4 of the following month. This captures
   four 24-hour returns: the final day and days 1–3.
5. Do not add, re-enter, stop, substitute an instrument, or condition on trend,
   volatility, funding, weekday, month, or market state.
6. If source identity, current venue eligibility, schedule freshness, or the
   user-entered plan amount is incomplete, the plan is `UNKNOWN`/not proposed.

The user must express the 0.5x target as the plan's explicit `max_notional`.
This is a framework-independent research instruction, not autonomous sizing in
the core.

## Evidence stages

- development: final days from 2022-01-31 through 2023-12-31 (24 plans)
- evaluation: final days from 2024-01-31 through 2024-12-31 (12 plans), opened
  only after development PASS
- confirmation: final days from 2025-01-31 through 2026-06-30 (18 plans), opened
  only after evaluation PASS

The two main external studies end in 2021, making all three stages forward of
their public samples. Halpha has nevertheless viewed the broad BTC paths in
other questions, so this is not investigator-blind market history.

## Costs, funding, hurdle, and fixed diagnostics

- favorable: 6 bps taker fee/side, zero slippage, actual settled funding
- base: 6 bps fee/side, 10 bps slippage/side, actual funding
- stress: 6 bps fee/side, 20 bps slippage/side; long-paid positive funding is
  multiplied by 1.5 and long-received negative funding is retained at 0.5
- full-plan capital hurdle: 4% annual
- additional research-program haircut: 2% annual; base must clear the combined
  6% annual hurdle
- matched schedule benchmark: 0.5x long from UTC day 14 open to day 18 open of
  the same month, with identical costs and funding treatment
- risk-premium reference: 0.5x long from month-start to next month-start; it is
  descriptive, because its market exposure is much larger
- fixed local diagnostics only: `TOM3` (last day to day 3 open) and `TOM5`
  (penultimate day to day 4 open). They may not replace the primary rule.
- mechanism replication: HAC regression of daily open-to-next-open log return
  on a dummy for the final calendar day and days 1–3; maximum lag 7.

## Gates and stopping rule

Every stage requires data-quality PASS, all scheduled plans, VectorBT/manual
agreement within `1e-10`, positive base and stress totals, stress after the 4%
capital hurdle, base after the 6% combined hurdle, positive paired base mean
versus the mid-month schedule, positive HAC TOM coefficient, nonnegative base
results for TOM3/TOM5, base maximum drawdown above -15%, at least half of stress
months positive, and every calendar-year base slice positive.

Development additionally requires the stress monthly block-bootstrap 95% lower
bound above zero and one-sided HAC `p < 0.10`. Later stages use sign/robustness
gates because 12 or 18 monthly observations are too few for a sensible standalone
95% lower-bound requirement. If all stages pass, pooled stress monthly return and
pooled paired base improvement versus mid-month must both have three-month-block
bootstrap 95% lower bounds above zero before support is possible.

Any stage FAIL seals later stages. No repair of leverage, dates, UTC boundary,
window, cost, direction, target, hurdle, filter, or month subset is allowed.

## Conclusion rule

- `SUPPORTS_WITHIN_SCOPE`: all three stages and pooled gates pass; research-only
  handoff still requires a later core qualification task.
- `DOES_NOT_SUPPORT`: a required economic sign/hurdle is non-positive.
- `INSUFFICIENT_EVIDENCE`: economic signs are favorable but statistical,
  neighbor, year, concentration, drawdown, or pooled evidence is inadequate.
- `CANNOT_DETERMINE`: public input or implementation integrity cannot be shown.

No conclusion changes product code, L4, capital, or real-account state.

