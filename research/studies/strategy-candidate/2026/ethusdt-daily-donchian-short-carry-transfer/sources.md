# 先行来源与边界

访问日：2026-07-22。

1. [Research Affiliates, *Should Trend Follow Carry?*](https://www.researchaffiliates.com/content/dam/ra/publications/pdf/1107-should-trend-follow-carry-lessons-from-bonds-gold-and-2022.pdf)：固定单侧/双侧 carry conditioning 定义，并明确效果依赖资产结构和趋势速度。ETH transfer 正是对资产可迁移性的反证。
2. [Schmeling、Schrimpf、Todorov, *Crypto Carry*](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4268371)：crypto carry 与杠杆趋势追逐、套利资本约束和 crash risk 相关；不能只从平均 funding 推断稳定收益。
3. [He 等, *Fundamentals of Perpetual Futures*](https://arxiv.org/abs/2212.06888)：固定 funding 支付方向、随机收敛和保证金风险；本回测纳入实际 funding，但仍不是执行或清算真相。
4. [Zarattini、Pagani、Barbon, *Catching Crypto Trends*](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5209907)：多周期 Donchian 外部基线；多资产组合结果不等于单一 ETH。
5. [Binance Public Data](https://github.com/binance/binance-public-data) 与 [Funding Rate History](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Get-Funding-Rate-History)：ETHUSDT `1d` kline、`8h` mark-price 和实际 funding 的官方输入与 checksum。
6. [Bailey、López de Prado, *Deflated Sharpe Ratio*](https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf)：候选来自先前 BTC 观察，必须把完整相关搜索纳入选择偏差，而非只计算 ETH 单列。
