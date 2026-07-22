# 来源与适用性

访问与核对日期：2026-07-22。

1. Pyo & Jang, *Revisiting the low-volatility anomaly in cryptocurrency markets*, Finance Research Letters 97 (2026), 109851, <https://doi.org/10.1016/j.frl.2026.109851>。
   - 采用：432 个 Binance 现货、2018-01 至 2025-11；按日收益实现波动做月度横截面组合，低波币系统性高于高波币；2–3 月形成、1 月持有最强，固定 2019 年前 cohort 和市场控制后仍保留。
   - 未覆盖：USD-M funding、固定 25 个当前幸存目标、单腿绝对收益、0.25x 全资本口径、one-shot 冷却和零售执行。
2. Kaya & Mostowfi, *Low-volatility strategies for highly liquid cryptocurrencies*, Finance Research Letters 46 (2022), 102422, <https://doi.org/10.1016/j.frl.2021.102422>；开放全文：<https://digitalcollection.zhaw.ch/server/api/core/bitstreams/5c4ee9d5-59bd-44fc-9934-d7a996d0ed96/content>。
   - 采用：2017-01 至 2021-06 高流动币；集中低波组合在较长形成/持有下有正超额收益，并显式讨论 17.5 bp 费用、50 bp spread 与止损。
   - 未采用：论文优化的止损和 6–12 个月持有不适合快速验证；原样加入会增加自由度并跨过当前计划周期。
3. Burggraf & Rudolf, *Cryptocurrencies and the low volatility anomaly*, Finance Research Letters 38 (2021), 101683, <https://doi.org/10.1016/j.frl.2020.101683>。
   - 采用为强反证：2013–2019 早期市场没有低波异常，反而高波伴随高收益；说明该关系可能随市场成熟度和样本期改变。
4. Binance, *Public Data*, <https://github.com/binance/binance-public-data>；USD-M monthly `fundingRate`、`markPriceKlines` 和相邻 `.CHECKSUM`：<https://data.binance.vision/?prefix=data/futures/um/monthly/>。
   - 采用：公开 1d Kline、settled funding、8h mark 与 gap-only 1m mark；不使用账户、凭据或产品数据。
   - 未覆盖：历史真实 spread/depth、订单队列、部分成交、保证金、强平与 ADL。
5. VectorBT 官方 `Portfolio.from_orders` 文档，<https://vectorbt.dev/api/portfolio/base/>。
   - 采用：明确两单的线性合约价格、fee 与 slippage 复算；另以手工公式逐笔核对。它不模拟 Binance 事件顺序或 NautilusTrader 在线状态。

项目内已暴露证据：`research/studies/legacy/2026/mature-liquid-spot-low-vol/` 在 2021–2022 固定 13 币、90 日、月频、三现货合计 0.5x 下得到 base +166.78%、回撤 -36.36%，因未过事前 -35% 风险门而为 `INSUFFICIENT_EVIDENCE`。该结果是选题线索而不是本题证据；价格时期、资产结构、分散、合约、funding 和计划语义均不同。
