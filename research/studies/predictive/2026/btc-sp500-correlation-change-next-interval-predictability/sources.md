# Source register

As-of 2026-07-22; stable product baseline
`0bdfeffa616260cebd2d2188ddc8deb9e85c77f4`.

## Primary mechanism and method

1. Yae and Tian, *Out-of-sample forecasting of cryptocurrency returns: A
   comprehensive comparison of predictors and algorithms*, Physica A 598 (2022),
   127379, <https://doi.org/10.1016/j.physa.2022.127379>.
   - The paper compares common public predictors and reports that changes in
     stochastic correlation with stock markets are the only meaningful predictor
     in its daily out-of-sample comparison; robust linear models outperform the
     tested machine-learning alternatives.
   - Applied here as a mechanism and sign prior, not as numerical replication.
2. Yae and Tian, *Sequential Learning, Asset Allocation, and Bitcoin Returns*,
   September 2021 working-paper version,
   <https://acfr.aut.ac.nz/__data/assets/pdf_file/0009/576990/George-Tian-NZ_2021.pdf>.
   - Full method source: DCC(1,1)-GARCH(1,1), change rather than level of
     conditional correlation, expanding real-time tests, and the asynchronous
     portfolio-rebalancing explanation.
   - Source data end in 2020 and the paper explicitly ignores the 3–4 hour gap
     between the U.S. cash close and the UTC BTC close. Halpha starts development
     after the July 2022 publication and adds a 15-minute action delay after the
     later UTC anchor.
3. Yae and Tian, *Volatile safe-haven asset: Evidence from Bitcoin*, Journal of
   Financial Stability 73 (2024), 101285,
   <https://doi.org/10.1016/j.jfs.2024.101285>.
   - Later peer-reviewed evidence for the same time-varying diversification-demand
     channel. It is corroboration, not an independent Halpha holdout.
4. Engle, *Dynamic Conditional Correlation: A Simple Class of Multivariate
   Generalized Autoregressive Conditional Heteroskedasticity Models*, Journal of
   Business & Economic Statistics 20(3) (2002),
   <https://doi.org/10.1198/073500102288618487>.
   - Defines the DCC recursion and parameter restrictions used here.
5. Bollerslev, *Generalized Autoregressive Conditional Heteroskedasticity*, Journal
   of Econometrics 31(3) (1986),
   <https://doi.org/10.1016/0304-4076(86)90063-1>.
   - Defines the univariate GARCH(1,1) variance filters used before DCC.

## Public data and implementation

6. Federal Reserve Bank of St. Louis FRED, S&P 500 series `SP500`,
   <https://fred.stlouisfed.org/series/SP500> and exact bounded `fredgraph.csv`
   requests retained in the manifest. FRED is the public delivery source; S&P Dow
   Jones Indices is the series source and its stated use restrictions still apply.
7. Binance public data repository,
   <https://github.com/binance/binance-public-data>, and checksummed USD-M
   `BTCUSDT` kline archives at <https://data.binance.vision/>. The study retains
   every available adjacent upstream `.CHECKSUM` and verifies raw ZIP bytes before
   use. The archive begins in 2020; the exact 2019-09 through 2019-12 warm-up gap is
   fetched from Binance's official public USD-M `/fapi/v1/klines` endpoint and bound
   by request URL plus response-byte SHA-256. This mechanical source fallback was
   added after the archive returned 404, before any outcome calculation or inspection.
8. SciPy 1.18.0 optimizer documentation,
   <https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.minimize.html>;
   statsmodels 0.14.6 OLS/HAC documentation,
   <https://www.statsmodels.org/stable/generated/statsmodels.regression.linear_model.OLS.html>;
   vectorbt 1.1.0 installed package and source. Versions and the study code hash are
   frozen in the checkpoint.

## Candidate screening evidence

- CME Group officially moved cryptocurrency futures and options to near-continuous
  24/7 trading on 2026-05-29:
  <https://www.cmegroup.com/media-room/press-releases/2026/6/01/cme_group_announceslaunchof247cryptocurrencyfuturesandoptionstra.html>.
  This creates a structural break in the popular historical “CME weekend gap” and
  removes it from long-horizon candidate status.
- Aleti and Mizrach, *Bitcoin spot and futures market microstructure*, Journal of
  Futures Markets 41(2) (2021), <https://doi.org/10.1002/fut.22163>, and current
  price-discovery work locate leading information at microstructure horizons. Such
  signals require tick/order-book data and automated low-latency execution, outside
  the present semi-automatic/basic-data boundary.
- Halpha already retained a failed VIX-beta weekly test. Replacing VIX with a nearby
  macro threshold would be adjacent search, not an independent new mechanism.

None of these sources proves current executable Alpha. They establish the research
question, its sign, its timing risk, and strong counterfactuals.
