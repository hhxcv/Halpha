# Sources and applicability

Surveyed 2026-07-22 UTC before registering outputs.

1. Zhang, W., Li, Y., Xiong, X. and Wang, P. (2021), “Downside risk and
   the cross-section of cryptocurrency returns,” *Journal of Banking & Finance*
   133, 106246. DOI `10.1016/j.jbankfin.2021.106246`.
   - Primary paper reports a positive cross-sectional downside-risk/next-return
     relation using portfolios and Fama–MacBeth regressions. Downside beta is one of
     its robustness measures; volatility explains much of the premium.
   - It also reports little reliable time-series one-week predictability. This study
     therefore tests monthly cross-sectional ranking, not timing a fixed coin.
   - Differences: CoinMarketCap spot universe including inactive coins versus a
     fixed current-survivor Binance perpetual universe; this study uses BTC as the
     observable market proxy and explicitly asks for incremental value beyond total
     volatility and total beta.

2. Dobrynskaya and Dubrovskiy (2023), “Is downside risk priced in
   cryptocurrency market?”, *International Review of Financial Analysis* 90,
   102866. DOI `10.1016/j.irfa.2023.102866`.
   - Publisher summary reports monotonically increasing returns for downside-beta
     portfolios and robustness to crypto- or equity-market proxies.
   - Difference: broad spot pricing evidence, not one-leg Binance USD-M execution.

3. Liu, Y., Tsyvinski, A. and Wu, X. (2022), “Common Risk Factors in
   Cryptocurrency,” *Journal of Finance* 77, 1133–1177. DOI
   `10.1111/jofi.13119`.
   - Establishes crypto market, size, and momentum as central cross-sectional
     benchmarks and shows that many apparent characteristics are subsumed by common
     factors. This motivates market-relative targets, controls, and skepticism.

4. Binance public USD-M daily kline endpoint `/fapi/v1/klines`, plus the
   previously retained official archive/checksum manifests referenced by
   `source_reuse_manifest.json`. No credentials or product data are used.

## Uncovered differences

- The fixed 25-symbol list omits delisted, illiquid, micro-cap, and newly listed
  coins, so it cannot reproduce a broad market downside-risk premium.
- Market capitalization is unavailable in the chosen basic-data boundary; log quote
  volume is only a liquidity/scale proxy, not a size control.
- The predictive economic proxy includes 52 bps round-trip underlying cost and a 4%
  full-plan annual hurdle but excludes funding and intramonth margin paths. Passing
  it would authorize only a separate perpetual strategy-conversion study.

