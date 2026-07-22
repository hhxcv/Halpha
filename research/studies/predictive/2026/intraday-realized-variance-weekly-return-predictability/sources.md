# 先行调研与来源

检索与核对日期：`2026-07-22`。优先原始同行评审论文、作者/期刊全文和交易场所官方资料；本地既有结果仅用于查重和项目适用性判断。

## 采用的原始证据

1. Suzanne S. Lee、Minho Wang，*Variance Decomposition and Cryptocurrency Return Prediction*，Journal of Financial and Quantitative Analysis 60(4), 2025, 1859–1890，DOI：<https://doi.org/10.1017/S002210902400022X>；期刊开放全文：<https://www.cambridge.org/core/services/aop-cambridge-core/content/view/9995E58095453CB44A3BC3C9C111969F/S002210902400022Xa.pdf/variance_decomposition_and_cryptocurrency_return_prediction.pdf>。
   - 论文使用 Kaiko 的交易所内高频报价/价格，样本为 100 个 Coinbase 加密资产，2015-10 至 2023-06；另用 Bitfinex/Bittrex 做稳健性。
   - 采用 15 分钟收益，在每周末用前一月观测估计 realized total variance、正/负 jump variance 和 jump-robust variance，预测下一周横截面收益。
   - total variance 高减低 tercile 的下一周等权/市值权重收益约为 `-3.7%/-3.0%`；论文还报告日线波动率系数不显著，而 15 分钟 realized variance 的负向关系显著。
   - 适用性：提供“日线高低波研究可能遗漏了日内 realized variance 信息”的独立机制和固定主定义。
   - 未覆盖差异：论文是宽 spot 横截面、可构造多币组合、含小型和低流动资产；Halpha 是 25 个当前成熟 USD-M 永续、单腿半自动映射、真实 funding 尚未在预测题建模。论文的历史盈利不证明本项目存在 Alpha。

2. Torben G. Andersen、Tim Bollerslev、Francis X. Diebold、Paul Labys，*The Distribution of Realized Exchange Rate Volatility*，Journal of the American Statistical Association 96(453), 2001, DOI：<https://doi.org/10.1198/016214501750332965>。
   - 原始 realized variance 基础：固定区间内高频对数收益平方和估计 quadratic variation。
   - 本题只采用最简单的 total variance；不在开发结果后追加 jump detector 或复杂微观结构修正。

3. Binance 官方公开数据仓库：<https://github.com/binance/binance-public-data>；USD-M K 线接口资料：<https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Kline-Candlestick-Data>。
   - 官方说明 USD-M archive K 线来自 `/fapi/v1/klines`，支持 `15m`，并为压缩包提供 `.CHECKSUM`。
   - 本题逐文件保存 URL、字节数、本地 SHA-256 和官方 checksum；大型数据位于 Git 外，可按同一身份重取。

## 反证与项目内查重

- `perp-low-volatility-monthly-one-shot-long`：日线总波动率低组绝对收益为正，但被无条件定期 LONG 击败并且 development 失败。
- `high-volatility-monthly-one-shot-short`：日线高波动 SHORT 只在 `VOL90/top3` 精确切片为正，邻域全负且统计区间跨零。
- `idiosyncratic-volatility-monthly-return-predictability`：IVOL rank 有方向，但控制后不显著且成本代理失败。
- `relative-signed-jump-next-day-predictability`：15 分钟相对 signed jump 的次日问题失败；该题的信号是日内正负半方差差异，而本题是前一月 total realized variance 对下一周收益，方向、聚合期和经济机制不同。

## 候选比较与选中理由

| 候选 | 决策价值 | 独立性 | 数据/执行 | 决定 |
|---|---|---|---|---|
| 15m realized total variance → next week | 同行评审幅度大；直接解释日线研究缺口 | 测量分辨率差异由论文明确检验 | 已有官方 15m 数据；周频 | 选中 |
| realized skewness → next day | 有论文证据 | 与 MAX/RSJ 接近 | 日频换仓、成本敏感 | 淘汰 |
| variance jump decomposition | 可能定位正 jump / continuous 部分 | 比 total variance 更复杂 | jump test、日内季节校正和自由度更高 | 仅当 total variance 独立通过后才可另题 |
| cross-crypto lead-lag | 已有论文 | 本地直接失败 | 分钟级、多腿、自动化 | 淘汰 |
| delivery basis / multi-leg carry | 机制较强 | 与单腿 premium 不同 | 双腿、滚动和产品映射不符 | 当前范围淘汰 |

选中不是因为容易或指标漂亮，而是它同时具备：明确的原始机制、与本地失败日线波动研究的可检验差异、可冻结的简单主定义、现成官方数据、周频半自动可维护性，以及很强的否定价值。最可能的反证是成熟永续横截面缺少论文中小型、低价、低流动资产的效应；如果发生，应保留失败而不是扩大到操纵风险币追逐论文结果。
