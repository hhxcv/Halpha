# 实际尝试与失败记录

## 2026-07-20 预注册

- 先扫描 `research/**`，确认五种现货资产和本机制此前未用；不依赖产品工作树未提交修改。
- 联网核对原始 momentum 论文、现实 crypto momentum 反证、seasonality 反证与 Binance 官方数据边界。
- 在读取任何 XRP/ADA/LTC/LINK/DOGE 价格前固定：五币宇宙、top-2、90 日、月首开盘、只做多/现金、6/16/26 bp、60/120 日扰动、三段时间、基准和所有门槛。
- 未选纯横截面多空、日历效应、动态全市场或 ML；原因见 README 候选表。

## 命令与结果

预注册代码通过 `python -m py_compile`；SHA-256 为 `89d9192cc5af59325d397028e34d5916a9e34c8ee2baa3a514e3a81475a8d67c`。此时尚未请求任何五币价格数据。

```powershell
python research/mature-alt-spot-top2-momentum/study.py fetch --cache-dir D:/projects/Codex/CodexHome/research-data/halpha/mature-alt-spot-top2-momentum --start-month 2020-09 --end-month 2022-12 --manifest research/mature-alt-spot-top2-momentum/source_manifest_development.json
python research/mature-alt-spot-top2-momentum/study.py analyze --cache-dir D:/projects/Codex/CodexHome/research-data/halpha/mature-alt-spot-top2-momentum --manifest research/mature-alt-spot-top2-momentum/source_manifest_development.json --phase development --output research/mature-alt-spot-top2-momentum/development.json
python research/mature-alt-spot-top2-momentum/study.py qualify-development --development research/mature-alt-spot-top2-momentum/development.json --output research/mature-alt-spot-top2-momentum/selection.json
```

- fetch：140 个 checksum-verified 月归档，0 条补数；manifest identity `3ab96ceeef8e615fb64f1e7929bb7bce093903c74cb642bed2c438e2a5e7d530`。
- 数据质量：五币各 730/730 日，0 gap，`PASS`。
- 固定 90 日 base/stress 总收益 +243.96%/+239.27%，2021/2022 +421.79%/-34.08%，最大回撤 -85.70%，turnover 13.69；基准 +278.74%、最大回撤 -90.57%。
- 60/120 日 base 均为正，但 90 日相对基准回撤只改善 4.87 个百分点，低于预注册 10 个百分点；`FAILED_DEVELOPMENT_GATE_STOP`。
- development digest `0ee0f06d77a05ff80ebb049ff9a4c8ae7546217927a7d138cea165c44736eed5`；selection digest `aefff9437b9caebb18d5af76767656c9346347960f80b23199aaf356f79d1b75`。
- 外部缓存 145 文件、266,808 bytes；Git 内保存所有 URL/checksum/hash 和机器结果。2023–2026 无 research 文件、无缓存文件，未启封。

结论：`DOES_NOT_SUPPORT`。
