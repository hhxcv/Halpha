# 实际尝试与失败记录

## 2026-07-20 预注册

- 继承 60/90/120 单窗口开发差异，不选择正收益窗口；固定三个周期等权投票。
- 2023–2026 未查看；先用已暴露开发数据检查 ensemble 实现与风险门。
- 固定三币、月频、每个正信号 1/18、最大 0.5、成本、基准和防守型确认门。

## 命令与结果

代码通过 `python -m py_compile`；SHA-256 `0f79f63a776ea2b00fb3fa0c0e7cf258e5c5c29b4609d1c4b4a9b2500d587c0d`，单窗口基础研究 SHA-256 `53b05f553d07bcbd3e1599e9844ca2d59cd4743a78c403f4bd40f0342d85c938`。此时 holdout 未下载。

按顺序执行：

```powershell
python research/avax-dot-near-spot-multihorizon-long-cash/study.py analyze --cache-dir D:/projects/Codex/CodexHome/research-data/halpha/avax-dot-near-spot-long-cash --manifest research/avax-dot-near-spot-long-cash/source_manifest_development.json --phase development --output research/avax-dot-near-spot-multihorizon-long-cash/development.json
python research/avax-dot-near-spot-multihorizon-long-cash/study.py qualify-development --development research/avax-dot-near-spot-multihorizon-long-cash/development.json --output research/avax-dot-near-spot-multihorizon-long-cash/selection.json
python research/avax-dot-near-spot-multihorizon-long-cash/study.py fetch --cache-dir D:/projects/Codex/CodexHome/research-data/halpha/avax-dot-near-spot-multihorizon-long-cash --start-month 2022-09 --end-month 2024-12 --manifest research/avax-dot-near-spot-multihorizon-long-cash/source_manifest_evaluation.json
python research/avax-dot-near-spot-multihorizon-long-cash/study.py analyze --cache-dir D:/projects/Codex/CodexHome/research-data/halpha/avax-dot-near-spot-multihorizon-long-cash --manifest research/avax-dot-near-spot-multihorizon-long-cash/source_manifest_evaluation.json --phase evaluation --authorization research/avax-dot-near-spot-multihorizon-long-cash/selection.json --output research/avax-dot-near-spot-multihorizon-long-cash/evaluation.json
python research/avax-dot-near-spot-multihorizon-long-cash/study.py qualify-evaluation --evaluation research/avax-dot-near-spot-multihorizon-long-cash/evaluation.json --output research/avax-dot-near-spot-multihorizon-long-cash/evaluation_gate.json
python research/avax-dot-near-spot-multihorizon-long-cash/study.py fetch --cache-dir D:/projects/Codex/CodexHome/research-data/halpha/avax-dot-near-spot-multihorizon-long-cash --start-month 2024-09 --end-month 2026-06 --manifest research/avax-dot-near-spot-multihorizon-long-cash/source_manifest_confirmation.json
python research/avax-dot-near-spot-multihorizon-long-cash/study.py analyze --cache-dir D:/projects/Codex/CodexHome/research-data/halpha/avax-dot-near-spot-multihorizon-long-cash --manifest research/avax-dot-near-spot-multihorizon-long-cash/source_manifest_confirmation.json --phase confirmation --authorization research/avax-dot-near-spot-multihorizon-long-cash/evaluation_gate.json --output research/avax-dot-near-spot-multihorizon-long-cash/confirmation.json
python research/avax-dot-near-spot-multihorizon-long-cash/study.py combine --development research/avax-dot-near-spot-multihorizon-long-cash/development.json --evaluation research/avax-dot-near-spot-multihorizon-long-cash/evaluation.json --evaluation-gate research/avax-dot-near-spot-multihorizon-long-cash/evaluation_gate.json --confirmation research/avax-dot-near-spot-multihorizon-long-cash/confirmation.json --output research/avax-dot-near-spot-multihorizon-long-cash/results.json
```

开发和评价先后通过，才分别启封评价和确认。最终确认输出 `base_total=-0.1961442359`、`max_drawdown=-0.2742116431`，合并输出 `DOES_NOT_SUPPORT`、评价+确认复合 `+0.1155792655`。没有尝试替换周期、币、权重或门槛。

复现时将三段 analyze 和 combine 输出改写到外部缓存的 `repro-*.json`；四个 `content_digest` 与保留结果逐项一致。第一次复现调用误把只含预注册内容的 `checkpoint.json` 当作评价授权文件而被程序以 `holdout is not authorized` 拒绝；纠正为实际开发闸门 `selection.json` 后成功。这是安全失败，未改变数据或规则。
