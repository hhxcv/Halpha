# Basic-data semi-automatic candidate frontier

Question: after the latest independent tests and feasibility screens, does Halpha
currently have multiple basic-data, one-leg, small-account strategy candidates that
meet the research threshold for trade-core qualification?

Conclusion: **DOES_NOT_SUPPORT**.

The auditable count remains zero. This does not claim that profitable strategies do
not exist. It says the current retained evidence cannot honestly label any candidate
as having demonstrated long-term profitability or as ready for core qualification.

## Latest changes to the frontier

- ETH monthly 60-day/8%-target/25%-cap perpetual long failed its development gate.
  It reduced drawdown but did not clear capital/research hurdles or improve Sharpe.
- BTC downside-beta monthly predictability failed in the opposite direction from
  the broad-spot literature; no strategy conversion is allowed.
- BTC turn-of-month long was negative before and after realistic perpetual costs;
  its daily mechanism test also had the wrong sign, so the calendar family stop is
  binding.
- Intermediate VIX-beta ranking produced a positive raw mean and rank IC, but the
  economic confidence intervals crossed zero, the controlled relationship was not
  significant, and its one-leg proxy was unstable. Later stages stayed sealed.
- Amihud illiquidity produced a positive controlled coefficient but a negative raw
  rank IC, negative 14/56-day diagnostics, intervals crossing zero, and 0.958
  absolute rank dependence on quote volume. It is retained as insufficient rather
  than reinterpreted as a new liquidity strategy.
- The public CC0 broad-spot bid-ask-spread factor was independently and
  approximately corroborated, but its leakage-safe CHL transfer to mature
  perpetuals failed development. The mean was positive, yet only 46.15% of weeks
  were positive, the first half and rank IC were negative, the bootstrap lower
  bounds crossed zero, the monthly-corrected diagnostic was negative, and 59.73%
  of positive proxy contribution came from one symbol. Later stages and strategy
  conversion remain sealed.
- Residual momentum produced a visually strong `+1.81%` development spread and
  reduced common-market beta exposure, but only 50% of weeks were positive, the
  first half, rank IC and controlled slope were negative, both economic intervals
  crossed zero, and 68% of positive proxy P&L came from SOL. The frozen gate failed;
  no later stage or strategy conversion is allowed.
- Relative signed jump added an independent intraday-asymmetry test using 15-minute
  official archives. Its mean rank IC and controlled slope had the published negative
  sign and were significant, but the preregistered low-minus-high tail spread was
  `-0.0235%` per day, its conservative one-leg proxy was `-0.2403%` per day, and
  30-minute/one-hour diagnostics were also negative. The development gate failed;
  average ordering was not relabeled as tradable alpha.
- Tether positive-jump spillover added a source-grounded stablecoin-to-BTC mechanism
  using official Bitfinex hourly USDT/USD and Binance BTCUSDT perpetual data. The
  development point estimates had the published direction, but the controlled HAC
  result was not significant (`p=0.187`), the two chronological halves disagreed,
  the gross event-short bootstrap lower bound was `-0.650%`, and the 52 bp plus 4%
  hurdle proxy was negative. It is retained as `INSUFFICIENT_EVIDENCE`; evaluation,
  confirmation and strategy conversion remain sealed.
- BTC–S&P 500 correlation-change added a fully post-publication, time-corrected test
  of the institutional diversification-rebalancing mechanism. Both source-near and
  controlled development coefficients had the wrong positive sign; chronological
  halves reversed, frozen forecasts had negative OOS R2, and the 52 bp plus 4%
  hurdle proxy lost about 15.7% at interval endpoints. It is retained as
  `DOES_NOT_SUPPORT`; its favorable second half cannot be selected post hoc.
- Cross-sectional dispersion gating tested the recent claim that high market-wide
  dispersion weakens subsequent momentum. The controlled dispersion coefficient
  was negative but insignificant, only 13 development weeks were in the high state,
  and the low-dispersion/otherwise-cash one-leg proxy was `-0.1588%` per week and
  worse than unconditional MOM20. Its 13 failed gates close evaluation and prevent
  threshold, smoothing or momentum-window rescue searches.
- Fifteen-minute realized total variance tested a peer-reviewed measurement gap
  left by the failed daily-volatility studies. RV28 rank IC was significantly
  negative, but the high-minus-low interval crossed zero, the coefficient became
  positive after daily-volatility/MOM/MAX/beta/volume controls, and the single high-RV
  short proxy was `-0.4085%` per week after the stress cost and capital hurdle. It
  underperformed the simpler daily-volatility short baseline; evaluation, jump
  decomposition and small-coin rescue searches remain sealed.
- CME weekend-gap convergence was not opened because CME began near-24/7 crypto
  futures trading on 2026-05-29, creating a forward structural break. Cross-venue
  price discovery was also screened out because the documented horizon is
  tick/sub-second/seconds and needs order-book data plus automated execution.
- Fixed time-of-day/weekday direction was not reopened: the multi-exchange source
  finds no persistent return pattern across years and a 2024 revisit finds no robust
  cryptocurrency return seasonality. Turn-of-candle rules are adjacent to the
  already rejected quarter-hour family. Scheduled FOMC research currently supports
  a volatility/volume window, not a directional edge; monetization would require a
  separately authorized options or multi-leg volatility scope.
- PAXGUSDT perpetual was listed only on 2025-03-27 and lacks sequential history.
  The existing PAXG spot monthly trend question already failed development.
- Cross-sectional same-weekday seasonality was not opened as a strategy question:
  the published rule implies near-daily plan maintenance and later calendar studies
  report that most anomalies are absent or adaptive. This is a low decision-value
  mismatch for Halpha's semi-automatic owner workflow.
- Medium-horizon taker-flow parameter exploration was not opened because the 1m
  quarter-hour proxy family is already directly rejected; changing aggregation after
  that result would be adjacent post-result search, not independent evidence.
- Aggregate stablecoin-supply timing was rejected before study because primary
  feedback-controlled evidence finds no systematic BTC/ETH response and explains
  why aggregate issuance does not identify wallet-level buying. Broad machine
  learning was also screened out: its main inputs are already-covered basic signal
  families and its gains concentrate in small, illiquid, volatile coins requiring a
  broad high-turnover portfolio rather than a mature one-leg plan.
- An exact replay of the formal Donchian/ATR logic was not opened as a new Alpha
  study. The product contract requires the user to choose an activation time and
  direction first, and no historical activation schedule exists. Adding a Monday
  schedule or slow-trend direction would create a new trend strategy rather than
  replay product history. Existing Halpha trend families already failed independent
  time gates, while peer-reviewed technical-rule evidence shows BTC out-of-sample
  failure and material dependence on transaction costs, parameters and bubble
  regimes. The expensive 1m/15m replay therefore lacks incremental decision value.
- Rolling entropy, Hurst or martingale-difference efficiency was also screened out
  as a trade gate. These measures diagnose whether dependence exists but do not
  determine whether the next action should be momentum, reversal or cash. Published
  rolling tests find most mature cryptocurrencies unpredictable most of the time and
  locate more apparent inefficiency at higher frequencies, which conflicts with a
  low-maintenance semi-automatic plan. Choosing the direction after inspecting the
  local statistic would be a new, unvalidated meta-rule over already-rejected
  momentum and reversal families.
- The only active frozen PPC forward rule received an explicit gate-power audit.
  Under the exact existing nested percentile-bootstrap gate, a true 50 bp weekly net
  edge passes after 26 eligible weeks only 5.92% of the time; the null rejection rate
  is 1.78%. Thus 26 weeks remains a first checkpoint and a possible positive gate,
  but a non-pass is normally inconclusive. This prevents the frontier from treating
  elapsed time alone as reliable strategy qualification.

## What remains worth doing

1. Preserve the closest positive-but-insufficient fixed rules as forward-incubation
   items. Only genuinely new dates under unchanged rules can improve their status.
   For PPC, 26 eligible weeks is only the first checkpoint; exact calibration does
   not establish a later complete-decision horizon.
2. The current basic-data families now have direct evidence across trend/momentum,
   reversal/extremes, volatility/downside risk, volume/liquidity/OHLC-spread/order-flow proxy,
   intraday signed variation and realized variance, premium/funding, calendar, BTC
   relationship, stablecoin price spillover, dispersion-state interaction,
   cross-asset correlation learning and external uncertainty. Continue a new historical question only when primary research
   establishes an independent mechanism and a credible low-maintenance one-leg
   mapping; do not fill the queue with neighboring variants of these families. The
   current historical basic-data search is stopped until such a mechanism appears.
3. If the owner later authorizes multi-leg product scope, revisit the retained
   structural cash-carry evidence in a separate product task. Current research must
   not pretend that six synchronized legs fit the one-leg plan contract.
4. Do not treat product execution compatibility as Alpha evidence. A future exact
   formal-strategy study first needs an independently supported, preregistered
   activation-time and direction policy; execution replay alone cannot supply them.

Run `python study.py audit` to recheck every retained evidence identity and regenerate
`frontier.json` and `validation.json`. The script only reads research evidence and the
Git-external public exchange snapshot referenced by a retained manifest.
