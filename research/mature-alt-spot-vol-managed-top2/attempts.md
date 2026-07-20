# 实际尝试与失败记录

## 2026-07-20 预注册

- 明确继承的已知失败：同五币未管理 90 日 top-2 在 2021–2022 收益高但最大回撤 -85.70%；开发数据已暴露。
- 联网核对 crypto momentum crash、4/8/12 周波动率管理及“尾部风险仍未消失”的原始反证。
- 固定 56 日、20% 年化、1x cap；保留原 90 日/月频/五币/成本，预注册六个邻域扰动和 -35% 风险门。
- 2023–2026 尚未下载；checkpoint 与代码 hash 固定后才运行。

## 命令与结果

预注册代码通过 `python -m py_compile`；SHA-256 `4f09905a3aca475fa768181c6836984df57738f69246e2b60d0c0100cf4b8304`，引用的基础执行代码 SHA-256 `89d9192cc5af59325d397028e34d5916a9e34c8ee2baa3a514e3a81475a8d67c`。此时没有下载或查看 2023–2026 数据。

### 已暴露开发实现门

```powershell
python research/mature-alt-spot-vol-managed-top2/study.py analyze --cache-dir D:/projects/Codex/CodexHome/research-data/halpha/mature-alt-spot-top2-momentum --manifest research/mature-alt-spot-top2-momentum/source_manifest_development.json --phase development --output research/mature-alt-spot-vol-managed-top2/development.json
python research/mature-alt-spot-vol-managed-top2/study.py qualify-development --development research/mature-alt-spot-vol-managed-top2/development.json --output research/mature-alt-spot-vol-managed-top2/selection.json
```

主规则 base/stress +27.50%/+27.15%，最大回撤 -25.76%（未管理 -85.70%），六个邻域全正、turnover 2.80；`PASSED_DEVELOPMENT_GATE`。development/selection digest：`f264b5acb721befbe0639e6eb7b36be49f49b6ac4b30bbb2e750fc00f9f88d59` / `9f2b7ccf8749ead4da68dfd5932b83750eda7ab31b27a4b1c1e088852f9029a9`。

### 独立评价

```powershell
python research/mature-alt-spot-top2-momentum/study.py fetch --cache-dir D:/projects/Codex/CodexHome/research-data/halpha/mature-alt-spot-vol-managed-top2 --start-month 2022-09 --end-month 2024-12 --manifest research/mature-alt-spot-vol-managed-top2/source_manifest_evaluation.json
python research/mature-alt-spot-vol-managed-top2/study.py analyze --cache-dir D:/projects/Codex/CodexHome/research-data/halpha/mature-alt-spot-vol-managed-top2 --manifest research/mature-alt-spot-vol-managed-top2/source_manifest_evaluation.json --phase evaluation --authorization research/mature-alt-spot-vol-managed-top2/selection.json --output research/mature-alt-spot-vol-managed-top2/evaluation.json
python research/mature-alt-spot-vol-managed-top2/study.py qualify-evaluation --evaluation research/mature-alt-spot-vol-managed-top2/evaluation.json --output research/mature-alt-spot-vol-managed-top2/evaluation_gate.json
```

140 个归档、0 补数；manifest `3e80d1efd6f250694d5e4749a069e2a7bf2372dcf0de5076cb1f024d4009b000`。base/stress +60.64%/+59.65%，2023/2024 均正，最大回撤 -21.06%（买持 -50.24%），六个邻域全正；`PASSED_EVALUATION_GATE`。evaluation/gate digest：`5b0cf9ce849d993852ee4d2ccdfe51a5961992a0c263df03272414c2bfae5d09` / `3d8636fad6b8de4b936a9f03059436b4d0aa0229fae40d3975e92624b23011e0`。

### 确认与结论

```powershell
python research/mature-alt-spot-top2-momentum/study.py fetch --cache-dir D:/projects/Codex/CodexHome/research-data/halpha/mature-alt-spot-vol-managed-top2 --start-month 2024-09 --end-month 2026-06 --manifest research/mature-alt-spot-vol-managed-top2/source_manifest_confirmation.json
python research/mature-alt-spot-vol-managed-top2/study.py analyze --cache-dir D:/projects/Codex/CodexHome/research-data/halpha/mature-alt-spot-vol-managed-top2 --manifest research/mature-alt-spot-vol-managed-top2/source_manifest_confirmation.json --phase confirmation --authorization research/mature-alt-spot-vol-managed-top2/evaluation_gate.json --output research/mature-alt-spot-vol-managed-top2/confirmation.json
python research/mature-alt-spot-vol-managed-top2/study.py combine --development research/mature-alt-spot-vol-managed-top2/development.json --evaluation research/mature-alt-spot-vol-managed-top2/evaluation.json --evaluation-gate research/mature-alt-spot-vol-managed-top2/evaluation_gate.json --confirmation research/mature-alt-spot-vol-managed-top2/confirmation.json --output research/mature-alt-spot-vol-managed-top2/results.json
```

110 个归档、0 补数；manifest `ac7ea43454f1872ba3e79832b2d26213be238d15b0270a75036d385fb7ef56c7`。确认 base/stress -20.45%/-20.71%，2025/2026H1 均负，六个邻域全负；`DOES_NOT_SUPPORT`。confirmation/results digest：`69a964239fc32f68bfe9f294dd7da32b15bdc98aad914c83babda34cd43ce510` / `1facfae120c32f88ae3cdeddd3c88675e98dc489aa584f0d6744d3b06dcf9cab`。

新 holdout 外部缓存 240 文件、426,498 bytes；开发缓存由上一研究保留。Git 内保存全部 manifest、结果和失败链。
