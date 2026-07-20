# 实际尝试与失败记录

## 2026-07-20 预注册

- 先查阅相互冲突的 2021、2022 与 2026 原始研究及 Binance 官方数据说明，再从五个候选中选择低波动小组合。
- 固定 13 币、90 日主形成期、60/180 日邻域、最低三币、0.5x、月频、成本带、基准、三阶段和否定条件；没有先下载本题数据或运行候选结果。
- 不采用论文内优化的止损，不建设动态成分数据库，不使用产品数据、配置、凭据或运行时。
- 代码通过 `python -m py_compile`；启封前 SHA-256 为 `31ea82a254942988d9626517c225a1399bf8b0448f4f55f05894a42ccd8a97b9`。

## 开发数据获取

- 首次运行开发 fetch 在 124 秒进程时限处被中止；程序尚未生成 manifest，但已下载文件均在下次运行前重新核对官方 checksum。随后从缓存续传，不改变数据范围或研究规则。
- 续传完成：390 个归档、0 个 REST 补数。命令为 `python research/mature-liquid-spot-low-vol/study.py fetch --cache-dir D:/projects/Codex/CodexHome/research-data/halpha/mature-liquid-spot-low-vol --start-month 2020-07 --end-month 2022-12 --manifest research/mature-liquid-spot-low-vol/source_manifest_development.json`。
- 运行 `analyze ... --phase development` 得到 90 日 base +166.78%、最大回撤 -36.36%；`qualify-development` 输出 `FAILED_DEVELOPMENT_GATE_STOP`。除 `>-35%` 主规则回撤门外，其余开发门均通过；没有放宽该门，也没有获取 evaluation/confirmation。
- 从锁定 manifest 重跑到外部 `repro-development.json` / `repro-selection.json`；内容摘要分别与保留文件一致：`14a585655efc3073f596b03387291fbdc43f6fe55e7021d734f5e6cfb825c7f3`、`f269cfb1e22ebb68ce7df3fe11315d8563badd4589e8687a9d729fa457f91779`。
