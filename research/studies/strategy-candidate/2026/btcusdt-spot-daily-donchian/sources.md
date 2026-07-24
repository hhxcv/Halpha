# 先行来源与适用边界

访问日：2026-07-22。

1. [Binance Public Data](https://github.com/binance/binance-public-data)：Spot 月度 kline 来源为 `/api/v3/klines`，提供 checksum；2025-01-01 后 Spot 时间戳改为微秒。本题装载时显式归一化为毫秒并检查连续 UTC 日。
2. [Binance Spot API 官方文档](https://github.com/binance/binance-spot-api-docs)：固定 Spot 订单、成交、commission、filter、Testnet 与 Demo 的官方语义来源。公开历史研究不读取账户 commission；10 bp taker 只是保守代理，产品资格时必须查询实际账户事实。
3. [Zarattini、Pagani、Barbon, *Catching Crypto Trends*](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5209907)：固定多周期 Donchian、中线跟踪退出和波动率 sizing 的外部基线；其多资产组合与 BTC 未扣费表不能直接移植。
4. [Moskowitz、Ooi、Pedersen, *Time Series Momentum*](https://w4.stern.nyu.edu/facdir/lpederse/papers/TimeSeriesMomentum.pdf)：趋势证据依赖跨市场、较长历史和波动归一化；单一 BTC Spot 只能检验本产品候选。
5. [Schmeling、Schrimpf、Todorov, *Crypto Carry*](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4268371) 与 [He 等, *Fundamentals of Perpetual Futures*](https://arxiv.org/abs/2212.06888)：说明永续 funding/carry 是时变现金流和风险来源，Spot 对照具有机制价值，但场所、保管和执行风险仍不同。
6. [Bailey、López de Prado, *The Deflated Sharpe Ratio*](https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf)：转场候选仍来自已查看的规则族；开发门按十个相关尝试处理选择偏差，不把单候选写成一次独立发现。
