# Source register

As-of 2026-07-22. Stable product baseline:
`0bdfeffa616260cebd2d2188ddc8deb9e85c77f4`. Formal comparator:
`ONE_SHOT_DONCHIAN_ATR_BREAKOUT 1.0.1 / BTCUSDT-PERP`.

## Primary research

1. Yakov Amihud, “Illiquidity and stock returns: cross-section and time-series
   effects,” *Journal of Financial Markets* 5(1), 2002,
   DOI `10.1016/S1386-4181(01)00024-6`.
   - Defines the daily absolute-return-to-dollar-volume proxy and interprets it as
     a coarse price-impact measure.
   - Equity evidence is only the measurement baseline, not proof of crypto
     transfer.
2. Wei Zhang and Yi Li, “Liquidity risk and expected cryptocurrency returns,”
   *International Journal of Finance & Economics* 28(1), 2023,
   DOI `10.1002/ijfe.2431` (first online 2021).
   - Uses Amihud liquidity, portfolio sorts, bivariate sorts, and Fama-MacBeth
     regressions; reports a negative relation between liquidity and crypto returns
     robust to alternative measures and size screens.
   - Also reports no significant intertemporal relation for three leading coins;
     this study therefore tests cross-sectional prediction only.
3. Wang Chun Wei, “Liquidity and market efficiency in cryptocurrencies,”
   *Economics Letters* 168, 2018, DOI `10.1016/j.econlet.2018.04.003`.
   - Examines 456 coins using Amihud illiquidity and reports weaker efficiency in
     illiquid coins but no signs of an illiquidity premium. This is the main
     skeptical baseline.
4. Bingbing Dong, Lei Jiang, Jinyu Liu, and Yifeng Zhu, “Liquidity in the
   cryptocurrency market and commonalities across anomalies,” *International
   Review of Financial Analysis* 81, 2022,
   DOI `10.1016/j.irfa.2022.102097`.
   - Uses January 2014–April 2019 CoinMarketCap data and monthly Amihud ratios;
     reports that low liquidity magnifies many anomaly spreads.
   - This is mechanism context, not evidence that raw illiquidity alone is a
     profitable one-leg rule.
5. Asgar Ali, Sanshao Peng, and Syed Shams, “Unravelling cross-sectional patterns
   in cryptocurrencies: a four-factor asset pricing model,” *China Accounting &
   Finance Review* 27(4), 2025, SSRN `5527518`, DOI
   `10.2139/ssrn.5527518`.
   - Uses 1,160 coins from 2014–2022 and reports a significant illiquidity premium
     not explained by size or other studied cross-sectional patterns.
   - The paper is newer than much of this study's development interval, but its
     source sample ends before the 2023 development decisions.

## Official data

- Binance USD-M public REST `exchangeInfo` and daily `klines` responses. The exact
  URLs, access time, byte sizes, and SHA-256 identities are inherited from the
  verified parent manifest bound by `source_reuse_manifest.json`.
- Parent manifest:
  `research/studies/predictive/2026/intermediate-vix-beta-weekly-return-predictability/source_manifest.json`;
  expected byte SHA-256
  `07d0c80a4ea858e767960c53bc9ef5345cecc1a07fb482d9d2d87b862fb50693`.

## Applicability and differences

- Published studies mainly use broad, dynamic spot universes and monthly sorts.
  Halpha uses a fixed survivor set of 25 current, mature Binance perpetuals and a
  weekly target. This reduces microcap manipulation and point-in-time universe
  cost, but creates survivor bias and a narrower liquidity cross-section.
- Quote volume is venue-reported USDT activity, not consolidated dollar volume;
  wash trading, cross-venue fragmentation, contract multipliers, and market-cap
  size are not fully observed.
- Amihud is a coarse daily proxy, not spread, depth, order-book impact, or realized
  execution cost. The study must not call it actual liquidity.
- The research program has already viewed broad price paths. Sequential gates stop
  within-question tuning but cannot restore a pristine researcher-blind history.

## Candidate screen before selection

| Direction | Decision value | Data / falsifiability | Decision |
|---|---|---|---|
| Cross-sectional Amihud illiquidity | Distinct risk/friction mechanism; weekly one-leg mapping | Existing verified daily OHLCV; direct conflicting literature; cheap to test | **Selected** |
| Abnormal Google search attention | Published return relation, potentially fast | Trends can resample/renormalize history; keyword and geography degrees of freedom; not base market data | Reject now |
| Token dilution / unlock | Potential structural seller pressure | A 2026 study says effect is absent in mature coins and concentrated in year one; point-in-time vesting data costly | Reject for current universe |
| Network-value / activity ratios | Different fundamental mechanism | Few independent BTC cycles; metric revision and release-time semantics; slow validation | Defer |
| DXY or another external risk beta | Simple public macro data | Weak directional prediction and adjacent to the just-failed VIX-beta family | Reject adjacent/low value |

Selection is based on project decision value, unresolved difference, falsifiability,
data identity, realistic plan cadence, and research cost—not novelty or the promise
of an attractive backtest.
