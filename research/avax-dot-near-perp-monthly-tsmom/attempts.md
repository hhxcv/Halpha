# 实际尝试与失败记录

## 2026-07-20 预注册

- 扫描已有研究；本题使用全新 AVAX/DOT/NEAR 永续数据，只计一个广义趋势候选。
- 联网核对 time-series momentum、crypto trend、现实 liquidation/funding/成本和 Binance 官方数据边界。
- 在任何三币数据前固定三标的、月频、90 日符号、每腿 1/6、总 gross 0.5、60/120 日扰动、6/16/26 bp、三段时间、基准与全部门槛。

## 命令与结果

预注册代码通过 `python -m py_compile`；SHA-256 `fba2d860afc015f953a4a88b54535b0d8487110bda9d928c27d62515f7bd6c2b`。此时未读取或下载任何三币数据。

首次 fetch 在结果分析前停止：AVAX 官方首根归档日线为 2020-09-23，而暖启动请求从 2020-09-01 开始；初始代码把上市前 22 天误判为待补缺且 REST 正确无数据。允许的数据边界修复改为“仅从每个合约首根官方归档 bar 起要求连续”，并在 manifest 记录 `available_start_ms`/`requested_prelisting_days`；经济规则、阶段、门槛均不变。初始代码 hash 保留如上。

修订代码通过 `python -m py_compile`；SHA-256 `8c16d07e1a02681aab2d215c2d6bfb5939c08f59bb2634a7fedc569465750ec0`。

第二次 fetch 同样在结果分析前停止：`NEARUSDT-1d-2020-09.zip.CHECKSUM` 返回官方 404，说明整个暖启动首月在上市前。数据边界修复进一步允许跳过“首个成功月归档以前”的连续 404，并记录月份；任一成功月之后的 404 仍是硬失败。经济规则与门槛不变。

第二次修订通过 `python -m py_compile`；SHA-256 `1204afe0284daab4c9763b93a56f4ba0fe637d9408c554cf57e4d36af2f6450f`。

```powershell
python research/avax-dot-near-perp-monthly-tsmom/study.py fetch --cache-dir D:/projects/Codex/CodexHome/research-data/halpha/avax-dot-near-perp-monthly-tsmom --start-month 2020-09 --end-month 2022-12 --manifest research/avax-dot-near-perp-monthly-tsmom/source_manifest_development.json
python research/avax-dot-near-perp-monthly-tsmom/study.py analyze --cache-dir D:/projects/Codex/CodexHome/research-data/halpha/avax-dot-near-perp-monthly-tsmom --manifest research/avax-dot-near-perp-monthly-tsmom/source_manifest_development.json --phase development --output research/avax-dot-near-perp-monthly-tsmom/development.json
python research/avax-dot-near-perp-monthly-tsmom/study.py qualify-development --development research/avax-dot-near-perp-monthly-tsmom/development.json --output research/avax-dot-near-perp-monthly-tsmom/selection.json
```

- fetch：83 个 checksum-verified 归档、5 条官方 REST 补数、7,472 条暖启动+开发 funding；manifest identity `48988b71d3e9b6a8b79da633ffa52f0ca6fd6712193cf09a84a04ffeee764ae9`。
- 开发质量：三币各 730 日、2,190 funding、0 funding 缺日，`PASS`。
- 90 日 base/stress +27.41%/+26.08%，但 2021 -33.10%、2022 +90.45%，最大回撤 -82.87%，最差单日 adverse -63.99%。60/120 日 base -60.50%/-50.29%。
- `FAILED_DEVELOPMENT_GATE_STOP`；development/selection digest `de3a119e5ae234ec32288a674e532517932d69908e20e26cc68b32f79f2b1f7f` / `f7af6ba22c22d9107f3808c9ffb66b93f2e2016d9b2e0db3799002615362f7a5`。
- 外部缓存 89 文件、740,447 bytes；2023–2026 无缓存或研究结果文件，未启封。

结论：`DOES_NOT_SUPPORT`。
