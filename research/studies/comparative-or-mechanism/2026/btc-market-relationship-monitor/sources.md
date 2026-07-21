# 先行调研与来源

访问日期均为 2026-07-21。来源只支持方法、接口语义或外部结果核对；本研究仍独立计算当前数据。

| 来源 | 类型与时间 | 采用内容 | 适用性 | 未覆盖差异 |
|---|---|---|---|---|
| [Binance Spot REST API 总则](https://developers.binance.com/en/docs/products/spot/rest-api) | 交易场所官方文档，访问 2026-07-21 | 公共市场数据优先使用 `data-api.binance.vision`；时间字段为 UTC 毫秒，返回顺序语义 | 支持无凭据、只读数据获取 | 不提供历史 point-in-time universe |
| [Binance Kline/Candlestick data](https://developers.binance.com/en/docs/catalog/core-trading-spot-trading/api/rest-api/market) | 交易场所官方文档，访问 2026-07-21 | `/api/v3/klines`、1d、UTC timezone、最多 1000、open/close/volume/trade count 字段 | 主行情的直接权威 | 单场所 close，不是全市场参考价 |
| Liu, Tsyvinski, Wu, [Common Risk Factors in Cryptocurrency](https://doi.org/10.1111/jofi.13119), *Journal of Finance* 2022 | 同行评审原始论文 | 加密市场、size、momentum 是共同风险结构；论文使用过去 365 日的日收益估计 beta/delay 等特征 | 支持市场共同因子、365 日 beta 和相对强弱背景 | 本研究用 BTC 单一基准而非论文市值加权 CMKT；不复现因子收益或策略 |
| Koutmos, [Return and volatility spillovers among cryptocurrencies](https://doi.org/10.1016/j.econlet.2018.10.004), *Economics Letters* 2018 | 同行评审原始论文 | 18 个大型币、1076 个日观测；BTC 是主要收益/波动冲击贡献者且连通性时变 | 外部方向性核对：BTC 在加密共同波动中居核心且关系随时间变化 | VAR forecast-error connectedness 不是相关或 beta；本研究不得声称复现冲击方向 |
| Benjamini & Hochberg, [Controlling the False Discovery Rate](https://www.dcscience.net/Benjamini-Hochberg-1995-FDR.pdf), 1995 | 原始统计论文 | 多重检验不能按逐项 p 值报告；FDR 控制错误发现比例 | 支持对数百币检验做统一校正 | 主研究因检验依赖采用更保守的 BY 实现而非原始独立 BH |
| [statsmodels HAC robust covariance](https://www.statsmodels.org/stable/generated/statsmodels.regression.linear_model.OLSResults.get_robustcov_results.html) | 官方库文档 0.14.6，访问 2026-07-21 | HAC 支持异方差/自相关稳健协方差、Bartlett kernel、maxlags 和小样本修正 | beta 推断使用成熟实现 | HAC 不修复模型遗漏、非平稳 regime 或选择偏差 |
| [statsmodels multipletests](https://www.statsmodels.org/stable/generated/statsmodels.stats.multitest.multipletests.html) | 官方库文档 0.14.6，访问 2026-07-21 | 提供 `fdr_by` 和校正后 p 值 | 直接实现依赖检验下更保守的 FDR | q 值仍不是效应大小，因此另设 0.50 相关阈值 |
| [Coin Metrics API v4](https://docs.coinmetrics.io/api/v4/) 与 [Prices FAQ](https://docs.coinmetrics.io/resources/faqs) | 独立数据提供方官方文档，访问 2026-07-21 | Community asset metrics；`PriceUSD` 是 UTC 日收盘并使用 beginning-of-interval 标签 | 尝试对 BTC/ETH/SOL/SUI/DOGE 做独立跨源核对 | Community 实测仅 BTC/ETH/DOGE 有所需完整免费历史，SOL/SUI 返回 403；覆盖和 constituent 与 Binance 不同，不能期待逐日 close 完全相等 |
| Binance, [Introducing bStocks](https://www.binance.com/en/support/announcement/detail/2c0c92ed15ac42d1b14bb1eac00d22bb), 2026-06-11/更新 2026-07-10 | 交易场所官方公告 | bStocks 是由 BTech Holdings 发行、1:1 美国股票支持、可在 Spot 24/7 交易的 tokenized securities，不是直接持股 | 支持从“币种 BTC 关联”主 universe 排除 bStocks | Spot exchangeInfo 没有直接 bStock taxonomy；本问题仍需保守身份规则并公开精确名单 |
| Binance Academy, [What Are bStocks?](https://academy.binance.com/en/articles/what-are-bstocks-a-guide-to-tokenized-stocks-on-binance), 2026-06-29 | 交易场所官方教育资料 | 给出 TSLAB 等 bStock 命名示例、Spot 24/7、发行/托管/公司行动语义 | 佐证上游默认 `CRYPTO_NATIVE` 不适用 | 文章不是机器可读全量当前清单 |

## 外部结果的正确核对方式

本研究可以核对：是否广泛存在正向共同波动、BTC 是否能解释许多当前币种收益变化、关系是否明显时变，以及 Binance 与 Coin Metrics 锚点的方向/数量级是否一致。

本研究不能声称直接复现 Koutmos 的冲击传导方向或 Liu 等人的三因子定价结论，因为模型、样本、universe 和价格来源不同。若当前结果方向不同，应先报告 regime、样本和数据差异，而不是把论文或本次数据判为错误。
