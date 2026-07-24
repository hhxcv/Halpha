# BTCUSDT 日线 Donchian × carry 条件

## 决策问题

上一题证明完整日线 Donchian 组合在 2021–2023 成本后为正，但实际 funding 使最接近候选的收益从“无 funding 的 +13.44%”降至 +8.38%，且风险调整优势不足。本文检验一个外部研究直接提出、又与该缺口一致的新机制：趋势方向只有在永续合约 carry 不冲突时是否更可靠。

- 研究类型：`STRATEGY_CANDIDATE`。
- 最强预期主张：若全部顺序门通过，支持一个可进入产品资格验证的一腿 BTCUSDT 永续候选；不证明 Alpha 或未来盈利。
- 被评价对象：固定 20/30/60/90 日 Donchian 状态组合、90 日波动估计、10% 年化波动目标、0.5x 绝对权重上限和 20% 再平衡容忍带。
- 基准：相同规则的无 carry 过滤多空版、long-only 版，以及持续波动目标多头。
- 反证：过滤后不能在现实成本下同时改善收益、Sharpe/Calmar、funding PnL 和跨年稳定性，或评价/确认任一顺序门失败。

## 为什么选这一题

已审计的其他方向没有替代价值：TRX 8% 波动目标只有 0.58% 的资本门余量且不是 Alpha；TRX/PAXG 需要当前产品没有的现货双资产；DOGE/XRP/ADA cash-and-carry 是明确排除的六腿方案。继续搜索 Donchian 周期、止盈或小型入场过滤会重复上一轮失败。本题保持一个合约、一套退出状态和当前 Demo 场所，只改变有经济解释的持仓许可。

开始前比较的三个后续方向是：

1. **trend × carry 单腿永续（选中）**：直接针对已量化的 funding 拖累，产品适配最好，只有三项成熟文献定义的过滤。
2. **同一 Donchian 改为 Binance Spot**：更可能消除 funding，但会引入产品尚不支持的 Spot 账户、成交和事实语义；仅在本题失败后另立问题。
3. **BTC/ETH 两资产趋势组合**：可能得到分散收益，但改变计划与组合边界；不在本题混入。

## 固定规则

所有信号只使用 UTC 日线闭合信息，并在下一 UTC 日开盘行动。基础趋势为四个 Donchian 状态的等权平均；每个状态在通道突破后持有，并使用只向有利方向移动的通道中线退出。carry 使用上一完整 UTC 日实际 funding 现金流的净符号：正 funding 表示 long 付、short 收；负 funding 相反。零 carry 不阻止任何方向。

三项候选在首次结果前固定：

- `CARRY_BOTH_SIDES`：long 只在 funding ≤ 0 时允许，short 只在 funding ≥ 0 时允许。
- `CARRY_LONG_SIDE_ONLY`：只约束 long；short 不受 carry 限制。
- `CARRY_SHORT_SIDE_ONLY`：long 不受限制；只约束 short。

不搜索 funding 阈值、滚动窗口、加权方式、Donchian 周期、波动窗口、成本、杠杆或调仓带。候选使用同一已审计数据装载与撮合代理，代码身份由 `checkpoint.json` 固定。

## 数据、成本与时间门

- 数据：Binance 官方 BTCUSDT USD-M `1d` kline、`8h` mark-price kline 和实际 funding 历史；复用上一研究 Git 外不可变缓存与 manifest。
- 已知暴露：2021–2026H1 的 BTC 市场历史已被其他问题查看；上一题没有读取本 carry 条件族的评价/确认收益。因此这是规则级时间隔离，不声称市场数据从未被研究者见过。
- development：2021–2023，运行全部三项候选。
- evaluation：2024–2025，仅在开发门通过后运行唯一选中候选。
- confirmation：2026H1，仅在评价门通过后运行。
- favorable/base/stress 每单位换手成本：6/14/19 bp，其中固定 taker 4 bp，滑点 2/10/15 bp；逐事件计入实际 funding。

开发支持门要求 base/stress 均正、Sharpe ≥ 0.50、最大回撤 > -15%、至少两年正、active days ≥ 180、Sharpe 与 Calmar 同时超过两个纯趋势基准、funding PnL 优于无过滤多空基准、三候选 DSR ≥ 0.80。只按最差年度、stress Sharpe、base Sharpe 的固定顺序选一个。

评价要求两年 base 均正、base/stress 总收益为正、Sharpe ≥ 0.50、回撤 > -15%、active days ≥ 120、Sharpe/Calmar 超过两个纯趋势基准且 funding PnL 改善。确认要求 base/stress 非负、回撤 > -10%、active days ≥ 15、funding PnL 不差于同期无过滤基准，且评价+确认复合 base/stress 为正。

## 运行

```powershell
research/.venv/Scripts/python.exe research/studies/strategy-candidate/2026/btcusdt-daily-donchian-carry-conditioned/study.py analyze --phase development --cache-root D:/projects/Codex/CodexHome/research-data/halpha/btcusdt-daily-donchian-ensemble --manifest D:/projects/Codex/CodexHome/research-data/halpha/btcusdt-daily-donchian-ensemble/source_manifest.json --output-dir research/studies/strategy-candidate/2026/btcusdt-daily-donchian-carry-conditioned
research/.venv/Scripts/python.exe research/studies/strategy-candidate/2026/btcusdt-daily-donchian-carry-conditioned/study.py select-development --input research/studies/strategy-candidate/2026/btcusdt-daily-donchian-carry-conditioned/development.json --output research/studies/strategy-candidate/2026/btcusdt-daily-donchian-carry-conditioned/selection.json
```

后续命令必须携带上一门生成的授权文件；未通过时脚本拒绝启封。研究只写 `research/**` 和显式 Git 外缓存，不读取产品数据库、凭据或运行配置，不发出交易请求。
