# 预注册：PPC14 连续赢家周频单目标 LONG

记录于 2026-07-22，任何本题收益输出之前。

## 候选筛选与决定价值

| 候选 | 当前未解决差异 | 半自动/小资金适配 | 取舍 |
|---|---|---|---|
| PPC14 连续赢家、周频单目标 LONG | 新论文给出价格路径连续性与短期收益交互，但没有证明流动永续、成本后、单腿长仓 | 基础日线、周频、单目标、无裸空 | **选中**；公式可精确复现，直接检验论文关系能否成为计划依据 |
| 同星期横截面季节性 | 2020 论文有线索，2024 大样本有反证 | 日频换手与人工维护更高 | 不选；相对当前用途成本高且外部反证强 |
| 截面 dispersion 状态动量 | 可能解释 momentum breakdown | 需每日动态市场组合和更多横截面状态 | 暂缓；与一次性单目标计划的表达差异更大 |
| PPC winner-minus-loser 多空 | 最贴近论文主要 portfolio spread | 同时多腿、裸空尾部、保证金与清算会主导 | 不选；Q19 已显示流动山寨永续 naked short 的极端尾部 |

PPC 不是因“新颖”入选。它的决策价值来自一个明确差异：现有 Halpha 动量、反转、低波与 premium/funding 转换均未通过新门槛，而 PPC 检查同样累计收益是由许多小幅同向日还是少数跳跃日形成。若它不能改善普通 MOM14，本机制对当前产品没有新增价值。

## 基准、类型与最强允许主张

- 稳定产品基准：Git `0bdfeffa616260cebd2d2188ddc8deb9e85c77f4`。
- 正式策略：`ONE_SHOT_DONCHIAN_ATR_BREAKOUT 1.0.1 / BTCUSDT-PERP`，只作背景，不参与规则选择。
- 类型：`STRATEGY_CANDIDATE`。
- 最强允许主张：在固定当前幸存者目标、公开 Binance 数据、冻结时间、零售成本代理和本题顺序评价下，PPC 条件是否提供足以继续新前向观察的历史经济证据。
- 盈利历史不证明 Alpha、未来盈利或真实可成交性。本题没有论文发表后的足量新市场期，因此即使历史门全过，结论上限仍为 `INSUFFICIENT_EVIDENCE`，不生成产品 handoff。

## 固定对象、数据与可用性

固定 25 个 Binance USD-M 永续目标：`1000XECUSDT, AAVEUSDT, AVAXUSDT, BCHUSDT, BNBUSDT, CRVUSDT, DASHUSDT, ENSUSDT, ETCUSDT, HBARUSDT, KAVAUSDT, LINKUSDT, LTCUSDT, NEARUSDT, RUNEUSDT, SNXUSDT, SOLUSDT, TRXUSDT, UNIUSDT, VETUSDT, XLMUSDT, XMRUSDT, XRPUSDT, ZECUSDT, ZILUSDT`。

- 目标名单及类别固定为开题时 `research/market-universe/universe.csv` 的 SHA-256 身份；它是当前幸存者集合，不是历史 point-in-time 全市场。
- 输入仅为 Binance 官方公开 1d Kline、settled funding 和 mark price/mark-price Kline。UTC；不使用 L2、新闻、舆情、OI、liquidation、产品数据库或运行配置。
- 每个决策至少 20 个目标可排名；目标过去 45 个自然日任一必需 OHLCV 缺失、30 日中位 quote volume 低于 1,000 万 USDT、入退场 open 缺失、funding 或 mark 无法可靠取得时，该目标 `NO_ACTION`，不填补、不换币。
- 复用已经冻结的 2024 与 2025 公共源 manifest/cache；每个文件按 bytes 和 SHA-256 复核。大型文件留在 Git 外。

## 固定公式、时间顺序与动作

每个 UTC 周一 `00:00` 为候选入场时间。为采用原论文的一日 gap，形成窗口最后一根日线是周六 `00:00` 开始并于周日 `00:00` 完成的 bar；完整跳过周日 bar，周一 open 才可行动。

对目标 `i` 的最后 14 个完整 close-to-close 日收益 `r(i,d)`：

1. `PastRet14 = close(last) / close(last-14) - 1`；
2. 按 `abs(r)` 升序排名；最小绝对收益日权重 14，最大绝对收益日权重 1；精确并列使用平均名次；
3. `PPC14 = sign(PastRet14) * sum(sign(r_d) * w_d) / sum(w_d)`；
4. 在当周合格目标中分别按 `PastRet14` 和 `PPC14` 降序、symbol 升序破同值；顶部数量为 `ceil(N/3)`；
5. 配置目标同时进入两个顶部三分位且 `PastRet14 > 0` 时，周一 open 提议 `0.25x LONG`；七天后的下周一 open 全退；否则 `NO_ACTION`。

每次激活只描述一个固定目标的一次计划，不同时提交横截面组合。同目标退出后至少经过一个完整 UTC 日才能重新激活，因此连续下一周即使仍入选也跳过；不加仓、不裸空、不盘中重选、不按结果增减金额。

## 固定成本与统计

- favorable/base/stress 每边成本：6/16/26 bp，即 6 bp taker fee 加 0/10/20 bp spread/slippage 代理。
- LONG 实际 funding：正 rate 为成本，负 rate 为收益；stress 将正 funding 成本乘 1.5，负 funding 收益只保留 0.5。
- 每笔使用计划资本 `0.25x` 名义；4% 年化资本门按完整计划资本和七日持有扣除，不按名义缩小。
- 同一周多个不同配置目标只用于横截面证据，按 entry date 等权形成日期队列；不把它当作用户同时运行多计划的收益承诺。
- 四周 circular block bootstrap 5,000 次，固定 seed `20260722`；报告 95% 区间、H1/H2、symbol、类别、正贡献集中、逐目标路径回撤。
- VectorBT `Portfolio.from_orders` 仅重演固定两笔价格/费用/滑点；funding、目标选择、gap、cooldown 和资本门为问题特有最小补充，并由独立手工公式逐笔核对。

## 固定基准、邻域与搜索披露

唯一 selectable primary configuration 是 `PPC14 top tercile AND MOM14 top tercile / gap1d / 0.25x LONG / hold7d`。

固定、不可择优的诊断列：

1. `mom14`：普通 14 日收益顶部三分位；
2. `ppc14`：仅 PPC 顶部三分位；
3. `formation7`：7 日收益与 7 日 PPC 双顶部三分位；
4. `formation21`：21 日收益与 21 日 PPC 双顶部三分位；
5. `inverse_max_share`：MOM14 顶部三分位与 `1-max(abs(r))/sum(abs(r))` 顶部三分位；
6. `directional_smoothness`：MOM14 顶部三分位与论文 Directional Smoothness 顶部三分位；
7. `scheduled_long`：所有合格目标按相同 cooldown 的定期 LONG；
8. `market_long`：所有合格目标、不加 cooldown 的同日期等权市场 LONG，仅作市场 beta 基准。

总计 1 个主配置、8 个否证/诊断输出。不会按结果搜索 tercile/quintile、形成期、gap、持有期、币种、类别、金额、成本、funding、止损、市场状态或方向。

## 时间阶段与已暴露边界

| 阶段 | 区间 | 打开条件 | 证据限制 |
|---|---|---|---|
| development | `[2024-01-01, 2024-12-30)` 周一 | checkpoint 与源身份冻结后 | 底层市场和外部论文均已暴露，只能作适配开发 |
| evaluation | `[2025-01-06, 2025-12-29)` 周一 | development 全门 PASS | 本题精确输出未查看，但论文样本包含该时期；不是独立于文献选择的市场证据 |

development 失败即停止；evaluation 不会因局部漂亮结果而救回主规则。即使两段 PASS，也只冻结为前向观察规则，至少再积累 26 个规则有效周、覆盖两个市场状态，并重过同一成本、基准、稳健、广度和风险门，才允许另题考虑 `SUPPORTS_WITHIN_SCOPE` 与产品交接。

## 固定门、否定与失效条件

每个开放阶段必须全部满足：

- 数据质量 PASS；VectorBT/手工最大误差 `<=1e-10`；missing mark/funding 排除不超过计划机会 2%；
- 主规则至少 50 笔、20 个入场周、15 个目标；H1/H2 各至少 8 个入场周；
- base/stress 日期均值扣 4% 门均 `>0`，stress 四周块 bootstrap 95% 下界 `>0`，H1/H2 base 扣门均 `>0`；
- base 相对普通 `mom14` 的日期均值差与 bootstrap 下界均 `>0`；gross 相对同日等权市场 LONG 的均值差与 bootstrap 下界均 `>0`；
- `formation7, formation21, inverse_max_share, directional_smoothness` 至少三个 stress 扣门日期均值 `>0`；
- 至少四个类别 base 扣门均值为正；至少有两笔机会的目标中至少一半为正；最大正贡献目标占比 `<=25%`；最差目标 base 路径回撤 `>-30%`。

主 base 或 stress 为负、或 PPC 相对 MOM14/市场的经济增量为负，结论 `DOES_NOT_SUPPORT`；经济方向为正但统计、稳健、广度、风险或证据独立性不足，结论 `INSUFFICIENT_EVIDENCE`；可靠输入或实现无法判断才为 `CANNOT_DETERMINE`。

失效条件包括：幸存者/场所迁移、PPC 只代理普通 momentum 或市场 beta、收益来自少数低质目标、零售成本或 funding 吞没、周内跳跃/清算使日线代理失真、论文关系依赖多空组合而单腿不成立、以及新前向期不延续。未建模项包括订单簿、部分成交、真实账户 fee tier、保证金/清算/ADL、人工激活延迟、税务与场所故障。

