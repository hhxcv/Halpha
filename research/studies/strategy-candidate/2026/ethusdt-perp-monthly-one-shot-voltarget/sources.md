# Prior work and sources

Survey cutoff: 2026-07-22 UTC.

## Primary research

1. Moreira, A. and Muir, T. (2017), “Volatility-Managed Portfolios,” *Journal
   of Finance* 72, 1611–1644. DOI: `10.1111/jofi.12513`.
   - Publisher abstract reports improved Sharpe ratios and utility from reducing
     exposure when volatility is high across several traditional factors.
   - Applicability: motivates a fixed inverse-volatility sizing rule.
   - Difference not covered: not cryptocurrency, not ETH perpetual funding, not a
     25%-capped monthly one-shot plan, and the original construction scales by
     inverse variance rather than this operationally simpler inverse volatility.

2. Cederburg, S., O'Doherty, M., Wang, F. and Yan, X. (2020), “On the
   performance of volatility-managed portfolios,” *Journal of Financial
   Economics* 138, 95–117. DOI: `10.1016/j.jfineco.2020.04.015`.
   - This is the required skeptical benchmark: realistic out-of-sample versions do
     not inherit every favorable in-sample result of volatility management.
   - Applicability: motivates sequential evidence, fixed parameters, simple
     benchmarks, and refusal to infer Alpha from improved Sharpe alone.
   - Difference not covered: traditional factors, not crypto perpetual execution.

3. Liu et al. (2022), “Liquidity Shocks, Price Volatilities, and Risk-managed
   Strategy: Evidence from Bitcoin and Beyond,” *Journal of Multinational
   Financial Management* 63, 100729. DOI: `10.1016/j.mulfin.2022.100729`.
   - The journal article studies Bitcoin and also reports ETH robustness, using
     liquidity shocks to forecast persistent volatility and manage crash risk.
   - Applicability: supports the narrower proposition that crypto exposure can be
     risk-managed using information available before the holding period.
   - Difference not covered: its liquidity signal and portfolio construction are
     deliberately not imported here; this study uses only daily returns and a much
     simpler fixed monthly rule.

## Official market-data and framework sources

4. Binance public USD-M REST endpoints: `/fapi/v1/klines`,
   `/fapi/v1/markPriceKlines`, `/fapi/v1/fundingRate`, and
   `/fapi/v1/exchangeInfo`. Access is public market-data access with no credentials.
   Each response page, request URL, byte count, and SHA-256 is recorded by the study.

5. VectorBT `Portfolio.from_orders` is used for order-price, quantity, fee, and
   slippage accounting. A separate manual cash-flow formula must agree within
   `1e-10`; actual or stressed funding is then added explicitly because the framework
   portfolio does not settle Binance perpetual funding by itself.

## Assumptions and exclusions

- Research assumes UTC daily bars and a month-open execution proxy. It does not use
  L2 order books, news, sentiment, OI, liquidation, on-chain, or product data.
- Daily-bar slippage scenarios are assumptions, not measured fills. Stress uses
  20 bps per side plus 6 bps taker fee per side and adverse funding multipliers.
- ETH historical paths through 2026-06 were already exposed in a prior Halpha SMA
  study. Exact-rule stage outputs were uncomputed at registration, but the market
  history is not investigator-blind.

