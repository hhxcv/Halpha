# 预注册：负溢价赢家日频 USD-M one-shot LONG

## 身份与证据边界

- 类型：`STRATEGY_CANDIDATE`；身份：`RESEARCH_WINNER5_TOP3_NEGATIVE_PREMIUM1_DAILY_LONG_0P25X_V1`。
- 基准提交：`0bdfeffa616260cebd2d2188ddc8deb9e85c77f4`；正式策略背景：`ONE_SHOT_DONCHIAN_ATR_BREAKOUT 1.0.1 / BTCUSDT-PERP`。
- 负 premium LONG、普通 winner、正 premium LONG/SHORT 等组件结果及多段价格字节已暴露，但 `winner5 top3 AND premium1<0` 从未计算。development/evaluation/validation 只作顺序筛选，不称为盲样本；2026H1 confirmation 只有在前三门通过后才打开。
- 顺序：development 2022–2023 → evaluation 2024 → validation 2025 → confirmation 2026H1；任一失败即停止。

## 固定规则

- 冻结 25 个 current-survivor Binance USD-M targets；30 日 quote-volume 中位数至少 10m USDT，至少 20 个目标有完整输入。
- 决策时点为 UTC 00:00 open 前。`winner5` 是过去 5 个完整 UTC 日 close-to-close 收益；在所有合格目标中降序、symbol 升序破同值。`premium1` 是前一完整 UTC 日三根 8h official premium close 的均值。
- 用户固定目标只在 `winner5>0`、winner rank `<=3` 且 `premium1<0` 时触发；下一 UTC 日 open 用 0.25x 全计划资本 LONG，下一日 open 退出；退出后一完整 UTC 日才能重激活。
- funding 严格计 `entry < event < exit`；LONG 现金流 `-quantity × mark × rate`。stress 对正 funding 成本乘 1.5，对负 funding 收益只留 0.5。缺 mark 整笔排除但占计划期；单目标 missing mark event ≤0.5%，主排除 ≤5%。
- 缺失、非法/不连续价格、winner 非正、premium 非负、rankable<20、流动性不足、持仓或冷却均 `NO ACTION`。

## 成本、邻域与基线

- favorable/base/stress 每边 fee+spread/slippage 为 6/16/26 bp；按 1 日持有从全计划资本扣 4% 年化门槛。
- 唯一主配置：`winner5/top3 + premium1<0 / 0.25x LONG / 1d`。
- 不可择优邻域：`winner3/top3`、`winner10/top3`、`winner5/top5`，均保持 `premium1<0` 和 winner>0。
- 简单基线：`winner5/top3 LONG`（不要求 premium）、`premium1 bottom3 LONG`（不要求 momentum）、所有流动目标 `SCHEDULED_LONG`。主 base 必须高于三个基线。
- entry-day 并发目标等权；14 日 circular block、5,000 次 bootstrap；VectorBT 与独立 LONG 公式逐笔核对。

## 阶段门

- development `[2022-01-01, 2024-01-01)`：至少 150 笔、12 目标、120 entry days、4 类，2022 和 2023 均正。
- evaluation `[2024-01-01, 2025-01-01)`：至少 75 笔、10 目标、60 days、4 类。
- validation `[2025-01-01, 2026-01-01)`：同 evaluation。
- confirmation `[2026-01-01, 2026-07-01)`：至少 50 笔、8 目标、40 days、3 类。各段独立空仓并含 45 日暖启动。
- 每段均要求：DQ `PASS`、排除≤5%、核对误差≤`1e-10`；base/stress 日期扣门均值正；stress 14 日块 95% 下界正；要求日历年均正；至少一半有≥5笔的目标正；至少上述数量且≥5笔的类别正；主 base 胜过三基线；至少 2/3 邻域 stress 正；最大正目标贡献≤25%；目标回撤中位>-10%、最差>-25%。
- 四段全 `PASS` 才 `SUPPORTS_WITHIN_SCOPE` 并生成 handoff。base/stress 非正为 `DOES_NOT_SUPPORT`；经济正但证据门不足为 `INSUFFICIENT_EVIDENCE`；数据/实现不可判为 `CANNOT_DETERMINE`。

## 失效与未覆盖

负 premium 是崩跌风险而非拥挤空头、winner 已耗尽、funding 收益太小、结果集中、普通 winner 或折价已足够解释、零售成本吞噬、跨年换符号均应否定。未覆盖盘中强平/ADL、盘口、部分成交、00:00 顺序、OI、liquidation、order flow 与人工计划延迟。通过也不授权产品或真实交易。
