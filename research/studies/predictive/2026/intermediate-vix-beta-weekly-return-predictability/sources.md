# Prior work and sources

Survey cutoff: 2026-07-22 UTC.

## Primary research

1. Han, S. (2024), “Nonlinear relationship between cryptocurrency returns and
   price sensitivity to market uncertainty,” *Finance Research Letters* 68,
   106016. DOI: `10.1016/j.frl.2024.106016`; working-paper DOI:
   `10.2139/ssrn.4881385`.
   - Primary abstract: June 2018–February 2023; cryptocurrencies with intermediate
     uncertainty risk earned 5.73% higher risk-adjusted weekly return than low/high
     uncertainty risk after market, size, reversal, and liquidity controls.
   - The paper reports two-pass cross-sectional regressions, alternative quantile
     portfolios, alternative factors, and a lottery-like explanation.
   - Applicability: fixes a nonlinear, middle-versus-extremes direction before
     Halpha outcomes are viewed.
   - Uncovered difference: the article uses a broad CoinMarketCap spot universe
     (hundreds of assets), value-weighted portfolios, and a relative long-short
     claim. This study uses 25 current-survivor perpetuals, equal weights, a
     weekend action gap, and only asks whether a later single-leg study is justified.

2. Ang, A., Hodrick, R., Xing, Y. and Zhang, X. (2006), “The Cross-Section of
   Volatility and Expected Returns,” *Journal of Finance* 61(1), 259–299.
   DOI: `10.1111/j.1540-6261.2006.00836.x`.
   - Establishes factor-beta portfolio sorting and innovations in aggregate
     volatility as an asset-pricing question.
   - Applicability: motivates residualizing changes in the volatility proxy and
     estimating exposure rather than sorting on the VIX level.

3. Daniel, K. and Titman, S. (1997), “Evidence on the Characteristics of
   Cross Sectional Variation in Stock Returns,” *Journal of Finance* 52(1),
   1–33. DOI: `10.1111/j.1540-6261.1997.tb03806.x`.
   - Han identifies characteristic-controlled portfolio sorts as part of the
     empirical design. Here the mature 25-object universe is too small for nested
     5×5 sorts, so controls enter weekly cross-sectional regressions instead.

4. Fama, E. and MacBeth, J. (1973), “Risk, Return, and Equilibrium: Empirical
   Tests,” *Journal of Political Economy* 81(3), 607–636.
   - Provides the repeated cross-sectional regression framework. Weekly slope
     means here use HAC inference; this does not fix omitted variables or selection.

## Official data and library sources

5. Cboe, “Historical Data for Cboe VIX Index,” daily closing values, official
   updated CSV: `https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv`.
   Cboe describes VIX as near-term volatility expected from SPX option prices.

6. FRED series `VIXCLS`, sourced from Cboe, is used only as an independent source
   description/cross-reference. The retained bytes come directly from Cboe.

7. Binance public USD-M `/fapi/v1/klines` and `/fapi/v1/exchangeInfo` supply
   credential-free daily OHLCV and current contract metadata. Request URL, bytes,
   and SHA-256 are retained for every page.

8. statsmodels 0.14.6 supplies OLS and HAC/Newey-West covariance. SciPy supplies
   Spearman rank correlation. VectorBT remains the preferred strategy framework,
   but this question has no position accounting and therefore does not create a
   `Portfolio` merely for branding.

## Method adaptation and limits

- The paywalled article's exact beta-estimation equation was not fully available
  from the primary preview. This study is explicitly an operational adaptation,
  not a numerical replication: weekly change in VIX is residualized by a strictly
  prior expanding AR(1), then asset return is regressed on leave-one-out crypto
  market return and that innovation over 36 weeks.
- Fixed 26- and 52-week beta windows are diagnostics only. They cannot replace the
  36-week primary result.
- VIX Friday close is not available at Saturday 00:00 under every publication
  channel with identical latency. The modeled Monday action leaves more than a
  day; any later strategy handoff must source a timestamped official close and
  revalidate availability.
- Current-survivor mature perpetuals omit delisted and small spot coins central to
  the paper. This reduces manipulation/capacity risk for a small personal account
  but may remove the mechanism itself.
- The study omits funding and live spread because it is predictive. A conservative
  52 bp round-trip plus full-plan hurdle is only an economic screen; any pass must
  open a new strategy question with actual funding and execution evidence.
- No result can prove Alpha or guarantee long-term profitability.

