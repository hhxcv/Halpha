# 预注册：永续溢价日频单腿 USD-M one-shot SHORT

## 身份与独立边界

- 类型：`STRATEGY_CANDIDATE`；身份：`RESEARCH_PERP_PREMIUM1_TOP3_DAILY_ONE_SHOT_SHORT_0P25X_V1`。
- 基准提交：`0bdfeffa616260cebd2d2188ddc8deb9e85c77f4`；正式策略背景：`ONE_SHOT_DONCHIAN_ATR_BREAKOUT 1.0.1 / BTCUSDT-PERP`。
- 上一题已查看 2022–2023 负 premium LONG 与基线；本题不使用该时期。2024 的部分非 premium 策略结果已暴露，但本题 premium-top SHORT 从未计算；2025 evaluation 与 2026H1 confirmation 保持未开封。
- 顺序为 development 2024 → evaluation 2025 → confirmation 2026H1；前段任一门失败则后段不下载。

## 固定规则

- 同一冻结的 25 个 current-survivor Binance USD-M targets；30 日 quote-volume 中位数至少 10m USDT，至少 20 个目标有完整输入。
- 每日 UTC 00:00 open 前，用前一完整 UTC 日三根 8h official premium-index Kline close 的简单均值 `premium1`；降序、symbol 升序破同值。
- 用户固定目标仅在 `premium1 > 0` 且 rank `<=3` 时触发；下一 UTC 日 open 以 0.25x 全计划资本 SHORT，下一日 open 平仓；退出后一个完整 UTC 日才可重激活同目标。
- funding 严格计 `entry < event < exit`；SHORT 现金流 `+quantity × mark × rate`。stress 对正 funding 收益只留 0.5，对负 funding 成本乘 1.5。缺 mark 整笔排除但占计划期；单目标 missing mark event ≤0.5%，主排除 ≤5%。边界 00:00 funding 不计。
- 缺失、非正价格、时间不连续、premium 不足三根、rankable 少于 20、流动性不足、premium 非正、已持仓或冷却均 `NO ACTION`。

## 成本、邻域和对照

- favorable/base/stress 每边 fee+spread/slippage 为 6/16/26 bp；按 1 日持有从全计划资本扣 4% 年化门槛。
- 唯一主配置：`premium1/top3/daily/0.25x SHORT`。
- 不可择优邻域：`premium3/top3`、`premium5/top3`、`premium1/top5`，均要求正 premium。
- 简单对照：prior-day settled funding 均值最高三名且为正的 `funding1-top3 SHORT`、5 日价格 winner top3 SHORT、全部满足流动性的 `SCHEDULED_SHORT`。主 base 必须高于全部三者。
- entry-day 并发目标等权；14 日 circular block、5,000 次 bootstrap；VectorBT 与独立 SHORT 线性公式逐笔核对。

## 阶段门

- development `[2024-01-01, 2025-01-01)`：至少 75 笔、10 目标、60 entry days。
- evaluation `[2025-01-01, 2026-01-01)`：同上。
- confirmation `[2026-01-01, 2026-07-01)`：至少 50 笔、8 目标、40 entry days。各段独立空仓并含 45 日暖启动。
- 每段都要求：DQ `PASS`、排除 ≤5%、核对误差 ≤`1e-10`；base/stress 日期扣门均值正；stress 14 日块 95% 下界正；阶段内每个日历年正；至少一半有不少于 5 笔的目标正；development/evaluation 至少四个、confirmation 至少三个有不少于 5 笔的类别正；主 base 胜过三个对照；至少 2/3 邻域 stress 正；最大正目标贡献 ≤25%；目标回撤中位 >-10%、最差 >-25%。
- 三段全部 `PASS` 才 `SUPPORTS_WITHIN_SCOPE` 并生成框架无关 handoff。base/stress 非正为 `DOES_NOT_SUPPORT`；经济正但其他证据不足为 `INSUFFICIENT_EVIDENCE`；数据/实现不可判才 `CANNOT_DETERMINE`。

## 失效与未覆盖

正 premium 反映信息性上涨而非拥挤、funding 远小于 squeeze、套利竞争消除价差、收益只在少数币/日期、零售成本吞噬均应否定。基础数据不覆盖 OI、liquidation、order flow、盘口、分钟内路径、00:00 先后、保证金/强平/ADL 与人工计划延迟。通过也不授权产品或真实交易。
