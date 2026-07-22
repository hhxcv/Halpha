# 预注册：高波动月频单腿 USD-M one-shot SHORT

## 身份与独立证据边界

- 类型：`STRATEGY_CANDIDATE`；身份：`RESEARCH_PERP_VOL90_TOP3_MONTHLY_ONE_SHOT_SHORT_0P25X_V1`。
- 基准提交：`0bdfeffa616260cebd2d2188ddc8deb9e85c77f4`；正式策略背景：`ONE_SHOT_DONCHIAN_ATR_BREAKOUT 1.0.1 / BTCUSDT-PERP`，不修改或声称重演。
- 发现样本：上一题 2022–2023 HIGHVOL90-LONG 对照已暴露且为负。Q8 不再使用该时期判断，只在尚未查看的 2024 固定规则后开始 development。
- 固定问题：低波论文的 high-vol SHORT 腿，能否在当前流动 USD-M、实际 funding、单工具人工计划和零售成本下独立产生正的绝对净收益？

## 候选与选择理由

| 候选 | 决策价值 | 主要反证 | 成本 | 决定 |
|---|---|---|---|---|
| VOL90 top3 月频 SHORT | 直接隔离论文 low-minus-high 的空腿；当前产品支持 SHORT | 高波币可能继续暴涨、short squeeze、funding 转负 | 日线+funding；月频 | **选中** |
| Q7 bottom5 LONG | 诊断更高 | 同题结果后选择参数，禁止升格 | 低 | 淘汰 |
| 14 日 winner LONG | 较早文献支持 | 最新 survivor 论文与多项内部 momentum 失败 | 低 | 后置 |
| negative-funding squeeze LONG | 不同机制 | 唯一阈值与确认定义不足 | 中 | 暂缓 |

本题不是把已知 LONG 亏损机械取负：SHORT 有不同的 bid/ask、fee、funding、尾部、保证金和 squeeze 路径，必须用未见时期重新计算。选择有原论文 long-short 结构支持，也有明确的产品单腿缺口。

## 固定规则

- 目标为与前两题相同的 25 个当前 A1/A2、长历史、现有 spread 快照不高于 5 bp 的 Binance USD-M perpetual；当前幸存者和分类不冒充历史 point-in-time universe。
- 每月首日 open 前，只用截至前一日 close 的完整数据。日对数收益 `log(close_t/close_{t-1})`；主特征为最近 90 日样本标准差 × `sqrt(365)`。
- 30 日 quote-volume 中位数至少 10m USDT，至少 20 个目标有完整输入。波动率降序、symbol 升序破同值；用户固定目标 rank `<=3` 才触发。
- 下一月首 UTC open 以 0.25x 计划资本 SHORT；下月首 open 完整平仓。退出后至少一个完整 UTC 日才能重新激活，因此同目标不连续月份交易。
- funding 只计 `entry < event < exit`。SHORT 实际现金流为 `+quantity × mark × rate`；stress 对正 funding 收益只留 0.5，对负 funding 支出乘 1.5。缺失 mark 的整笔排除并继续占计划期，不插值、不按零、不以成交价替代；单目标缺失事件率 ≤0.5%，主排除比例 ≤5%。
- 输入缺失、非正、时间不连续、可排名不足、成交额不足、已持仓或冷却均为 NO ACTION。

## 成本、诊断与推断

- favorable/base/stress 每边 fee+spread/slippage 为 6/16/26 bp；每笔按实际月长从全计划资本扣 4% 年化门。
- 主配置唯一：`VOL90/top3/monthly/0.25x SHORT`。
- 不可择优邻域：`VOL60/top3`、`VOL120/top3`、`VOL90/top5`。
- 简单对照：`LOWVOL90/bottom3 SHORT`、`LOSER90/bottom3 SHORT`、同样月频/one-shot 的 `SCHEDULED_SHORT`。
- entry month 并发目标等权聚合；三个 entry-month circular block、5,000 次 bootstrap；VectorBT 与手工 SHORT 线性公式逐笔核对。

## 顺序门

阶段：development 2024；evaluation 2025；confirmation 2026-01-01 至 2026-07-01。暖启动为各段开始前 135 日，阶段独立从空仓开始。

- development 最低 15 笔、6 目标、8 个 entry months；evaluation 相同；confirmation 最低 8 笔、4 目标、4 个月。
- 全阶段：数据质量 PASS、排除 ≤5%、核对误差 ≤`1e-10`；base/stress 日期扣门均值正；stress 三月块 95% 下界正；对应日历年正；至少一半有不少于两笔的目标正；至少三个类别正（confirmation 至少两个）；主 base 高于三个简单对照；至少 2/3 邻域 stress 正；最大正目标贡献 ≤40%；目标回撤中位 >-15%、最差 >-30%。
- 只有三段全部 PASS 才为 `SUPPORTS_WITHIN_SCOPE` 并生成框架无关 handoff。前段失败立即封闭后段。

样本/质量可判而 base 或 stress 非正为 `DOES_NOT_SUPPORT`；经济为正但统计、年份、广度、对照、风险或独立时间不足为 `INSUFFICIENT_EVIDENCE`；输入或实现不可判才用 `CANNOT_DETERMINE`。不能在结果后改变方向、lookback、rank、月份、名单、金额、成本、funding 或门。

## 未覆盖事实

日线无法表达月内 short squeeze、intraday margin path、历史盘口、排队、部分成交、最小订单、强平/ADL 和人工计划延迟；目标幸存者偏差仍在。0.25x 与回撤门降低但不能消除无限上行尾部。研究通过也不授权产品或真实交易，只释放以后由所有者选择的核心资格验证候选。
