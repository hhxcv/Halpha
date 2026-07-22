# 预注册：低波动月频单腿 USD-M one-shot LONG

## 身份、基准与问题边界

- 类型：`STRATEGY_CANDIDATE`；候选身份：`RESEARCH_PERP_VOL90_BOTTOM3_MONTHLY_ONE_SHOT_LONG_0P25X_V1`。
- 基准提交：`0bdfeffa616260cebd2d2188ddc8deb9e85c77f4`；正式策略背景：`ONE_SHOT_DONCHIAN_ATR_BREAKOUT 1.0.1 / BTCUSDT-PERP`，不复制、修改或重演其历史绩效。
- 固定问题：当用户已固定一个 Binance USD-M 工具、LONG 和计划金额后，该工具 90 日实现波动在当前流动 25 目标中处于最低三名时，下一月的绝对 LONG 收益能否在永续 funding、零售成本、全计划资本门与 one-shot 生命周期后稳定为正？
- development 为 2022–2023。相同价格字节已在其他问题出现，因此不是全新时期；本题规则、选择与结果尚未查看。只有 development 全门 PASS 才可打开 2024，之后才可打开 2025–2026H1。

外部 Pyo/Jang 研究的是 432 币 spot 的 low-minus-high 横截面关系；Kaya/Mostowfi 是多币现货组合；项目父证据也是三币共享资本。它们都没有回答单个 USD-M LONG 的绝对净收益。本题通过也只释放资格验证候选，不证明未来 Alpha。

## 候选筛选

| 候选 | 未解决差异 | 可证伪性与幅度 | 数据/维护成本 | 决定 |
|---|---|---|---|---|
| VOL90 最低三名的单腿月频 perp LONG | 最新 spot 低波效应能否跨 funding、单腿和 one-shot | stress、年份、目标、类别、high-vol 与定期 LONG 可直接否定 | 日线 + funding；月频 | **选中** |
| 14 日流动赢家周频 LONG | winner 论文较多 | 2026 survivor 研究与项目动量失败构成强反证 | 低 | 后置 |
| 深负 funding squeeze LONG | 拥挤反转机制 | 阈值和确认条件缺少唯一成熟定义，易搜索 | 中 | 暂缓 |
| BTC 残差 momentum | 去市场 beta | 与既有 residual reversal/lead-lag 接近，需 beta 估计 | 中 | 淘汰 |

选择不是因为容易或预期收益漂亮，而是近期原始研究、项目内强但未过风险门的现货证据和当前唯一产品适配缺口三者同时存在；失败可关闭“把组合低波直接拆成单腿永续”的捷径。

## 固定对象、信号与行动

- 目标固定为与上一题相同的 25 个当前 A1/A2、长历史且现有 spread 快照不高于 5 bp 的 USD-M perpetual。当前幸存者与分类不是历史 point-in-time universe；名单完整写入 checkpoint。
- 每个 UTC 月首 open 前，只使用截至前一日 close 的完整日线。日对数收益 `log(close_t / close_{t-1})`；主特征为最近 90 个完整日收益样本标准差乘 `sqrt(365)`。
- 目标过去 30 日 quote-volume 中位数至少 10m USDT，至少 20 个目标有完整 VOL90 和成交额。按年化波动升序、symbol 升序破同值；用户固定目标只有 rank `<=3` 才触发。
- 入场为下一 UTC 月首日 open，名义为全计划资本 0.25x，方向只允许 LONG；退出为下一月首日 open。退出后至少一个完整 UTC 日才可再次激活，因此同目标不能连续月份交易，持仓期间的新信号不排队。
- 数据缺失、非正、时间不连续、可排名目标不足、成交额不足、计划已持仓或仍在重新激活冷却期均不行动。
- funding 只计 `entry_time < event_time < exit_time` 的 settled event；缺失 mark 的整笔交易排除但继续占原计划期，不插值、不按零、不用成交价代替。单目标缺失事件率最多 0.5%，主规则排除交易比例最多 5%；较周频旧题放宽只因为月频理论样本更少，且是在本题结果前根据已知官方缺口固定，不是经济调参。

## 搜索披露、成本与统计

主配置只有一个：`VOL90 / bottom3 / monthly hold / 0.25x LONG`。

不可择优邻域：`VOL60/bottom3`、`VOL120/bottom3`、`VOL90/bottom5`。简单对照：`HIGHVOL90/top3`、`MOM90/top3`、同样月频/one-shot 的 `SCHEDULED_LONG`。诊断全部保存，不能事后升格。

- favorable：每边 6 bp taker fee、零 spread/slippage、实际 funding。
- base：每边 6 bp fee + 10 bp spread/slippage、实际 funding。
- stress：每边 6 bp fee + 20 bp spread/slippage；正 funding 支出乘 1.5、负 funding 收益只留 0.5。
- 每笔按实际持有日从全计划资本扣 4% 年化门；0.75x 未使用部分不缩小门槛。
- 同 entry month 的目标先等权聚合；使用三个 entry-month circular block、5,000 次 bootstrap。VectorBT 计算价格、fee 和 slippage，逐笔手工线性合约公式核对，funding 显式补充。

## 顺序门与四类结论

development 最低 30 笔、6 个目标、15 个 entry months；evaluation 最低 15 笔、4 个目标、8 个月；confirmation 最低 10 笔、4 个目标、6 个月。每段都要求数据质量 PASS、排除比例不超过 5%、VectorBT 核对误差不超过 `1e-10`。

development PASS 必须全部满足：

- base 和 stress 日期队列扣门槛均值为正，stress 三月块 bootstrap 95% 下界大于零；
- 2022 与 2023 base 分别为正；
- 至少一半有不少于三笔的目标 base 均值为正，至少三个当前类别为正；
- 主规则 base 分别高于 HIGHVOL90、MOM90 与 SCHEDULED_LONG；
- 三个邻域至少两个 stress 日期队列均值为正；
- 最大正目标贡献不超过 40%；目标级最大回撤中位数高于 -15%，最差高于 -30%。

evaluation 使用相同门并要求 2024 为正；confirmation 要求 2025 和 2026H1 各自为正。只有三段全部 PASS 才是 `SUPPORTS_WITHIN_SCOPE` 并生成框架无关 handoff。

若样本和质量可判断而 base 或 stress 非正，结论为 `DOES_NOT_SUPPORT`；经济结果为正但统计、稳健、广度、风险或独立时间门不足为 `INSUFFICIENT_EVIDENCE`；可靠输入或实现无法判断才用 `CANNOT_DETERMINE`。任一阶段失败立即封闭后段，不改名单、方向、lookback、rank、月份、金额、成本、funding 或门槛来挽救。

## 未覆盖事实

论文使用 spot 和多腿 low-minus-high，当前研究使用单腿 perpetual；这会引入 funding、合约规则和绝对市场 beta。固定当前幸存目标缺少退市币和动态上市历史。日线 open、公开 mark 与成本带不表达真实 order book、队列、部分成交、最小订单、保证金、强平/ADL、人工延迟和场所故障。即使通过，仍需产品所有者另开 NautilusTrader 资格验证任务；本研究不修改产品或交易状态。
