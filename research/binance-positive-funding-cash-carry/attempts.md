# 实际尝试与失败记录

## 2026-07-20 预注册

- 扫描已有 funding carry、ETH 反转和 SMA200 研究；确认本问题只回答裸 carry 明确保留的 spot hedge 差异。
- 联网核对 perpetual 定价、basis risk、funding clamp、Binance spot/futures 档案及 2025 spot 微秒时间戳。
- 固定 BTC development/evaluation、BNB confirmation、1/3/5 bp、正 funding 进入/非正退出、两单位资本和 16/24/40 bp 资本 round-trip 成本。
- 尚未下载或查看任何 spot kline 或 BNB 数据。

## 命令与结果

外部缓存：`D:/projects/Codex/CodexHome/research-data/halpha/binance-positive-funding-cash-carry/`。

```powershell
python research/binance-positive-funding-cash-carry/study.py fetch --cache-dir D:/projects/Codex/CodexHome/research-data/halpha/binance-positive-funding-cash-carry --symbol BTCUSDT --start-month 2021-01 --end-month 2023-12 --manifest research/binance-positive-funding-cash-carry/source_manifest_btc_development.json
python research/binance-positive-funding-cash-carry/study.py analyze --cache-dir D:/projects/Codex/CodexHome/research-data/halpha/binance-positive-funding-cash-carry --manifest research/binance-positive-funding-cash-carry/source_manifest_btc_development.json --phase development --output research/binance-positive-funding-cash-carry/development.json
python research/binance-positive-funding-cash-carry/study.py select --development research/binance-positive-funding-cash-carry/development.json --output research/binance-positive-funding-cash-carry/selection.json
```

- BTC development 72 个官方档案及 3,285 条 funding 完整对齐；`3 bp` 通过开发门并固定。
- 通过后才获取 BTC 2024–2025 spot；固定评价 +5.35%，但 2025 无 active interval，评价完整门失败。
- BNB 跨标的仍有直接决策价值，最后获取 120 个此前未查看档案与 5,478 条 funding；固定确认 +9.04%，但只有 2021 为正。

```powershell
python research/binance-positive-funding-cash-carry/study.py fetch --cache-dir D:/projects/Codex/CodexHome/research-data/halpha/binance-positive-funding-cash-carry --symbol BTCUSDT --start-month 2021-01 --end-month 2025-12 --manifest research/binance-positive-funding-cash-carry/source_manifest_btc_evaluation.json
python research/binance-positive-funding-cash-carry/study.py analyze --cache-dir D:/projects/Codex/CodexHome/research-data/halpha/binance-positive-funding-cash-carry --manifest research/binance-positive-funding-cash-carry/source_manifest_btc_evaluation.json --phase evaluation --selection research/binance-positive-funding-cash-carry/selection.json --output research/binance-positive-funding-cash-carry/evaluation.json
python research/binance-positive-funding-cash-carry/study.py fetch --cache-dir D:/projects/Codex/CodexHome/research-data/halpha/binance-positive-funding-cash-carry --symbol BNBUSDT --start-month 2021-01 --end-month 2025-12 --manifest research/binance-positive-funding-cash-carry/source_manifest_bnb_confirmation.json
python research/binance-positive-funding-cash-carry/study.py analyze --cache-dir D:/projects/Codex/CodexHome/research-data/halpha/binance-positive-funding-cash-carry --manifest research/binance-positive-funding-cash-carry/source_manifest_bnb_confirmation.json --phase confirmation --selection research/binance-positive-funding-cash-carry/selection.json --output research/binance-positive-funding-cash-carry/confirmation.json
python research/binance-positive-funding-cash-carry/study.py combine --development research/binance-positive-funding-cash-carry/development.json --selection research/binance-positive-funding-cash-carry/selection.json --evaluation research/binance-positive-funding-cash-carry/evaluation.json --confirmation research/binance-positive-funding-cash-carry/confirmation.json --output research/binance-positive-funding-cash-carry/results.json
```

最终为 `INSUFFICIENT_EVIDENCE`。没有静默改变阈值或年度门，没有运行产品或真实交易动作。
