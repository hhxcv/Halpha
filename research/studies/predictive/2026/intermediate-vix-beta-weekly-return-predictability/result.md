# Result

## Conclusion

`INSUFFICIENT_EVIDENCE`

The pre-registered development gate failed. The study therefore does not support
opening evaluation or confirmation, converting this signal into a strategy, or
claiming long-term profitability. Product effects are `NONE`.

## Answer to the question

The 36-week intermediate VIX-beta ranking showed an encouraging raw development
mean and a significant rank IC, but did not demonstrate a sufficiently stable,
controlled, economically actionable predictive relationship. Specifically:

- middle-minus-extremes averaged +0.5968% per target week, with four-week
  block-bootstrap 95% interval [-0.8612%, +1.9742%];
- 48.08% of weekly spreads were positive, below the frozen 55% requirement;
- mean rank IC was +0.08438 (one-sided HAC p=0.000128);
- the controlled middle-score slope was +0.0485% per standardized score unit but
  was not significant (one-sided HAC p=0.4238);
- the quadratic term had the expected negative sign but was not significant
  (one-sided HAC p=0.2701);
- the single-leg feasibility proxy averaged +0.2259% of full-plan capital per
  week after modeled stress cost and hurdle, but its 95% interval was
  [-0.4225%, +0.9485%] and its first half was negative.

These failures are not repaired by the positive 26- and 52-week diagnostic means:
those windows were frozen as non-selectable robustness diagnostics.

## Evidence boundary

- Stable product baseline:
  `0bdfeffa616260cebd2d2188ddc8deb9e85c77f4`.
- Formal comparator: `ONE_SHOT_DONCHIAN_ATR_BREAKOUT` version `1.0.1` on
  `BTCUSDT-PERP`; it was not changed or re-estimated here.
- Research identity:
  `RESEARCH_INTERMEDIATE_VIX_BETA_36W_NEXT_WEEK_V1`.
- Fixed universe: 25 mature Binance USD-M perpetuals listed in
  `preregistration.md`.
- Binance data: 1,663 complete daily UTC OHLCV bars per symbol, 2022-01-01 through
  2026-07-21, retained as 50 official public-response pages outside Git.
- Cboe data: 1,929 VIX closes from 2019-01-02 through 2026-07-21, from the official
  historical CSV.
- Development evidence: 52 Saturday decisions from 2023-03-04 through
  2024-02-24, Monday entry and next-Monday target. Later stages stayed sealed.
- Checkpoint digest:
  `b07b8e6290531c4a2754d683028319fffcc34689bc7192825483cd616eab7c85`.
- Source-manifest digest:
  `d8cab91fb7ccdc39204aa2b783d13376b92ba0137fb3cb8e6a164cb432ed3514`.

The source paper's exact paywalled model equation was unavailable, so this is an
explicit operational, post-publication adaptation rather than a numerical
replication. All test dates follow the paper's stated February 2023 sample end,
but earlier Halpha work exposed the researcher to broad crypto price paths; that
weakens the interpretation of this development period as wholly untouched.

## Costs and missing dimensions

This predictive screen models a conservative 52 bp underlying round trip, 25%
full-plan notional allocation, and a 4% annual full-plan hurdle for the single-leg
proxy. It does not model actual symbol-specific funding, spread histories,
liquidation, depth, borrow constraints, or order execution. That omission is
acceptable only because the development gate failed before strategy conversion;
it would be unacceptable evidence for a tradable candidate.

## Counterevidence and failure conditions

The result would have needed a positive bootstrap lower bound, at least 55%
positive weekly spreads, controlled and concavity evidence at the frozen HAC
threshold, a positive proxy interval and both halves, and broader symbol
selection. It failed seven mandatory checks. The most consequential counterfacts
are that the controlled slope was statistically weak, the economic intervals
crossed zero, and the proxy's first half lost money.

The family stop prohibits searching adjacent VIX-beta windows, reversing the
ranking, changing quantiles, choosing favorable symbols, shifting the entry day,
or opening later stages under this question. A genuinely independent future
question may reuse the retained data but must establish a new economic mechanism
and preregistration.

## Reproduction and validation

Run the commands in `README.md` with `research/.venv`. Raw sources are restored or
re-fetched from the identities in `source_manifest.json`; generated development
panels, weekly summaries, and selected-leg rows are retained as nine CSV files.

Validation status is `PASS`: calculations were independently recomputed from the
hashed raw cache, the gate is bound to the analyzed result, and all CSV byte hashes
match. Validation digest:
`62616654fc97a84d3206a5da644cca632ac55485cc1b30232069866d9c62b1fd`.

## Remaining unknowns

- Whether Han's exact unpublished/paywalled specification would materially change
  the result cannot be determined from accessible primary material.
- Evaluation and confirmation behavior is deliberately unknown because the
  development gate failed.
- Actual funding and executable spread/slippage for a concrete one-leg rule remain
  unknown; no such rule was authorized for study.
- The observed rank IC may be genuine but too weak, episodic, or captured by the
  controls to support a personal-small-capital strategy. This study cannot
  distinguish those explanations with adequate confidence.
