# 预注册：两周风险调整动量的周频单腿 one-shot 转换

## 基准、缺口与主张

- 开题基准提交：`0bdfeffa616260cebd2d2188ddc8deb9e85c77f4`。
- 正式策略背景：`ONE_SHOT_DONCHIAN_ATR_BREAKOUT 1.0.1 / BTCUSDT-PERP`；不复制或修改其实现，也不把研究代理称为正式策略重演。
- 主要研究类型：`STRATEGY_CANDIDATE`；最强预期主张是“可供产品资格验证考虑”，不是 Alpha 证明、资金许可或长期盈利保证。
- 当前缺口：累计动量、MAX、类别动量、UP–UP winner 和 CTREND 已经失败或证据不足，但尚未直接检验原始 crypto factor 文献定义的短期风险调整动量。它用收益/波动比排序，可能减轻 raw momentum 的高 beta、高波与集中；也可能只是低波或同一动量的伪装。
- 可证伪问题：固定 `RMOM2 / top quintile / 0.5x LONG / 7d` 是否在个人零售成本和 funding 后，为当前固定目标提供稳定、分散、显著优于 `MOM14`、`LOWVOL14`、定时做多和等权市场的净结果？若 stress 不正、置信下界不正、不能优于 raw momentum/low-vol、集中或相邻窗口不稳，即不支持。

## 开题前候选与取舍

| 候选 | 未解决差异 | 数据/现实成本 | 项目价值与取舍 |
|---|---|---|---|
| 两周风险调整动量 `RMOM2` | 直接以日收益均值/波动排序；不是累计收益换窗 | 只需日线、funding、mark；周频、单腿 | **选中**：原始 crypto 因子研究直接定义，近期因子压缩仍保留相关短期因子；可快速证伪且可关闭剩余横截面动量近邻 |
| 趋势内回撤续涨 | 条件反转而非突破 | 定义与止损高度可调，缺少足够强的 crypto 原始方法 | 淘汰：搜索自由度高，容易事后解释 |
| 新上市永续做空 | 上市后注意力与供给压力 | 历史盘口、下架、极端跳空和强平风险主导 | 淘汰：不符合当前低维护、较低尾部风险优先级 |
| PAXG 风险开关 | 跨资产风险状态 | 多输入、token wrapper，永续仅自 2025-03 | 暂缓：历史过短，且主要是 beta 配置而非独立 Alpha |

选中后不从 `RMOM1/3`、top3 或任何基准中改选赢家。若本题失败，基础 OHLCV 横截面动量家族按当前项目优先级关闭，除非出现真正新数据、独立机制或新的未见时间证据。

## 已暴露数据与顺序边界

- 25 个目标的 2023 日线、funding 和 mark 已被 Q13/Q14 及更早问题读取；2024–2026 的同市场路径也在其他机制问题中出现。因此本题不能声称原始价格路径对项目完全未见。
- 在本检查点前，Halpha 没有计算、排序或人工查看这 25 个目标的 `RMOM2` 计划结果。后段只能称“固定方法输出的顺序时间证据”，不能称全项目从未看过市场路径。
- development 固定 `[2023-01-02, 2024-01-01)`；仅开发门 PASS 才允许实现并打开 2024 evaluation，再仅评价 PASS 才允许打开 2025–2026H1 confirmation。
- 如果全部历史门通过，进入核心资格验证仍应把既有市场路径暴露列为限制；项目所有者可以要求检查点后的 forward shadow 作为更强证据。任何结果都不授权产品或真实交易动作。

## 固定对象、信号和计划

- 目标固定为：`1000XECUSDT,AAVEUSDT,AVAXUSDT,BCHUSDT,BNBUSDT,CRVUSDT,DASHUSDT,ENSUSDT,ETCUSDT,HBARUSDT,KAVAUSDT,LINKUSDT,LTCUSDT,NEARUSDT,RUNEUSDT,SNXUSDT,SOLUSDT,TRXUSDT,UNIUSDT,VETUSDT,XLMUSDT,XMRUSDT,XRPUSDT,ZECUSDT,ZILUSDT`。
- 这是 2026 当前幸存且当前活动名单，不是历史 point-in-time universe；结论不得推广到退市币或全市场。
- 完整 UTC 日收益 `r_t = close_t / close_{t-1} - 1`。周日收盘后计算最近 14 个完整日收益的 `RMOM2 = mean(r) / sample_std(r)`；风险自由收益固定为零，年化缩放不影响横截面排名。标准差非正、输入缺失或非有限时不行动。
- 过去 30 日 quote volume 中位数至少 10m USDT，且同周至少 20 个目标可排名。按 RMOM2 降序、symbol 升序破同值，顶部 `ceil(N/5)` 触发。
- 下一可行动时间是周一 UTC open；固定 `0.5x LONG`，七天后下周一 open 退出。退出后至少一个完整 UTC 日才能重新激活，所以同一目标不能连续周持有。
- funding 仅计 `entry_time < funding_time <= exit_time` 的 settled event。任何 event 缺 mark 时整笔排除且仍占冷却期；不插值、不按零、不以成交价替代。
- 输入缺失、不连续、数值无效、活动不足、可排名对象不足、持仓中或冷却中时输出零个提议。

## 唯一主配置、诊断和总搜索

唯一可选择主配置：`RMOM14 / top quintile / hold7d / 0.5x LONG`。

不可选择诊断：

1. `RMOM7 / top quintile`；
2. `RMOM21 / top quintile`；
3. `RMOM14 / top3`；
4. `MOM14 / top quintile`；
5. `LOWVOL14 / top quintile`；
6. `SCHEDULED_LONG`；
7. 同周无冷却等权市场。

实际 selectable primary configurations = 1；实际计算列 = 8。诊断只用于否证，不形成新的候选。主规则与 `MOM14` 的周横截面 Spearman 相关必须报告，以判断是否只是同一排序。

## 成本、统计和 development 门

- favorable：每边 taker fee 6 bp，额外 spread/slippage 0；实际 funding。
- base：每边 fee 6 bp + spread/slippage 10 bp；实际 funding。
- stress：每边 fee 6 bp + spread/slippage 20 bp；正 funding 支出乘 1.5，负 funding 收益只保留 0.5。
- 每个七日计划按全计划资本扣除 `4% × 7 / 365` 门槛；不能只对 0.5x 名义腿降低门槛。
- 同一 entry date 并发目标等权聚合；四个周日期循环 block、5,000 次 bootstrap。VectorBT `Portfolio.from_orders` 重演固定两单并与手工现金流逐笔核对，funding 显式补充。

development PASS 必须全部满足：

- 数据身份、连续性和 VectorBT/手工核对通过；
- 至少 150 笔、20 个目标、45 个 entry dates；缺 mark 排除机会比例不超过 2%；
- base 和 stress 扣资本门均值均正，stress block-bootstrap 95% 下界大于零；两个时间半段 base 均正；
- base date-portfolio 最大回撤高于 -20%，最差目标高于 -40%；
- base 分别高于 `MOM14`、`LOWVOL14`、`SCHEDULED_LONG`；gross 相对同周等权市场为正且 bootstrap 下界大于零；
- 三个邻域中至少两个 stress 非负；至少一半实际入选目标、至少四个类别 base 正；最大正 PnL 目标贡献不超过 20%；
- 逐笔 VectorBT/手工误差不超过 `1e-10`。

若 base 或 stress 不正，或 RMOM2 不优于 `MOM14`，结论为 `DOES_NOT_SUPPORT`；经济结果为正但统计、广度、独立时间、稳健或风险门不足为 `INSUFFICIENT_EVIDENCE`；输入或实现身份无法判断才是 `CANNOT_DETERMINE`。只有顺序后段全部通过才可能是 `SUPPORTS_WITHIN_SCOPE`，且仍不证明未来 Alpha。

## 失效条件与未覆盖事实

- 原论文使用 CoinMarketCap 广泛币种、市值权重与 long-short；本题是当前幸存 Binance 永续、成交额活动门、固定单目标和 long-only，不能直接移植论文收益。
- RMOM2 可能主要奖励低波而非收益持续；若 `LOWVOL14` 相同或更好，独立机制失败。
- 当前名单缺少退市和微盘对象；原因子可能依赖 size、流动性或 short leg。
- 日线代理不能表达历史盘口、队列、部分成交、最小订单、保证金、强平/ADL、用户激活延迟和场所故障。
- 同市场历史路径已被其他问题查看；本题通过也必须降低独立性表述，禁止宣称长期必然盈利。
