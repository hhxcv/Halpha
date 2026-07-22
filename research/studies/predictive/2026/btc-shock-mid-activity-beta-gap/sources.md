# 来源与适用性

访问日期 2026-07-21。

1. Kurihara & Matsumoto (2026), [Price Transmission from Bitcoin to Altcoins](https://link.springer.com/article/10.1007/s10690-026-09589-z)：Binance 1m 数据显示大/中币近同步，而小币和低 trade-count 币有数分钟延迟；直接形成“换对象层、规则不变”的研究先验。其小币选择、短 OOS、0.02% fee 与不完整 spread/depth 仍偏乐观。
2. Guo, Sang, Tu & Wang (2024), [Cross-cryptocurrency return predictability](https://doi.org/10.1016/j.jedc.2024.104863)：top 30 Binance 分钟数据存在跨币 lag predictability；模型更复杂、样本 2019–2021，不能移植收益。
3. [Binance Public Data](https://github.com/binance/binance-public-data)：官方 USD-M 5m Kline 和 SHA-256 CHECKSUM，是唯一结果数据源。
4. Schmitz & Hoffmann (2025), [Wish or reality?](https://doi.org/10.1016/j.frl.2024.106508)：Binance 高频表面套利在费用、滑点和盘口量后消失；支持本题的成本停止门。
5. 父问题的 `sources.md` 与 `result.md`：成熟币固定表达已失败；本题只检验外部文献提出的活动度异质性，不重新搜索阈值。

市场快照只提供当前一次 spread、24h activity 和官方/派生标签。它无法证明 2024 的可交易性或未操纵；本题从官方 Kline 补充历史 quote volume/trade count，但仍不等于历史盘口。

