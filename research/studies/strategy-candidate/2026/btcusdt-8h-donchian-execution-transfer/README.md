# BTCUSDT 8 小时 Donchian 执行频率固定迁移

## 问题与用途

保持已研究的 20/30/60/90 **日历日** long-only Donchian、10% 波动目标、0.5x 上限与成本假设不变，只把状态判断、跟踪退出和再平衡从日线提高到 Binance 原生 8 小时 bar，能否在现实 funding 与成本后稳定改善单 BTC 趋势表现，并通过顺序门进入 Demo 考虑？

- 类型：`STRATEGY_CANDIDATE`。
- 候选：8h 决策，lookback 为 60/90/180/270 bars，等价于 20/30/60/90 日；long-only；下一根 8h bar 开盘行动。
- 机制：公开研究认为 crypto 的中频趋势比日线更及时，而动态跟踪退出是主要贡献之一。本题只隔离“更快更新”这一项，不使用月度优化、RSI、滚动 Sharpe 选币或 150 币组合。
- 反证：任一顺序门失败；不根据结果改变 lookback、频率、方向、成本或门槛。

## 固定设计

- Binance USD-M BTCUSDT perpetual，UTC 原生 `8h`，实际 funding 逐事件计入。
- 四个 stateful Donchian long-only 分量等权；突破入场，中线只向有利方向更新并退出。
- 270 个 8h bar realized volatility（90 日）、10% 年化目标、0.5x 绝对权重上限、20% 再平衡容忍带。
- favorable/base/stress 为 4 bp taker fee 加 2/10/15 bp 滑点，每单位 turnover 收取。
- 基准：同规则仅每日更新；8h 持续波动目标多头。
- 开发选择偏差按 12 个相关尝试处理：此前 11 个日线 Donchian/carry/Spot/ETH 尝试加本候选。

## 顺序门

- development 2021–2023：base/stress 正；stress CAGR >4%；base Sharpe ≥0.75；12-trial DSR ≥0.80；回撤 >-12%；至少两年正且最差年度 ≥-3%；active days ≥365；turnover ≤50；Sharpe 与 Calmar 均超过每日更新的同规则。
- evaluation 2024–2025：仅开发通过后；base/stress 正；stress CAGR >4%；两年均正；Sharpe ≥0.75；回撤 >-12%；active days ≥240；turnover ≤40；Sharpe 与 Calmar 均超过每日更新同规则。
- confirmation 2026H1：仅评价通过后；base/stress 非负；回撤 >-8%；active days ≥30；评价+确认 base/stress CAGR >4%。

BTC 历史已被此前研究查看，本题不声称 virgin data；证据来自参数不变的机制迁移、明确计入 12 次相关尝试和未读时间窗的顺序门。

## 数据与运行

Git 外官方缓存：`D:/projects/Codex/CodexHome/research-data/halpha/btcusdt-8h-donchian-execution-transfer/`。

```powershell
research/.venv/Scripts/python.exe research/studies/strategy-candidate/2026/btcusdt-8h-donchian-execution-transfer/prepare_data.py --cache-root D:/projects/Codex/CodexHome/research-data/halpha/btcusdt-8h-donchian-execution-transfer
research/.venv/Scripts/python.exe research/studies/strategy-candidate/2026/btcusdt-8h-donchian-execution-transfer/study.py analyze --phase development --cache-root D:/projects/Codex/CodexHome/research-data/halpha/btcusdt-8h-donchian-execution-transfer --manifest D:/projects/Codex/CodexHome/research-data/halpha/btcusdt-8h-donchian-execution-transfer/source_manifest.json --output-dir research/studies/strategy-candidate/2026/btcusdt-8h-donchian-execution-transfer
```

研究不读取产品事实、凭据或配置，不调用交易端点。
