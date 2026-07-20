# TRXUSDT 月度现货时间序列动量

问题：TRXUSDT 180 日正趋势时月度持有 0.5x、否则现金，能否跨顺序的 2023–2024 与 2025–2026-06，在 60bp/换手和 4% 年化全资本门后保持正收益，并比 0.5x 被动持有降低回撤？

- 基准 `de6b3052f28fe547730e89e58186d4ab397884b1`；正式背景 `ONE_SHOT_DONCHIAN_ATR_BREAKOUT 1.0.0 / BTCUSDT-PERP`。
- 候选 `RESEARCH_TRXUSDT_SPOT_POSITIVE_180D_0P5X`。
- 一腿、月度、无需永续/融资，适合个人小资金；单币治理与场所风险高度集中。

大数据目录 `D:/projects/Codex/CodexHome/research-data/halpha/trxusdt-spot-monthly-tsmom/`；研究目录保留 checkpoint、manifest、代码、命令、所有门、结果和重演。

## 结果

结论：`INSUFFICIENT_EVIDENCE`。

开发 base/stress 虽为 +57.17%/+55.45%，但最大回撤 -44.52%，不仅越过 -25% 否定门，也深于 0.5x 被动。正收益不足以把固定仓位版本称为可用；evaluation/confirmation 未获取。

开发/门摘要 `4043ccb11f51d1caab4d100cb169af8b48f8e418eae338c767b05cc19c96297b` / `2eb098673a8e05e54e6d686a5f18c875257a27badc3bd5518441430e8d4f46fe`；Git 外重演 2 文件、13,115 bytes，摘要一致。
