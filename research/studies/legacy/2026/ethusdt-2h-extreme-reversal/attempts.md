# 实际尝试与失败记录

所有记录时间为 Asia/Shanghai（UTC+08:00），数据事件时间为 UTC。任何结果区间一旦被收益、方向、图表或摘要暴露，即使删除文件也保持已暴露。

## 2026-07-20 选题与预注册

- 扫描已有 `research/**`，确认 BTCUSDT funding carry 与本问题不重复，但其 BTC 2021–2026 数据已经暴露，因此改用此前未查看的 ETHUSDT。
- 联网核对中频反转、日内 momentum/reversal、日历效应、配对交易、现实 momentum 风险以及 Binance 官方数据契约。
- 从五个候选中固定 ETHUSDT 2h 极端反转；选择依据、规则、否定条件和三个时间区间在任何 ETH 历史结果前写入 `README.md`。
- 此时没有下载、解析或查看 ETHUSDT 历史价格、funding、收益或汇总。

## 命令与结果

外部缓存：`D:/projects/Codex/CodexHome/research-data/halpha/ethusdt-2h-extreme-reversal/`。

```powershell
python research/ethusdt-2h-extreme-reversal/study.py fetch --cache-dir D:/projects/Codex/CodexHome/research-data/halpha/ethusdt-2h-extreme-reversal --start-month 2021-01 --end-month 2023-12 --manifest research/ethusdt-2h-extreme-reversal/source_manifest_development.json
python research/ethusdt-2h-extreme-reversal/study.py inspect --cache-dir D:/projects/Codex/CodexHome/research-data/halpha/ethusdt-2h-extreme-reversal --manifest research/ethusdt-2h-extreme-reversal/source_manifest_development.json --start 2021-01-01T00:00:00Z --end 2024-01-01T00:00:00Z --output research/ethusdt-2h-extreme-reversal/data_quality_development.json
python research/ethusdt-2h-extreme-reversal/study.py analyze --cache-dir D:/projects/Codex/CodexHome/research-data/halpha/ethusdt-2h-extreme-reversal --manifest research/ethusdt-2h-extreme-reversal/source_manifest_development.json --phase development --output research/ethusdt-2h-extreme-reversal/development.json
python research/ethusdt-2h-extreme-reversal/study.py select --development research/ethusdt-2h-extreme-reversal/development.json --output research/ethusdt-2h-extreme-reversal/selection.json
```

- 36 个 ETHUSDT 2h 月档案全部通过官方 `.CHECKSUM`；funding snapshot 有 3,285 条。缓存共 37 个文件、977,064 bytes。
- 数据质量：13,140/13,140 根预期 bar，0 gap、0 duplicate、0 invalid OHLC；funding 无重复。
- 2σ/3σ/4σ 的 32 bp 后均值分别为 -0.299170%、-0.315410%、-0.057407%；无人通过开发门。
- 4σ 的 gross +0.254648%/笔、有利成本 +0.142593%/笔是最强支持，但 base 区间跨零且仅 2023 略正，不满足固定门槛。
- `selection.json` 输出 `NO_VARIANT_PASSED_DEVELOPMENT_GATE_STOP`。按预注册停止；缓存中没有 2024、2025 或 2026 档案，evaluation/confirmation 未运行。
- manifest、development、selection 文件 SHA-256 分别为 `abbc6c25cfd6d4be0cfa6d12c4d1787f3c9a88afed0e9bd9b53556340251e486`、`81f24e7b3b1805556754e057c68bf489ed426b31141609f1de77c8eda4457c45`、`ad7889f1c17df3253225c99133b8176f73b30d7532148acf1e1030b9c56a12d6`。

没有发生需要改变经济规则的实现问题，也没有运行产品代码、访问产品数据、加载秘密或调用交易所变更端点。
