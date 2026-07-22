# Preregistration

Frozen before fetching or calculating this rule's source pages.

## Identity and claim

- Research kind: `STRATEGY_CANDIDATE`
- Instrument: Binance USD-M `ETHUSDT-PERP`, long only
- Strategy identity: `RESEARCH_ETHUSDT_PERP_VOL60_TARGET8_CAP25_MONTHLY_ONE_SHOT_V1`
- Formal comparison only: `ONE_SHOT_DONCHIAN_ATR_BREAKOUT@1.0.1`
- Claim under test: economic and operational suitability as a semi-automatic monthly
  risk-premium plan. This is not a claim of market-neutral Alpha.

## Fixed rule

At UTC month open `t`:

1. Use the 60 daily close-to-close log returns ending at `t-1 day`.
2. Annualize sample standard deviation with `sqrt(365)`.
3. Set `weight = min(0.25, 0.08 / realized_volatility_60d)`.
4. Enter one ETHUSDT perpetual long with target notional equal to `weight` times the
   user's full-plan capital reference; close at next UTC month open. No additions,
   re-entry, stop, or discretionary substitution is allowed.
5. If warm-up, source identity, current venue eligibility, decision freshness, or
   user plan amount is incomplete, output is `UNKNOWN` and no plan is proposed.

The user—not the core strategy—must convert the target notional into the current
plan's `max_notional`. This is a monthly research handoff instruction, not autonomous
capital allocation and not a product implementation.

## Frozen evidence stages

- development: 2021-01-01 through 2022-12-31 (24 plans)
- evaluation: 2023-01-01 through 2024-12-31 (24 plans), opened only after a
  development PASS
- confirmation: 2025-01-01 through 2026-06-30 (18 plans), opened only after an
  evaluation PASS

The earlier ETH SMA research exposed all market periods. Sequential access here
prevents exact-rule outcome peeking, but does not make the price history pristine.

## Costs, benchmarks, diagnostics

- favorable: 6 bps fee/side, zero slippage, actual settled funding
- base: 6 bps fee/side, 10 bps slippage/side, actual settled funding
- stress: 6 bps fee/side, 20 bps slippage/side, positive funding multiplied by 1.5
  and negative funding multiplied by 0.5 from the long's perspective
- full-plan annual capital hurdle: 4%
- additional full-plan research-program haircut: 2%; combined gate hurdle: 6%
- simple risky benchmark: fixed 25% ETH perpetual long with identical monthly forced
  round trips and cost/funding scenarios
- simple safe benchmark: cash at zero return; the 4% hurdle separately represents
  minimum capital opportunity cost
- 6% and 10% volatility targets are frozen local diagnostics only. They cannot
  replace the 8% primary target after results are viewed.

## Stage gates

Every stage requires complete expected plans, data-quality PASS, VectorBT/manual
error no greater than `1e-10`, positive base total return, positive stress return
after the 4% hurdle, positive base return after the 6% combined hurdle, better base
drawdown and Sharpe than fixed 25%, nonnegative base results for both neighbor
targets, and no calendar-year base return below -10%. The confirmation additionally
requires positive stress total return and base drawdown above -10%.

Evaluation and confirmation remain sealed after any prior FAIL. No parameter repair,
alternate entry day, trend filter, subgroup, or instrument substitution is allowed
inside this question.

## Conclusion rule

- `SUPPORTS_WITHIN_SCOPE`: all three gates pass; conclusion remains limited by prior
  market-path exposure and requires later product qualification before implementation.
- `DOES_NOT_SUPPORT`: development fails, or an opened later stage has non-positive
  primary base total return.
- `INSUFFICIENT_EVIDENCE`: point estimates remain positive but one or more robustness
  gates fail, or later stages cannot be opened.
- `CANNOT_DETERMINE`: required public data or integrity cannot be established.

No conclusion changes product strategy, L4 state, capital, or account state.

