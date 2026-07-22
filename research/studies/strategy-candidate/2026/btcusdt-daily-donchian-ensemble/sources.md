# 先行来源核查

以下来源在任何候选结果产生前用于固定机制、参数族、反证和数据语义。

1. [Zarattini, Pagani, Barbon (2025), Catching Crypto Trends](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5209907) 与[作者版 PDF](https://concretumgroup.com/wp-content/uploads/2026/02/Catching-Crypto-Trends.pdf)：加密资产日线 Donchian 组合的直接外部锚点。论文使用 5/10/20/30/60/90/150/250/360 日通道、通道中线单向跟踪退出、90 日波动率估计、25% 波动目标、2.0x 上限；分散组合按 10bp 成本和 20% 再平衡阈值报告。BTC 单资产表未扣交易成本，因此不能直接当作本场所的可交易收益。
2. [Original Turtle Trading Rules](https://www.tradingwithrayner.com/wp-content/uploads/2014/11/OriginalTurtleRules.pdf)：20/55 日突破、10/20 日反向通道退出、N/ATR 仓位与保护、加仓和跨市场风险限制。它说明经典 Donchian 是完整的持仓与退出系统，不是孤立入场指标；本研究不复制其路径依赖加仓。
3. [Moskowitz, Ooi, Pedersen, Time Series Momentum](https://w4.stern.nyu.edu/facdir/lpederse/papers/TimeSeriesMomentum.pdf) 与 [Hurst, Ooi, Pedersen, A Century of Evidence on Trend-Following](https://www.aqr.com/-/media/AQR/Documents/Insights/Journal-Article/AQR-JPM-Fall-2017.pdf)：跨市场、跨时间尺度和波动率归一化是趋势证据的重要部分。单一 BTC 只能验证产品适配，不继承多资产分散结论。
4. [Liu and Tsyvinski, Risks and Returns of Cryptocurrency](https://www.nber.org/papers/w24877)：加密资产存在周/月尺度时间序列动量证据，但该资产定价结果不等于某个 Donchian 交易规则扣费后盈利。
5. [Corbet et al., The Effectiveness of Technical Trading Rules in Cryptocurrency Markets](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3454216)：Bitcoin 高频技术规则结果随规则和方向而异，构成“Donchian 必然有效”的反证。
6. [Chevalier and Darolles, Futures Market Liquidity and the Trading Cost of Trend Following Strategies](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3523005)：趋势策略的表现和成本、市场波动状态必须分开归因。
7. [Bailey and López de Prado, Deflated Sharpe Ratio](https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf)：多候选选择会抬高观测 Sharpe；开发选择使用完整 6 候选分布计算 DSR。
8. [Binance Public Data](https://github.com/binance/binance-public-data)、[USD-M Kline API](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Kline-Candlestick-Data) 与 [Funding Rate History](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Get-Funding-Rate-History)：本题行情、校验和、时间戳和实际 funding 的官方语义。每个实际输入文件由 Git 外 manifest 与 SHA-256 固定。
9. [Poluri (2026), Donchian Channel Breakout with ATR-Based Risk Management](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6272239)：近期 BTC 单资产正结果，但作者明确说明成本、参数与市场状态敏感，且目前缺少引用与独立复现；只作为窄证据，不影响本题候选。

来源边界：公开论文的成功结果大多来自多资产分散或更长历史。Halpha 当前只研究单一 BTCUSDT 永续，因此必须以本场所 funding、成本、时间分段和单资产回撤重新判断。
