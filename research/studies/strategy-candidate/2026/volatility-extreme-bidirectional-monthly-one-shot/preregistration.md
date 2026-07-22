# 预注册：VOL90 极端双向月频 one-shot

## 候选筛选

| 候选 | 决策价值 | 未解决差异 | 可证伪/基准 | 数据与现实成本 | 研究成本 | 决定 |
|---|---:|---:|---:|---:|---:|---|
| VOL90 最低三名 LONG、最高三名 SHORT，单目标月频 | 5 | 5 | 5 | 5 | 3 | 选择；直接检验现有单腿研究没有回答的相对波动溢价，且适合 one-shot |
| 20 周同星期横截面季节性 | 3 | 5 | 5 | 3 | 3 | 不选；成熟论文的日频换手和多目标组合对零售成本、半自动操作不利 |
| 14 日价格路径连续性周频动量 | 4 | 3 | 4 | 5 | 3 | 不选；2026 工作论文、缺少独立复现，且与已失败/不足的持续上涨状态相邻 |

选择不是因为已知单腿指标漂亮。恰恰因为这些单腿证据不足，本题把市场方向解释拆开，并把支持权压在后续精确规则时间段；若后续失败，已知正回放不得保留为候选。

## 固定规则

1. 基准提交：`0bdfeffa616260cebd2d2188ddc8deb9e85c77f4`；正式策略背景：`ONE_SHOT_DONCHIAN_ATR_BREAKOUT 1.0.1 / BTCUSDT-PERP`。
2. 固定目标：当前研究名单中的 25 个 Binance USD-M 永续目标；它是 2026 当前幸存者名单，不补造成历史 point-in-time universe。
3. 每个 UTC 月首 `00:00` open 前，以前一日完成 bar 为截止点；目标必须有连续 91 个日历日有效 OHLCV、30 日 quote volume 中位数至少 `10,000,000 USDT`。至少 20 个目标可排名，否则全部 `NO_ACTION`。
4. `RV90 = std(ddof=1, prior 90 completed daily log returns) * sqrt(365)`；数值相同按 symbol 升序确定性打破平局。
5. 固定配置目标位于最低三名时提议 `LONG`，最高三名时提议 `SHORT`，其他排名不行动。每笔名义金额为用户已决定计划金额的 `0.25`；次月月首 open 时间退出，无价格止损。
6. 同一目标退出后要求一个完整 UTC 日冷却；因此连续月份仍处极端排名时，紧邻月份不重入。
7. favorable/base/stress 每边 fee 固定 `6 bp`，每边 slippage 分别 `0/10/20 bp`。使用实际 settled funding；stress 对 LONG 的正 funding 支出乘 `1.5`、负 funding 收益乘 `0.5`，对 SHORT 的正 funding 收益乘 `0.5`、负 funding 支出乘 `1.5`。
8. 按实际持有天数扣 `4%` 年化全计划资本门槛。推断单位为 entry month 的等权目标 cohort；3 月循环块 bootstrap，5,000 次，固定 seed `20260722`。

## 不可择优诊断

- RV60、RV120、VOL90 最低/最高五名；
- 反向波动策略（低波 SHORT、高波 LONG）；
- 90 日普通横截面动量（赢家 LONG、输家 SHORT）；
- 全目标 scheduled LONG、scheduled SHORT；
- LONG 与 SHORT 腿分别报告，任何单腿不得替代主规则。

## 阶段与门

### Development：2024 选择回放

该段已由相邻单腿研究部分暴露，只允许确认：数据 PASS；至少 30 笔、8 个 entry months、10 个目标；base/stress 主规则和两条方向均为正；VectorBT 与手工收益误差不超过 `1e-10`；排除比例不超过 5%。它不提供独立统计支持。

### Evaluation：2025

必须同时满足：数据与核对门；至少 30 笔、10 个 entry months、10 个目标、4 类；base/stress 扣门槛 cohort 均值为正；stress 三月块 bootstrap 95% 下界大于零；H1/H2 base 均为正；LONG 与 SHORT 的 base/stress 均正；主规则胜过反向波动和普通动量；RV60/RV120/extreme5 至少 2/3 stress 为正；至少一半合格目标、至少 3 类为正；最大单一正目标贡献不超过 35%；目标回撤中位高于 -15%、最差高于 -30%；missing-mark 交易排除不超过 5%。任一失败不打开 confirmation。

### Confirmation：2026H1

至少 15 笔、5 个 entry months、8 个目标、3 类；base/stress 为正；LONG 与 SHORT stress 均正；至少 2/3 邻域 stress 为正；至少一半合格目标和 2 类为正；集中度不超过 40%；回撤中位高于 -15%、最差高于 -30%。此外 evaluation+confirmation 合并 entry-month stress 均值及三月块 bootstrap 95% 下界必须大于零。

## 结论与停止

- 三阶段及合并门通过：`SUPPORTS_WITHIN_SCOPE`，生成框架无关 handoff，仅供以后交易核心资格验证。
- 样本充分但主规则 base/stress 或任一方向不正：`DOES_NOT_SUPPORT`。
- 经济结果为正但统计、稳健性、广度或风险门不足：`INSUFFICIENT_EVIDENCE`。
- 输入或实现身份无法可靠判断：`CANNOT_DETERMINE`。

失败后关闭固定 90 日、最低/最高三名、月频双向极端家族；没有新前向数据或独立机制时，不搜索 cutoff、lookback、方向、币种或持有期邻域。

