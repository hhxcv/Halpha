# 先行调研、来源与适用性

访问日期均为 2026-07-20，运行任何新 holdout 前记录。

- Pyo & Jang, [Revisiting the low-volatility anomaly in cryptocurrency markets](https://doi.org/10.1016/j.frl.2026.109851), *Finance Research Letters* (2026)：近期现货样本支持低波动组合，2–3 月形成期、1 月持有期最强，并报告固定的 2019 年前上市 cohort 稳健性。适合本题的 90 日/月度设定；但其横截面、统计检验、币池和成交假设不等同本研究。
- Shen et al., [Cryptocurrencies and the low volatility anomaly](https://doi.org/10.1016/j.frl.2020.101683), *Finance Research Letters* 40 (2021)：1000 多币、2013–2019 样本没有显著低波动溢价，且高波动币收益更高。这是直接反证，要求本题不能把局部盈利解释为普遍低波动 Alpha。
- Kaya & Mostowfi, [Low-volatility strategies for highly liquid cryptocurrencies](https://doi.org/10.1016/j.frl.2021.102422), *Finance Research Letters* 46 (2022)：高流动性集中低波动组合在 2017–2021 样本有效，stop-loss 可改善下行风险。支持选择成熟流动币；其最佳形成/持有期为 6–12 月且包含 stop-loss，本题刻意不复制，属于未覆盖差异。
- Ammann et al., [Survivorship and Delisting Bias in Cryptocurrency Markets](https://doi.org/10.2139/ssrn.4287573), SSRN (2022)：3904 币样本估计等权组合年化幸存者/退市偏差达 62.19%。本研究固定的是今天回看选出的成熟存续币池，无法消除该偏差；这是最强结构性限制。
- Binance, [Public Data](https://github.com/binance/binance-public-data)：官方 checksum 月度现货 1d kline；缺档只由 Binance 无鉴权公开 market-data REST 补齐。它支持 OHLC 与 quote volume 身份，不支持真实盘口、排队、滑点或订单可成交性。

假设：UTC 日线在每月首日开盘换仓，信号只使用前一 UTC 收盘及更早数据；每单位换手成本 favorable/base/stress 为 6/16/26bp；没有 funding，未计税、法币出入金、最小订单、价差时变、市场冲击、场所故障或账户容量。固定当前存续币池使结论只能是候选级证据。
