# 实际尝试与失败记录

## 2026-07-20 预注册

- 在前一 ETH 反转研究运行前，本候选已作为低换手趋势/风险过滤方向保留。
- 开发期 ETH 价格已暴露，明确只作探索；2024–2026 尚未下载或查看。
- 联网核对 Faber SMA 风险过滤、传统 time-series momentum、crypto momentum 现实限制、crypto Donchian 研究及 Binance 官方数据契约。
- 固定 SMA200 long/cash 单一规则、1x、funding、12/32/52 bp round-trip 情景、开发资格门和留出启封条件；没有运行本策略指标。

## 命令与结果

外部缓存：`D:/projects/Codex/CodexHome/research-data/halpha/ethusdt-daily-sma200-long-cash/`；69 个文件、1,308,733 bytes。

```powershell
python research/ethusdt-daily-sma200-long-cash/study.py fetch --cache-dir D:/projects/Codex/CodexHome/research-data/halpha/ethusdt-daily-sma200-long-cash --start-month 2021-01 --end-month 2023-12 --manifest research/ethusdt-daily-sma200-long-cash/source_manifest_development.json
python research/ethusdt-daily-sma200-long-cash/study.py analyze --cache-dir D:/projects/Codex/CodexHome/research-data/halpha/ethusdt-daily-sma200-long-cash --manifest research/ethusdt-daily-sma200-long-cash/source_manifest_development.json --phase development --output research/ethusdt-daily-sma200-long-cash/development.json
python research/ethusdt-daily-sma200-long-cash/study.py qualify --development research/ethusdt-daily-sma200-long-cash/development.json --output research/ethusdt-daily-sma200-long-cash/selection.json
```

- 开发输出：策略 +96.94%、持续持有 +94.27%；策略回撤/持有回撤绝对值比 `0.4229`，三个开发年中 2021、2023 为正，通过固定门。
- 通过后才获取并分析 2024–2025；策略 +24.18%，但 2025 -6.00%，没有通过完整支持门。
- “确认拒绝还是保留防御候选”有直接决策价值，因此按预注册顺序最后获取 2026H1。策略全程现金，收益 0，持续持有 -47.38%。

```powershell
python research/ethusdt-daily-sma200-long-cash/study.py fetch --cache-dir D:/projects/Codex/CodexHome/research-data/halpha/ethusdt-daily-sma200-long-cash --start-month 2021-01 --end-month 2025-12 --manifest research/ethusdt-daily-sma200-long-cash/source_manifest_evaluation.json
python research/ethusdt-daily-sma200-long-cash/study.py analyze --cache-dir D:/projects/Codex/CodexHome/research-data/halpha/ethusdt-daily-sma200-long-cash --manifest research/ethusdt-daily-sma200-long-cash/source_manifest_evaluation.json --phase evaluation --selection research/ethusdt-daily-sma200-long-cash/selection.json --output research/ethusdt-daily-sma200-long-cash/evaluation.json
python research/ethusdt-daily-sma200-long-cash/study.py fetch --cache-dir D:/projects/Codex/CodexHome/research-data/halpha/ethusdt-daily-sma200-long-cash --start-month 2021-01 --end-month 2026-06 --manifest research/ethusdt-daily-sma200-long-cash/source_manifest.json
python research/ethusdt-daily-sma200-long-cash/study.py analyze --cache-dir D:/projects/Codex/CodexHome/research-data/halpha/ethusdt-daily-sma200-long-cash --manifest research/ethusdt-daily-sma200-long-cash/source_manifest.json --phase confirmation --selection research/ethusdt-daily-sma200-long-cash/selection.json --output research/ethusdt-daily-sma200-long-cash/confirmation.json
python research/ethusdt-daily-sma200-long-cash/study.py combine --development research/ethusdt-daily-sma200-long-cash/development.json --selection research/ethusdt-daily-sma200-long-cash/selection.json --evaluation research/ethusdt-daily-sma200-long-cash/evaluation.json --confirmation research/ethusdt-daily-sma200-long-cash/confirmation.json --output research/ethusdt-daily-sma200-long-cash/results.json
```

最终输出 `INSUFFICIENT_EVIDENCE`。没有修改规则、产品文件、L4、资金或真实账户状态。
