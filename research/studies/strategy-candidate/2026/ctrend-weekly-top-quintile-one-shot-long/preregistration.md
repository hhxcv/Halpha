# 预注册：CTREND 周频顶部五分位单腿 LONG

## 基准、问题来源与证据边界

- 开题基准提交：`0bdfeffa616260cebd2d2188ddc8deb9e85c77f4`。
- 正式比较背景：`ONE_SHOT_DONCHIAN_ATR_BREAKOUT 1.0.1 / BTCUSDT-PERP`；本题不修改、复现或替代正式策略。
- 外部主假设来自 Fieberg、Liedtke、Poddig、Walker 与 Zaremba 的 *A Trend Factor for the Cross-Section of Cryptocurrency Returns*。原研究用 2015–2022 年 3,000 多币、28 个价格/成交量/波动技术信号、52 周滚动 CS-C-ENet，报告顶部组合与 long-short 组合在大币、流动币、较高成本和最长四周持有下仍有显著收益。
- 原研究是多币、按市值加权、现货聚合数据和 long-short 因子证据；本题是当前幸存 Binance 永续、成交额代理权重、用户固定单目标、单腿 LONG、实际 funding、零售 one-shot 计划。二者不是同一个 estimand，不能把论文收益复制为 Halpha Alpha 证明。
- 论文样本截至 2022-05。本题开发期为 2023，属于论文后的时间段；但 Halpha 其他研究已经看过部分相同市场路径。精确 CTREND 模型、排名和收益在 checkpoint 前未计算或人工查看，因此是方法固定后的新输出，不是完全未知的市场历史。

## 候选筛选与选中理由

| 候选 | 项目未解决差异 | 可证伪性/数据 | 现实与研究成本 | 取舍 |
|---|---|---|---|---|
| 28 信号 CTREND 顶部五分位单腿 LONG | 聚合价格、成交量和波动信号，检验是否超越简单动量与 Donchian 近邻 | 日线 OHLCV；周频；论文给出完整模型与强基准 | 中等模型复杂度，低执行频率 | **选中** |
| 异常成交量后次日 SHORT | 分歧/乐观者定价 | 日线成交量，易验证 | 原论文明确称可做空后效应消失；永续机制不匹配 | 淘汰 |
| 日历/星期/时段 LONG | 固定时间流 | 日线可验证 | 近期约 500 币复核未发现稳健收益季节性 | 淘汰 |
| 8–10 周中盘高波反转 | 流动性提供/长期过度反应 | 低换手 | 原研究是 70–500 币 long-short、高波中盘；单腿转换慢且偏离低风险对象 | 暂缓 |
| salience 低估币 LONG | 行为偏差 | 日线可算 | 已有研究称效应主要在微盘/套利受限币，不适合当前个人低风险名单 | 淘汰 |
| 52 周高点 anchoring | 锚定不足反应 | 日线可算 | 与正式突破趋势族高度重合，且需更长暖启动 | 查重暂缓 |

选择不是因为模型新颖或指标漂亮，而是：外部效应在大而流动对象中仍有报告；只需基础公开数据；执行为周频单腿；有清楚的简单动量、单均线和市场基准；若失败可以关闭“把更多技术指标组合起来就能修复简单动量”的高诱惑方向。

## 固定对象、数据和时间顺序

- 固定对象是当前 universe 快照中 25 个长历史、当前相对低 spread 的 A1/A2 Binance USD-M perpetual：`1000XEC,AAVE,AVAX,BCH,BNB,CRV,DASH,ENS,ETC,HBAR,KAVA,LINK,LTC,NEAR,RUNE,SNX,SOL,TRX,UNI,VET,XLM,XMR,XRP,ZEC,ZIL` 的 `USDT` 合约。
- 当前幸存者名单不是历史 point-in-time 全市场，不能推断退市币或 2023 当时全部可交易币；分类只用于结果广度，不进入信号。
- 复用 `category-momentum-gated-one-shot-long` 的 2021-11-17 至 2024-01-02 Binance 公共日线，以及 2022–2023 官方 funding/mark 归档；为 200 日最长指标补取 2020-06-01 至 2021-11-17 的 Binance 公共 REST 日线。所有源文件逐项 SHA-256，新增大数据只留 Git 外。
- development：入场 `[2023-01-02, 2024-01-01)`；只有全部门通过才允许下载/打开 evaluation `[2024-01-01, 2025-01-01)`；之后才允许 confirmation `[2025-01-01, 2026-07-01)`。
- 每个周一 `00:00 UTC` open 是唯一入场时点。信号只使用刚结束的周日及更早完整日线；未来一周收益绝不进入当周训练或排名。

## 固定 28 个信号与滚动模型

信号按原论文附录的标准定义：

1. 动量振荡器：`rsi14, stoch_rsi14, stoch_k14, stoch_d3, cci20`；
2. 价格趋势：收盘价归一化 `sma_3/5/10/20/50/100/200`，以及论文平滑参数 `alpha=1/(1+L)` 的 `macd12_26` 与 `macd_diff9`；
3. 成交量趋势：当前 quote volume 归一化 `volsma_3/5/10/20/50/100/200`、`volmacd12_26`、`volmacd_diff9`、`chaikin21`；
4. 波动：`boll_low20, boll_mid20, boll_high20, boll_width20`。

每周对每个指标在当周合格对象间做平均秩，映射到 `[-0.5,0.5]`。合格对象须有完整 200 日暖启动、过去 30 日 quote volume 中位数不低于 10m USDT；每周至少 20 个对象。

主模型固定为：

- 最近 52 个已经完整实现下一周收益的周截面；
- 每个指标逐周做带权横截面一元回归，权重为当时 30 日中位 quote volume 在周内 5%–95% 截尾后的归一值；52 周系数等权平均，形成 28 个单变量收益预测；
- 在相同 52 周的 pooled 预测上拟合 `l1_ratio=0.5` elastic net；`alpha` 在固定 `10^-6` 至 `10^-1` 的 41 点对数网格，以带权 AICc 最小化选择；
- 只保留 elastic-net 系数严格为正的单变量预测，再等权平均为 CTREND。没有正系数、训练不足、数值不收敛或任一必需输入未知时不行动。

这是对论文 CS-C-ENet 的可重演 Halpha 转换。关键差异是没有历史市值，使用可执行成交额作为 WLS 经济权重；因此必须称为“paper-guided conversion”，不是精确论文复现。

## 固定计划语义

- 主配置：`52w CS-C-ENet / top quintile / 0.5x LONG / hold 7d`。
- 对用户固定的单一目标，只有当其 CTREND 在当周合格对象中位于顶部 `ceil(N/5)` 才激活；排行按预测降序、symbol 升序破同值。
- 下一周一 open 以全计划资本 `0.5x` 名义 LONG，下一周一 open 全部退出。持仓中的新信号不下未来订单；退出后至少一个完整 UTC 日才能重新激活，因此同一目标不能连续两周交易。
- 研究为覆盖所有可能用户固定目标而并列回放 25 个独立计划；同一 entry date 先等权聚合，绝不把五个同时入选目标误称为一个用户同时部署 `2.5x`。
- funding 只计 `entry < funding_time <= exit` 的已结算事件；mark 缺失整笔排除且仍占冷却期。任何非连续日线、非正价格、成交额门失败、模型失败、排名数不足均不行动。

## 成本、比较与不可选择诊断

- favorable：每边 6 bp taker fee，0 spread/slippage，实际 funding。
- base：每边 6 bp fee + 10 bp spread/slippage，实际 funding。
- stress：每边 6 bp fee + 20 bp spread/slippage；正 funding 支出乘 1.5，负 funding 收益只留 0.5。
- 每笔按七日持有扣除 `4% * 7/365` 的全计划资本门槛；未投入的一半资本不降低门槛。
- 主结果以 entry-date 队列做四周 circular block bootstrap 5,000 次；VectorBT `Portfolio.from_orders` 与独立手工现金流逐笔核对。
- 同周简单基准：顶部五分位 `MOM21`、`close/SMA20`、无条件固定目标周度 LONG；另比较同周全部合格对象等权市场的 gross 与相同成本 LONG。
- 不可选择稳健性：训练窗 26/78 周、排除成交量指标、elastic net 不筛选而等权全部 28 个单变量预测。它们只反证主配置，不能事后晋升。

实际 selectable primary configurations = 1。所有诊断交易、模型选择和失败必须保留。

## development 通过门

全部满足才 PASS：

- 数据质量、manifest、时间顺序、VectorBT/手工核对通过；模型失败周不超过 5%；
- 主配置至少 150 笔、20 个目标、45 个 entry dates；因 funding mark 缺失排除不超过计划机会的 2%；
- base 与 stress 的 entry-date 扣门槛均值为正，stress 95% 四周 block-bootstrap 下界大于 0；
- 2023H1 与 2023H2 base 扣门槛均值分别为正；date-portfolio base 最大回撤高于 -20%，目标级最差最大回撤高于 -45%；
- 主配置 base 高于 `MOM21`、`close/SMA20`、`SCHEDULED_LONG`；主配置 gross 相对同周等权市场为正且其 95% block-bootstrap 下界大于 0；
- 26/78 周和无成交量三个邻域中至少两个 stress 扣门槛均值非负；等权全部预测不能显示主结论只靠 AICc 网格偶然选择；
- 有至少五笔的目标中至少一半 base 均值为正、至少四个当前类别为正；最大正贡献目标不超过全部正贡献的 20%；
- 每周入选指标中位数至少 5，避免单一隐藏指标冒充“聚合趋势”。

evaluation/confirmation 使用同一冻结规则和相称的样本、分期、成本、基准与风险门。只有三段全部 PASS 才能得出 `SUPPORTS_WITHIN_SCOPE` 并生成框架无关 handoff；这仍只表示候选资格，不保证长期盈利，不自动修改核心、L4、资金或真实账户。

如果 base 或 stress 明确不正则 `DOES_NOT_SUPPORT`；经济结果为正但统计、基准、稳健性、广度、风险或独立时间不足则 `INSUFFICIENT_EVIDENCE`；只有输入/实现无法可靠判断才 `CANNOT_DETERMINE`。

## 失效条件与未覆盖差异

- 论文收益可能来自多币 long-short、现货全市场、市值权重和 2015–2022 的市场结构；单腿固定目标可能只有市场 beta。
- CTREND 与动量高度相关；如果不能持续战胜 MOM21、SMA20、同周市场或正式趋势族的合理代理，就没有独立项目价值。
- 当前名单、分类和 spread 是 2026 快照，存在幸存者偏差；缺少历史退市币和 point-in-time 市值。
- quote volume WLS 不是市场资本权重；Binance 单场所成交量可能受衍生品结构和异常交易影响。
- 日线代理不能表达历史盘口、队列、部分成交、保证金、强平/ADL、人工重激活延迟和场所故障。
- 模型训练与 AICc 是固定但复杂的第三方统计能力；任何数值不稳定、版本变化或选择集中都必须降低结论。
