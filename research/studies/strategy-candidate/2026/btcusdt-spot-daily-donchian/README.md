# BTCUSDT Spot 日线 Donchian 场所适配

## 问题

把上一轮最接近的固定 `LONG_BALANCED_4`（20/30/60/90 日）完整 Donchian 状态机从 Binance USD-M 永续迁移到 Binance Spot，能否在更高 Spot 交易成本但没有 funding 的条件下，通过开发、评价和确认门，形成一个值得产品资格与 Demo 验证的一腿候选？

- 研究类型：`STRATEGY_CANDIDATE`。
- 决策价值：直接区分“规则没有足够经济优势”和“同一规则被永续 funding 场所结构吞噬”。
- 最强预期主张：若所有顺序门通过，只支持评估 Binance Spot 产品扩展；不证明 Alpha、未来盈利或授权真实交易。
- 反证：现实 Spot 成本后收益、4% 资本门、选择偏差、年度稳定性或风险门任一失败。

## 与已有研究的差异

既有 `btcusdt-spot-multihorizon-long-cash` 是月度 60/90/180 日正动量，在全新确认中为负；本题不复活或改参该规则。既有日线 Donchian 使用 USD-M 永续和实际 funding；其 fixed `LONG_BALANCED_4` 开发 base +8.38%、无 funding 诊断 +13.44%。本题保持其信号、退出和风险语义，只以官方 Spot bar 和保守 Spot 成本重新判断。

本题只有一个固定候选，不搜索周期、退出、仓位、场所、成本或阈值。为诚实反映形成路径，开发 DSR 使用当前相关搜索的十列完整日收益：上一 Donchian 六候选、carry 条件三候选和本 Spot 候选，而不是把转场后的单列假装成第一次尝试。

## 固定规则

- Binance Spot `BTCUSDT`，long-only，无杠杆、short、借币、funding 或收益型现金。
- 20/30/60/90 日 Donchian 各自突破后持有；各自以只向有利方向移动的通道中线退出；四状态等权。
- 90 日 realized volatility，10% 年化目标，最大权重 0.5，目标相对变化超过 20% 才调仓。
- 日线闭合后形成目标，下一 UTC 日开盘行动；阶段末清仓。
- favorable/base/stress 每单位换手成本 12/15/20 bp：统一按 10 bp Spot taker 代理，加 2/5/10 bp 滑点。账户实际费率未知，只有 Demo 前查询账户 commission 才能替换代理。

## 时间与门

- warmup：2020。
- development：2021–2023。要求 base/stress 正；stress CAGR >4%；Sharpe ≥0.60；十试验 DSR ≥0.80；回撤 >-15%；至少两年正且最差年度 ≥-5%；active days ≥180；Calmar 超过持续波动目标 Spot 多头；相对 0.5x buy-and-hold 回撤至少浅 25%。
- evaluation：2024–2025，仅在开发门通过后运行。要求 base/stress 正、stress CAGR >4%、两年均正、Sharpe ≥0.60、回撤 >-12%、active days ≥120、Calmar 超过同期持续波动目标多头。
- confirmation：2026H1，仅在评价门通过后运行。要求 base/stress 非负、回撤 >-8%、active days ≥15，且评价+确认 base/stress 复合 CAGR >4%。

BTC 价格历史已被其他研究查看，因此这是固定规则的顺序评价，不声称底层市场数据从未见过。开发失败时不运行本规则的评价或确认。

## 数据与运行

官方月度 Spot `1d` archives、checksum 和 manifest 留在 Git 外：

`D:/projects/Codex/CodexHome/research-data/halpha/btcusdt-spot-daily-donchian/`

```powershell
research/.venv/Scripts/python.exe research/studies/strategy-candidate/2026/btcusdt-spot-daily-donchian/prepare_data.py --cache-root D:/projects/Codex/CodexHome/research-data/halpha/btcusdt-spot-daily-donchian --start-month 2020-01 --end-month 2026-06
research/.venv/Scripts/python.exe research/studies/strategy-candidate/2026/btcusdt-spot-daily-donchian/study.py analyze --phase development --cache-root D:/projects/Codex/CodexHome/research-data/halpha/btcusdt-spot-daily-donchian --manifest D:/projects/Codex/CodexHome/research-data/halpha/btcusdt-spot-daily-donchian/source_manifest.json --output-dir research/studies/strategy-candidate/2026/btcusdt-spot-daily-donchian
```

研究不读取产品数据库、凭据或配置，不启动产品，不发交易请求。Spot 产品和 Demo 当前均未授权为已有能力；即使研究通过，也要先审计产品扩展复杂度和 Nautilus/Binance Spot Demo 语义。
