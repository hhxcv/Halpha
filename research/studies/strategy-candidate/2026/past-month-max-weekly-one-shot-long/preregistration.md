# 预注册：过去一月 MAX 门控周频单腿 LONG

## 基准、产品缺口与证据边界

- 开题基准提交：`0bdfeffa616260cebd2d2188ddc8deb9e85c77f4`。
- 正式策略背景：`ONE_SHOT_DONCHIAN_ATR_BREAKOUT 1.0.1 / BTCUSDT-PERP`；不复制、修改或声称重演其历史绩效。
- 产品约束：工具、方向和交易金额由用户固定；候选只决定何时提出一次 LONG、受约束名义比例和明确退出。一次激活结束后不会自动重入。
- 本题开始前已暴露：多个累计 time-series/cross-sectional momentum、周频输家延续、类别动量、日级/小时级反转、BTC lead-lag、funding/carry 结果。尚未计算或人工查看“过去 28 日 MAX 横截面排名”的任何 Halpha 收益。
- development 使用 2022–2023；只有全部开发门通过才允许打开 2024，之后才允许打开 2025–2026H1。上一题已看过相同日线和 funding 字节，但本题 MAX 信号、交易选择和结果未看过；因此价格时期不是全新，方法输出和顺序后段仍可作为本题固定方法的独立时间证据。

## 候选筛选与选中理由

| 候选 | 未解决差异 | 可证伪性与经济幅度 | 维护/数据成本 | 取舍 |
|---|---|---|---|---|
| 过去一月 MAX 前列后的下一周 continuation | 单个极端日而非累计 momentum；外部周度高低组合原始差约 3.03% | 若流动永续中成本后不正或不优于累计/单日动量即否定 | 只需日线与 funding；周频 | **选中** |
| 日内 realized skewness/MAX 后次日 reversal | 5m 高阶矩/极端收益 | 原论文年化横截面幅度可能小于 32 bp 往返成本，且高换手 | 5m 全宇宙、日频换手 | 暂缓 |
| ML 日收益预测 | 非线性组合 momentum/technical/network/activity | 外部结果使用 41 币和大量特征；搜索与维护高，基础数据不完整 | 模型、特征与滚动再训练 | 淘汰 |
| 52 周高点 anchoring | 日线即可，2025 文献报告横截面关系 | 与现有突破/趋势族接近，暖启动和验证周期较长 | 低 | 淘汰 |
| bubble-conditioned MA/breakout | 文献含成本和 69 条规则 | 与正式 Donchian 及多项既有趋势研究高度重复 | 参数搜索大 | 查重停止 |

选中理由不是实现容易，而是：外部报告的周度幅度足以面对零售成本；定义单一；与累计 momentum 有明确基准差；当前 Binance 流动永续和 one-shot 适配仍未回答；若失败能关闭一个有强先验但可能只来自小币/旧时期的方向。

## 固定对象、信号与计划语义

- 公共信号/交易目标固定为 25 个当前 A1/A2、当前相对 spread 快照不高于 5 bp、长历史且 development funding 归档可用的 USD-M perpetual；名单与上一题相同并写入 checkpoint。当前幸存者与当前流动性筛选不冒充历史 point-in-time universe。
- 每个完整 UTC 日收益为 `close_t / close_{t-1} - 1`。决策只发生在完整 UTC 周日 close 后。
- 主特征 `MAX28_t` 为截至周日 `t` 的最近 28 个完整日收益中的最大值；不使用周一 open 或之后信息。
- 当天以目标过去 30 日 quote volume 中位数至少 10m USDT 筛出可排名对象；至少 20 个对象可用。按 `MAX28` 降序、symbol 升序破同值。用户固定目标只有排名 `<=3` 才触发。
- 下一可行动时间为周一 UTC open；入场名义固定为计划资本 `0.5x`，方向只允许 `LONG`；七天后的下周一 open 完整退出。
- 为表达 one-shot 重新激活，退出后至少一个完整日才可重新拥有新激活。因此同一目标不能连续两周交易；持仓中的周日信号不产生未来订单。
- funding 只计严格满足 `entry_time < funding_time < exit_time` 的 settled event。缺失 mark 的持仓整笔排除，但仍占用原计划时段；单目标缺失事件率最多 0.5%，主规则排除交易比例最多 2%。不插值、不按零、不用成交价替代。
- 输入缺失、不连续、非正、排名对象不足、成交额不足、计划已持仓或仍在重新激活冷却期时不行动。

## 搜索披露、基准与固定诊断

主配置只有一个：`MAX28 / top3 / hold7d / 0.5x LONG`。

以下只作反证，不参与选主配置：

1. `MAX21 / top3`；
2. `MAX35 / top3`；
3. `MAX28 / top5`；
4. `MOM28 / top3`：按 28 日累计收益排名；
5. `LAST1 / top3`：按上一日收益排名；
6. `SCHEDULED_LONG`：每个合格目标按同一周频/one-shot 时序无条件 LONG。

实际 selectable primary configurations = 1；三个参数邻域与三个简单解释不能被事后改选为新主策略。完整交易 CSV 和全部诊断结果必须保存。

## 成本、统计与顺序门

- favorable：每边 taker fee 6 bp，额外 spread/slippage 0；实际 funding。
- base：每边 fee 6 bp + spread/slippage 10 bp；实际 funding。
- stress：每边 fee 6 bp + spread/slippage 20 bp；正 funding 支出乘 1.5，负 funding 收益只留 0.5。
- 每笔按七日持有将 4% 年化全计划资本门折算后扣除。0.5x 未投入部分仍属于用户固定计划资本，不能只对名义腿降低资本门。
- 同一 entry date 的并发目标先等权聚合为日期队列；用四个 entry-date 的 circular block、5,000 次 bootstrap 描述均值区间，保留 28 日特征重叠。
- VectorBT `1.1.0` 用 `Portfolio.from_orders` 重演每笔固定两单，并与手工公式逐笔核对；funding 是显式补充现金流。它不代表真实盘口、保证金或 NautilusTrader 事件语义。

development PASS 必须全部满足：

- 数据质量、manifest、VectorBT/手工核对通过；
- 主规则至少 150 笔、20 个目标、40 个 entry dates；排除缺失 funding mark 的比例不超过 2%；
- base 与 stress 日期队列扣门槛均值都为正，stress block-bootstrap 95% 下界大于零；
- 2022、2023 base 日期队列均值分别为正；
- 至少一半有不少于五笔的目标 base 均值为正，至少四个当前类别为正；
- 主规则 base 分别高于 `MOM28`、`LAST1` 和 `SCHEDULED_LONG`；
- 三个参数邻域至少两个 stress 日期队列均值为正；
- 最大正收益目标贡献不超过 20%；目标级最大回撤中位数高于 -20%，最差高于 -40%。

evaluation/confirmation 使用同一门；evaluation 最低样本为 75 笔、15 个目标、20 个 entry dates，confirmation 最低样本为 100 笔、15 个目标、30 个 entry dates。evaluation 要求 2024 为正；confirmation 要求 2025 和 2026H1 分别为正。只有三段全部 PASS 才为 `SUPPORTS_WITHIN_SCOPE` 并生成框架无关 handoff。

若样本/质量可判断且 base 或 stress 不正，结论为 `DOES_NOT_SUPPORT`；经济结果为正但稳健性、广度、独立时间或排除门不足为 `INSUFFICIENT_EVIDENCE`；可靠输入或实现无法判断才为 `CANNOT_DETERMINE`。正回测从不证明未来 Alpha 或长期必然盈利。

## 失效条件与未覆盖事实

- 外部 MAX 结果可能依赖广泛小币、2014–2020 市场结构和 value-weighted portfolio，而非当前流动永续。
- 周度 MAX continuation 与日内 MAX 次日 reversal 方向相反；若结果随 21/28/35 日或 top3/top5 翻转，即不稳定。
- funding、spot/perp basis、历史 spread/depth、队列、部分成交、最小订单、保证金、强平/ADL、用户重新激活延迟和场所故障没有被日线回测完整表达。
- 当前分类只作结果广度，不参与信号；退市币和历史不可交易对象缺失造成幸存者偏差。
- 通过研究也只释放候选资格验证，不修改正式策略、产品代码、L4、资金或真实账户。
