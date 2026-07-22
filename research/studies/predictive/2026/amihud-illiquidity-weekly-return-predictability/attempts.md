# Attempts and failures

## 2026-07-22 — selection and registration

1. Audited existing Halpha families before selection. Momentum, reversal,
   volatility, MAX/lottery, premium/funding, calendar, order-flow, BTC-relative,
   and external VIX-beta questions already have direct retained evidence; changing
   their windows would be adjacent search.
2. Compared liquidity, Google attention, token dilution, network-value/activity,
   and DXY/external-beta directions. Selected Amihud illiquidity for decision value,
   conflicting primary evidence, basic-data availability, weekly one-leg mapping,
   and low research cost.
3. Froze one primary 28-day specification, two diagnostic windows, controls,
   timing, costs, stage gates, family stop, fixed survivor universe, and data
   limitations before computing this question's ranks or target returns.
4. This question is not a replication of a source paper. Published work uses broad
   dynamic spot universes and mostly monthly portfolios; this is a transparent
   operational adaptation to fixed mature Binance perpetuals and weekly plans.

## 2026-07-22 — implementation, binding, and quality checks

1. `py_compile` passed under `research/.venv`. A separate synthetic test recovered
   a known market beta, verified daily open-to-next-open return alignment with the
   same bar's quote volume, confirmed high-minus-low sort direction, and checked
   all 52/52/72 Saturday decisions plus Monday entry/exit timestamps.
2. Checkpoint digest:
   `50ee173a8e60d483e5dbc54dfd1a7658d9b73f8b7cea80b2bee7a81addc9ee77`.
3. Reuse binding verified 51 existing raw files and 6,713,938 bytes without copying
   or downloading. Binding digest:
   `45aac73154794b268f210e9112c339c4037ac9157b119b9ed643c0b6070b5980`.
4. Data quality passed: all 25 fixed symbols had 1,663 consecutive UTC daily bars,
   positive quote volume, valid OHLC, and no missing/duplicate dates; all were
   present as currently trading perpetuals in the bound public exchange snapshot.
   Data-quality digest:
   `a44a3a4b31a545fdfd95680ffe50ddcbd84f3ab444902178c11ae644cf5c6cd0`.

## 2026-07-22 — development attempt and family stop

1. Opened only 52 development decisions from 2023-03-04 through 2024-02-24.
   Evaluation and confirmation were never analyzed.
2. The primary high-minus-low mean was +0.2452% per target week, but the four-week
   block-bootstrap 95% interval was [-1.3478%, +2.0347%], only 48.08% of weeks were
   positive, and the first-half mean was -0.1883%.
3. Rank IC contradicted the claimed direction: mean -0.05441, HAC t=-1.526, and
   one-sided positive-direction p=0.9365.
4. The controlled Amihud slope was positive and significant (mean 0.03708, HAC
   t=2.096, one-sided p=0.0180), but the score's median absolute rank correlation
   with log quote volume was 0.9579. The opposite raw rank IC and extreme mechanical
   dependence make the controlled coefficient a fragile suppression result rather
   than independent liquidity evidence.
5. The feasibility proxy averaged +0.3465% of full-plan capital per week after the
   frozen cost and hurdle, but its 95% interval [-0.2594%, +0.9559%] crossed zero.
6. Diagnostic 14- and 56-day spreads averaged -0.7481% and -0.0186%; neither may be
   replaced or re-signed. Nine mandatory checks failed. Development-gate digest:
   `a1bf6c40d11aaf0316bcaf2edb6c208c80ec11b043ae81e200fcd79fdc5509a6`.
7. Per the family stop, no inverse rank, different window, subset, liquidity floor,
   entry day, target, or low-volume/volatility diagnostic was opened. Conclusion:
   `INSUFFICIENT_EVIDENCE`; result digest:
   `21f7f1584600da07cde38a285d1b76dd4d91df65de898de804884ef4a06dbe79`.
8. Deterministic recomputation, raw binding, gate binding, and all nine generated
   CSV identities passed. Validation digest:
   `001250bdefa4a60f1caa9c0e8a4cb082505de3dde7034c8b3f556d02e317e00e`.
