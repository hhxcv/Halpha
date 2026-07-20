# 实际尝试与失败记录

## 2026-07-20 预注册

- 明确 2021–2022 三币方向已由失败的永续 long/short 研究暴露；新鲜证据从 2023 开始。
- 固定三币、spot、月频、90 日、每币 1/6、负趋势现金、6/16/26 bp、60/120 日扰动和防守型支持门。
- 目标是完整周期盈利与资本保存，不把确认期现金或小幅负收益表述成 Alpha。

## 命令与结果

代码通过 `python -m py_compile`；本研究 SHA-256 `53b05f553d07bcbd3e1599e9844ca2d59cd4743a78c403f4bd40f0342d85c938`，基础 spot 执行代码 SHA-256 `89d9192cc5af59325d397028e34d5916a9e34c8ee2baa3a514e3a81475a8d67c`。此时未下载三币 spot 研究数据。

```powershell
python research/avax-dot-near-spot-long-cash/study.py fetch --cache-dir D:/projects/Codex/CodexHome/research-data/halpha/avax-dot-near-spot-long-cash --start-month 2020-11 --end-month 2022-12 --manifest research/avax-dot-near-spot-long-cash/source_manifest_development.json
python research/avax-dot-near-spot-long-cash/study.py analyze --cache-dir D:/projects/Codex/CodexHome/research-data/halpha/avax-dot-near-spot-long-cash --manifest research/avax-dot-near-spot-long-cash/source_manifest_development.json --phase development --output research/avax-dot-near-spot-long-cash/development.json
python research/avax-dot-near-spot-long-cash/study.py qualify-development --development research/avax-dot-near-spot-long-cash/development.json --output research/avax-dot-near-spot-long-cash/selection.json
```

- manifest `2b15ca11340ba2770bdeb28dd9fdff3180220b31e27f7e2d23f5274728e69ad5`；78 归档、0 补数、数据 `PASS`。
- 90 日 base/stress +96.65%/+95.96%，最大回撤 -31.52%（基准 -62.54%），turnover 3.49；60 日 +65.21%，120 日 -15.45%。
- 失败：120 日 base 不为正；`FAILED_DEVELOPMENT_GATE_STOP`。development/selection digest `800511a82b120ceec9f273aaecad95938e55317d7fb236568e9abd2bf648e453` / `4b10718ab9d41c5f5972a789134018479002f92fb994e269a9b7836c5731bf7b`。
- 外部缓存 81 文件、145,134 bytes；holdout 无文件。

结论：`DOES_NOT_SUPPORT`。
