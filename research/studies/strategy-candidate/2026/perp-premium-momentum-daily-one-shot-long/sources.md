# 来源、时间、候选与适用性

访问与核对日期：2026-07-22。

1. Xuan, *Funding Rates and the Conditional Informativeness of Order Flow: Evidence from the Binance XAUUSDT Gold Perpetual* (2026), SSRN <https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6872638>。
   - 支持：203,037 个 1m 观测中，funding 对未来 5/15/30 分钟收益的系数为正，作者解释为杠杆需求的持续和方向成分；这直接反对“正 funding 必然马上反转”。
   - 强反证：效应很小且交易成本后不盈利；funding 与额外买方 order flow 的交互为负，拥挤后可能反转。标的是 2026 新 XAUUSDT，不代表加密横截面或日持有。
2. Cao, Luo, Cheng & Dong, *Anatomy of Cryptocurrency Perpetual Futures Returns* (2026), SSRN <https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6365329>。
   - 支持方法：作者以价格加 funding 的 total return 评估 170 个 basis、momentum、liquidity、size、volatility predictors，63 个排序收益显著，并以 log-basis 与 price-volume 因子解释。
   - 限制：当前可核对摘要没有给出本题 `premium1/top3/LONG/1d` 的方向、成本或阶段结果；预印本不能替代本项目时间外证据。
3. Chi, Hao, Hu & Ran, *An empirical investigation on risk factors in cryptocurrency futures*, Journal of Futures Markets (2023), DOI <https://doi.org/10.1002/fut.22425>；[开放全文](https://www.repository.cam.ac.uk/bitstreams/50f9c065-2731-4ab3-bba9-3ec4dcfc7ef7/download)。
   - 强反证：其最强日频 basis 多头是“现货相对当季期货更高”的折价腿，而不是高永续 premium 的多头；样本、场所、合约与约 5 bp 成本也不同。本题不能把 basis 因子统称为支持。
4. Guo, Sang, Tu & Wang, *Cross-cryptocurrency return predictability*, Journal of Economic Dynamics and Control (2024), DOI <https://doi.org/10.1016/j.jedc.2024.104863>。
   - 候选比较：Binance 分钟级中 BTC 与其他币存在正 lead-lag，作者的期货长短组合在成本后仍有结果；但单分钟量级约 0.40–4.82 bp，需 5–10 分钟自动轮动、LASSO/PCA 与多腿组合，不适合当前半自动 one-shot 优先级。
5. He, Manela, Ross & von Wachter, *Fundamentals of Perpetual Futures*（2022，2025 修订），<https://arxiv.org/abs/2212.06888>。
   - 机制与反证：永续不保证到期收敛，funding 与交易摩擦决定边界；论文高 Sharpe 主要来自现货—永续两腿，不能证明单腿 LONG。
6. Binance Developers, [Premium index Kline Data](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Premium-Index-Kline-Data)、[Funding Rate History](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Get-Funding-Rate-History) 与 [Public Data](https://github.com/binance/binance-public-data)。
   - 采用：公开 8h premium、1d OHLCV、settled funding、mark 和 checksum；无账户或凭据。
7. VectorBT, [`Portfolio.from_orders`](https://vectorbt.dev/api/portfolio/base/)。
   - 采用：LONG 开平与 fee/slippage 框架复算，并逐笔与独立线性公式核对；不模拟盘口、排队、部分成交、保证金、强平或 ADL。

## 候选筛选

| 候选 | 未解决差异与可证伪性 | 现实成本/交付 | 决定 |
|---|---|---|---|
| 正 premium top3、次日 LONG | 检验需求持续能否覆盖 funding 与零售摩擦；2025/2026 未开封 | 单腿日频、0.25x，可直接表达为半自动计划 | **选中** |
| BTC→alt 分钟 lead-lag | 同行评审且有 OOS，但量级仅数 bp | 高频自动轮动、多模型和多腿；与人工计划不匹配 | 淘汰 |
| 现货 LONG + 永续 SHORT carry | 机制强、可收 funding | 原子两腿、库存与不同资金契约；核心不能原样接收 | 后置为独立产品能力问题 |
| funding + OI/order-flow 拥挤反转 | 可区分延续和反转 | 用户当前不引入 OI/order flow；改变数据边界 | 后置 |
| funding 感知做市/RL | 可捕捉 spread 与 funding | tick、低延迟、库存控制和持续自动化过重 | 淘汰 |

选择不是因为 2024 指标漂亮：2024 只产生方向假设并永久排除出 gate；主配置在 2025 首段失败即停止。
