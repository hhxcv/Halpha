# 预注册：52 周高点接近度周频单腿 LONG

## 研究身份与问题

- 类型：`STRATEGY_CANDIDATE`。
- 基准提交：`0bdfeffa616260cebd2d2188ddc8deb9e85c77f4`。
- 正式策略固定背景：`ONE_SHOT_DONCHIAN_ATR_BREAKOUT 1.0.1 / BTCUSDT-PERP`；不修改、不继承其参数，也不把本题结果写回产品。
- 问题：在固定的 25 个当前长期、较高活动 Binance USD-M 永续中，用户固定目标是否只有在 `Nearness52` 横截面顶部十分位时，才值得提出一次 `0.25x LONG / 7d` 计划；该转换在现实零售成本、funding、4% 全计划资本门、动量/市场基准、邻域、广度、风险和顺序时间证据下能否达到研究资格门？

## 先行候选筛选

| 候选 | 决策价值 | 数据/操作成本 | 主要反证 | 决定 |
|---|---|---|---|---|
| 52 周高点接近度 | 高：新论文、周频、单腿，可直接检验是否超越普通趋势 | 仅日线+funding，低 | 与趋势相邻、论文/历史路径已暴露 | 选中；提高基准门并限制支持 |
| 日内 signed jump | 中：独立注意力/跳跃机制 | 5 分钟、每日换仓，人工负担高 | 论文 VW 毛价差约 34bp/日，小于压力往返成本 | 淘汰 |
| 残差/特质波动率 | 中 | 日线可得 | 最新论文非微盘符号相反；本地波动长短族已覆盖 | 淘汰，避免近邻搜索 |
| 日历/星期效应 | 低 | 最低 | 近期复核称 2015 后不持续 | 淘汰 |
| 残差动量 | 中 | 日线可得 | 与已失败的 MOM14、赢家、CTREND 和趋势族高度重叠 | 淘汰 |

选中原因不是新颖或易实现，而是：外部预期价差相对成本较大；周频适合个人半自动计划；只需已持久化的基础数据；最强替代解释可以被同一设计直接证伪；即使失败，也能关闭一个 2026 年最新且与正式 breakout 相邻的高价值方向。

## 固定对象与数据边界

- 目标：`1000XEC,AAVE,AVAX,BCH,BNB,CRV,DASH,ENS,ETC,HBAR,KAVA,LINK,LTC,NEAR,RUNE,SNX,SOL,TRX,UNI,VET,XLM,XMR,XRP,ZEC,ZIL` 的 `USDT` 永续。
- 当前存续固定名单不是 point-in-time 全市场；不含退市币，不能复现论文的宽市场/市值加权因子。
- 每个信号日要求最近 30 日 quote volume 中位数至少 `10m USDT`，至少 20 个目标可排名；否则目标或整周 `NO_ACTION`，不插值、不用未来上市信息回填。
- 公开日线和 funding 缓存位于 Git 外，读取前核对既有 manifest 和文件 SHA-256；研究目录只保留小型身份、代码、逐笔与汇总证据。

## 时间顺序与唯一主规则

- 每个周一 `00:00 UTC` 为最早行动时点；信号截止前一周周六日线收盘，完整周日不用于信号，形成一个完整 UTC 日间隔。
- `Nearness52 = close_sat / max(last 52 Saturday closes, including close_sat)`。
- 同一时点按 `Nearness52` 降序、symbol 升序破同值；顶部 `ceil(N/10)`（25 个时为 3 个）为合格目标。
- 用户固定目标合格时，周一 open 建立 `0.25x LONG`，七天后下周一 open 退出；退出后需一个完整日冷却，因此同一目标不能连续两周重入。
- 未选中、数据不足、流动性不足、funding/mark 缺失时 `NO_ACTION`；不得由研究器替用户自动选择另一目标。
- 唯一可选择主配置：`Nearness52 / top decile / 0.25x / hold7d / one-day signal gap / one-day cooldown`。

## 不可择优诊断与简单基准

- `Nearness26`、`Nearness100`：论文报告的 13–100 周稳健范围内两端邻域。
- `Nearness52/top5`：检查十分位截断是否脆弱。
- `MOM52/top decile`：最近 52 个周六收盘累计收益，作为普通趋势/动量解释。
- `SCHEDULED_LONG`：同周所有合格目标、相同 0.25x、7d 与冷却；主规则无交易日按现金 0 对齐。
- `MARKET_LONG`：同周所有合格目标、不冷却，只用于逐日 gross 横截面市场 beta 基准。
- 所有诊断完整保存，不能事后升级为主规则。

## 成本、funding 与推断单位

- 每边 taker fee `6bp`；favorable/base/stress 另含每边 `0/10/20bp` spread/slippage 代理。
- LONG funding 现金流使用实际 settled funding 与对应 mark；stress 将正 funding 支出乘 1.5、负 funding 收益乘 0.5。
- 每个 7 日计划按全部计划资本扣 `4% × 7/365` 门，不因 0.25x 名义仓位而缩小。
- 同一 entry date 的多目标先等权聚合为一个日期队列观察；四周 circular block bootstrap，5,000 次，固定 seed `20260722`。
- VectorBT 两单回放必须与独立手工现金流误差不超过 `1e-10`；funding 另行显式加入。

## 顺序阶段与停止规则

- development：2024 周一行动。
- evaluation：2025 周一行动，仅 development 全门通过后打开。
- 本题历史数据及外部论文均已暴露。即使两个阶段全门通过，结论仍封顶为 `INSUFFICIENT_EVIDENCE`，不生成 handoff；至少需要 checkpoint 后 26 个合格周、覆盖两个市场状态的冻结规则证据，另题复核同一门，才可讨论核心资格验证。
- 任一阶段失败立即停止，不打开后续阶段，不搜索周数、top 数、行动日、持有期、方向、币种、类别、成本或状态近邻。

## 资格门

除数据质量、哈希和 VectorBT 核对外，阶段必须同时满足：

1. 排除缺 mark/funding 的计划机会比例不超过 2%；至少 50 笔、20 个 entry dates、15 个目标；每半期至少 8 个日期。
2. base、stress 扣门日期均值为正；stress 四周 block-bootstrap 95% 下界大于 0；两个半期 base 扣门均为正。
3. base 相对 MOM52 增量为正且 bootstrap 95% 下界大于 0。
4. gross 相对 MARKET_LONG 增量为正且 bootstrap 95% 下界大于 0。
5. `Nearness26`、`Nearness100`、`top5` 至少两个 stress 扣门均值为正。
6. 至少四个类别 base 扣门为正；至少交易两次的目标中一半为正；最大正 PnL 目标占比不超过 25%。
7. 日期组合 base 最大回撤大于 -20%，最差单目标 base 最大回撤大于 -30%。

若经济核心（base/stress、MOM52 增量、market excess）任一均值不为正，失败结论为 `DOES_NOT_SUPPORT`；若均值方向有利但统计、分期、广度、邻域或风险门不足，则为 `INSUFFICIENT_EVIDENCE`。数据无法可靠判断时为 `CANNOT_DETERMINE`。
