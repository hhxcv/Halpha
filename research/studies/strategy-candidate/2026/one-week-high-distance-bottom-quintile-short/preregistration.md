# 预注册：一周高点距离底部五分位单腿 SHORT

## 基准、问题来源与主张边界

- 开题基准提交：`0bdfeffa616260cebd2d2188ddc8deb9e85c77f4`。
- 正式策略背景：`ONE_SHOT_DONCHIAN_ATR_BREAKOUT 1.0.1 / BTCUSDT-PERP`；不复制或修改其实现，也不把本题称为正式策略重演。
- 主要研究类型：`STRATEGY_CANDIDATE`。最强允许结论是“可供交易核心资格验证考虑”，不是 Alpha 证明、资金许可或长期盈利保证。
- 外部主问题来自 Fičura（2023，2024 修订）的 high-momentum 定义：`hmom(t,h)=ln(C_t/H_t,h)`，其中 `C_t` 是周末收盘，`H_t,h` 是过去 h 周最高盘中价。论文的大且流动币 `HMOM1W` Q1 下一周原始均值为 `-0.70%`，BTC/三因子 alpha 为 `-1.95%/-1.79%`，且只有 Q1 负 alpha 显著；这直接支持把“做空离周高最远的流动币”作为可证伪问题，而不是事后改写普通动量。
- 论文使用多场所聚合现货、point-in-time 市值/成交量和分位组合。本题使用当前幸存 Binance 永续、单场所成交额门、固定目标、单腿 SHORT、实际 funding 和 one-shot 冷却；二者 estimand 不同。

## 开题前候选与取舍

| 候选 | 当前未解决差异 | 数据与执行 | 取舍 |
|---|---|---|---|
| `HMOM7` 底部五分位 SHORT | 最近周内高点到周末收盘的路径信息；论文称优于普通周动量，且 Q1 负 alpha 显著 | 日线 OHLCV、funding；周频单腿 | **选中**：论文定义清楚、经济幅度足以面对成本、适配半自动计划并可快速证伪 |
| 资金费率结算后分钟级反转 | funding/basis 机制 | 一天多次准点、分钟级冲击和成本 | 淘汰：与既有 funding 研究重叠，且不适合当前人工计划节奏；原始证据主要支持两腿 basis 收敛而非单腿方向 |
| cointegration/pairs | 隔离部分市场 beta | 两腿同步、模型漂移、双 funding | 暂缓：当前单工具/方向计划不能直接交付 |
| tokenized 股票/贵金属偏离 | 非 crypto 风险源 | 历史短、参考市场时段与 wrapper 差异 | 暂缓：无法快速形成长期证据 |
| 新上市做空 | 供给与注意力 | 极端尾部、下架、point-in-time 名单 | 淘汰：不符合个人低风险和可维护优先级 |

选择依据是项目决策价值与可否证性，不是新颖或容易实现。若 `HMOM7` 不优于普通 `MOM7` 输家、无条件 SHORT 或市场 short，不能以变更窗口、币名单或 bottom 数量救回。

## 已暴露数据与顺序边界

- 同一批 25 个目标的 2023 市场路径已被其他问题读取；本题不能声称价格路径对项目完全未见。
- checkpoint 前没有计算、排序或人工查看这 25 个目标的 `HMOM7` 底部五分位 SHORT 结果。论文样本截至 2022-12，因此 2023 development 是论文结束后的时间，但不是全项目从未看过的市场历史。
- development 固定 `[2023-01-02, 2024-01-01)`。只有全部门通过，才能另加不可变 amendment 并打开 2024 evaluation；再通过才允许 2025–2026H1 confirmation。
- 全部历史门通过仍须披露当前幸存者偏差与项目级路径暴露；项目所有者可要求 checkpoint 后自然形成的 forward shadow 才进入实盘前判断。

## 固定对象、信号与计划

- 目标固定为：`1000XECUSDT,AAVEUSDT,AVAXUSDT,BCHUSDT,BNBUSDT,CRVUSDT,DASHUSDT,ENSUSDT,ETCUSDT,HBARUSDT,KAVAUSDT,LINKUSDT,LTCUSDT,NEARUSDT,RUNEUSDT,SNXUSDT,SOLUSDT,TRXUSDT,UNIUSDT,VETUSDT,XLMUSDT,XMRUSDT,XRPUSDT,ZECUSDT,ZILUSDT`。
- 这是 2026 当前幸存、当前活动且长历史名单，不是历史 point-in-time 全市场；不包含退市币，不能推广到微盘或全部永续。
- 每个周一 UTC open 前，以刚结束的周日为决策日。主信号为最近七个完整 UTC 日（周一至周日）`HMOM7 = ln(close_sun / max(high_mon...high_sun))`。它非正；越负表示周末收盘离周内最高盘中价越远。
- 过去 30 日 quote volume 中位数至少 `10m USDT/day`，同周至少 20 个目标可排名。按 `HMOM7` 升序、symbol 升序破同值，底部 `ceil(N/5)` 触发。
- 下一可行动时间为周一 UTC open；固定 `0.5x SHORT`，七天后下周一 open 全平。退出后至少一个完整 UTC 日才可重新激活，因此同一目标不能连续两周交易。
- funding 仅计 `entry_time < funding_time <= exit_time` 的 settled event。正 rate 为 SHORT 收益、负 rate 为支出；任何 event 缺 mark 时整笔排除且仍占冷却期，不插值、不按零、不以成交价替代。
- 缺少连续 OHLCV、非正价格、成交额门失败、可排名对象不足、持仓中或冷却中时不提出计划。

## 唯一主配置、诊断与总搜索

唯一可选择主配置：`HMOM7 / bottom quintile / hold7d / 0.5x SHORT`。

不可选择诊断：

1. `HMOM14 / bottom quintile`；
2. `HMOM28 / bottom quintile`；
3. `HMOM7 / bottom3`；
4. `MOM7 / bottom quintile`，普通前周累计收益输家；
5. `SCHEDULED_SHORT`，相同时序下所有合格固定目标；
6. `MARKET_SHORT`，同周所有合格目标、无 one-shot 冷却的等权市场 short。

实际 selectable primary configurations = 1；实际计算列 = 7。诊断只反证，不得事后晋升。报告 `HMOM7` 与 `MOM7` 的周横截面 Spearman 相关，确认是否有独立排序信息。

## 成本、统计与 development 门

- favorable：每边 taker fee `6 bp`，额外 spread/slippage `0`；实际 funding。
- base：每边 fee `6 bp` + spread/slippage `10 bp`；实际 funding。
- stress：每边 fee `6 bp` + spread/slippage `20 bp`；正 funding 收益只保留 `0.5`，负 funding 支出放大 `1.5`。
- 每个七日计划按全计划资本扣 `4% × 7/365` 门槛，不能只对 0.5x 名义腿降低资本门。
- 同一 entry date 的并发目标等权聚合；四周循环 block、5,000 次 bootstrap。VectorBT 固定两单 SHORT 与独立手工现金流逐笔核对，funding 显式补充。

development PASS 必须全部满足：

- 数据身份、连续性与 VectorBT/手工核对通过；
- 至少 150 笔、20 个目标、45 个 entry dates；缺 mark 排除机会不超过 2%；
- base 和 stress 扣资本门均值为正，stress block-bootstrap 95% 下界大于零；2023 前后半段 base 均正；
- base 日期组合最大回撤高于 -20%，最差目标高于 -40%；
- base 高于 `MOM7` 和 `SCHEDULED_SHORT`；主规则 gross short 相对同周等权 `MARKET_SHORT` 为正且 bootstrap 下界大于零；
- `HMOM14`、`HMOM28`、bottom3 三个邻域至少两个 stress 非负；
- 至少一半实际入选目标、至少四个当前类别 base 为正；最大正 PnL 目标贡献不超过 20%；
- VectorBT/手工最大误差不超过 `1e-10`。

若 base/stress 不正，或不优于普通 `MOM7`，结论为 `DOES_NOT_SUPPORT`；经济结果为正但统计、基准、稳健、广度、风险或独立时间不足为 `INSUFFICIENT_EVIDENCE`；输入/实现身份无法判断才为 `CANNOT_DETERMINE`。只有顺序三阶段全部通过才可能为 `SUPPORTS_WITHIN_SCOPE`，仍不证明未来 Alpha。

## 失效条件与未覆盖事实

- 效应可能来自论文的 point-in-time 大市值筛选、市值加权、多场所价格和 2017–2022 市场结构；当前幸存 Binance 名单可能丢失关键横截面。
- SHORT 有 squeeze、保证金、强平和 ADL 尾部；日线无法重放真实盘口、队列、部分成交、盘中爆仓、最小订单、人工激活延迟和场所故障。
- 论文 Q1 原始均值不显著，显著的是风险调整 alpha；单腿绝对收益若依赖全市场方向，就不能称为稳定 Alpha。
- `HMOM7` 与正式 Donchian 同属价格高点信息家族，但方向、截面排名、时间尺度和一次性计划不同。若不能胜过普通周输家和市场 short，就没有新增项目价值。

