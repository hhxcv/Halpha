# Development 结果摘要

## Answer first

`DOES_NOT_SUPPORT`

BTC 冲击后的成熟山寨币 beta-gap 在 2024 年只有约 `+2.08 bp` 的下一 open 后 15 分钟 BTC 中性方向延续；95% UTC 日聚类 CI 为 `[+0.02, +4.13] bp`。它没有击败 BTC 方向 `+2.34 bp` 和币自身方向 `+2.37 bp` 两个简单基准，并远低于预注册的 `12 bp` 最低继续门。因此不支持把这一固定表达继续推进为个人小资金策略候选，2025–2026 保持封存。

## 关键反证

- 2024H1 CI 跨零，主要弱效应集中在 H2。
- 正 BTC 冲击 +4.33 bp，负冲击 -0.21 bp；不是对称规律。
- 额外等待一根 5m bar 后为 +1.66 bp，CI 跨零。
- 95%/99% shock 和 5m/30m 目标均未形成稳定、随强度或时间积累的结果。
- 只有 DOGE 在 15 币 BY-FDR 后显著，但 +6.53 bp 仍低于成本门，且不得从探索结果反向筛币。
- 本题未含 spread、盘口深度、部分成交、funding、mark price、强平或税；这些现实项只会进一步提高从预测到净盈利的门槛。

## 数据和复现身份

- Binance 官方 USD-M 月度 5m Kline；2023-10 至 2024-12，其中 2023Q4 只作 90 日暖启动。
- 16 个标的 × 15 个月 = 240 个 ZIP；85,688,452 bytes；全部通过官方 SHA-256。
- 每标的 131,904 根，完整 UTC 5m 网格；主事件 1,562 个。
- 代码 SHA-256：`3c2d83c79881c81fdc08e9ea0e55a568ecd677c3809b0a86a1f8905fdfff1ea6`。
- `development.json` SHA-256：`dfb3eec79b8503df7bdfa99ae6e9aab77aa0cded46cdc1e8386165bda86c8785`。
- `source_manifest_development.json` SHA-256：`847588d0721c162374b794bc6720dced970c94095bebc1c0d9c965bc59737b81`。
- Git 外原始缓存：`D:/projects/Codex/CodexHome/research-data/halpha/btc-shock-beta-gap-predictability/raw/`；可由 manifest 中官方 URL 和 checksum 重取。

完整数值以 `development.json` 为准。本摘要不扩大为 Alpha、盈利或因果主张。
