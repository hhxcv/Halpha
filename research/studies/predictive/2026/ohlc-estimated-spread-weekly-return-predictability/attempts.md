# Attempt log

## 2026-07-22 — question selection and preregistration

- Surveyed dynamic cross-crypto networks/lead-lag, turnover-volatility
  disagreement, and low-frequency bid-ask-spread evidence.
- Rejected network/lead-lag because the mature-perpetual operational version was
  already tested in Halpha and the published profitable variants require minute
  data and frequent rebalancing.
- Deferred turnover volatility because point-in-time supply/market-cap data are
  absent and the short-constraint mechanism is weakly matched to perpetuals.
- Selected CHL spread because it has a published crypto factor benchmark, precise
  OHLC-only estimator, low research cost, and a clear unresolved transfer gap.
- Downloaded the official RepOD CC0 tabular and original-format files to Git-
  external research storage. Both are retained by exact path, byte size, and
  SHA-256; the tabular export is used only for an independent reference summary.
- Frozen one primary configuration, two window diagnostics, one correction-form
  diagnostic, sequential stage gates, fixed simple explanations, costs, and a
  family stop before observing this question's stage outcomes.

Execution outcomes are appended only after the checkpoint and gates are run.

## 2026-07-22 — bound execution and sequential stop

- `checkpoint`, `bind`, and `inspect` completed. All 25 fixed symbols had 1,663
  continuous daily rows and passed OHLC/range/volume checks. Fifty-one reused
  Binance files and two Git-external RepOD files were verified by identity.
- The external benchmark check retained 325 usable value-weighted bid-ask weekly
  returns. Its arithmetic annualized mean was `1.084392`, with positive first- and
  second-half means. This approximately corroborates the broad-spot published
  phenomenon but was excluded from Halpha gates.
- Opened only `development` (52 weeks). Primary CHL high-minus-low mean was
  `0.008694`, but the four-week block 95% interval was
  `[-0.014817, 0.034821]`, only `46.15%` of weeks were positive, and the first
  chronological half mean was `-0.015039`.
- Mean rank IC was `-0.048457` (one-sided HAC p `0.8681`). The controlled CHL
  slope was positive but weak (`0.003911`, one-sided HAC p `0.1883`). Median
  absolute score correlation was highest with volatility (`0.7341`), below the
  duplicate threshold but economically important.
- CHL exceeded Amihud by `0.006241` on average, but exceeded high-volatility by
  only `0.000116`; both increment intervals included zero. The monthly-corrected
  CHL diagnostic spread was negative (`-0.002470`).
- The single-leg full-plan proxy after 52 bp underlying stress and a 4% annual
  hurdle averaged `0.003108`, but its 95% block interval was
  `[-0.006400, 0.014719]`, its first-half mean was negative, and one symbol
  supplied `59.73%` of aggregate positive contribution.
- Development gate `FAIL`. Evaluation and confirmation were not opened. No sort
  reversal, alternative window, correction, cost, universe, weekday, symbol, or
  regime was selected after observing the outcome.
- Final conclusion: `INSUFFICIENT_EVIDENCE`. The broad-spot diversified factor
  does not justify a mature-perpetual single-leg strategy candidate under this
  preregistration. Validation independently recomputed the economics and passed
  every stored identity check.
