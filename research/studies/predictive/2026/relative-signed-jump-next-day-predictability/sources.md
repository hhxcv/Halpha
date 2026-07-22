# Sources and applicability

Research lock date: 2026-07-22. Baseline commit:
`0bdfeffa616260cebd2d2188ddc8deb9e85c77f4`.

## Primary research

1. Zehua Zhang and Ran Zhao, **“Good volatility, bad volatility, and the cross
   section of cryptocurrency returns,”** *International Review of Financial
   Analysis* 89 (2023), 102712, DOI `10.1016/j.irfa.2023.102712`.
   - Accepted-paper record:
     https://www.sciencedirect.com/science/article/pii/S1057521923002284
   - Open conference manuscript:
     https://cirforum.org/cirf2022/forum_files/papers/CIRF-306.pdf
   - Observed on 2026-07-22: 51 active cryptocurrencies, January 2017 through
     June 2021, 5-minute high-frequency data, daily quintile sorts. The paper defines
     `RSJ = (RV+ - RV-) / RV` and reports monotonically lower next-day returns as
     RSJ rises; equal-weight high-minus-low was `-84.4 bp` with Newey–West
     t-statistic `-7.103`, and the negative relation survived reversal, realized
     volatility, salience, beta, size and momentum controls.
   - Applicability: direct basis for a current out-of-source-period predictive test.
     It does not establish a liquid-perpetual long leg after a 15-minute delay,
     funding, spread/slippage, retail costs, survivor selection or manual activation.

2. Tim Bollerslev, Sophia Zhengzi Li and Bingzhi Zhao, **“Good Volatility, Bad
   Volatility, and the Cross Section of Stock Returns,”** *Journal of Financial
   and Quantitative Analysis* 55(3) (2020), 751–781,
   DOI `10.1017/S0022109019000097`.
   - Author manuscript:
     https://public.econ.duke.edu/~boller/Papers/jfqa_19.pdf
   - Applicability: establishes the positive/negative realized semivariance framework
     and the importance of asymmetric intraday variation. Equity results are only
     methodological context, not cryptocurrency evidence.

3. Ole E. Barndorff-Nielsen and Neil Shephard, **“Power and Bipower Variation
   with Stochastic Volatility and Jumps,”** *Journal of Financial Econometrics*
   2(1) (2004), 1–37, DOI `10.1093/jjfinec/nbh001`.
   - Applicability: foundational realized-variation/jump framework. Halpha uses the
     source paper's normalized signed semivariance difference rather than claiming
     exact jump identification from finite 15-minute sampling.

## Official data

4. Binance official public-data repository:
   https://github.com/binance/binance-public-data
   - Documents monthly/daily public archives, supported `15m` klines and companion
     SHA-256 checksum files. Archives are sourced from the USD-M `/fapi/v1/klines`
     endpoint. No credentials are required.

5. Binance USD-M Kline/Candlestick API documentation:
   https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Kline-Candlestick-Data

6. Binance USD-M Exchange Information:
   https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Exchange-Information

## Transfer differences and unknowns

- Sampling is 15 minutes, not 5-minute vendor tick data. Coarser sampling may attenuate
  or alter RSJ. The 15m/30m/1h agreement gate makes this limitation falsifiable.
- Halpha uses Binance perpetual prices rather than value-weighted cross-venue spot
  prices. Funding and basis may change the economics; funding is not available from
  kline data and is deferred to a strategy conversion only after three predictive gates.
- The universe is a fixed set of current survivors. This reduces operational churn but
  creates survivorship bias and excludes the paper's small/new coins.
- OHLCV cannot identify investor attention, causal buyers, spread, depth or fills.
  Volume surprise may be controlled later only as a basic-data diagnostic; Google
  search/news mechanisms are outside the user's chosen data boundary.
- Static archive files can be corrected upstream. The stage manifest records URL,
  upstream checksum, local byte size and SHA-256 so results bind to exact bytes.

