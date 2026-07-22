# Preregistration

Frozen before downloading or inspecting exact development target outcomes.

## Candidate screen and selection

| Direction | Decision value and evidence | Main falsifier or mismatch | Decision |
|---|---|---|---|
| BTC–S&P 500 conditional-correlation change | Published daily OOS mechanism; one BTC leg; public prices; post-publication window available | Post-ETF/2022 regime may eliminate the effect; timing correction may absorb it | **Selected** |
| CME weekend-gap convergence | Familiar slow weekly mapping | CME began near-24/7 crypto trading on 2026-05-29, structurally ending the historical closure mechanism | Reject before backtest |
| Cross-venue price discovery | Strong microstructure literature | Information is incorporated over sub-second/seconds horizons; needs L2/trades and automation | Reject for semi-automatic scope |
| Direct VIX or macro threshold | Cheap public daily data | Existing Halpha VIX-beta study failed; nearby thresholds would be adjacent post-result search | Family stop |
| Tokenized-equity/metal basis reversion | Potentially independent reference-price mechanism | Current Binance contracts have short histories and unresolved reference/index/funding behavior | Defer |

The selected question has the highest current project decision value because it is
mechanistically independent of existing trend, reversal, carry, liquidity, VIX-beta,
calendar and stablecoin-jump tests while remaining a one-leg daily plan a personal
owner can actually maintain.

## Hypotheses

Primary predictive hypothesis:

- `delta_rho_t`, the change in recursively filtered BTC–S&P 500 DCC correlation
  after observing U.S. trading date `t`, has a negative coefficient for the next
  actionable BTC interval return.

Operational tail hypothesis:

- a fixed low-correlation-change tail is followed by positive BTC returns and a
  fixed high-correlation-change tail by negative BTC returns; a 25%-notional signed
  one-shot proxy survives conservative cost and capital hurdles.

The predictive relationship is closest to the source. The tail mapping is a stricter
Halpha feasibility screen, not a claim made by the source paper.

## Frozen stages and observation timing

- Calibration only: U.S. trading dates from the first complete Binance-aligned row
  through `2022-07-29`; it estimates model parameters, predictive coefficients and
  fixed event thresholds but supplies no qualification evidence.
- Development signal dates: `[2022-08-01, 2023-11-01)`.
- Evaluation signal dates: `[2023-11-01, 2025-02-01)`.
- Confirmation signal dates: `[2025-02-01, 2026-07-18)`.
- Every qualification stage begins after the Physica A publication. Evaluation opens
  only after development `PASS`; confirmation only after evaluation `PASS`.

For S&P 500 trading date `D`, use the FRED close dated `D` and the Binance USD-M
BTCUSDT daily open at `D+1 00:00 UTC`. Act at the 15-minute kline open at
`D+1 00:15 UTC`; close at `00:15 UTC` after the next observed S&P trading date.
No U.S. holiday or weekend value is forward-filled. Holding time is measured exactly.

## Frozen conditional-correlation model

1. Form aligned close-to-close log returns for BTC and S&P 500 on U.S. trading dates.
2. Fit separate zero-mean Gaussian GARCH(1,1) filters on calibration returns, with
   `omega>0`, `alpha>=0`, `beta>=0`, `alpha+beta<0.999`.
3. Standardize residuals and fit Gaussian DCC(1,1), with `a>=0`, `b>=0`,
   `a+b<0.999` and unconditional standardized-residual covariance `Qbar`.
4. Freeze all fitted parameters at the calibration boundary. Recursively filter
   later observations without refitting or using future data.
5. After current standardized residual `z_t` is observed, update
   `Q_(t+1)=(1-a-b)Qbar+a z_t z_t' + b Q_t`; normalize it to correlation
   `rho_t`. The signal is `delta_rho_t=rho_t-rho_(t-1)`.

Freezing rather than daily refitting is intentionally stricter than the source and
tests a low-maintenance implementation. SciPy performs bounded transformed maximum
likelihood; study validation repeats the estimation and checks optimizer convergence,
stationarity and positive-definite correlation matrices.

## Frozen predictive tests

Calibration fits and freezes:

- source-near OLS: `target ~ const + delta_rho`;
- controlled OLS: `target ~ const + delta_rho + rho + btc_return + sp500_return
  + btc_variance_20`;
- event thresholds: calibration 20th and 80th percentiles of `delta_rho`;
- historical-mean target forecast.

For each qualification stage report:

- source-near and controlled OLS coefficient with Newey–West/HAC maximum lag 5;
- controlled coefficient in chronological halves;
- truly out-of-time predictions from frozen calibration coefficients, with OOS
  `R2` against zero and against the frozen calibration historical mean;
- forecast sign accuracy;
- low-tail minus high-tail target spread and each tail mean;
- simple lagged-BTC reversal, scheduled long and scheduled short comparisons.

No DCC window, distribution, control, tail, direction, delay, target interval or
stage boundary may be selected from qualification outcomes.

## Economic feasibility and vectorbt role

- `delta_rho <= q20`: hypothetical 25%-notional BTC long.
- `delta_rho >= q80`: hypothetical 25%-notional BTC short.
- otherwise flat for that interval.
- Every triggered one-shot pays 52 bp of underlying round-trip cost. This deliberately
  stresses fees, spread and slippage; it does not substitute for actual funding.
- Every calendar day in the stage pays a 4% annual full-plan hurdle, including flat
  intervals.
- Same-direction adjacent events still pay a new round trip, matching one-shot plan
  semantics rather than silently assuming a persistent automated position.

The exact event arithmetic is primary. vectorbt 1.1.0 independently computes total
return, annualized volatility, Sharpe and maximum drawdown from the resulting full-plan
capital series. A later strategy-candidate study must use actual funding, executable
spread/slippage and a core-compatible framework-neutral handoff.

## Frozen quality and decision gates

Data quality must pass:

- every available raw Binance ZIP matches its adjacent upstream checksum; the
  pre-2020 archive gap uses exact bounded official public REST responses whose bytes
  and URLs are bound in the manifest; every FRED byte matches the manifest;
- unique, on-grid, positive BTC prices and unique positive S&P closes;
- at least 650 calibration rows and 300 eligible development rows;
- at least 99% of expected stage S&P rows have both exact action prices;
- both GARCH fits and DCC optimization converge; all stationarity and positive-
  definiteness checks pass;
- at least 20 events per tail and events span at least five calendar quarters.

Each qualification stage must independently pass all of the following:

1. source-near and controlled `delta_rho` coefficients are negative with one-sided
   HAC `p<5%`;
2. controlled coefficients are negative in both chronological halves;
3. frozen controlled forecasts have OOS `R2>0` against both zero and the frozen
   historical mean, and sign accuracy is at least 52%;
4. low-minus-high tail spread is positive with a circular 10-observation block-
   bootstrap 95% lower bound above zero;
5. both tail directions have positive gross signed means;
6. full-plan net mean is positive, both chronological halves are positive, and its
   block-bootstrap 95% lower bound is above zero after 52 bp/event and the 4% hurdle;
7. the fixed-tail gross mean exceeds lagged-BTC reversal and both scheduled-direction
   baselines;
8. no positive calendar quarter contributes more than 50% of total positive-quarter
   net P&L.

Bootstrap repetitions: 5,000; deterministic seed `20260722` plus stage offset.

## Stop and interpretation rules

Any stage failure seals all later stages. No reversed sign, neighboring quantile,
rolling window, daily refit, alternate equity index, same-close entry, favorable
subperiod or single tail may rescue this question.

- Wrong controlled coefficient sign or non-positive tail spread:
  `DOES_NOT_SUPPORT`.
- Correct signs but failed uncertainty, stability, quality or economic gates:
  `INSUFFICIENT_EVIDENCE`.
- Three passes: `SUPPORTS_WITHIN_SCOPE` for the predictive question only, followed
  by a separately frozen funding-aware strategy-candidate study.
- Unrecoverable source/computation failure: `CANNOT_DETERMINE`.

No result changes the formal strategy, product code, L4, capital or real-account state.
