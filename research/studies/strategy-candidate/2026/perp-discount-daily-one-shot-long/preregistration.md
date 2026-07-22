# 预注册：永续折价日频单腿 USD-M one-shot LONG

## 身份与证据边界

- 类型：`STRATEGY_CANDIDATE`；身份：`RESEARCH_PERP_PREMIUM1_BOTTOM3_DAILY_ONE_SHOT_LONG_0P25X_V1`。
- 基准提交：`0bdfeffa616260cebd2d2188ddc8deb9e85c77f4`；正式策略背景：`ONE_SHOT_DONCHIAN_ATR_BREAKOUT 1.0.1 / BTCUSDT-PERP`，不修改、不重演。
- 2022–2024 的价格与部分其他策略结果已经暴露，不能称为完全盲样本；但本题 official premium feature、入选集合和收益未被计算。development 为 2022–2023，evaluation 为 2024；只有 2025–2026H1 confirmation 是相对更干净的未开封时间证据。
- 只有前段全门通过才下载下一段。前段失败立即封闭后段，不可用已知市场涨跌解释为通过。

## 固定主规则

- 固定 25 个当前 A1/A2、长历史、现 spread 快照不高于 5 bp 的 Binance USD-M perpetual；分类取冻结的 2026-07-21 market-universe。它是 current-survivor universe，不冒充 point-in-time 全市场。
- 每个 UTC 日 `00:00` open 前，只用前一完整 UTC 日三根 8h official premium-index Kline 的 close，取简单均值 `premium1`。30 日 quote-volume 中位数至少 10m USDT，至少 20 个目标有完整 premium、价格和流动性输入。
- 按 `premium1` 升序、symbol 升序破同值。用户固定目标仅在 `premium1 < 0` 且 rank `<=3` 时触发，否则 `NO ACTION`。
- 下一 UTC 日 open 以 0.25x 全计划资本 LONG，下一日 UTC open 完整退出；退出后至少一个完整 UTC 日才能重新激活同一目标，因此同目标入场至少间隔两天。
- funding 只计 `entry < event < exit`，LONG 现金流为 `-quantity × mark × rate`。stress 对正 funding 成本乘 1.5，对负 funding 收益只留 0.5。缺 mark 整笔排除但继续占计划期；单目标 missing mark event fraction ≤0.5%，主排除比例 ≤5%。边界 00:00 funding 不计，避免假定结算与开盘成交先后。
- 输入缺失、非正价格、8h/1d 时间不连续、premium 不足三根、rankable 少于 20、成交额不足、目标非负 premium、已持仓或冷却均为 `NO ACTION`。

## 固定成本、邻域与简单解释

- favorable/base/stress 每边 fee+spread/slippage 为 6/16/26 bp；每笔按实际持有日数从全计划资本扣 4% 年化门槛。
- 主配置唯一：`premium1/bottom3/daily/0.25x LONG`。
- 不可择优邻域：`premium3/bottom3`（过去 3 个完整日）、`premium5/bottom3`、`premium1/bottom5`；仍要求 feature <0。
- 简单对照：过去完整一日 settled funding 均值最低三名且为负的 `funding1-bottom3 LONG`、5 日价格 winner top3 LONG、所有满足流动性目标的 `SCHEDULED_LONG`。主配置必须以 base 日期均值同时胜过三者。
- entry-day 并发目标等权；14 日 circular block、5,000 次 bootstrap；VectorBT 与独立 LONG 线性公式逐笔核对。参数邻域和对照只做反证，不能升级为主配置。

## 顺序时间门

阶段：development `[2022-01-01, 2024-01-01)`；evaluation `[2024-01-01, 2025-01-01)`；confirmation `[2025-01-01, 2026-07-01)`。各段独立从空仓开始，包含 45 日暖启动。

- development 最低 150 笔、12 目标、120 个 entry days；evaluation 最低 75 笔、10 目标、60 日；confirmation 最低 100 笔、10 目标、90 日。
- 全阶段：数据质量 `PASS`、排除 ≤5%、核对误差 ≤`1e-10`；base/stress 日期扣门均值正；stress 14 日块 95% 下界正；阶段内每个日历年正；至少一半有不少于 10 笔的目标 base 均值正；development/evaluation 至少四个、confirmation 至少三个有不少于 10 笔的类别正；主 base 高于三个简单对照；至少 2/3 邻域 stress 正；最大正目标贡献 ≤25%；目标回撤中位 >-10%、最差 >-25%。
- 三段全部 `PASS` 才为 `SUPPORTS_WITHIN_SCOPE` 并生成框架无关 handoff。样本/质量不可判用 `CANNOT_DETERMINE`；base 或 stress 非正用 `DOES_NOT_SUPPORT`；经济为正但统计、年份、广度、基线、邻域、集中度、回撤或独立时间不足用 `INSUFFICIENT_EVIDENCE`。

## 失效条件与未覆盖事实

premium 折价随套利竞争消失、单腿方向波动淹没收敛、负 funding 成本持续、日频零售摩擦过高、收益只来自少数币/日期/年份，均应否定交付。日线/8h 数据不覆盖盘口、队列、部分成交、00:00 精确先后、分钟内跳空、保证金/强平/ADL 和人工计划延迟。研究通过也不授权产品修改、资金或真实交易，只释放以后由所有者选择的核心资格验证候选。
