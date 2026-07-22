# BTCUSDT 单次突破持仓期限研究

- 研究类型：`STRATEGY_CANDIDATE`
- 开题时间：2026-07-22（Asia/Shanghai）
- 产品基准：Git `bbd2458204389f05b58594a9a255b66062080fe3`
- 正式策略背景：`ONE_SHOT_DONCHIAN_ATR_BREAKOUT 1.0.1 / BTCUSDT-PERP`
- 产品影响：`NONE`；结果不改变策略定义、计划、资金或真实账户状态
- 父问题：`../btcusdt-one-shot-entry-selectivity/`

## 决策缺口与问题

父问题已经锁定并完整运行 72 组入场选择性配置；在当前最长 4×15m（60 分钟）退出下，所有配置在 favorable、base、stress 成本中平均净收益均为负，因此关闭入场近邻搜索。旧 `btcusdt-next-funding-carry` 又保存过一个 1.0.0、最长 96×15m 的比较代理，其 2024–2025 base 多空同样为负，但没有回答当前 1.0.1 语义下 2–8 小时的中间持仓期。

本问题只问：在正式默认入场、止损和两档止盈全部固定时，把最长持仓从 1 小时延长到事前锁定的 2、4、8 小时，是否存在一个方向/期限组合，能在顺序时间门、实际 funding 和市场单成本后取得正平均净收益，同时维持基本尾部约束？否定条件是开发期没有任何新期限通过固定门；若发生即停止，不读取该规则在 evaluation 或 confirmation 的结果。

## 固定规则与搜索

- 固定入场：20×15m Donchian、2×1m 确认、最大追价 0.5 ATR。
- 固定退出：1.5 ATR 初始止损、50% @ 1.5R、余量 @ 3R；同一分钟冲突按 stop-first。
- 固定候选：`8/16/32 × 15m`，即 2/4/8 小时；分别评价 LONG、SHORT，共 6 个新候选。
- 已暴露基准：当前 `4×15m` 与历史 `96×15m`，只作同方向边界比较，不进入候选选择。
- 信号形成后下一根 1m 开盘成交；每次退出后才允许下一次重武装。研究代理不是产品的人工激活日程。
- favorable/base/stress 单边分别为 `4+2 / 4+10 / 4+15 bps`（手续费 + 不利成交），并计入持仓期间实际 funding。

## 顺序时间门

| 阶段 | UTC 区间（右开） | 作用 |
|---|---|---|
| development | 2021-01-01 至 2024-01-01 | 一次运行 6 个新候选及 4 个已暴露基准；按固定门最多选 1 个 |
| evaluation | 2024-01-01 至 2026-01-01 | 只运行固定候选及同方向 1 小时基准 |
| confirmation | 2026-01-01 至 2026-07-01 | 只运行通过评价门的固定候选及同方向 1 小时基准 |

开发门：候选至少 100 笔，base 与 stress 平均净收益/笔均大于 0，2021–2023 至少两个年度 base 为正，最差年度不低于 -10 bps/笔，base 1% 分位不低于 -2%，最差单笔不低于 -5%。按最差年度、stress、base 依次降序，同分偏好更短持仓，最多固定一个。

评价门：至少 60 笔，base 与 stress 整体、2024 和 2025 各自 base 均为正，base 比同方向 1 小时基准至少高 5 bps/笔，并继续满足相同尾部门。确认门：至少 15 笔，base 与 stress 为正、尾部门通过，且评价+确认按笔数合并的 base 均值为正。

## 数据、环境与命令

仅使用 Binance 官方公开 BTCUSDT USD-M 1m 月档案和 funding history，沿用父问题已核验的 Git 外缓存与 source manifest；2021–2026H1 底层数据均已在其他问题中暴露，本研究只有规则级顺序评价，不能称为全新市场留出。

```powershell
research/.venv/Scripts/python.exe study.py analyze --phase development --cache-root D:/projects/Codex/CodexHome/research-data/halpha/btcusdt-next-funding-carry --manifest ../../../legacy/2026/btcusdt-next-funding-carry/source_manifest.json --output-dir .
research/.venv/Scripts/python.exe study.py select-development --input development.csv --output selection.json
```

若 `evaluation_authorized=false`，到此停止。1m OHLC 无法表达订单簿、部分成交、真实延迟、保证金、强平和 bar 内真实路径；保守代理与固定成本只支持否定或继续研究的决定，不证明产品收益。

## 结论

`DOES_NOT_SUPPORT`。六个新候选在 development 的 favorable、base、stress 平均净收益全部为负，开发门通过数为 0，evaluation 和 confirmation 未解封。完整数值、反证与收敛范围见 `development.csv`、`results.json` 和 `result.md`。
