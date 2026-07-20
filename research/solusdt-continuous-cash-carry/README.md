# SOLUSDT 连续 fully-funded cash-and-carry

问题：单一 SOLUSDT 两腿连续 carry 能否在 2023、2024、2025–2026-06 顺序隔离区间中，都覆盖 40bp round-trip 与 4% 年化全资本门，并保持 funding 主导和正的 bootstrap 下界？

- 基准 `de6b3052f28fe547730e89e58186d4ab397884b1`；正式背景 `ONE_SHOT_DONCHIAN_ATR_BREAKOUT 1.0.0 / BTCUSDT-PERP`。
- 候选 `RESEARCH_SOLUSDT_CONTINUOUS_FULLY_FUNDED_CASH_CARRY`。
- 单对两腿适合小资金快速验证，但没有篮子分散，仍非无风险套利。

大型数据放在 `D:/projects/Codex/CodexHome/research-data/halpha/solusdt-continuous-cash-carry/`；仓库保留 checkpoint、manifest、代码、顺序门、结果、失败和重演摘要。

## 结果

结论：`DOES_NOT_SUPPORT`。

2023 与 2024 base 分别 +12.03%/+10.48%，但全新确认转为 -0.3758% base、-0.5358% stress，且 funding 本身为 -0.1226%；2026 切片为负。最终阶段失败优先于三阶段合计正收益，说明早期 carry 不能代表当前可用性。

确认/最终内容摘要 `ad19350cfab11c760b1b8cc76ea4aeb454b4ed61ee9badb8b5a6eacd35b7498e` / `44aa75b8097028ed164c7d928b0fce56f46b34badaca37af5d36d6b417df8521`。Git 外重演目录 `D:/projects/Codex/CodexHome/research-data/halpha/solusdt-continuous-cash-carry-repro/` 有 6 文件、18,846 bytes，所有摘要一致。
