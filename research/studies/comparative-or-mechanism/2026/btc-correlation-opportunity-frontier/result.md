# 机会前沿审计结果

## 结论

`DOES_NOT_SUPPORT`

在当前个人/小资金、基础公开 Kline、下一可行动时间、保守成本与避开最低活动高风险币的约束下，没有证据支持新增一个直接来自 BTC 相关性的策略候选。

- 高/中活动币的直接 BTC→ALT 延迟只有约 2.08/2.41 bp，不能稳定击败简单方向基准，且远低于 12 bp 最低门；额外 5m 后中等活动组仅 +0.25 bp。
- 小时级 BTC-neutral residual 双向反转均值 -10.61 bp，并有 -2,240 bp 最差事件小时；不支持简单 stat-arb。
- 历史 reversal/momentum 证据为失败或不足；当前正式 Donchian/ATR 已是固定 trend 比较基准。
- funding carry 的支持来自独立 carry/basis 机制，不是 BTC 相关性 Alpha。
- 谁在同步买入仍不能由 OHLCV 确定；最低活动/1m 与跨所机会需要本项目当前不采用的盘口、订单流、延迟和市场完整性证据。

因此停止相关性近邻参数/子组搜索，保留描述监测和未来多资产 risk-model 用途。只有出现新数据能力、独立结构关系、新未见时期/场所或数量级更低的可验证成本/延迟时才重开。

机器审计：`audit.json` SHA-256 `b3d6d416138432eefc43cd52626e4d59630148a91dbf0860c695a0b487093b78`；代码 SHA-256 `37eb47968e97c3e8ebeefe8ee81a3508bfca69124daec72a4cafde184dd297f2`。
