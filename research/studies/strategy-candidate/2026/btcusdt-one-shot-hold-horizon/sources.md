# 来源与适用边界

访问日均为 2026-07-22。

1. [父问题：BTCUSDT 单次突破入场选择性](../btcusdt-one-shot-entry-selectivity/README.md)：当前 4×15m 退出下 72 个入场配置全部成本后平均为负，直接关闭继续调入场参数的路径，并提出“60 分钟是否截断趋势”这一未回答差异。
2. [历史 `btcusdt-next-funding-carry` 比较代理](../../../legacy/2026/btcusdt-next-funding-carry/README.md)：保存了正式策略 1.0.0、最长 96×15m 的有界代理；2024–2025 base LONG/SHORT 仍为负。它是已暴露的远端持仓基准，不等于当前策略绩效，也没有测试本题的 2/4/8 小时。
3. [Zarattini、Pagani、Barbon，Catching Crypto Trends](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5209907)（2025，SSRN 修订版）：使用多 Donchian 周期、流动性轮换、波动 sizing 与费用控制，支持趋势期限和换手需要成组评价；其 20 币组合与当前单 BTC、一次激活、固定止盈明显不同，不能移植收益。
4. [Liu、Tsyvinski，Risks and Returns of Cryptocurrency](https://www.nber.org/papers/w24877)（2018；2021 期刊版）：报告 BTC 日频和周频多个未来期限的时间序列动量，为“趋势可能长于 60 分钟”提供机制先验；它没有给出当前分钟级 Donchian、市场单成本或永续 funding 下的可交易结论。
5. [Bui、Nguyen，Systematic Trend-Following with Adaptive Portfolio Construction](https://arxiv.org/abs/2602.11708)（2026，预印本）：采用 6 小时信号、多资产月度自适应组合、动态 trailing stop 与非对称多空。它说明近期工作把 crypto 趋势放在更长的日内区间并做成本/状态分析，也反向表明其复杂框架不能证明 Halpha 只延长持仓就有效。
6. [Binance Public Data](https://github.com/binance/binance-public-data) 与 [Binance USD-M funding history](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Get-Funding-Rate-History)：本题采用的官方公开行情与 funding 语义；实际文件身份由沿用的 source manifest 和 SHA-256 固定。

没有来源直接回答当前固定入场、固定 ATR 止损/止盈、单 BTC 永续、2–8 小时最长持有在保守市场单成本后的结果，因此需要本地有界复现。外部正向趋势证据只构成先验，不是放宽本题顺序门的理由。
