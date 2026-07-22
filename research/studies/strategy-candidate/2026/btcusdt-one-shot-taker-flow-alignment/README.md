# BTCUSDT 单次突破主动成交方向过滤研究

- 主要类型：`STRATEGY_CANDIDATE`
- 候选标识：`RESEARCH_BTCUSDT_ONE_SHOT_TAKER_FLOW_ALIGNMENT_2026`
- 开题时间：2026-07-22（Asia/Shanghai）
- 产品基准：Git `bbd2458204389f05b58594a9a255b66062080fe3`
- 正式策略背景：`ONE_SHOT_DONCHIAN_ATR_BREAKOUT 1.0.1 / BTCUSDT-PERP`
- 产品影响：`NONE`；研究不修改产品策略、计划、资金、凭据或账户状态
- 父问题：`../btcusdt-one-shot-entry-selectivity/`

## 决策缺口与选题

父问题的 72 组入场选择性、2/4/8 小时持仓期限和已结算 funding 符号过滤均未在开发期产生正的成本后平均净收益。本次 Demo 又在自然做空信号成交后 2 秒触发保护止损。继续搜索 Donchian、确认、追价、止损、止盈或持仓近邻缺少毛边际，也会扩大结果驱动调参。

开题前只比较三个不同机制：

1. 高时间框架趋势或波动阈值仍属于当前价格趋势族，并需要新窗口或阈值；不选。
2. quarter-hour tick/order-book 不平衡最贴近最新文献，但需要新的逐笔数据、时钟相位规则和更长持有语义，研究与未来运行复杂度更高；暂不选。
3. Binance USD-M 现有 1m K 线已包含总成交量和 taker buy base volume，可在不新增数据服务和数值阈值的情况下判断两根确认 K 线的主动成交净方向；选中。

本题只判断这一最小过滤能否修复当前固定策略代理，不把 K 线成交量代理称为完整订单流不平衡，也不推断因果。

## 固定问题与规则

保持正式默认 `20×15m Donchian / 2×1m 确认 / 0.5 ATR 最大追价 / 1.5 ATR 止损 / 50%@1.5R / 余量@3R / 最长 4×15m` 全部不变，只允许两根确认 K 线的合计主动成交净方向与突破方向一致，能否在现实成本和顺序时间门下取得正的成本后平均净收益？

- 每根 1m 的成交方向代理为 `2 × taker_buy_base_volume - total_base_volume`。
- 对固定两根确认 K 线求和；LONG 要求合计值 `> 0`，SHORT 要求 `< 0`，恰为零、缺失或总量无效时不行动。
- 所有输入在第二根确认 K 线闭合后可知；策略仍在下一根 1m 开盘行动，禁止同收盘成交。
- LONG/SHORT 各一个过滤候选，共 2 个；同方向未过滤正式默认只作基准。
- 入场、退出、funding、stop-first 同 bar 顺序和不可重叠重武装语义全部复用父研究。
- favorable/base/stress 单边分别为 `4+2 / 4+10 / 4+15 bps`（手续费 + 不利成交），持仓跨结算时计入实际 funding。

否定条件：开发期没有任一方向同时满足样本、成本后正均值、年度、同向基准改善和尾部门，即停止且不启封 evaluation/confirmation；不得根据结果追加 imbalance 幅度、分位数、z-score、成交笔数、成交量、时钟相位、OI、basis 或波动阈值。

## 顺序时间门

| 阶段 | UTC 区间（右开） | 固定用途 |
|---|---|---|
| development | 2021-01-01 至 2024-01-01 | 运行 2 个候选和 2 个未过滤基准；最多固定 1 个方向 |
| evaluation | 2024-01-01 至 2026-01-01 | 只运行固定候选及同方向未过滤基准 |
| confirmation | 2026-01-01 至 2026-07-01 | 只运行通过评价门的候选及同方向基准 |

开发门：候选至少 100 笔，base/stress 平均净收益均大于零，2021–2023 至少两个年度 base 为正，最差年度不低于 -10 bps/笔，比同方向未过滤 base 至少改善 5 bps/笔，base 1% 分位不低于 -2%，最差单笔不低于 -5%。按最差年度、stress、base、改善幅度排序，最多固定一项。

评价门：至少 60 笔，base/stress、2024 和 2025 各自 base 均为正，比同方向未过滤 base 至少改善 5 bps/笔，并通过同一尾部门。确认门：至少 15 笔，base/stress 和评价+确认加权 base 均为正，并通过尾部门。

## 数据、执行边界与命令

复用父研究已核验的 Binance 官方 BTCUSDT USD-M 1m 月档案、funding snapshot、Git 外缓存、指标、触发、模拟和指标；只新增读取官方 K 线第 10 列 `taker buy base asset volume`。底层 2021–2026H1 已在其他问题暴露，本题只有规则级顺序评价，不能称为全新市场留出。

```powershell
research/.venv/Scripts/python.exe study.py analyze --phase development --cache-root D:/projects/Codex/CodexHome/research-data/halpha/btcusdt-next-funding-carry --manifest ../../../legacy/2026/btcusdt-next-funding-carry/source_manifest.json --output-dir .
research/.venv/Scripts/python.exe study.py select-development --input development.csv --output selection.json
```

若 `evaluation_authorized=false`，到此停止。1m 聚合 taker volume 不是完整订单簿 OFI，无法表达限价单、撤单、深度、逐笔顺序、盘口、部分成交、延迟、保证金、强平或人工激活日程；正结果也只能支持继续研究，不能证明 Alpha 或授权产品改动。

## 结论

`DOES_NOT_SUPPORT`。

开发期共加载 1,576,861 根 1m K 线；所有 29,084 个原始 LONG/SHORT 触发都能取得两根确认 K 线的成交方向代理，因而 241 根无效 taker-flow K 线没有移除目标触发。方向过滤保留 LONG 59.684% 和 SHORT 61.741% 的原始触发，但没有改善经济结果：

| 方向 | 过滤候选 base 均值 | 未过滤 base 均值 | 每笔改善 | 过滤候选 stress 均值 |
|---|---:|---:|---:|---:|
| LONG | -0.329638% | -0.324678% | -0.496 bps | -0.448498% |
| SHORT | -0.372200% | -0.368648% | -0.355 bps | -0.507714% |

两项候选在 favorable、base、stress 和 2021–2023 每个年度均为负；LONG base 1% 分位为 -2.1041%，SHORT 为 -2.5536%，也未通过固定尾部门。`selection.json` 因而记录 `gate_pass_count=0`、`evaluation_authorized=false` 和 `NO_TAKER_FLOW_DIRECTION_PASSED_DEVELOPMENT_GATE`。2024–2025 evaluation 与 2026H1 confirmation 均未启封。

这项两分钟聚合 taker-volume 符号只能描述成交侧方向，无法修复当前单次突破代理在成本前后都缺少正毛边际的问题。按照开题停止规则，不再追加 imbalance 幅度、分位数、z-score、成交笔数、成交量、时钟相位、OI、basis 或波动阈值；结果不进入产品，也不支持再开一笔相同策略族的 Demo 交易。

原始结果见 `development.csv`、`development.json` 和 `selection.json`，解释性摘要见 `result.md` / `results.json`。2026-07-22 的独立重演得到完全相同的 development CSV SHA-256 `6da9891eeb82b2dc656326c5c1f59208923f8569c3ec5fc39b427cf6c1d99322`，选择门仍为 0 项通过。
