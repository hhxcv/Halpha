# 来源、时间、候选与适用性

访问与核对日期：2026-07-22。

1. Chi, Hao, Hu & Ran, *An empirical investigation on risk factors in cryptocurrency futures*, Journal of Futures Markets (2023), DOI <https://doi.org/10.1002/fut.22425>；[开放全文](https://www.repository.cam.ac.uk/bitstreams/50f9c065-2731-4ab3-bba9-3ec4dcfc7ef7/download)。
   - 支持：OKEx 12 个主要币、2017–2021 中，高 basis（现货相对期货高）做多、低 basis 做空的日频因子最强，收益主要来自 long leg；日频显著性强于周/月频。
   - 强反证：普通 momentum 不够显著，basis-momentum 被 basis 因子解释；其 5 bp 成本、当季期货和长短组合不等于 Binance 单腿永续计划。
2. Cao, Luo, Cheng & Dong, *Anatomy of Cryptocurrency Perpetual Futures Returns* (2026), SSRN <https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6365329>。
   - 支持方法：以 price + funding total return 比较 170 个 predictors，最终由 log-basis 与 price-volume 因子解释显著策略；说明联合考察 basis 和价格信息比单因子更合理。
   - 限制：摘要不披露本题交互的精确定义和方向，不能当作盈利证明。
3. Zhang, *Funding Rate Mechanism in Perpetual Futures* (2026), SSRN <https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6185958>。
   - 机制：风险受限套利者与 momentum speculators 共存时，funding 反馈产生内生 basis 均值回归；跳跃/危机扩展会产生巨大负 basis 与慢恢复。
   - 限制：理论并不保证负 premium + 正价格趋势会继续上涨；危机中的负 basis 可能只是高风险状态。
4. Han, Kang & Ryu, *Momentum in the Cryptocurrency Market: A Comprehensive Analysis under Realistic Assumptions* (2023/2024 working paper), SSRN <https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4675565>。
   - 强反证：考虑日内价格路径后，不少表面均值显著的 momentum 组合会遭清算或产生负利润；均值不足以证明可交易性。本题虽用 0.25x 降低该风险，仍必须保留 stress、回撤和未建模盘中路径限制。
5. Xuan, *Funding Rates and the Conditional Informativeness of Order Flow* (2026), SSRN <https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6872638>。
   - 比较：正 funding 在 XAUUSDT 分钟级更像需求延续，但 funding×额外买盘交互为负且成本后不盈利；说明 funding 与价格/流量交互可能换符号，必须时间外验证。
6. Binance Developers, [Premium index Kline Data](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Premium-Index-Kline-Data)、[Funding Rate History](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Get-Funding-Rate-History) 与 [Public Data](https://github.com/binance/binance-public-data)。
   - 采用：公开 8h premium、1d OHLCV、settled funding、mark 和 checksum；无账户或凭据。
7. VectorBT, [`Portfolio.from_orders`](https://vectorbt.dev/api/portfolio/base/)。
   - 采用：LONG 开平与成本复算，并逐笔与独立线性公式核对；不代表盘口、清算或人工计划延迟。

## 候选筛选

| 候选 | 决策价值、数据与证伪 | 现实/交付差异 | 决定 |
|---|---|---|---|
| 5 日 winner top3 且 premium1<0 的 LONG | 价格确认 + 收 funding；可与两个单因子直接比较 | 日频单腿、0.25x、基础数据 | **选中** |
| 双向 funding-price disagreement | 样本更多 | 同时引入 LONG/SHORT 两个机制；SHORT squeeze 风险高 | 后置 |
| 横截面 dispersion 状态动量 | 可解释 regime | 动态大币池、状态选择与研究自由度更高 | 后置 |
| 均线/突破趋势 | 文献成熟 | 与正式 Donchian 家族未解决差异较小 | 淘汰 |
| 分钟级跨币 lead-lag | 同行评审 OOS | 数 bp、自动轮动、多腿，不适合半自动 | 淘汰 |

组件结果在 2022–2025 已部分暴露，但精确 conjunction 从未计算；因此早期阶段只能筛选，2026H1 才是相对干净的最终时间证据。
