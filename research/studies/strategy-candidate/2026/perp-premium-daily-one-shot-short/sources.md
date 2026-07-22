# 来源、时间与适用性

访问与核对日期：2026-07-22。

1. He, Manela, Ross & von Wachter, *Fundamentals of Perpetual Futures* (2022), <https://arxiv.org/abs/2212.06888>。
   - 采用：Binance 正 funding 事件附近，论文报告 ex-funding price 显著下降；正 funding 时空永续、买现货是收敛方向。funding 与价格腿必须一起核算，价差随市场成熟缩小。
   - 未覆盖：论文事件窗口约 funding 前后数分钟且主要是两腿交易；本题是下一日 open 到再下一日 open 的单腿 SHORT，承担 squeeze 与方向风险。
2. Chi, Hao, Hu & Ran, *An empirical investigation on risk factors in cryptocurrency futures*, Journal of Futures Markets (2023), DOI <https://doi.org/10.1002/fut.22425>；[开放全文](https://www.repository.cam.ac.uk/bitstreams/50f9c065-2731-4ab3-bba9-3ec4dcfc7ef7/download)。
   - 强反证：OKEx 当季期货 basis 因子收益主要来自 long leg，short leg 不显著。故“溢价最高就做空”必须独立证伪，不能由 long-short 因子推出。
3. Xuan, *Funding Rates and the Conditional Informativeness of Order Flow: Evidence from the Binance XAUUSDT Gold Perpetual* (2026), SSRN <https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6872638>。
   - 强反证：正 funding 单独在 5/15/30 分钟预测正收益；只有与额外买方 order flow 交互才呈 reversal，部分时段结果不耐多重检验。本题没有 order flow，必须允许 momentum/squeeze 压倒 funding。
   - 差异：XAUUSDT 是 2026 新 TradFi tokenized perpetual，不代表加密目标或日持有。
4. Binance Developers, [Premium index Kline Data](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Premium-Index-Kline-Data) 与 [Funding Rate History](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Get-Funding-Rate-History)；Binance [Public Data](https://github.com/binance/binance-public-data)。
   - 采用：公开 8h premium、1d OHLCV、settled funding、mark 和 checksum；无账户与凭据。
5. VectorBT, [`Portfolio.from_orders`](https://vectorbt.dev/api/portfolio/base/)。
   - 采用：SHORT 开平、fee/slippage 框架复算并逐笔手工核对；不模拟保证金、强平、ADL、盘口和人工计划延迟。

## 选择理由

候选包括 premium-top SHORT、funding-top SHORT、5 日 winner SHORT 和需要 OI/order-flow 共同确认的拥挤交易。选择 premium-top 是因为它更接近永续定价机制、信号在入场前完全可知、数据公开且当前单腿 SHORT 可交付；funding-top 和 winner 作为简单基线，OI/order-flow 版本因用户明确采用基础数据且会改变问题维度而后置。2022–2023 已知熊市不进入本题 gate。
