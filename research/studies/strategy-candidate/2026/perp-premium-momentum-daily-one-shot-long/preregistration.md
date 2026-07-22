# 预注册：永续正溢价延续日频 USD-M one-shot LONG

## 身份与证据边界

- 类型：`STRATEGY_CANDIDATE`；身份：`RESEARCH_PERP_PREMIUM1_TOP3_DAILY_ONE_SHOT_LONG_0P25X_OOS_V1`。
- 基准提交：`0bdfeffa616260cebd2d2188ddc8deb9e85c77f4`；正式策略背景：`ONE_SHOT_DONCHIAN_ATR_BREAKOUT 1.0.1 / BTCUSDT-PERP`。
- 2024 的同信号 SHORT 已失败，其价格腿使相反 LONG 方向成为已暴露发现；2024 不得作为本题 gate、稳健性或盈利证据。2022–2023 也已有相关 premium 研究暴露，不使用。
- 唯一资格证据顺序为 evaluation 2025 → confirmation 2026H1；evaluation 任一门失败则 confirmation 不下载。没有把发现样本改名为 development。

## 固定规则

- 同一冻结的 25 个 current-survivor Binance USD-M targets；30 日 quote-volume 中位数至少 10m USDT，至少 20 个目标有完整输入。
- 每日 UTC 00:00 open 前，用前一完整 UTC 日三根 8h official premium-index Kline close 的简单均值 `premium1`；降序、symbol 升序破同值。
- 用户固定目标仅在 `premium1 > 0` 且 rank `<=3` 时触发；下一 UTC 日 open 以 0.25x 全计划资本 LONG，下一日 open 平仓；退出后一个完整 UTC 日才可重激活同目标。
- funding 严格计 `entry < event < exit`；LONG 现金流 `-quantity × mark × rate`。stress 对正 funding 成本乘 1.5，对负 funding 收益只留 0.5。缺 mark 整笔排除但占计划期；单目标 missing mark event ≤0.5%，主排除 ≤5%。边界 00:00 funding 不计。
- 缺失、非正价格、时间不连续、premium 不足三根、rankable 少于 20、流动性不足、premium 非正、已持仓或冷却均 `NO ACTION`。

## 成本、邻域和对照

- favorable/base/stress 每边 fee+spread/slippage 为 6/16/26 bp；按 1 日持有从全计划资本扣 4% 年化门槛。
- 唯一主配置：`premium1/top3/daily/0.25x LONG`；这是从 2024 一次方向发现后冻结的一个配置，自由度明确计 1。
- 不可择优邻域：`premium3/top3`、`premium5/top3`、`premium1/top5`，均要求正 premium。
- 简单对照：prior-day settled funding 均值最高三名且为正的 `funding1-top3 LONG`、5 日价格 winner top3 LONG、全部满足流动性的 `SCHEDULED_LONG`。主 base 必须高于全部三者。
- entry-day 并发目标等权；14 日 circular block、5,000 次 bootstrap；VectorBT 与独立 LONG 线性公式逐笔核对。

## 顺序阶段门

- evaluation `[2025-01-01, 2026-01-01)`：至少 75 笔、10 目标、60 entry days、4 个类别。
- confirmation `[2026-01-01, 2026-07-01)`：至少 50 笔、8 目标、40 entry days、3 个类别。各段独立空仓并含 45 日暖启动。
- 每段均要求：DQ `PASS`、排除 ≤5%、核对误差 ≤`1e-10`；base/stress 日期扣门均值正；stress 14 日块 95% 下界正；阶段内每个日历年正；至少一半有不少于 5 笔的目标正；至少上述数量且有不少于 5 笔的类别正；主 base 胜过三个对照；至少 2/3 邻域 stress 正；最大正目标贡献 ≤25%；目标回撤中位 >-10%、最差 >-25%。
- 两段全部 `PASS` 才 `SUPPORTS_WITHIN_SCOPE` 并生成框架无关 handoff。base/stress 非正为 `DOES_NOT_SUPPORT`；经济正但其他证据不足为 `INSUFFICIENT_EVIDENCE`；数据/实现不可判才 `CANNOT_DETERMINE`。

## 失效与未覆盖

正 premium 只反映已经发生的上涨、LONG 支付 funding、需求在下一个日开盘前消散、收益只在少数币/日期、无条件市场 beta 即可解释、零售成本吞噬或 2025/2026 状态改变，均应否定。基础数据不覆盖 OI、liquidation、order flow、盘口、分钟内路径、00:00 先后、保证金/强平/ADL 与人工计划延迟。通过也只允许进入以后由所有者选择的核心资格验证，不授权产品或真实交易。
