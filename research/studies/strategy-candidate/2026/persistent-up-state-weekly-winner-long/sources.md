# 先行调研与资料

访问/核对于 2026-07-22。来源只用于固定问题、方法和反证，不能替代 Halpha 自身数据检验。

1. Hsieh、Huang、Liu，[State transitions and momentum effect in cryptocurrency market](https://doi.org/10.1016/j.frl.2025.108356)，Finance Research Letters，2025。作者用 2015–2023 CoinMarketCap 日数据构造周收益，按过去四周 value-weighted 市场累计收益划分 UP/DOWN，并报告 momentum 集中在持续 UP–UP 状态。适用：提供状态窗口和“无条件 momentum 可能掩盖状态依赖”的可证伪先验。差异：本题只有 Binance 六个高活动幸存永续、等权市场代理、单腿 LONG、实际 funding 和零售成本；不复现其全市场 long-short portfolio，也不接受行为机制为已识别因果。
2. Grobys、Kolari、Sapra，[On survivor cryptocurrency momentum](https://doi.org/10.1016/j.frl.2026.109602)，Finance Research Letters，2026。2017-01 至 2024-08 的九个 top-100 survivor coins 没有显著 momentum，广义 momentum 的显著性高度依赖修剪和样本。适用：本题正是固定幸存大币，故它是必须面对的最强反证。差异：本题测试明确的 UP–UP 条件、Binance perpetual 与成本，不把失败推广到动态全市场。
3. Fičura、Colak，[Impact of Size and Volume on Cryptocurrency Momentum and Reversal](https://ssrn.com/abstract=4378429)，2023，2024-04 修订。论文报告小/低流动币周反转，而大/高流动币周动量，并强调 size/liquidity 分层。适用：支持只用高活动对象、避免把小币反转结果移植到当前边界。差异：其市场、分组和组合规则不等于六个永续的 one-shot LONG。
4. Zhang、Makgolo，[Cross-Sectional Dispersion and the State Dependence of Cryptocurrency Momentum](https://ssrn.com/abstract=6648082)，2026-04。论文使用动态、幸存者感知的 CoinGecko top-500 universe，报告高 dispersion 预示后续 momentum 变弱；日频 20 日 momentum 的 dispersion 缩放改善 full-sample 风险，但 post-2020 long-only 更偏向 BTC-vol 缩放。适用：说明状态变量确有当前研究价值。未选原因：动态市值/成交过滤、每日多资产权重和最高 2x 组合与当前半自动 one-shot 和基础 Binance 数据差异过大，不应为追逐论文指标先建设复杂交付。
5. Kim、Hansen，[The Quarter-Hour Effect](https://arxiv.org/abs/2607.09426)，2026-07-10/2026-07-16 修订。六个 Binance perpetual 的前 10 秒订单流对 4–12h 收益有预测关联。未选原因：Halpha 已用论文后时期、1m Kline 代理和现实成本完成同方向策略题并得到 `DOES_NOT_SUPPORT`；精确逐笔 10 秒版本要求更高数据/执行复杂度且论文没有个人净成本策略证明。
6. [Binance Public Data 官方仓库](https://github.com/binance/binance-public-data)、[USD-M Kline 官方文档](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Kline-Candlestick-Data)、[Funding Rate History 官方文档](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Get-Funding-Rate-History)。适用：本题复用的只读公开日线、mark 与 settled funding 身份和字段含义。差异：官方历史数据不提供本题所需的历史真实 bid/ask、队列、部分成交、保证金或账户费率。
7. [VectorBT Portfolio.from_orders 官方文档](https://vectorbt.dev/api/portfolio/base/)。适用：用显式 entry/exit 数组核对费用和 slippage，不把 VectorBT 当作产品成交语义权威。

库内直接反证与查重：`liquid-perp-weekly-loser-continuation` 的周输家 short 未获支持；`mature-alt-spot-top2-momentum` 与风险管理后续均未获支持；`category-momentum-gated-one-shot-long` 的固定单腿类别门失败；正式 Donchian/ATR 只作固定背景。上述失败阻止继续做无状态窗口调参，但没有直接回答持续 UP–UP 的单腿周赢家问题。
