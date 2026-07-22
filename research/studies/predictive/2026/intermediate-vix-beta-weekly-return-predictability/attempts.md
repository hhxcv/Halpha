# Attempts and failures

## 2026-07-22 — selection and registration

1. Selected Han (2024) only after the independently tested BTC TOM strategy failed.
   The mechanism uses an external risk factor and nonlinear cross-sectional pricing,
   not a nearby calendar parameter.
2. Read the primary abstract/SSRN record, publisher metadata, Cboe/FRED source
   descriptions, and asset-pricing methods. A secondary technical summary was used
   only to locate the paper's weekly sorts; claims retained here are limited to what
   the primary abstract and official sources establish.
3. The exact paywalled equation was unavailable, so this is labeled an operational
   adaptation. The AR(1) innovation, leave-one-out market control, 36-week window,
   Saturday decision, Monday entry gap, quantiles, controls, costs, stages, gates,
   diagnostics, and family stop were frozen before results.

## 2026-07-22 — implementation and data checks

1. `py_compile` passed under `research/.venv` (Python 3.12.10). A separate synthetic
   check recovered a known market beta of 0.7 and VIX beta of -0.03 to numerical
   precision, confirmed 52/52/72 stage weeks, Saturday-to-Monday timing, and
   disjoint low/middle/high assignments.
2. Checkpoint digest:
   `b07b8e6290531c4a2754d683028319fffcc34689bc7192825483cd616eab7c85`.
3. Fetch retained 50 Binance kline response pages for all 25 fixed symbols, the
   official Cboe VIX CSV, and Binance exchange metadata under the external cache
   root. Source-manifest digest:
   `d8cab91fb7ccdc39204aa2b783d13376b92ba0137fb3cb8e6a164cb432ed3514`.
4. Data quality passed: each symbol had 1,663 consecutive UTC daily bars from
   2022-01-01 through 2026-07-21 with no missing or duplicate dates and valid OHLC;
   all 25 were currently trading perpetuals. VIX had 1,929 positive, unique daily
   closes from 2019-01-02 through 2026-07-21. Data-quality digest:
   `0e30d2ba4a22b18843f9d480c7d682c518c4922a2cb7d7339f25d59eb1b2e691`.

## 2026-07-22 — development attempt and family stop

1. Only the pre-registered 2023-03-04 through 2024-02-24 development decisions
   were opened. The evaluation and confirmation stages were never analyzed.
2. The primary 36-week middle-minus-extremes mean was +0.5968% per target week,
   but its four-week block-bootstrap 95% interval was [-0.8612%, +1.9742%] and
   only 48.08% of weekly spreads were positive.
3. Rank IC was positive (mean 0.08438; one-sided HAC p=0.000128), but the
   pre-registered controlled middle-score slope was not significant (one-sided
   HAC p=0.4238) and the quadratic concavity test was not significant (p=0.2701).
   This is important counterevidence: the attractive univariate rank statistic did
   not survive the specified multivariate interpretation test.
4. The highest-volume middle-member feasibility proxy averaged +0.2259% of the
   full plan per week after a 52 bp underlying round trip, 25% notional fraction,
   and 4% annual hurdle. Its 95% interval was [-0.4225%, +0.9485%], its first half
   averaged -0.3220%, and only nine distinct symbols were selected.
5. The 26- and 52-week diagnostic spreads were positive on average, but neither
   may replace the failed primary specification. Seven mandatory checks failed.
   Development gate digest:
   `62f5c41f47757fbedf64d7ae36c26fde7b3a48ab1996410188f39310533c1589`.
6. Per the frozen family stop, no reversal, different quantile, different entry,
   favorable subgroup, alternate target, or later-stage peek was attempted. The
   result is `INSUFFICIENT_EVIDENCE`, not a strategy qualification. Result digest:
   `3838952db2e0e15e2cc371025ec62e8dafc84cd7f126acd9994ae373f924809b`.
7. Deterministic recomputation, gate binding, source identity, and all nine CSV
   identities passed. Validation digest:
   `62616654fc97a84d3206a5da644cca632ac55485cc1b30232069866d9c62b1fd`.
