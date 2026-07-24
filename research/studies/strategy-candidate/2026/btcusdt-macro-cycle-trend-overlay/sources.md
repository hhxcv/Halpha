# 外部来源与采用边界

访问日期：2026-07-22。

1. [Moskowitz、Ooi、Pedersen，*Time Series Momentum*](https://doi.org/10.1016/j.jfineco.2011.11.003)：跨 58 个流动期货记录 1～12 个月收益延续；支持 84 日慢动量作为一个信号，不保证单一 BTC 或 1.5x 敞口盈利。
2. [Faber，*A Quantitative Approach to Tactical Asset Allocation*](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=962461)：10 月均线是低换手风险过滤的成熟基准；本题用近似交易日尺度的 SMA200，并增加 SMA50/SMA200 状态而非搜索均线长度。
3. [Kang、Ryu，*Time-series momentum and market timing in Bitcoin*](https://doi.org/10.1057/s41283-026-00234-7)：报告 BTC 的慢速 12 周信号优于快速和动态速度，直接决定 84 日信号；论文结论仍需在本数据、成本与严格牛段基准下复核。
4. [Liu、Tsyvinski，*Risks and Returns of Cryptocurrency*](https://www.nber.org/papers/w24877)：报告加密特有的时间序列动量和注意力预测证据；不等同于可执行 BTC 大周期策略。
5. [Zarattini、Pagani、Barbon，*Catching Crypto Trends*](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5209907) 与[作者 PDF](https://concretumgroup.com/wp-content/uploads/2026/02/Catching-Crypto-Trends.pdf)：支持 BTC 多尺度趋势、90 日波动率与成本敏感性；论文明确指出波动缩放会在强牛市降低敞口，且 BTC 单资产表以波动匹配而不是原始 1x buy-and-hold 比较。这正是本题改用分层慢趋势敞口并设置严格牛段门的原因。
6. [Grobys、Näsman、Sandretto，*Using on-chain data to predict Bitcoin cycles*](https://doi.org/10.1016/j.ribaf.2026.103486)：MVRV Z-score、NUPL 与 CVDD 的三周期结果支持链上持仓成本可能帮助识别极端区域。但其 buy-and-hold 从 2013 高点下跌 50% 后才开始，MVRV 退出阈值被作者承认并非完全客观，数据来自第三方图表且没有交易成本；因此本题只用 Coin Metrics MVRV 描述当前状态，不把它直接加入候选。
7. [Coin Metrics Community API](https://docs.coinmetrics.io/api) 与[价格口径说明](https://docs.coinmetrics.io/resources/faqs)：提供无需密钥的 UTC 日频 `PriceUSD`、`CapMVRVCur` 及规则化价格方法。原始响应保存在 Git 外并用 SHA-256 与内容身份固定。
8. [Binance Public Data](https://github.com/binance/binance-public-data)、[USD-M Kline](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Kline-Candlestick-Data) 和 [Funding History](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Get-Funding-Rate-History)：场所桥接复用的官方行情、mark price 与 funding 语义。
9. [Bailey、López de Prado，*The Deflated Sharpe Ratio*](https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf)：用于披露相关历史搜索的选择偏差；20/40 次只是敏感性量级，不声称独立同分布。

外部资料共同支持的是慢趋势、风险过滤和链上极端区域可能含信息。没有来源证明当前已见底，也没有来源证明一个固定 BTC 规则能在每次低点到高点超过 buy-and-hold。
