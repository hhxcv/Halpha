# BTCUSDT 单次突破 funding 符号过滤研究

- 研究类型：`STRATEGY_CANDIDATE`
- 开题时间：2026-07-22（Asia/Shanghai）
- 产品基准：Git `bbd2458204389f05b58594a9a255b66062080fe3`
- 正式策略背景：`ONE_SHOT_DONCHIAN_ATR_BREAKOUT 1.0.1 / BTCUSDT-PERP`
- 产品影响：`NONE`；研究不改变策略、计划、资金、凭据或账户状态
- 父问题：`../btcusdt-one-shot-entry-selectivity/`

## 决策缺口与选题

父问题已否定 72 组入场近邻，持仓期限问题又否定 2/4/8 小时。继续搜索 Donchian、确认、追价、止损、止盈或持仓组合会成为结果驱动调参。当前历史代理虽已把实际 funding 计入持仓收益，却没有回答入场前已结算 funding 是否能作为拥挤和方向持有成本过滤器。

开题前比较了四个方向：高时间框架趋势过滤与现有趋势家族高度重叠；ATR/波动状态需要另选回看与阈值；2026 年 quarter-hour 订单流需要新 tick/trade 输入且运营复杂；funding 符号过滤已有官方事件数据、无需数值阈值，并直接面对正式策略历史模型的已知 funding 缺口。因此只选中一个二元规则。

## 固定问题、规则与否定条件

问题：保持正式默认 `20×15m Donchian / 2×1m 确认 / 0.5 ATR 最大追价 / 1.5 ATR 止损 / 50%@1.5R / 余量@3R / 最长 4×15m` 全部不变时，只允许 funding 对持仓方向不不利的突破进入，能否在现实成本和顺序时间门下把成本后平均净收益转正？

- 信号形成与成交：闭合 1m 信号，下一根 1m 开盘行动；同一分钟退出冲突 stop-first。
- 可用 funding：只使用触发分钟收盘前已经结算的最新 Binance USD-M funding rate，按事件时间向前保持；未来 rate、premium index 和下一次预测 rate 均不可用。
- 固定过滤：LONG 仅当最新已结算 funding `<= 0`；SHORT 仅当 `>= 0`；恰为零视为两边都不不利。没有可知结算事件时不行动。
- 候选数：LONG/SHORT 各一项，共 2 个；同方向未过滤正式默认只作基准，不参与选择。
- favorable/base/stress 单边成本分别为 `4+2 / 4+10 / 4+15 bps`，持仓跨越实际 funding 事件时继续计费。

否定条件：开发期没有任一方向同时满足样本、成本后正均值、年度、基准改善和尾部门，立即停止且不启封 evaluation/confirmation。不得根据结果添加 funding 幅度、持续次数、均值、z-score、OI、basis 或波动阈值。

## 顺序时间门

| 阶段 | UTC 区间（右开） | 固定用途 |
|---|---|---|
| development | 2021-01-01 至 2024-01-01 | 同时运行 2 个候选和 2 个未过滤基准；最多固定 1 个方向 |
| evaluation | 2024-01-01 至 2026-01-01 | 只运行固定候选及同方向未过滤基准 |
| confirmation | 2026-01-01 至 2026-07-01 | 只运行通过评价门的候选及同方向基准 |

开发门：候选至少 100 笔，base/stress 均值均为正，2021–2023 至少两个年度为正，最差年度不低于 -10 bps/笔，比同方向未过滤 base 至少改善 5 bps/笔，base 1% 分位不低于 -2%，最差单笔不低于 -5%。按最差年度、stress、base、改善幅度排序，最多固定一项。

评价门：至少 60 笔，base/stress、2024、2025 均为正，比同方向未过滤 base 至少改善 5 bps/笔，并通过同一尾部门。确认门：至少 15 笔，base/stress 和评价+确认加权 base 均为正，并通过尾部门。

## 数据、边界与命令

复用父研究已核验的 Binance 官方 BTCUSDT USD-M 1m 月档案和 funding history snapshot、Git 外缓存、解析器、指标、触发、模拟与指标。底层 2021–2026H1 已在其他问题暴露，本题只有规则级顺序留出；正向结果也不能证明新市场数据上的 Alpha。

```powershell
research/.venv/Scripts/python.exe study.py analyze --phase development --cache-root D:/projects/Codex/CodexHome/research-data/halpha/btcusdt-next-funding-carry --manifest ../../../legacy/2026/btcusdt-next-funding-carry/source_manifest.json --output-dir .
research/.venv/Scripts/python.exe study.py select-development --input development.csv --output selection.json
```

若 `evaluation_authorized=false`，到此停止。1m OHLC 仍不表达订单簿、部分成交、延迟、保证金、强平和 bar 内真实路径；当前固定成本与保守代理只支持拒绝或继续研究的决定。

## 结论

`DOES_NOT_SUPPORT`。开发期两个预注册候选的 favorable、base、stress 平均净收益均为负，没有候选通过开发门，evaluation 与 confirmation 均未打开。

LONG 过滤保留 12.71% 触发，相对同向未过滤 base 改善约 5.09 bps/笔，但 base 仍为 -27.38 bps/笔、三个年度均为负，且 1% 尾部为 -2.19%，未通过预注册尾部门。SHORT 过滤保留 87.32% 触发，base 为 -37.91 bps/笔并比未过滤基准更差。当前零阈值 funding 符号过滤分支关闭，产品状态保持不变；详见 `results.json` 与 `result.md`。
