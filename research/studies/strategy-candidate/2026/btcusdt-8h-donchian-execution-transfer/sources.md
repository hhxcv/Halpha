# 外部证据与数据源

- Zarattini, Pagani, Barbon, *Catching Crypto Trends; A Tactical Approach for Bitcoin and Altcoins*：多周期 Donchian ensemble、波动率定仓与完整趋势状态是本题的基础；论文的高 Sharpe 还依赖 20 币轮动，不能外推到本单腿题。<https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5209907>
- Bui, Nguyen, *Systematic Trend-Following with Adaptive Portfolio Construction*：公开消融报告中频 H6/H8 优于 D1、动态 trailing stop 贡献显著，并指出 crypto 正漂移支持非对称方向。本题只检验 H8 更新，不采用其 150+ 币、滚动优化和选币模块。<https://arxiv.org/abs/2602.11708>
- Karassavidis et al., *Quantitative Evaluation of Volatility-Adaptive Trend-Following Models in Cryptocurrency Markets*：BTC/ETH 中频、波动调整与 trailing exit 的近期同方向证据；其大规模参数优化不是本题证据。<https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5821842>
- Binance 官方公共数据：USD-M 月度 8h Kline 与 mark-price Kline，逐文件官方 CHECKSUM。<https://data.binance.vision/>
- Binance USD-M funding history：固定快照补足实际 funding 事件。<https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Get-Funding-Rate-History>
- Bailey 与 López de Prado, *The Deflated Sharpe Ratio*：对非正态收益与多重尝试校正。<https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551>

外部论文只用于形成可证伪问题，不作为 Halpha 回测结果或未来收益的替代证据。
