# 预注册：MOM70 底部 30% 一周 one-shot LONG

## 唯一主假设

`H1`：对 owner 已固定的一个目标，当且仅当它在完整周日收盘后的 70 日收益处于当周合格横截面的底部 30%，下一周一以计划资金 `0.25x` 做多并持有 7 日，其条件日期组合在零售 base/stress 成本与 4% 全计划资金年化门槛后仍为正，并胜过同资格无筛选做多及等权市场收益；该结果能在未用于开发的 2024、2025 时间段复现。

否定条件不是“回测亏损”一个数字，而是以下任一核心经济条件：现实压力净收益不为正；不胜过简单做多/市场；邻域不稳；结果只由少数币或单一阶段推动；风险越界；关键输入缺失；或顺序留出证据失败。

## 冻结身份与时间顺序

- strategy id：`RESEARCH_MOM70_BOTTOM30_WEEKLY_ONE_SHOT_LONG_0P25X_V1`
- direction：只允许 `LONG`；owner 指定方向不是 LONG 时 `NO_ACTION`。
- 目标名单与分类：固定使用当前 `research/market-universe/universe.csv` 中预注册的 25 个 USD-M 永续目标及其分类；checkpoint 绑定其 SHA-256。
- 决策：每个 UTC 周日 1d bar 完成后；`MOM70 = close[t] / close[t-70d] - 1`。
- 资格：30 日 quote volume 中位数 `>= 10,000,000 USDT`；MOM70 与价格完整；横截面至少 20 个目标。
- 排序：按 `MOM70` 从低到高、symbol 字典序打破并列；底部数量 `ceil(0.30 * N)`。
- 入场：紧随其后的 UTC 周一开盘代理；`0.25 * owner 已批准计划金额`，不加仓。
- 退出：入场后 7 个完整日的下一个 UTC 周一开盘代理。
- cooldown：退出后必须经过一个完整 UTC 日；因此同一目标不能连续两周入场。
- protection：0.25x 名义上限、单仓、不加仓、7 日强制退出和 cooldown；无盘中价格止损。未来若加入止损，视为新经济规则。
- unknown/no-action：目标不在冻结名单、目标或横截面数据缺失/过期、可排名少于 20、目标不在底部 30%、资金/方向不一致、执行边界不可判定时均不动作。

日线的 `t` 行代表该 UTC 日完整 K 线；研究在该行收盘之后才形成信号，交易价格用下一行周一 `open`。不得使用周内 high/low 形成信号或优化止损。

## 固定目标

`1000XECUSDT, AAVEUSDT, AVAXUSDT, BCHUSDT, BNBUSDT, CRVUSDT, DASHUSDT, ENSUSDT, ETCUSDT, HBARUSDT, KAVAUSDT, LINKUSDT, LTCUSDT, NEARUSDT, RUNEUSDT, SNXUSDT, SOLUSDT, TRXUSDT, UNIUSDT, VETUSDT, XLMUSDT, XMRUSDT, XRPUSDT, ZECUSDT, ZILUSDT`

这是 current-survivor 固定名单，不得描述为历史时点完整市场。研究的交易样本是“若 owner 当时固定该目标、且资格规则触发”的条件机会；日期组合等权平均用于处理同周相关性，不表示多目标同时配置。

## 成本、收益和统计单位

- favorable：每边 fee 6 bp，slippage 0 bp，真实 funding。
- base：每边 fee 6 bp，slippage 10 bp，真实 funding。
- stress：每边 fee 6 bp，slippage 20 bp；正 funding（LONG 成本）乘 1.5，负 funding（LONG 收益）乘 0.5。
- funding 事件窗口：`entry < fundingTime <= exit`；缺 mark 不插值，整笔机会排除并计入 2% 上限。
- hurdle：每个 7 日日期组合扣除 `4% * 7 / 365` 的全计划资金机会成本；不是仅对 0.25x 已用名义资金扣除。
- 主统计单位：同一 entry date 内交易净收益等权平均；避免把同周高度相关的币当独立样本。
- 区间：4 周 circular block bootstrap，5,000 次，固定 seed `20260722`。
- drawdown：日期组合复合路径；还报告每目标条件交易路径。
- VectorBT `Portfolio.from_orders` 计算价格/fee/slippage 收益，逐笔手工公式必须在 `1e-10` 内一致；funding 另以事件现金流加入。

## 不可升级的诊断列

- `mom56`：8 周输家，底部 30%。
- `mom84`：12 周输家，底部 30%。
- `bottom20`：主 MOM70，但底部 20%。
- `mom7`：1 周输家，底部 30%；检验是否只是已经失败的短期反转。
- `winner70`：10 周赢家，顶部 30%；分解论文所说的输家长腿。
- `scheduled_long`：同一目标资格和 cooldown，但不做横截面筛选。
- `market_long`：所有合格目标每周 LONG，不做 cooldown；只用于市场 gross 基准。

无论诊断结果多好，均不得在本题中取代主规则。要研究诊断规则必须另开新问题和时间锚。

## 阶段与门槛

共同硬门：数据质量 `PASS`；缺 mark 或整段 funding 缺失的排除合计不超过 2%；VectorBT/手工差 `<=1e-10`；至少 20 个有交易目标；base 与 stress 扣 hurdle 日期均值均 `>0`；base 两个半段均 `>0`；base 日期组合 MDD `>-15%`；最差单目标 MDD `>-30%`；base 胜过 `mom7`、`winner70` 和 `scheduled_long`；gross 胜过等权市场；至少 2/3 邻域（56d、84d、bottom20）stress 不为负；至少一半交易目标和至少 4 个分类 base 扣 hurdle 为正；最大正 PnL 目标占比 `<=20%`。

development（98 个预定周，最低 90 个实际 entry dates、300 笔主机会）：除共同硬门外，要求 stress 扣 hurdle 的 95% bootstrap 下界 `>0`，gross 市场超额的 95% bootstrap 下界 `>0`。失败则不得打开后期。

evaluation（52 个预定周，最低 48 个 entry dates、150 笔主机会）：共同硬门；stress 和 gross 市场超额只要求点估计 `>0`，不要求单年区间下界为正。失败则不得打开 confirmation。

confirmation（51 个预定周，最低 47 个 entry dates、145 笔主机会）：共同硬门；随后把 evaluation+confirmation 的日期组合按日期拼接，要求：

- 合并留出期 stress 扣 hurdle 均值 `>0` 且 95% bootstrap 下界 `>0`；
- 合并留出期 gross 市场超额均值 `>0` 且 95% bootstrap 下界 `>0`；
- 2024、2025 两个阶段的 stress 点估计分别 `>0`；
- 两个留出阶段均满足风险、广度、集中度和共同基准差门。

阶段门不允许因样本实际略少而事后降低。若官方输入本身不足，结论为 `CANNOT_DETERMINE` 或 `INSUFFICIENT_EVIDENCE`，不得用补插值跨过。

## 结论映射

- `SUPPORTS_WITHIN_SCOPE`：三阶段全部 PASS、合并留出显著、复演通过，才生成 handoff。
- `DOES_NOT_SUPPORT`：任一开放阶段的 base/stress 扣 hurdle `<=0`，或不胜过 scheduled/market 的经济方向，说明当前固定转换不成立。
- `INSUFFICIENT_EVIDENCE`：点估计有利但统计、稳健性、广度、集中度或某个留出门不足。
- `CANNOT_DETERMINE`：可靠数据/身份/实现无法确认。

正结论仍只说明该规则在当前固定数据、成本和目标范围内值得进入交易核心的资格验证，不证明真实 Alpha、未来长期盈利，也不授权实盘。
