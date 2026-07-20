# XRPUSDT 单对连续 cash-and-carry 简化候选

问题：把已支持的 DOGE/XRP/ADA 六腿篮子简化为单一 XRP 两腿，在完全资本化、40bp round-trip 压力成本和 4% 年化全资本机会成本下，能否在父缓存之后的 2025-09 至 2026-06 全新数据继续为正，并保持可接受的 basis 路径风险？

- 基准提交 `de6b3052f28fe547730e89e58186d4ab397884b1`。
- 正式策略背景 `ONE_SHOT_DONCHIAN_ATR_BREAKOUT 1.0.0`、`BTCUSDT-PERP`；经济机制不同，仅固定身份。
- 候选 `RESEARCH_XRPUSDT_SINGLE_PAIR_CONTINUOUS_CASH_CARRY`。
- 价值重点是六腿降为两腿，代价是失去三币分散；即使支持仍需最小订单、同步成交和保证金/强平验证。

大型公开数据放在 `D:/projects/Codex/CodexHome/research-data/halpha/xrpusdt-single-pair-continuous-cash-carry/`；本目录保留父证据身份、新 checkpoint、manifest、代码、命令、结果、限制和重演摘要。

## 结果

结论：`DOES_NOT_SUPPORT`。

全新确认 base/stress -0.0149%/-0.1749%，stress 扣资本门槛后 -3.4918%；2025 段小幅正但 2026 段为负，bootstrap 区间跨零。funding +0.2395% 虽大于 basis 绝对值，却不足以覆盖一次进出成本和资本门槛。父篮子截至 2025-08 的 XRP 正收益因此不能外推为当前单对可用策略。

确认/最终内容摘要 `510bcfe3bd5fc008c9b2c5123a7ab0edebae837ee4a6251d0a7c61db02dc31a3` / `bf0a0e4bbdddacf5458a16d159cccafaa941129b923a889e0106e84124f06ec3`。Git 外重演目录 `D:/projects/Codex/CodexHome/research-data/halpha/xrpusdt-single-pair-continuous-cash-carry-repro/` 共 2 文件、7,726 bytes，摘要一致。
