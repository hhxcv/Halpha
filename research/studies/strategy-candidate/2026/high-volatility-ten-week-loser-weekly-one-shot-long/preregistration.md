# 预注册：RV28 高波动半区的 MOM70 输家 LONG

## 冻结主规则

- 固定目标：`1000XEC,AAVE,AVAX,BCH,BNB,CRV,DASH,ENS,ETC,HBAR,KAVA,LINK,LTC,NEAR,RUNE,SNX,SOL,TRX,UNI,VET,XLM,XMR,XRP,ZEC,ZIL` 的 `USDT` 永续。
- 每个 UTC 周日完整 1d bar 后计算；下一周一 open 行动。信号与入场严格相隔一个完成 bar 边界，禁止用周内 high/low 或未来 funding。
- 资格：连续 85 个 UTC 日 OHLCV 完整；30 日 quote volume 中位数 `>=10m USDT`；横截面至少 20 个。
- `RV28`：28 个完整日 log return 的样本标准差年化；高波动组为 RV28 降序前 `ceil(50%*N)`，symbol 升序破同值。
- `MOM70`：完成周日 close 除以 70 个日历日前 close 减一；在高波动组升序取 `ceil(30%*N_high)`。
- owner 固定目标入选时，下一周一 `0.25x LONG`，7 日后退出；一整 UTC 日 cooldown。目标、方向、输入、universe identity、排序或执行边界有未知即不动作。
- protection：0.25x 上限、单仓、不加仓、7 日时间退出、cooldown；没有盘中价格止损。任何止损都需另题重验。

本题聚合多个目标/日期只用于条件期望统计，不表示同时持有全部入选币；策略不替 owner 选 instrument。

## 成本与统计

- favorable/base/stress 每边均为 6 bp fee，加 `0/10/20 bp` slippage。
- LONG 真实 funding：`entry < fundingTime <= exit`；stress 将正 funding 成本乘 1.5、负 funding 收益乘 0.5。缺 mark 不插值，整笔排除；缺 funding/mark 总排除 `<=2%`。
- 每个 entry-date 等权平均条件机会；每周扣 `4%*7/365` 全计划资金门槛。
- 4 周 circular block bootstrap，5,000 次，seed `20260722`。
- VectorBT 与手工价格/fee/slippage逐笔误差 `<=1e-10`；funding 单列事件现金流。

## 不可升级诊断

1. `rv21`、`rv42`：高波动半区窗口邻域。
2. `mom56`：RV28 高波动半区内的 8 周输家。
3. `lowvol_loser`：RV28 低波动半区内 MOM70 输家。
4. `unconditional_loser`：不做波动条件的 MOM70 底部 30%（Q17 同类基准）。
5. `highvol_winner`：RV28 高波动半区内 MOM70 顶部 30%。
6. `highvol_scheduled`：高波动半区全部目标 LONG，保留 cooldown。
7. `market_long`：全部合格目标每周 LONG，无 cooldown，仅作 gross 市场基准。

主规则必须胜过 `unconditional_loser`、`lowvol_loser`、`highvol_winner` 与 `highvol_scheduled`；不能只说 high-vol 本身涨了。至少 2/3 参数邻域（rv21、rv42、mom56）stress 非负。任何诊断不得取代主规则。

## 顺序阶段

| 阶段 | entry 区间 | 证据身份 |
|---|---|---|
| development | `[2024-01-01, 2024-12-30)` | 本条件输出未见；复用已绑定官方缓存 |
| evaluation | `[2025-01-06, 2025-12-29)` | development PASS 才打开 |
| confirmation | `[2026-04-06, 2026-06-29)` | evaluation PASS 后才下载；为论文 2026-03 样本后的短 Q2 确认 |

外部论文覆盖 2021–2026-03，故 2024/2025 是 Halpha 精确规则的内部留出，不是文献发表后的新市场；2026Q2 才是短的 post-paper 时间片。Q2 只有约 12 周，不能单独证明长期稳定。

## 硬门

development/evaluation 共同：数据 PASS；至少 48 entry dates、120 笔、15 个目标；排除 `<=2%`；base/stress 扣 hurdle `>0`；两个半段 base `>0`；日期 MDD `>-15%`、最差目标 `>-30%`；base 胜过四个主要条件/简单基准；gross 市场超额 `>0`；2/3 邻域 stress 非负；至少一半目标、4 类别为正；最大正 PnL 目标占比 `<=25%`；计算双算一致。

development 不要求单年区间下界为正，避免用不足一年样本作不现实显著门；但上述经济方向必须全部成立。

evaluation 还把 2024+2025 合并，要求：stress 扣 hurdle、相对 unconditional loser 的 stress 增量、gross 市场超额三者均值和四周 block-bootstrap 95% 下界全部 `>0`。否则不下载 2026。

confirmation 至少 10 entry dates、20 笔、8 目标、3 类别；base/stress 扣 hurdle、相对 unconditional/highvol scheduled/market 的差均 `>0`；日期 MDD `>-10%`；最大正贡献 `<=40%`；至少 2/3 邻域 stress 非负。三门全过且复演一致才 `SUPPORTS_WITHIN_SCOPE`。

任一开放阶段 base/stress、波动条件增量或市场相对方向不正为 `DOES_NOT_SUPPORT`；方向为正但统计、广度、稳健、风险或短确认不足为 `INSUFFICIENT_EVIDENCE`；可靠输入/实现不能判断才 `CANNOT_DETERMINE`。正结论仍不证明 Alpha 或长期盈利。
