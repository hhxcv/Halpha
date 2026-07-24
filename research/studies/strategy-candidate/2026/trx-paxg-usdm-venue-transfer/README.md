# TRX/PAXG 两腿组合的 USD-M 场所迁移

> 当前状态：后续 `../trx-paxg-overfit-logic-audit/` 已将总体证据降为 `INSUFFICIENT_EVIDENCE`，Demo 资格撤回并暂停。本目录保留场所迁移方法与当时结果，不应单独用于产品决策。

## 问题与用途

此前 `trx-paxg-balanced-spot` 已按顺序阶段支持“每月 25% TRXUSDT + 25% PAXGUSDT + 50% 现金”的固定现货配置。本题只问：不改变标的、权重、方向或月度调仓规则，将两条多头腿换成 Binance USD-M perpetual 后，PAXG 合约自首个完整月以来的实际 funding、合约价格和现实成本，是否仍保留可供 Demo 前向验证的收益与风险特征？

- 类型：`STRATEGY_CANDIDATE` 的固定场所迁移桥接，不是新的参数搜索。
- 候选：`TRX_PAXG_USDM_MONTHLY_25PCT_EACH`。
- 范围：两腿，各 25% long，总 gross/net 0.50；不使用杠杆扩张，不包含六腿组合。
- 反证：任一迁移门失败即停止；不得改权重、调仓频率、起始日、成本或筛选片段挽救结果。

## 固定设计

- Binance USD-M `TRXUSDT`、`PAXGUSDT` perpetual，UTC 日线。
- 迁移确认区间：`[2025-04-01, 2026-07-01)`；这是 PAXGUSDT 2025-03-27 上线后的首个完整 UTC 月至最后完整归档月。
- 每月第一个 UTC 日开盘将两腿恢复到各 25%；月内不再平衡；末日按同一成本平仓以完整计量。
- favorable/base/stress 每单位绝对 turnover 的总成本为 10/30/60 bp，其中 taker fee 固定 4 bp、其余为滑点。
- 逐实际 funding 事件、对应 mark price 分别计入两腿；不把现货回测价格替代成合约价格。
- 基准：相同合约价格但忽略 funding 的 price-only 诊断，以及 50% TRX-only、50% PAXG-only。基准只解释 funding 与分散效果，不用于事后换候选。
- 4% 年化门按全部初始资本计，不按已投资的 50% 单独缩放。

## 预注册迁移门

以下全部通过才把研究结论升级为“可进入产品可达性审计与 Demo 前向验证”，不等同于稳定盈利已被证明：

- 原现货证据仍为 `SUPPORTS_WITHIN_SCOPE`；两份输入数据 checksum、连续性与 OHLC 合法性通过。
- Base 与 Stress 总收益为正，且 Stress 扣除 4% 年化全资本门后仍为正。
- 2025-04 至 2025-12、2026H1 两段 Stress 收益均为正。
- Base Sharpe 至少 0.75、Calmar 至少 1.0、最大回撤优于 -10%。
- 组合最大回撤浅于两条 50% 单腿，组合 Calmar 高于两条单腿。
- funding 不得消耗超过 price PnL 的 50%；若 funding 为净收入则此项直接通过。
- active days 至少 450，turnover 不超过 2.5。

现货确认与本迁移期共享底层价格结果，因此本题不声称拥有全新的价格 holdout；新证据只针对 USD-M 合约价、funding 和执行成本。若通过，仍必须依靠严格 AI 标识的 Demo 前向验证补足场所运行证据。

研究仅读取公开市场数据，产品作用为 `NONE`。
