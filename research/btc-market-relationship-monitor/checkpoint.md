# 启封前研究检查点

冻结时间：2026-07-21（首次下载本问题的 OHLCV 与查看结果之前）。

## 候选与选择

| 候选 | 已有方法 | 对当前决定价值 | 主要缺口/成本 | 选择 |
|---|---|---|---|---|
| 全币种日收益相关、BTC beta 与相对强弱持续监测 | Pearson/Spearman、市场模型、滚动窗口、稳健协方差 | 直接回答用户问题；基础数据即可；个人可快速更新；可扩到数百币 | 当前名单有幸存者偏差；关联不是方向或因果 | 选中 |
| DCC-GARCH 动态相关 | 多变量波动模型 | 对少量资产的条件相关更精细 | 约 446 对象难以稳定维护，模型选择和收敛成本高；页面主要决定不需要 | 不选，作为后续少量重点对象的独立问题 |
| Diebold-Yilmaz VAR connectedness 网络 | 成熟溢出/连通性方法 | 更接近“谁传导给谁” | 高维 VAR 需要降维、滞后和预测误差方差选择；不等同于用户当前关联清单 | 不选，不能用简单相关冒充传导 |

选中理由：成熟方法已足以回答当前问题；自研究价值是独立数据、固定口径、全当前宇宙扩展、失败可见和持续刷新，而不是方法新颖性或漂亮指标。

## 固定问题与否定条件

主问题：当前合格对象中是否存在一组在最近 365 个共同日收益观测上对 BTC beta 经 HAC 推断和 BY-FDR 后仍显著，且 Pearson 绝对值至少 0.50、秩相关同号、两个非重叠 180 日窗口同号的强关联对象？

否定/降级条件：

- 无对象同时达到样本、BY-FDR 与效应/稳定性门，则主问题 `DOES_NOT_SUPPORT`。
- 数据截止无法固定、BTC 或大部分对象缺失、官方语义无法确认，结论降为 `CANNOT_DETERMINE`。
- 样本或跨窗口证据不足，或跨源锚点严重不一致且无法解释，结论降为 `INSUFFICIENT_EVIDENCE`。
- 任何正向结果只允许 `SUPPORTS_WITHIN_SCOPE`，不表示因果、领先关系、预测收益或 Alpha。

## 固定数据与变换

- Universe 只从已记录的 `research/market-universe/universe.csv` 快照读取；首次问题运行不动态把最新 exchangeInfo 替换为另一个名单。
- Binance endpoint：`https://data-api.binance.vision/api/v3/klines`，`interval=1d`，`timeZone=0`，每对象最多请求 1000 bars；保留最多 800 个已闭合 bar 供 365 日和稳定性计算。
- cutoff：运行时 `floor(now_utc, 1d) - 1ms`；任何 close time 大于 cutoff 的 bar 丢弃。
- 价格必须为有限正数；open time 唯一、严格递增；重复保留最后一条并在质量记录中计数。
- 以收盘价对数差计算收益；每一对按 UTC open time 内连接，不做前向填充；只使用同时存在的收益。
- 主窗口：最多 365 个共同收益；样本门槛 120。
- 稳定性：最近 180 个共同收益与其之前最多 180 个非重叠共同收益；每段至少 90 才评价符号稳定。
- 90 日 rolling Pearson 至少 60 个观测。
- 相对强弱：严格使用共同价格的最后 7/30/90 个日收益之和差；不足则为空。
- Cross-source：Coin Metrics Community `PriceUSD`, `frequency=1d`，尝试用于 BTC/ETH/SOL/SUI/DOGE 的收益相关/beta方向核对，不替代主数据、不扩展主 universe。`PriceUSD` 使用 beginning-of-interval 标签并表示该 UTC 日的 daily close，与 Binance kline open date 同标签；Community 不提供的对象保留为不可用。

## 固定模型、推断和分类

- Pearson 与 Spearman 全部报告，不对价格水平求相关。
- OLS 含截距；statsmodels HAC covariance, Bartlett kernel, `maxlags=7`, `use_correction=True`。
- 多重检验 family 是本次所有达到 120 样本门的对象 beta 双侧 p 值；statsmodels `multipletests(method='fdr_by', alpha=0.05)`。
- `statistically_significant = q <= 0.05`。
- `strong_association = statistically_significant AND abs(Pearson) >= 0.50 AND sign(Pearson)=sign(Spearman) AND recent_180/prior_180 同号`。
- 相关强度只是预注册的展示分层：`>=0.70 VERY_STRONG`、`0.50–0.70 STRONG`、`0.30–0.50 MODERATE`、其余 WEAK；不据此推断可交易性。
- 跨窗口稳定性辅助量：365、最近 180、前 180 相关的最小绝对值与最大差；不做后验删选。

## 尝试总数和结果揭示规则

- 一个固定方法 family，最多 446 个对象；每对象不做参数搜索。
- 预先指定 365/180/90 与相对强弱 7/30/90，合计不是从结果中选择最佳窗口。
- 页面可排序/筛选不新增统计试验；导出的完整 CSV 是权威结果，不能只保留最佳对象。
- 首次结果揭示后，任何阈值、窗口、universe 或模型变化必须记录为新尝试，不能覆盖此检查点或称为未暴露证据。

## 已知未覆盖差异

- 单一 Binance Spot close 与论文使用的聚合市场、不同交易所或市值加权 crypto market factor 不同；这里的 BTC beta 不是论文 CMKT beta。
- 当前 universe 不重建历史上市/下架；新币样本更短，已下架币不在主清单。
- 日线不能识别日内领先滞后、溢出方向、微观结构或操纵。
- 不使用 L2、新闻、OI、liquidation、funding 或链上数据；这不妨碍回答共同日收益问题，但限制机制、执行和预测解释。

## 结果揭示后的方法修订（不属于原检查点）

首次结果已于 2026-07-21T10:19Z 揭示，之后数据质量审查发现当前 Spot universe 把 36 个 2026 年新增 bStock 代币化证券默认标成 `CRYPTO_NATIVE`。Binance 官方说明 bStocks 是由美国股票 1:1 支持的 tokenized securities，可在 Spot 24/7 交易，并非原生加密币。修订版只在本问题固定快照内排除同时满足以下条件的对象：`economic_exposure_source=DEFAULT_CRYPTO_NATIVE_AFTER_EXPLICIT_EXCLUSIONS`、`classification_subtypes` 为空、`base_asset` 以 `B` 结尾，并显式保留核对为原生加密资产的 DGB 例外。精确排除与例外名单写入每次输出的 universe identity；未来快照必须重新审核，不能自动泛化此后缀规则。

这是一项身份语义 bug 修正，不是根据相关结果选币；但因发生在结果揭示后，修订版不能称为原预注册 universe。首次修订前结果为 446 个对象、400/402 个达到样本门（两次抓取）、383/385 个统计显著、236/238 个强关联；bStocks 均因历史不足未进入 120 日统计，因此修订不会改变已分析对象的相关、beta 或强关联清单，只纠正 universe 和样本不足分母。
