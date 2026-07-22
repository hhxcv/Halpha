# 来源与适用性

访问/核对日期：2026-07-22。

1. Li, Urquhart, Wang & Zhang, *Lottery-like preferences and the MAX effect in the cryptocurrency market*, Financial Innovation 7, 74 (2021), <https://doi.org/10.1186/s40854-021-00291-9>。
   - 采用：按过去一个月最大单日收益进行周度横截面排序；2014-01 至 2020-09，最高与最低 MAX decile 的下一周 value-weighted raw/risk-adjusted 差为 3.03%/1.99%；报告控制 size、price、momentum、短期 reversal、liquidity、volatility、skewness 与 sentiment 后仍为正。
   - 未覆盖：当前 Binance 永续、funding、零售成交成本、固定用户工具、one-shot 重激活、当前幸存者 universe；原始研究为多币横截面组合且方向与部分文献相反。

2. Jia, Liu & Yan, *Higher moments, extreme returns, and cross-section of cryptocurrency returns*, Finance Research Letters 39 (2021), 101536, <https://doi.org/10.1016/j.frl.2020.101536>。
   - 采用为强反证：Bitfinex 2017-01 至 2019-06、84 个币、5m 构造 daily realized moments；过去一日极端正收益/MAX 与下一日横截面收益为负。
   - 未覆盖：28 日形成和下一周；它说明 MAX 的方向高度依赖定义与持有期，不能把正周度结果视为普遍规律。

3. Svogun & Bazán-Palomino, *Technical analysis in cryptocurrency markets: Do transaction costs and bubbles matter?*, Journal of International Financial Markets, Institutions and Money 79 (2022), 101601, <https://doi.org/10.1016/j.intfin.2022.101601>。
   - 采用：69 个 MA/breakout 规则在 2016–2021 的日线/1m 上显示 transaction costs 与 bubble state 会改变盈利概率；支持现实成本和状态分解。
   - 未采用为候选：与正式 Donchian 及 Halpha 已有趋势族高度重复，且规则搜索很大。

4. Filippou, Rapach & Thimsen, *Cryptocurrency Return Predictability: A Machine-Learning Analysis* (2024 revision), <https://ssrn.com/abstract=3914414>。
   - 采用为候选比较：41 币 out-of-sample ML 报告 momentum、size、value、network/online predictors 与非线性有预测价值。
   - 未采用：特征和模型搜索、持续训练、额外数据与个人维护成本高；不能从其组合结果推出单个基础数据规则。

5. Binance, *Public Data*, <https://github.com/binance/binance-public-data>；USD-M monthly `fundingRate` 与 `markPriceKlines`, <https://data.binance.vision/?prefix=data/futures/um/monthly/>。
   - 采用：公开 Kline、funding、mark-price 月归档及相邻 `.CHECKSUM`；本题复用已校验原始字节并生成自己的 manifest。
   - 未覆盖：历史订单簿、真实成交、保证金、强平、账户规则；归档可能修订，必须用已存 hash 判断输入身份。

6. VectorBT 1.1.0 官方文档，<https://vectorbt.dev/api/portfolio/base/>。
   - 采用：`Portfolio.from_orders` 对明确 entry/exit 订单数组计算费用与滑点，外加逐笔手工公式核对。
   - 未覆盖：交易所事件顺序、部分成交、funding、保证金和 NautilusTrader 在线状态。

外部结果只决定问题、定义、基准和反证，不移植收益或显著性。当前问题最终只能使用四类 Halpha 结论之一。
