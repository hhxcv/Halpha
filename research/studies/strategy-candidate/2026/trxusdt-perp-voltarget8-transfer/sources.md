# 来源与适用性

- [Moreira & Muir, Volatility Managed Portfolios, NBER w22208](https://www.nber.org/papers/w22208)：高波动后降低风险可能改善风险调整表现；研究对象主要是传统因子，不直接证明 TRX 或 perpetual 有效。
- [Cederburg et al., On the performance of volatility-managed portfolios](https://doi.org/10.1016/j.jfineco.2020.04.015)：103 个权益策略的实时样本外结果并不普遍优于未缩放策略，结构不稳定是关键反证；因此本题要求顺序时间门和 50% always-long 基准。
- [Binance USD-M Funding Rate History](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Get-Funding-Rate-History)：逐事件 funding 来源。
- [Binance Public Data](https://data.binance.vision/)：checksum 可复取的月度 `1d` futures kline 与 `8h` mark-price kline。
- 内部固定先验：`research/studies/legacy/2026/trxusdt-voltarget-8pct-long/results.json`。8% 目标在现货侧已有顺序证据；本题不重新选择 target 或 lookback。

外部文献只支持检验机制和反证设计，不作为 Halpha 盈利结论。
