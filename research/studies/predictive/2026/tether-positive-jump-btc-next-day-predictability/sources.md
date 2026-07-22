# Prior research and source record

Survey and access date: 2026-07-22. Sources are ordered by evidential role. Secondary
indexes were used only to locate primary work.

## Selected result and method

### Grobys and Huynh (2022)

- Klaus Grobys and Toan Luu Duc Huynh, “When Tether says ‘JUMP!’ Bitcoin asks ‘How
  low?’”, *Finance Research Letters* 47, 102644.
- DOI: <https://doi.org/10.1016/j.frl.2021.102644>
- Open accepted/publisher article: <https://osuva.uwasa.fi/server/api/core/bitstreams/679578e2-20cb-4c78-9335-a0fc587aba48/content>
- Source sample: hourly Bitfinex BTC/USD and USDT/USD, 2018-11 through 2021-06;
  992 descriptive observations and 922 regression observations.
- Method: daily jump indicators from 60-minute log returns using realized variance,
  realized bipower variation and 5% BNS inference; jump direction is the sign of the
  aggregated daily return. Regressions include lagged USDT returns, jump interactions,
  BTC returns, time effects and volatility controls.
- Reported claim: the lagged `positive USDT jump * USDT return` coefficient is negative
  for next-day BTC returns, ranging from -3.647 to -8.486 across main specifications.
  Model R-squared is only 0.004 to 0.021. The paper provides no executable strategy,
  costs, funding, delayed entry or post-2021 evidence.
- Proposed mechanism: investors exchange BTC for USDT, temporarily increasing USDT
  demand; BTC selling and triggered stops may propagate into lagged BTC declines. This
  is an interpretation, not identified causality.
- Important source ambiguities: the text reports 102 BNS USDT jumps while another
  descriptive mean appears inconsistent with that count; the paper does not publish
  code or the exact filtered-bar procedure. This study therefore records an operational
  transfer rather than claiming numerical replication.

### Barndorff-Nielsen and Shephard (2006)

- Ole E. Barndorff-Nielsen and Neil Shephard, “Econometrics of Testing for Jumps in
  Financial Economics Using Bipower Variation”, *Journal of Financial Econometrics*
  4(1), 1-30.
- Author-hosted paper: <https://shephard.scholars.harvard.edu/sites/g/files/omnuum7741/files/split.pdf>
- Role: primary asymptotic basis for separating realized quadratic variation from the
  continuous component estimated by bipower variation. The paper derives linear and
  ratio jump statistics and documents finite-sample behavior.
- Applicability gap: its asymptotics assume increasingly fine observations; this study
  has 24 hourly returns per day and a discretely quoted stablecoin.

### CRAN `highfrequency` 1.0.2

- Package manual: <https://stat.ethz.ch/CRAN/web/packages/highfrequency/highfrequency.pdf>
- `BNSjumpTest` source: <https://rdrr.io/cran/highfrequency/src/R/jumpTests.R>
- realized-measure source: <https://rdrr.io/cran/highfrequency/src/R/realizedMeasures.R>
- internal bipower source: <https://rdrr.io/cran/highfrequency/src/R/internalRealizedMeasures.R>
- Role: mature executable reference for the exact default linear statistic using
  bipower variance, tripower quarticity, `theta = pi^2/4 + pi - 3`, a two-sided 5%
  critical boundary, and current finite-sample tripower scaling.
- This project reimplements only the small fixed formula needed by the question and
  independently tests it; it does not add R or the package to product dependencies.

## Competing stablecoin directions considered

### Ante, Fiedler and Strehle (2021)

- “The influence of stablecoin issuances on cryptocurrency markets”, *Finance Research
  Letters* 41, 101867. DOI: <https://doi.org/10.1016/j.frl.2020.101867>
- University record: <https://www.fis.uni-hamburg.de/en/publikationen/detail.html?id=6d48dbbb-ddc5-4d0f-88cf-75fcca17f59c>
- Evidence: an event study of 565 issuance events from seven stablecoins, 2019-04 to
  2020-03, reports downturns before issuance and positive abnormal returns around it.
- Why not selected: effects vary by stablecoin, issuance size is not significant, and
  reverse causality from crypto demand is a simpler explanation.

### Wei (2018)

- “The impact of Tether grants on Bitcoin”, *Economics Letters* 171, 19-22.
  DOI: <https://doi.org/10.1016/j.econlet.2018.07.001>
- Evidence: ADL/VAR tests find Tether grants do not Granger-cause BTC returns, though
  they affect later trading volume and tend to follow BTC declines.
- Relevance: direct counterevidence to interpreting issuance as exogenous return alpha.

### Lyons and Viswanath-Natraj (2023)

- “What keeps stablecoins stable?”, *Journal of International Money and Finance* 131;
  NBER Working Paper 27136: <https://www.nber.org/papers/w27136>
- Evidence: signed trades and order books across exchanges indicate demand-side
  arbitrage, not issuance, is the primary peg-stabilization mechanism; issuance plays a
  limited role.
- Relevance: strengthens the endogeneity objection to an issuance-growth strategy.

### Foley, Lee and Milunovich (2026)

- “How Tether Depegging Affects Cryptocurrency Returns”, *Accounting & Finance*.
  DOI/full text: <https://doi.org/10.1111/acfi.70201>
- Sample: ten major cryptocurrencies, 2017-11 through 2024-11, with constant and
  rolling depeg thresholds.
- Evidence: severe three-standard-deviation negative depegs often coincide with crypto
  declines and partial next-day rebounds.
- Why deferred: severe events are too rare to produce a timely new confirmation set;
  selecting the threshold after observing 2025-2026 would be invalid.

## Official market-data sources

### Bitfinex

- Public endpoint overview: <https://docs.bitfinex.com/docs/rest-public>
- Candles endpoint: <https://docs.bitfinex.com/reference/rest-public-candles>
- Pair configuration endpoint used to confirm `USTUSD`:
  <https://api-pub.bitfinex.com/v2/conf/pub:list:pair:exchange>
- Data used: `trade:1h:tUSTUSD`, ascending UTC millisecond timestamps, maximum 10,000
  rows per request. Response fields are timestamp, open, close, high, low and volume.
- Boundary: the endpoint supplies public exchange candles without credentials or an
  upstream checksum. Exact response bytes, URL, retrieval time, byte count and SHA-256
  are therefore retained outside Git and bound by the stage manifest.

### Binance public data

- Official archive repository and schema:
  <https://github.com/binance/binance-public-data>
- Data used: USD-M `BTCUSDT` 15-minute klines, which Binance documents as originating
  from `/fapi/v1/klines`.
- Boundary: each downloaded zip is verified against Binance’s adjacent `.CHECKSUM`.
  The archive can be revised later, so exact downloaded bytes and hashes are retained
  and recorded, not silently refreshed.

## Deliberately absent data

No product database, credentials, account state, L2 book, trades, news, sentiment,
open interest, liquidation feed, on-chain supply, issuer attestations or private vendor
data is used. Those omissions limit causal interpretation, but they do not prevent a
clean falsification of the published price-only prediction.

