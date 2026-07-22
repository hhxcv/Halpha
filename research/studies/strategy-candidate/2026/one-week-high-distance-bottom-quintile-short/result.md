# 结果：HMOM7 底部五分位 SHORT 未通过开发门

## 结论与决策

`DOES_NOT_SUPPORT`

在固定的 2023 development 窗口中，`HMOM7 / bottom quintile / 0.5x SHORT / 7d` 在有利、基础和压力成本下的绝对收益均为负，也未可靠胜过普通 `MOM7` 输家、按相同时点无条件做空或等权市场做空。它还同时违反回撤、邻域稳健、目标与类别广度、正 PnL 集中度门。

因此本题停止在 development：不打开 2024 evaluation 或 2025–2026H1 confirmation，不生成交易核心 handoff，不作为半自动计划候选，也不改变正式策略、核心交易代码、L4、资金或真实账户。该结论否定的是本目录预注册的具体转换，不是证明所有 high-price-distance 信息无效。

## 固定方法与数据

- 基准提交：`0bdfeffa616260cebd2d2188ddc8deb9e85c77f4`；正式策略身份仅作固定背景：`ONE_SHOT_DONCHIAN_ATR_BREAKOUT 1.0.1 / BTCUSDT-PERP`。
- 对象：25 个固定的当前幸存、长历史 Binance USD-M 永续；不是历史 point-in-time 全市场，也不含退市币。
- 信号：每个周日收盘计算最近七个完整 UTC 日的 `HMOM7 = ln(close_sun / max(high_mon...high_sun))`；按升序取底部 `ceil(N/5)`。
- 执行：下周一 open 以 `0.5x` 做空，七天后周一 open 平仓；退出后有一个完整 UTC 日冷却，所以同一目标不能连续两周入场。
- 数据：官方 Binance 日 OHLCV、结算 funding rate 与 mark price 公开归档；funding 事件仅计 `entry < funding_time <= exit`，缺 mark 的整笔机会排除但仍占冷却。
- 成本：每边 taker fee `6 bp`；favorable/base/stress 另加 `0/10/20 bp` 滑点。压力场景把正 funding 收益乘 `0.5`、负 funding 支出乘 `1.5`。
- 资本门：每个七日计划按全部计划资本扣 `4% × 7/365`，没有因名义仓位为 `0.5x` 而减半。
- 统计：先按同一 entry date 等权聚合，再做四周循环 block bootstrap 5,000 次；只允许一个主配置。三个 HMOM 邻域、普通 MOM、无条件 short 和市场 short 均为预注册反证，不能事后晋升。

## 开发期实际结果

| 证据 | 结果 | 判断 |
|---|---:|---|
| 实际交易 / entry dates / symbols | `193 / 51 / 25` | 样本量门通过 |
| planned / cooldown skips / missing-mark exclusions | `257 / 60 / 4` | 缺 mark 比例 `1.556%`，通过 `≤2%` |
| favorable 扣资本门日期均值 | `-0.845802%` | 负 |
| base 扣资本门日期均值 | `-0.946533%` | 负 |
| stress 扣资本门日期均值 | `-1.123430%` | 负 |
| base 95% block-bootstrap 区间 | `[-2.086862%, +0.102116%]` | 跨零 |
| stress 95% block-bootstrap 区间 | `[-2.273922%, -0.069160%]` | 整段为负 |
| favorable / base / stress 日期组合复利 | `-35.8301% / -39.0817% / -44.4313%` | 不可接受 |
| base 日期组合最大回撤 | `-39.0817%` | 失败 `>-20%` 门 |
| 最差目标最大回撤 | `-49.2081%`（RUNE） | 失败 `>-40%` 门 |
| 前半 / 后半 base 扣门均值 | `-1.075642% / -0.822389%` | 两半均负 |

这些是同日期 cohort 结果，不把同一周多币并发误当独立观察。stress 区间整体低于零，说明在预注册的当前样本和成本模型内，问题不是“仅统计功效不足”，而是收益方向不支持该交易规则。

## 收益分解与尾部风险

主规则逐笔平均：

- gross short price return：`-0.866232%`；
- 实际 funding：`+0.014980%`；
- base 扣价格端费用/滑点后：`-1.027618%`；
- base 加 funding 后：`-1.012638%`；
- stress 加 funding 后：`-1.193310%`。

193 笔合计 gross short、funding、base price-cost、base net 分别为 `-1.6718275 / +0.0289112 / -1.9833035 / -1.9543923` 个单位收益。正 funding 对空头有少量帮助，远不足以覆盖标的反弹和成本。

base 胜率为 `50.259%`、中位数为 `+0.126365%`，但均值为负。这是重要反证：频繁小赢被较少但更大的上涨挤压损失吞没；若以后只以胜率、交易中位数或正 funding 判断本规则，会重复遗漏 SHORT 的右尾风险。

## 简单基准、增量信息与稳健性

- 相对普通 `MOM7` 底部五分位 SHORT：主规则 base 日期均值低 `0.052220%`；差值区间 `[-0.576520%, +0.464272%]`。未证明 high-distance 比简单前周输家更有价值。
- 相对相同时序的 `SCHEDULED_SHORT`：低 `0.210512%`；差值区间 `[-0.838919%, +0.481489%]`。
- gross 相对同周等权 `MARKET_SHORT`：高 `0.220104%`，但区间 `[-0.240917%, +0.662942%]` 跨零。存在弱的相对选币迹象，却既不可靠，也不能转化为绝对可盈利的单腿 short。
- `HMOM7` 与 `MOM7` 周横截面 Spearman 中位数 `0.4194`（范围 `-0.5826` 至 `0.9883`，52 周）。它确实不等同于普通动量，但“不同信息”不等于可交易 Alpha。
- 邻域 stress 扣门均值：`HMOM14 -1.033073%`、`HMOM28 -1.920756%`、`HMOM7 bottom3 -1.548392%`；三个均为负。
- 其他压力基准：`MOM7 -1.061738%`、`SCHEDULED_SHORT -0.903354%`、`MARKET_SHORT -1.313512%`。
- 按所有实际入选目标计，只有 `10/25` 为正；在至少五笔的目标中只有 `9/22` 为正。六类中仅 Infrastructure `+1.0091%`、PoW `+0.3416%` 为正；DeFi `-2.5976%`、L1 `-0.1027%`、L2 `-0.4822%`、Payment `-1.4250%`。
- 最大正 PnL 目标贡献 `27.2338%`，超过 `20%` 上限。

失败门共 13 个：`base_after_hurdle_positive`、`stress_after_hurdle_positive`、`stress_bootstrap_lower_positive`、`both_halves_base_positive`、`date_portfolio_drawdown_above_minus_20pct`、`worst_symbol_drawdown_above_minus_40pct`、`base_beats_mom7`、`base_beats_scheduled_short`、`gross_excess_bootstrap_lower_positive`、`at_least_two_of_three_neighbors_stress_nonnegative`、`at_least_half_selected_targets_positive`、`at_least_four_categories_positive`、`largest_positive_pnl_share_at_most_20pct`。

## 与先行论文结果为何不同

Fičura 报告的是 2017-06 至 2022-12、point-in-time 大且流动币、多场所聚合现货的周横截面组合；其 `HMOM1W` Q5-Q1 均值与风险调整结果支持“检查 Q1 short”，但论文的 Q1 原始均值本身不显著，显著证据主要是因子调整 alpha。Halpha 检验的是 2023 当前幸存 Binance 永续、固定对象、单腿、实际 funding、零售成本、one-shot 冷却和绝对资本门，estimand 不同。

本结果说明：论文中的横截面相对效应不能直接转换成当前半自动单腿 SHORT。最可能的差异包括样本时期、幸存者名单、现货/永续结构、市值加权/单目标计划、市场 beta、成本和空头挤压。现有设计不能分别识别每项贡献，因而不猜测唯一原因。

## 过程完整性与复现

- checkpoint digest：`7f8290b894b72a1fb94c7df0d1d6c9268490a276d122f358bca5c02c15b0b1df`。
- 首次 DQ 因完整性检查错误地要求数据延伸至最后退出后一周而失败；当时没有生成或查看 HMOM 排名、交易、收益或 gate。`amendment-001.json` 只把 DQ 终点改为实际最后退出日 `2024-01-01`，没有改变信号、交易、成本、funding、统计或门槛；首次失败仍留存在 amendment 身份链中。
- VectorBT 固定两单 SHORT 与独立手工现金流最大误差 `1.42247e-16`，通过 `1e-10` 门；funding 另行显式加入。
- 缓存重放命令：

```powershell
& 'research/.venv/Scripts/python.exe' 'research/studies/strategy-candidate/2026/one-week-high-distance-bottom-quintile-short/study.py' prepare --stage development
& 'research/.venv/Scripts/python.exe' 'research/studies/strategy-candidate/2026/one-week-high-distance-bottom-quintile-short/study.py' analyze --stage development
& 'research/.venv/Scripts/python.exe' 'research/studies/strategy-candidate/2026/one-week-high-distance-bottom-quintile-short/study.py' gate --stage development
& 'research/.venv/Scripts/python.exe' 'research/studies/strategy-candidate/2026/one-week-high-distance-bottom-quintile-short/study.py' validate
```

- 2026-07-22 的重放再次得到 development digest `657eb4dc17cd1a214c13b2bdf7d56ffb8cc0052f6affc9fc7ff21e5f2b10b624`、gate digest `27fad77be1d366101a97e4274beec1811fb026de48aba89b4c6e920b47b019e2`、results digest `dda5426841c1a9021acc6d19429966808cbacd5fc2a76a84c661d8355e8829dd`；六个 JSON 稳定摘要和七个逐笔 CSV 哈希均与首次运行一致。`validation.json` 为 PASS，检查 6 个 JSON、7 个 CSV、0 个后续阶段文件。

## 限制与剩余未知

- 2023 路径此前已被项目其他研究看到；它位于论文样本结束之后，但不是整个项目从未观察的历史。因此本题即使通过，也仍需要真正未见期或 checkpoint 后 forward shadow。
- 当前幸存者固定名单无法回答 point-in-time 全市场或退市币是否保留论文效应；这也是为什么结果不外推到所有币。
- 日线不能模拟盘口深度、队列、部分成交、人工激活延迟、盘中保证金/强平、ADL 和场所故障；真实 short 尾部只会比本回测更复杂。
- 没有因开发门失败而查看 2024 以后结果。后续不得以换窗口、名单、bottom 数量或持有期对本题进行事后救援；任何实质新假设必须作为独立问题，重新说明机制和多重研究负担。
- 盈利回测本来也不能证明长期 Alpha；本轮负结果更不能推断未来所有市场状态，只能说明此固定规则不应被交付。
