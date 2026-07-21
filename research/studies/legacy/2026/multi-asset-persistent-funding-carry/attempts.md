# 实际尝试与失败记录

## 2026-07-20 预注册

- 继承既有 3 bp carry 的正累计收益与年度/短 episode 反证，不修改其结论。
- 联网核对 perpetual 定价、basis 风险、funding persistence/反馈与 Binance 数据规则。
- 在新 8h basis/funding 前固定两个宇宙、连续两次 3 bp、最高 rate、一次一币、退出、两单位资本、成本和所有门槛。

## 命令与结果

预注册代码通过 `python -m py_compile`；本研究 SHA-256 `4c34fe20204b488b7877cc8bf479a182c2e509cefb827d8b5db99d1a8aa11436`，保留的单币基础执行代码 SHA-256 `4d383f72c0d1ce998b5521a4b24b07061695936303322bc8c569848720e007b1`。此时未下载任何五币 8h basis/funding 数据。

首次 core fetch 已写出完整 manifest 后外层命令在 120 秒边界返回 timeout；manifest 可解析，216 个归档与 9,855 条 funding 身份完整。首次 analyze 仅作未决数据质量尝试：XRP 在官方月归档缺 2022-02-26 至 28、2022-04-01 至 02 的共 15 个 8h funding 边界 price，和公开 issue #297 的归档缺失模式一致；DOGE/ADA 无缺。未补结果为 5 episodes、827 active、base/stress +69.06%/+68.26%，但不能据此启封。

允许的数据完整性修复只从官方 public Spot/USD-M Kline REST 填归档缺失 timestamp，不覆盖归档，并把两类补数哈希写入新 manifest；经济规则与门槛不变。原 `source_manifest_development.json`、`development.json`、`selection.json` 保留。

修订代码通过 `python -m py_compile`；SHA-256 `41408a2b75718132153c0c5338273a4898146ae9f1a28d267eeb4f0c2b1ab2e7`。

```powershell
python research/multi-asset-persistent-funding-carry/study.py fetch --cache-dir D:/projects/Codex/CodexHome/research-data/halpha/multi-asset-persistent-funding-carry --universe core --start-month 2021-01 --end-month 2023-12 --manifest research/multi-asset-persistent-funding-carry/source_manifest_development_backfilled.json
python research/multi-asset-persistent-funding-carry/study.py analyze --cache-dir D:/projects/Codex/CodexHome/research-data/halpha/multi-asset-persistent-funding-carry --manifest research/multi-asset-persistent-funding-carry/source_manifest_development_backfilled.json --phase development --output research/multi-asset-persistent-funding-carry/development_backfilled.json
python research/multi-asset-persistent-funding-carry/study.py qualify-development --development research/multi-asset-persistent-funding-carry/development_backfilled.json --output research/multi-asset-persistent-funding-carry/selection_backfilled.json
```

- 修复后 manifest identity `1587d2f2505177db808e915a5a83dd1b4d35991e6f9588cf4dd95adcdb438609`；XRP futures 15 条补数，其余 market/symbol 0。
- 完整对齐后结果与未补公共交集结果一致：base/stress +69.06%/+68.26%，827 active、5 episodes、中位数 +2.74%、胜率 80%、最大回撤 -1.77%。
- 失败条件：episodes 5 < 10；ADA 0 次也预示资产集中（确认门虽尚未运行）。`FAILED_DEVELOPMENT_GATE_STOP`。
- development/selection digest `d7591b90bdc24848d8ee6ba2b33a0310aaa44441e9eacb335da4c6187f43c412` / `ec6d816208c4013f45f807e732cc743aa8146b454ceac5751cd9103172e31e1a`。
- 外部缓存 225 文件、1,877,485 bytes；Git 内保留两次 manifest/结果。评价和确认未下载。

结论：`INSUFFICIENT_EVIDENCE`。
