# 先行调研与来源

检索与核对时间：`2026-07-22`。以下优先正式论文、公开作者/会议版本、官方交易场所和库文档。

## 直接影响主问题

1. Han, Newton, Platanakis, Sutcliffe, Ye, *On the (almost) stochastic dominance of cryptocurrency factor portfolios and implications for cryptocurrency asset pricing*, European Financial Management 30 (2024), DOI `10.1111/eufm.12431`：<https://onlinelibrary.wiley.com/doi/10.1111/eufm.12431>
   - 公开会议版：<https://www.efmaefm.org/0EFMAMEETINGS/EFMA%20ANNUAL%20MEETINGS/2021-Leeds/papers/EFMA%202021_stage-2049_question-Full%20Paper_id-225.pdf>。
   - 数据/方法：CoinMarketCap 2014–2019，按周把币分成五组；`RMOM2` 定义为两周风险调整动量（Sharpe ratio），下一周价值加权；论文报告顶部组周均值约 2.80%、top-minus-bottom 约 3.15%。
   - 适用性：直接固定两周收益/波动排序和周持有，不需要新数据种类。
   - 差异：论文是广泛现货代理、市值权重、long-short，未覆盖当前幸存 Binance 永续、funding、零售成本或 one-shot 冷却。
   - Git 外会议 PDF 身份：`1,765,118` bytes，SHA-256 `5caf406d0250c132351fc8e83e7c63da945f6363e70fc3e897d6be0913b9b444`。

2. Li & Zhu, *Taming crypto anomalies: A Lasso-type factor model*, Research in International Business and Finance 83 (2026), article 103298, DOI `10.1016/j.ribaf.2026.103298`：<https://www.sciencedirect.com/science/article/pii/S0275531926000255>
   - 数据：CoinMarketCap 日线价格、市值和成交额，复查 49 个 anomaly，2014–2023，并比较样本外表现。
   - 采用：近期因子压缩仍选择短期 momentum/RMOM 相关因子，说明本题有更新后的研究价值。
   - 未覆盖：因子解释能力不是净成本 long-only 策略证据；论文使用 size 与市值权重，本题没有历史 point-in-time market cap。

3. Grobys et al., *Cryptocurrency momentum has (not) its moments*, Financial Markets and Portfolio Management 39 (2025), DOI `10.1007/s11408-025-00474-9`：<https://link.springer.com/article/10.1007/s11408-025-00474-9>
   - 2016–2023、30 至 2,500 币的复查显示普通 crypto momentum 对极端尾部、权重和样本非常敏感；价值加权组合可为负，risk management 不能可靠恢复正均值。
   - 用途：作为主反证，要求本题面对集中、相邻窗口、低波解释和真实成本；不把已发表因子当 Alpha 证明。

4. Fičura & Colak, *Impact of Size and Volume on Cryptocurrency Momentum and Reversal*, SSRN 4378429，2024-04-03 修订：<https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4378429>
   - 报告大且流动币存在周动量，而小/低流动币更多呈反转；适合当前流动对象的方向先验。
   - 未覆盖：工作论文、广泛现货横截面和分组结果不代表 Halpha 固定 long leg。

## 官方数据与研究框架

5. Binance USD-M Futures Kline 官方 API：<https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Kline-Candlestick-Data>；Binance 官方公共历史数据：<https://github.com/binance/binance-public-data/>。
   - 本题只复用已冻结的公开日线、fundingRate、markPriceKlines 及官方 checksum，不使用凭据或交易端点。

6. VectorBT `Portfolio.from_orders` 官方文档：<https://vectorbt.dev/api/portfolio/base/#vectorbt.portfolio.base.Portfolio.from_orders>
   - 只用于独立复算固定开平两单与费用；funding 显式补充。它不代表真实盘口、保证金或 NautilusTrader 执行语义。

## 固定未知

- 公开论文没有给出与 Halpha 完全相同的 `mean / sample std` 日收益实现细节；本题把零风险自由收益和不影响排名的年化常数明确固定为 Halpha 适配，不宣称逐字复制。
- Binance quote volume 是活动代理，不是历史 market cap。
- 当前名单和相同市场时期已被其他问题查看；只能报告方法特定的顺序证据，不能冒充全局未见路径。
