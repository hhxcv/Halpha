# Attempt log

1. Rechecked the retained basic-data frontier before selection. Trend/momentum,
   reversal/extremes, volatility/downside, liquidity/order-flow proxies, intraday
   signed variation, premium/funding, calendar, BTC-relative effects, VIX-beta and
   stablecoin price spillover already have direct Halpha evidence; nearby parameter
   searches were excluded.
2. Surveyed CME weekend gaps. CME's official 2026-05-29 near-24/7 launch creates a
   forward structural break, so historical gap-fill frequency would not answer the
   long-term question.
3. Surveyed cross-exchange price discovery. The strongest evidence is at tick,
   sub-second or seconds horizons and requires data/execution explicitly outside the
   current basic-data semi-automatic scope.
4. Located Yae and Tian's peer-reviewed 2022 OOS comparison, full 2021 working-paper
   method and 2024 follow-up. The mechanism, one-leg mapping, public data and fully
   post-publication dates dominate the remaining candidate set.
5. Verified FRED's bounded `SP500` CSV and Binance's adjacent archive checksums are
   publicly retrievable without credentials. No target outcomes were downloaded or
   inspected before freezing this preregistration.
6. The first fetch found that Binance USD-M monthly kline archives begin in 2020;
   requests for 2019-09 through 2019-12 returned official 404. The original checkpoint
   is preserved as `checkpoint_pre_archive_coverage_fix.json`. Before calculating or
   inspecting any signal/target outcome, the fetcher was changed only to fill that
   exact warm-up interval from Binance's public `/fapi/v1/klines` endpoint. Question,
   stages, signal, model, costs, gates and stop rules were unchanged.
7. The repaired fetch retained 104 bounded source objects totaling 8,259,995 bytes:
   official FRED `SP500`, checksummed Binance monthly `1d/15m` ZIPs, and nine bounded
   pre-2020 REST pages. Source identity is
   `9d3e1eb25c9286c56d26b02f0ad59dd69fee6ed51adf60254852a7a084788a8d`.
8. Data quality passed with 709 calibration rows and 316/316 eligible development
   rows. The low/high frozen tails contained 50/44 events across six quarters. Both
   GARCH fits and DCC converged; persistence was 0.8652, 0.9851 and 0.9854, and the
   minimum correlation-matrix eigenvalue was 0.4555.
9. Development did not reproduce the published negative relation. Source-near and
   controlled coefficients were `+0.032875` and `+0.089889`; chronological controlled
   halves were `+0.560533` and `-0.534787`. Frozen controlled forecasts had OOS R2
   `-1.0672%` versus zero and `-1.2553%` versus the calibration historical mean.
10. The fixed low-minus-high tail spread was only `+0.041585%`, with 10-observation
    circular-block 95% interval `[-1.809520%, +1.578465%]`. The high-correlation-change
    short tail itself had gross mean `-0.012963%`; the two event halves were
    `-1.189747%` and `+1.235641%`.
11. After the 52 bp underlying round trip, 25% notional and 4% annual full-plan
    hurdle, net mean was `-0.036519%` per calendar day and endpoint compound return
    `-15.6913%`; bootstrap interval was `[-0.085071%, +0.004244%]` per day. Twelve
    gates failed. Development therefore stopped as `DOES_NOT_SUPPORT`; evaluation,
    confirmation, parameter changes and strategy conversion remain sealed.
12. Independent validation re-read every bound raw byte, re-estimated both GARCH
    filters and DCC, recomputed regressions/bootstraps/gate, matched both retained
    CSV identities and confirmed later-stage sealing: `PASS`.
