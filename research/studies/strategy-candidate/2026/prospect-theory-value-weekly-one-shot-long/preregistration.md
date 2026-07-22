# 预注册：前景理论价值低分周频单腿 LONG

## 身份、问题与顺序证据

- 基准提交：`0bdfeffa616260cebd2d2188ddc8deb9e85c77f4`。
- 正式策略背景：`ONE_SHOT_DONCHIAN_ATR_BREAKOUT 1.0.1 / BTCUSDT-PERP`；不修改、不复制其参数、不声称重演其绩效。
- 问题：固定流动永续目标的 `PTV52` 进入横截面最低十分位时，`0.25x LONG / 7d` 是否在现实成本、actual/stress funding、4% 全计划资本门、简单特征、市场 beta、邻域、广度、风险和顺序证据下达到研究资格门？
- development 为 2022–2023，evaluation 为 2024；仅前段全门通过才打开后段。论文样本止于 2020，但 Halpha 已在其他问题中看过底层价格路径；事前冻结保护本题方法输出，不把市场路径冒充全新。
- 两段历史全通过最多得到 `INSUFFICIENT_EVIDENCE`，不生成 handoff。还需冻结规则在 checkpoint 后积累至少 26 个合格周并覆盖两种市场状态，另题通过相同门后才讨论核心资格验证。

## 固定对象、信号与计划

- 25 个当前 Binance USD-M 永续：`1000XEC,AAVE,AVAX,BCH,BNB,CRV,DASH,ENS,ETC,HBAR,KAVA,LINK,LTC,NEAR,RUNE,SNX,SOL,TRX,UNI,VET,XLM,XMR,XRP,ZEC,ZIL` 对 USDT。
- 每周一 `00:00 UTC` 为最早行动；只使用截至前一周周六收盘的数据，完整周日形成时间间隔。
- 对每个周六，先计算 25 个固定对象的周对数收益。每个决策只用当时具备连续 78 周输入、最近 30 日 quote-volume 中位数至少 10m USDT 的对象；至少 20 个才可排名。每个历史周的等权横截面周收益作为市场参考。
- `PTV52` 使用最近 52 个“目标周对数收益减同期市场等权周收益”，升序排列后按原文累计前景理论公式：`alpha=beta=0.88, lambda=2.25, gamma=0.61, delta=0.69`。数值更低表示历史分布在该偏好模型下更不具吸引力。
- 按 PTV 升序、symbol 升序破同值；最低 `ceil(N/10)`（25 个时 3 个）合格。用户固定目标合格时，周一 open 以计划资本 `0.25x LONG`，七日后下周一 open 退出；退出后一个完整日冷却，所以同目标不能连续两周再入。
- 任何输入、entry/exit、funding/mark 缺失均 `NO_ACTION`，不插值、不替换目标。

## 不可择优诊断与基准

唯一主配置为 `PTV52 / bottom decile / 0.25x / 7d / one-day gap / one-day cooldown`。

固定诊断：`PTV26`、`PTV78`、以零为参考的 `PTV52_ZERO`。简单基准：`LOW_MOM52`（最低 52 周累计相对收益）、`LOW_SKEW52`（最低 52 周相对收益偏度）、`HIGH_VOL52`（最高 52 周相对收益波动）、`SCHEDULED_LONG`、`MARKET_LONG`。诊断不允许事后升格为主规则。

## 成本、统计与资格门

- 每边 taker fee 6bp；favorable/base/stress 另含每边 0/10/20bp spread-slippage。
- actual settled funding；stress 对正 funding 支出乘 1.5、负 funding 收益只保留 0.5。
- 七日计划扣 `4% × 7/365` 全计划资本门；不因 0.25x 名义缩小。
- 同 entry date 多目标先等权成日期队列；四周 circular block-bootstrap 5,000 次，seed `20260722`。VectorBT 两单必须与独立现金流逐笔误差不超过 `1e-10`。

每阶段全部满足才 PASS：

1. 数据、来源身份、哈希、时间顺序与 VectorBT 核对通过；缺 mark/funding 排除不超过 2%；至少 100/50 笔（development/evaluation）、40/20 个日期、18/15 个目标，每半段至少 15/8 个日期。
2. base、stress 扣门日期均值正；stress block-bootstrap 95% 下界大于零；各日历年和每半段 base 均为正。
3. base 相对 `LOW_MOM52`、`LOW_SKEW52`、`HIGH_VOL52` 三者均值为正，且相对三者中事前固定的每日期最高收益包络增量 bootstrap 下界大于零。
4. gross 相对 `MARKET_LONG` 增量为正且 bootstrap 下界大于零。
5. 三个 PTV 邻域至少两个 stress 扣门均值为正；至少四个类别为正；至少一半有两笔以上的目标为正；最大正 PnL 目标占比不超过 25%。
6. 日期组合 base 最大回撤大于 -20%，最差目标大于 -30%。

若 base/stress、简单特征增量或 market excess 任一核心经济均值不为正，则 `DOES_NOT_SUPPORT`；方向有利但统计、分期、广度、邻域或风险门不足则 `INSUFFICIENT_EVIDENCE`；可靠数据无法判断才 `CANNOT_DETERMINE`。失败立即停止，不搜索窗口、top 数、持有期、方向、类别、成本或状态近邻。

## 支持边界

即使历史两段全通过，也不承诺长期盈利，不修改产品、L4、资金或真实账户，不产生真实交易动作。只有后续前瞻题通过且项目所有者明确选择，才能另开产品任务制作框架无关决策轨迹并验证 Nautilus 执行资格。
