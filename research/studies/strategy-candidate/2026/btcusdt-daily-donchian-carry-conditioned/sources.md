# 先行来源与适用边界

访问日：2026-07-22。以下来源在候选收益产生前用于固定机制与反证。

1. [Research Affiliates, *Should Trend Follow Carry?*](https://www.researchaffiliates.com/content/dam/ra/publications/pdf/1107-should-trend-follow-carry-lessons-from-bonds-gold-and-2022.pdf)（2026）：在 83 个传统期货/远期上明确比较纯趋势、双侧 carry 条件和两种单侧条件；发现趋势与 carry 同向常有帮助，但效果取决于 carry 对长期收益的贡献、趋势速度和资产结构，并警告简单过滤不是通用解。本题复用其三种过滤定义，不移植其业绩。
2. [Schmeling、Schrimpf、Todorov, *Crypto Carry*](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4268371)（2023）：加密 futures carry 高度时变，可能来自杠杆趋势追逐与套利资本稀缺，并伴随保证金和清算风险。它支持把 funding 当作经济状态，而不是免费修正项。
3. [He、Manela、Ross、von Wachter, *Fundamentals of Perpetual Futures*](https://arxiv.org/abs/2212.06888)（2022）：正 funding 由 long 支付给 short，永续与现货没有固定到期收敛，理论套利仍受成本和随机持有期风险影响。本题只做单腿方向策略，不冒充无风险套利。
4. [Zarattini、Pagani、Barbon, *Catching Crypto Trends*](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5209907)（2025）：提供多周期 Donchian、中线跟踪退出和波动目标的直接外部基线；其强结果主要来自更长历史和多资产组合，BTC 单资产表未扣成本。
5. [Binance Funding Rate History](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Get-Funding-Rate-History) 与 [Binance Public Data](https://github.com/binance/binance-public-data)：固定实际 funding、kline、mark price、时间戳和可重取身份。2025 年后 funding 间隔可动态变化，因此代码按实际事件计入，不硬编码每天三次。

外部来源没有回答固定 BTCUSDT、20/30/60/90 日 Donchian、0.5x 上限和 Halpha 成本下哪种 carry 条件能够样本外盈利。本题必须自行验证；成熟研究的正结论不构成本题支持。
