# ETHUSDT 日线 Donchian short-carry 固定转移

## 问题与用途

把 BTC 开发期表现最好的固定 `CARRY_SHORT_SIDE_ONLY` 原样转移到 ETHUSDT USD-M 永续，能否在不改周期、carry 定义、成本、仓位或门槛的条件下跨 instrument、跨时间保持现实成本后盈利，并达到当前 Demo instrument 的产品考虑门？

- 类型：`STRATEGY_CANDIDATE`。
- 候选：20/30/60/90 日完整 Donchian 多空状态；long 不受 carry 限制；short 仅在上一完整 UTC 日实际 funding ≥0（short 收或不付）时允许。
- 用途：判断 BTC 的 +13.97%、Sharpe 0.636 线索是否是 BTC 开发期偶然，还是可迁移的“保留 crypto 正漂移、只在 carry 不冲突时做空”机制。
- 反证：ETH 开发、评价或确认任一固定门失败；不根据 ETH 结果改规则。

ETHUSDT-PERP 已在当前 L4 Demo instruments 中，但当前正式策略仍只支持 BTC。本研究通过也不自动增加第二策略；它只可能形成供产品所有者选择的候选。

## 固定设计

- Binance USD-M ETHUSDT perpetual，UTC `1d`，下一日开盘行动。
- 四个 stateful Donchian 分量等权；突破入场，中线只向有利方向跟踪退出。
- 90 日 realized vol、10% 年化目标、0.5x 绝对权重上限、20% 再平衡容忍带。
- 上一完整 UTC 日实际 funding 净现金流为正时 short 可用；为负时所有负目标归零；long 不过滤。
- favorable/base/stress 为 4 bp taker 加 2/10/15 bp 滑点；逐实际事件和 mark price 计 funding。
- 基准：同参数纯 long-short、纯 long-only、持续波动目标 long。
- 相关搜索数：11（BTC Donchian 六项、BTC carry 三项、BTC Spot 一项、ETH transfer 一项）。

## 顺序门

- development 2021–2023：base/stress 正、stress CAGR >4%、Sharpe ≥0.60、11-trial DSR ≥0.80、回撤 >-15%、至少两年正且最差年度 ≥-5%、active days ≥180，Sharpe 与 Calmar均超过 ETH 纯 long-short 和纯 long-only。
- evaluation 2024–2025：仅在开发通过后；base/stress 正、stress CAGR >4%、两年均正、Sharpe ≥0.60、回撤 >-15%、active days ≥120，Sharpe/Calmar超过两个纯趋势基准。
- confirmation 2026H1：仅在评价通过后；base/stress 非负、回撤 >-10%、active days ≥15，评价+确认 base/stress CAGR >4%。

BTC 候选是在查看 BTC 开发结果后选中，ETH 的其他价格历史也曾被不同规则查看；本题提供固定方法的 instrument transfer 和顺序时间证据，不声称底层价格完全未暴露。

## 数据与运行

Git 外官方缓存：`D:/projects/Codex/CodexHome/research-data/halpha/ethusdt-daily-donchian-short-carry-transfer/`。

```powershell
research/.venv/Scripts/python.exe research/studies/strategy-candidate/2026/ethusdt-daily-donchian-short-carry-transfer/prepare_data.py --cache-root D:/projects/Codex/CodexHome/research-data/halpha/ethusdt-daily-donchian-short-carry-transfer
research/.venv/Scripts/python.exe research/studies/strategy-candidate/2026/ethusdt-daily-donchian-short-carry-transfer/study.py analyze --phase development --cache-root D:/projects/Codex/CodexHome/research-data/halpha/ethusdt-daily-donchian-short-carry-transfer --manifest D:/projects/Codex/CodexHome/research-data/halpha/ethusdt-daily-donchian-short-carry-transfer/source_manifest.json --output-dir research/studies/strategy-candidate/2026/ethusdt-daily-donchian-short-carry-transfer
```

研究不读取产品事实、凭据或配置，不调用交易端点。
