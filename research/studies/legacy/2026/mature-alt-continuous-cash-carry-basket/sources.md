# 先行调研与适用性

访问日期 2026-07-20，结果运行前记录。

- [Fundamentals of Perpetual Futures](https://arxiv.org/abs/2212.06888)（He et al.）：含摩擦无套利边界与 implied arbitrage，支持 spot/perp 对冲，亦说明交易成本不可省略。
- [Perpetual Futures Pricing](https://www.nber.org/papers/w32936)（Ackerer et al.）：periodic funding 的复制与锚定条件；不能外推实际多币 basis、清算与资本约束。
- [Perpetual Futures and Basis Risk](https://ssrn.com/abstract=5036933)（Gornall et al.）：受限套利资本与 basis 风险直接反对“无风险”表述。
- Chi et al., [An Empirical Investigation on Risk Factors in Cryptocurrency Futures](https://doi.org/10.1002/fut.22425)：同行评审研究中 basis 是主要横截面信号，提示跨币 funding/basis 异质性可能有分散价值，也可能造成集中风险。
- Binance [Public Data](https://github.com/binance/binance-public-data) 与 [Funding History](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Get-Funding-Rate-History)：官方 8h spot/perp 与 settled funding 数据及 checksum。

筛选的三项为固定三币篮子、单一 DOGE carry、动态最高 funding 轮动。固定篮子不搜索赢家、每阶段只进出一次，较单币降低事件集中；相较轮动大幅减少换手。代价是六腿、最小订单与个人维护复杂度，因此即使支持也只能作为有资本下限和执行验证前置的候选。
