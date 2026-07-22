# Sources and applicability

Research lock date: 2026-07-22. Baseline commit:
`0bdfeffa616260cebd2d2188ddc8deb9e85c77f4`.

## Primary research

1. Jinchuan Li and Yifeng Zhu, **“Taming crypto anomalies: A Lasso-type
   factor model,”** *Research in International Business and Finance* 83 (2026),
   103298, DOI `10.1016/j.ribaf.2026.103298`.
   - Publisher: https://www.sciencedirect.com/science/article/pii/S0275531926000255
   - Working paper record: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4437594
   - Observed on 2026-07-22: the paper re-examines 49 anomalies through 2023 and
     selects market, two-week momentum and residual momentum for its DS3 model;
     the publisher reports an out-of-sample advantage over compared factor models.
   - Applicability: direct support for testing residual momentum in crypto and for
     using a two-week horizon. It is not evidence that a single liquid perpetual leg
     is profitable after funding, retail spread/slippage or a capital hurdle.
   - Difference not covered: broad CoinMarketCap spot data, value-weighted quintiles,
     market-cap information and long-short factor construction differ from Halpha’s
     fixed 25-perpetual survivor universe and one-leg plan.

2. David Blitz, Joop Huij and Martin Martens, **“Residual Momentum,”**
   *Journal of Empirical Finance* 18(3) (2011), 506–521,
   DOI `10.1016/j.jempfin.2011.01.003`.
   - Publisher-version repository PDF:
     https://pure.eur.nl/ws/files/46882404/ResidualMomentum-2011.pdf
   - Observed on 2026-07-22: the method ranks on common-factor residual returns,
     standardizes by residual volatility, excludes the fitted alpha from the score,
     and finds lower time-varying factor exposure than total-return momentum.
   - Applicability: establishes the residualization mechanism and the ordinary
     momentum comparator. Equity factors and monthly 36/12-month windows are not
     transplanted literally to a young 24/7 crypto market.

3. Yukun Liu, Aleh Tsyvinski and Xi Wu, **“Common Risk Factors in
   Cryptocurrency,”** *Journal of Finance* 77(2) (2022), 1133–1177,
   DOI `10.1111/jofi.13119`.
   - NBER/SSRN record: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3394671
   - Observed on 2026-07-22: market, size and momentum capture important
     cross-sectional cryptocurrency return variation in the paper’s historical
     universe. This motivates hard ordinary-momentum and market-exposure baselines;
     it does not prove a current one-leg alpha.

## Official data and implementation context

4. Binance USD-M Futures API, Kline/Candlestick Data:
   https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Kline-Candlestick-Data
   - Public, credential-free market data. The study reuses previously downloaded
     daily pages and checks their byte size and SHA-256 before every analysis.

5. Binance USD-M Futures exchange information:
   https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Exchange-Information
   - Used only to verify that the frozen symbols are currently present, trading and
     perpetual. Current status cannot remove historical survivorship bias.

## Evidence boundary

- Li–Zhu’s broad sample ends in 2023. The Halpha development window overlaps part
  of 2023–2024, while later stages are chronologically newer, but Halpha has already
  inspected the broad market path in other studies. The later stages are therefore
  sequential for this exact frozen rule, not pristine market-history evidence.
- Daily open-to-open bars cannot observe spread, depth, fills, liquidation, who
  traded, or coin-specific news. The 52 bp round-trip proxy is a conservative screen,
  not an execution replay; funding is intentionally deferred to a separate strategy
  question if and only if all predictive stages pass.
- A positive predictive result would justify only a separate strategy-candidate
  conversion. It would not prove Alpha or long-term profitability.

