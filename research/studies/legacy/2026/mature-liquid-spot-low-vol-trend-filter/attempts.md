# 实际尝试与失败记录

## 2026-07-20 预注册

- 纯低波开发门因 -36.36% 回撤失败后，保留其收益信号但不放宽门槛、不按已知结果缩放固定 gross。
- 搜索并核对 time-series momentum 原始论文；固定同周期正趋势过滤作为最小风险修复。没有先运行新规则或下载父研究仍封存的 2023–2026 数据。
- 代码通过 `python -m py_compile`；启封前 SHA-256 `c58cff2b0b83b9052521ab800620a199e7cfabd6ab59d2a298efd4150fe52c46`。
- 从父研究锁定开发 manifest 运行 `analyze`：90 日 base +179.82%、最大回撤 -32.95%；`qualify-development` 输出 `FAILED_DEVELOPMENT_GATE_STOP`。失败项为 `>-30%` 绝对回撤门及相对父规则至少改善 5pp；没有启封后续数据。
- 重跑到外部 `repro-development.json` / `repro-selection.json`，两项内容摘要均与 Git 内保留结果一致。
