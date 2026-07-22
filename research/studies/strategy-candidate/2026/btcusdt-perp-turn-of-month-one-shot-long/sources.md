# Prior work and sources

Survey cutoff: 2026-07-22 UTC.

## Primary research

1. Kumar, S. (2022), “Turn-of-the-month effect in cryptocurrencies,”
   *Managerial Finance* 48(5), 821–829. DOI: `10.1108/MF-02-2022-0084`.
   - Sample: Bitcoin, Ethereum, and Litecoin, August 2015–August 2021.
   - Method: TOM dummy regressions with HAC errors, comparison with non-TOM
     days, GARCH robustness, and an explicit timing strategy.
   - Reported result: TOM returns are positive and higher than non-TOM returns;
     the paper reports annual BTC strategy outperformance of 21.77% and says
     its conclusion survives a 1% breakeven transaction cost.
   - Applicability: fixes the sign and motivates a directly tradable monthly
     schedule. Difference: aggregated spot-market history, not Binance USD-M,
     actual funding, UTC open execution, a 0.5x capital cap, or post-2021 data.

2. Kaiser, L. and Stöckl, S. (2022), “Seasonal and Calendar Effects and the
   Price Efficiency of Cryptocurrencies,” *Finance Research Letters* 46A,
   102354. DOI: `10.1016/j.frl.2021.102354`.
   - The study tests 22 non-economic events across eight established coins.
   - It reports that most effects do not exist; TOM is evident in Bitcoin but
     not the other coins, while within-month is the only common anomaly.
   - Applicability: provides a skeptical independent replication and supports
     BTC as the pre-specified target. Difference: it does not establish that a
     current retail perpetual plan survives costs or funding.

3. Lakonishok, J. and Smidt, S. (1988), “Are Seasonal Anomalies Real? A
   Ninety-Year Perspective,” *Review of Financial Studies* 1(4), 403–425.
   DOI: `10.1093/rfs/1.4.403`.
   - The conventional TOM definition is the last trading day of a month plus
     the first three trading days of the next month.
   - Applicability: fixes `(-1,+3)` before Halpha outcomes are viewed.
     Difference: U.S. equities and trading days, not a 24/7 crypto market.

4. Vasileiou, E. (2023), “Is the Turn of the Month an anomaly on which an
   investment strategy could be based? Evidence from Bitcoin and Ethereum,”
   *International Journal of Banking, Accounting and Finance*.
   - The study confirms that profitable four-day windows cluster around month
     turns but warns that TOM need not beat buy-and-hold on raw return; its
     main value may be risk-adjusted timing.
   - Applicability: motivates matched exposure and capital-hurdle comparisons.
     Its optimization over alternative windows is not imported here.

## Candidate comparison before selection

- **Selected: conventional BTC TOM.** One fixed target, one plan per month,
  daily/funding inputs, post-publication evidence, and direct one-leg handoff.
- **Not selected: daily/weekly skewness.** Intraday realized-skewness evidence
  uses 5-minute data and next-day turnover; Halpha's preregistered 52-week
  `LOW_SKEW52` diagnostic already lost money in 2022–2023. Changing its window
  would be adjacent search, not an independent question.
- **Deferred: nonlinear VIX beta.** A 2024 primary study reports large weekly
  returns for intermediate VIX beta, but it adds an external macro series and
  dynamic cross-sectional selection. It has higher implementation and semantic
  cost than TOM and remains a separate future question.

## Official market-data and framework sources

5. Binance public USD-M REST endpoints: `/fapi/v1/klines`,
   `/fapi/v1/markPriceKlines`, `/fapi/v1/fundingRate`, and
   `/fapi/v1/exchangeInfo`. Access is public and credential-free. Every response
   page is retained outside Git with URL, bytes, and SHA-256 in the manifest.

6. VectorBT `Portfolio.from_orders` accounts independently for entry/exit
   prices, quantities, taker fees, and slippage. An explicit cash-flow formula
   must reconcile within `1e-10`; Binance perpetual funding is added separately.

## Assumptions and uncovered differences

- A crypto “day” is fixed to UTC. The equity convention uses exchange trading
  days, so this is an explicit 24/7 adaptation rather than literal identity.
- Daily open is an execution proxy. Base/stress use 10/20 bps slippage per side
  plus 6 bps taker fee per side; these are conservative assumptions, not fills.
- The plan includes actual settled funding and an adverse funding transform,
  but not L1/L2 queues, partial fills, exchange outage, liquidation, ADL,
  collateral interaction, or human activation delay.
- The fixed current-survivor instrument avoids cross-sectional survivorship but
  cannot establish that historical spot results generalize to a perpetual.
- Earlier Halpha work exposed BTC price paths. Post-2021 timing and a frozen
  exact rule reduce, but do not eliminate, research-program selection bias.
- A profitable backtest would be conditional evidence, never proof of Alpha or
  a guarantee of long-term profitability.

