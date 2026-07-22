# 来源、时间与适用性

访问与核对日期：2026-07-22。

1. Chi, Hao, Hu & Ran, *An empirical investigation on risk factors in cryptocurrency futures*, Journal of Futures Markets (2023), DOI <https://doi.org/10.1002/fut.22425>；Cambridge 开放全文 <https://www.repository.cam.ac.uk/bitstreams/50f9c065-2731-4ab3-bba9-3ec4dcfc7ef7/download>。
   - 原始范围：OKEx 12 个主要币、2017-11 至 2021-03、现货与当季期货。高 basis（论文定义为现货相对期货更高）组合做多、低 basis 做空；5 日观察/1 日持有的 basis 因子最强，收益主要来自多头腿，日频显著性强于周/月频。
   - 采用：优先检验单腿 LONG、日频持有、基差而非普通动量，并保留动量基线。
   - 未覆盖：Binance 永续 premium index、funding、当前幸存 25 目标、用户 one-shot 冷却、0.25x 和 16/26 bp 每边成本。论文约 5 bp 成本不能直接移植。
2. He, Manela, Ross & von Wachter, *Fundamentals of Perpetual Futures* (2022), <https://arxiv.org/abs/2212.06888>。
   - 原始范围：永续定价、交易成本下无套利边界、Binance 小时级现货/永续/funding；超界价差的两腿策略可产生高 Sharpe，但价差随市场成熟缩小。
   - 采用：折价/溢价具有收敛机制，funding 必须作为现金流计入，成本与效率衰减是主要反证。
   - 未覆盖：其主要策略是现货—永续对冲而非单腿方向性 LONG；本题不能把两腿套利结果当作盈利证明。
3. Binance Developers, [Premium index Kline Data](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Premium-Index-Kline-Data) 与 [Funding Rate History](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Get-Funding-Rate-History)。
   - 采用：无需凭据的 `/fapi/v1/premiumIndexKlines` 8h bars；settled funding 的时间、rate 与关联 mark。信号只使用入场前已结束的三根 8h premium bars。
4. Binance, [Public Data](https://github.com/binance/binance-public-data) 与月度 USD-M archives <https://data.binance.vision/?prefix=data/futures/um/monthly/>。
   - 采用：1d 合约 OHLCV、funding、mark 和官方 checksum；档案可修订，因此清单保存实际字节 SHA-256 与 checksum 身份。
5. VectorBT, [`Portfolio.from_orders`](https://vectorbt.dev/api/portfolio/base/)。
   - 采用：LONG 开平、fee/slippage 框架复算，并与独立线性公式逐笔核对；不代表盘口、排队、部分成交或 NautilusTrader 事件语义。

## 候选筛选

| 候选 | 项目决策价值 | 可证伪性/数据 | 现实与交付差异 | 决定 |
|---|---|---|---|---|
| 永续折价 bottom3、1 日 LONG | 文献最强因子且收益主要来自 long leg | 官方 premium/OHLCV/funding；日样本多 | 单腿可交付，但必须反证方向风险和成本 | **选中** |
| 正 funding 的现货多头+永续空头 | 更接近套利 | 数据可得 | 需要原子两腿、现货库存和不同核心契约 | 淘汰 |
| 极端 funding 单腿反转 | crypto-native | 数据可得 | 文献更多支持 funding/基差机制，不直接支持方向收益 | 后置 |
| 做市/RL funding capture | 可捕捉 spread | 需 tick、成交与延迟 | 自动化、基础设施和模型风险超出个人半自动场景 | 淘汰 |
| 5 日 winner LONG | 易执行 | OHLCV 可得 | 多项内部动量诊断已弱，且论文显示 basis 更强 | 后置 |

外部研究只产生本题，不能替代本项目的顺序时间证据。
