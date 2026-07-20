# 实际尝试与失败记录

## 2026-07-20 预注册

- 扫描已有研究，确认本问题属于趋势家族后续，不重复计数 ETH long/cash。
- 联网核对传统和 crypto time-series momentum、低自由度均线、现实 liquidation/fat-tail 反例和 Binance 官方数据。
- 在任何 SOL 数据前固定 SMA200、0.5x long/short、funding、6/16/26 bp turnover 成本、三段时间和 adverse/gate。

## 命令与结果

外部缓存：`D:/projects/Codex/CodexHome/research-data/halpha/solusdt-daily-sma200-long-short/`。

```powershell
python research/solusdt-daily-sma200-long-short/study.py fetch --cache-dir D:/projects/Codex/CodexHome/research-data/halpha/solusdt-daily-sma200-long-short --start-month 2021-01 --end-month 2023-12 --manifest research/solusdt-daily-sma200-long-short/source_manifest_development.json
python research/solusdt-daily-sma200-long-short/study.py analyze --cache-dir D:/projects/Codex/CodexHome/research-data/halpha/solusdt-daily-sma200-long-short --manifest research/solusdt-daily-sma200-long-short/source_manifest_development.json --phase development --output research/solusdt-daily-sma200-long-short/development.json
python research/solusdt-daily-sma200-long-short/study.py qualify --development research/solusdt-daily-sma200-long-short/development.json --output research/solusdt-daily-sma200-long-short/selection.json
```

首次运行保存为原始失败证据：1,090/1,095 日、2 个 gap、缺 2022-02-26 至 28 和 2022-04-01 至 02，`data_quality=FAIL`；未补数的 base 总收益 +191.37%、2022 +51.22%、2023 -18.72%、bootstrap 下界 -0.0454%。`development.json`、`selection.json` 和原 manifest 不覆盖。

## 数据完整性调查与允许修复

- 公开只读 `GET https://fapi.binance.com/fapi/v1/klines` 对上述 5 天均返回连续 SOLUSDT 1d OHLC。
- [Binance Public Data](https://github.com/binance/binance-public-data) 明确 USD-M Kline 归档来自该端点、提供 checksum，并说明归档可能因已发现问题更新。
- [官方仓库 issue #297](https://github.com/binance/binance-public-data/issues/297) 独立记录 2022-04-01 至 02 的 futures monthly Kline 缺失，受影响列表包含 SOL；未找到同等可靠来源解释 2 月三天，故只把 API 响应当作补数来源，不猜原因。
- 代码修订仅新增“归档缺失 timestamp 才补数”、补数哈希入 manifest、毫秒/微秒规范化，并阻止 `data_quality!=PASS` 启封 holdout。初始代码 SHA-256 `f4c11129f30398d0860918b4602a102678c2f45bf5713532889de0c7dc1619c9`，修订后 `57a08da1d3706167496749ce6585f91dccc448d874169e8ac457565ddccc54f6`；规则、成本、区间和门槛不变。

```powershell
python -m py_compile research/solusdt-daily-sma200-long-short/study.py
python research/solusdt-daily-sma200-long-short/study.py fetch --cache-dir D:/projects/Codex/CodexHome/research-data/halpha/solusdt-daily-sma200-long-short --start-month 2021-01 --end-month 2023-12 --manifest research/solusdt-daily-sma200-long-short/source_manifest_development_backfilled.json
python research/solusdt-daily-sma200-long-short/study.py analyze --cache-dir D:/projects/Codex/CodexHome/research-data/halpha/solusdt-daily-sma200-long-short --manifest research/solusdt-daily-sma200-long-short/source_manifest_development_backfilled.json --phase development --output research/solusdt-daily-sma200-long-short/development_backfilled.json
python research/solusdt-daily-sma200-long-short/study.py qualify --development research/solusdt-daily-sma200-long-short/development_backfilled.json --output research/solusdt-daily-sma200-long-short/selection_backfilled.json
```

复跑得到 1,095 日、0 gap、`PASS`；5 行补数 SHA-256 `6ce36c95cfa8138f3e70a7ccd047da029fdb20e4dd86fe3f8fcd13826451ef0b`。base 总收益 +166.84%，2021/2022/2023 为 +137.06%/+38.48%/-18.72%，bootstrap 日均 95% CI [-0.0526%, +0.3289%]，最大回撤 -71.88%，最差 episode adverse -9.72%。开发门失败，2024–2026 未下载、未查看。

外部缓存复跑时共 38 个文件、332,697 bytes；Git 内保留 36 个归档 checksum/URL、funding 与补数哈希、两次结果及失败原因。结论：`DOES_NOT_SUPPORT`。
