# Sources and applicability record

Accessed on 2026-07-22 unless stated otherwise. Primary publications, official
data, and official API documentation take precedence. External results motivate
the question; only the preregistered Halpha evidence determines its conclusion.

## Selected prior evidence

### Mercik, Zaremba, and Demir (2026), *Crypto factor zoo (.Zip)*

- Publication: *International Review of Financial Analysis* 113, 105137.
- DOI: <https://doi.org/10.1016/j.irfa.2026.105137>
- Publisher record: <https://www.sciencedirect.com/science/article/pii/S1057521926000645>
- Public result data: Zaremba (2026), RepOD V1,
  <https://doi.org/10.18150/IIVQQE>.
- Direct Dataverse tabular export used for the reference calculation:
  <https://repod.icm.edu.pl/api/access/datafile/105344>.
- Direct original-format download retained for provenance:
  <https://repod.icm.edu.pl/api/access/datafile/105344?format=original>.
- License: CC0 1.0, as declared by RepOD.

The paper studies 36 characteristics on as many as 565 cryptocurrencies from
2018-01-01 through 2024-07-25 using weekly quartile sorts and both equal- and
value-weighted portfolios. Bid-ask spread is one of the rare factors reported as
positive in both halves. The authors' value-weighted zero-cost annualized mean is
reported near 108%; the bound public weekly series is independently summarized in
`reference_benchmark.json`.

Applicability: high for selecting a low-frequency cross-sectional question and
for defining a simple published comparator. Direct transfer is low: the paper's
broad spot universe, market-cap weighting, quartile portfolios, and likely
microcap exposure differ from 25 mature Binance USD-M perpetuals and a one-leg
semi-automatic plan. The source factor return is not used in any Halpha gate.

### Abdi and Ranaldo (2017), *A Simple Estimation of Bid-Ask Spreads from Daily Close, High, and Low Prices*

- *Review of Financial Studies* 30(12), 4437-4480.
- DOI and official full text: <https://doi.org/10.1093/rfs/hhx084>
- Author-hosted accepted-paper PDF:
  <https://alexandria.unisg.ch/server/api/core/bitstreams/dfb85399-5bcf-465c-8b63-9bfc97ad2ee0/content>

The primary estimator is the recommended two-day-corrected CHL measure:

`eta_t = (log(high_t) + log(low_t)) / 2`

`s_t = sqrt(max(4 * (log(close_t) - eta_t) * (log(close_t) - eta_(t+1)), 0))`

and the window estimate is the arithmetic mean of applicable `s_t`. The paper
finds this correction more closely associated with high-frequency effective
spreads than its monthly-corrected form, although it can be more biased because
negative two-day moments are set to zero.

Applicability: the estimator is transparent, cheap, and available from Halpha's
base OHLC data. It was developed mainly for equities with daily closes, not
24/7 perpetual futures. Consequently this study calls the variable an
OHLC-estimated spread, not an observed executable spread. The monthly-corrected
form is retained only as a non-selectable robustness diagnostic.

### Brauneis et al. (2021), *How to Measure the Liquidity of Cryptocurrency Markets?*

- *Journal of Banking & Finance* 124, 106041.
- DOI: <https://doi.org/10.1016/j.jbankfin.2020.106041>

The paper benchmarks low-frequency crypto-liquidity proxies against order-book
and transaction measures and reports that high/low/close estimators perform well
for capturing time-series liquidity variation.

Applicability: it supports using an OHLC estimator as a low-cost research proxy.
It covers BTC/ETH spot markets at selected exchanges, not a cross-section of
Binance USD-M perpetuals, and does not establish next-week return predictability.

## Official market data

- Binance USD-M Kline/Candlestick Data:
  <https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Kline-Candlestick-Data>
- Binance USD-M Exchange Information:
  <https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Exchange-Information>
- Binance public-data repository: <https://github.com/binance/binance-public-data>

The study reuses a previously bound cache of public daily USD-M REST responses,
with every raw item fixed by byte count and SHA-256. It does not query account or
product storage. Exchange information is present/current-contract quality context;
it does not dynamically change the fixed survivor universe.

## Candidate survey and selection record

### Dynamic crypto network and cross-crypto lead-lag

- Guo, Härdle, and Tao (2024), *A Time-Varying Network for Cryptocurrencies*,
  *Journal of Business & Economic Statistics*.
  <https://doi.org/10.1080/07350015.2022.2146695>
- Guo et al. (2024), *Cross-Cryptocurrency Return Predictability*, *Journal of
  Economic Dynamics and Control*.

These methods are mature, but their economically useful versions use minute data,
large cross-sections, frequent rebalancing, and network/LASSO estimation. Halpha
has already tested the closer operational question—BTC-shock lead-lag into mature
perpetuals—and found only roughly 1-3 bp before realistic delays and costs. A
network relabeling would duplicate a failed family and be poorly matched to a
semi-automatic plan, so it was not selected.

### Turnover volatility and disagreement

- Garfinkel et al. (2025), *Disagreement and returns: The case of
  cryptocurrencies*, *Financial Management*.
  <https://doi.org/10.1111/fima.12491>

Turnover-based disagreement is interesting, but it requires circulating-supply or
market-cap histories not present in the fixed basic-data cache. More importantly,
the reported lower-return mechanism weakens after margin trading becomes
available, which is a central mismatch for current perpetuals. It was retained as
a future data-dependent question, not chosen now.

### OHLC-estimated spread

Selected because it has the highest immediate decision value: published broad
crypto evidence, a precise and falsifiable low-frequency estimator, public base
data, low compute/storage cost, and direct compatibility with weekly
semi-automatic planning. The important unresolved difference—whether a broad
spot portfolio premium survives as incremental information in mature perpetuals
and a one-leg proxy—is exactly what this study tests.

## Evidence and data limitations

- Current-survivor selection; no point-in-time delisted/new-listing universe.
- No observed bid/ask, depth, queue, market impact, or partial fills.
- No actual funding series in this predictive stage.
- No market capitalization, circulating supply, or broad-spot replication panel.
- The external CC0 return table has one malformed early value-weighted observation
  and one trailing numeric value without a date in its Dataverse tabular export;
  the independent check is therefore approximate and explicitly records numeric,
  dated, and undated counts.
- Prior factor evidence may reflect illiquidity risk, microcap exposure,
  diversification, or omitted characteristics rather than a tradable alpha.
- A positive backtest would support only a scoped predictive relation, never prove
  long-term profitability.
