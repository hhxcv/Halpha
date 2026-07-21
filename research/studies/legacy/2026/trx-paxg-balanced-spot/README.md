# TRX/PAXG 25/25 月度现货配置

问题：每月持有 25% TRXUSDT、25% PAXGUSDT、50% 现金，能否跨 2021–2026-06 顺序阶段，在 60bp 压力成本和 4% 年化全资本门后持续为正，并降低相对 0.5x TRX 的回撤？

基准 `de6b3052f28fe547730e89e58186d4ab397884b1`；候选 `RESEARCH_TRX_PAXG_MONTHLY_25PCT_EACH`；正式策略只固定背景。大型数据目录 `D:/projects/Codex/CodexHome/research-data/halpha/trx-paxg-balanced-spot/`。

## 结果与限制

结论：`SUPPORTS_WITHIN_SCOPE`。

全新确认 base/stress +18.74%/+18.25%，stress 扣 4% 年化全资本门后 +11.51%；2025 与 2026 均正，最大回撤 -7.26%，同时浅于 0.5x TRX -14.18% 与 0.5x PAXG -15.16%。评估+确认复合 +97.14%。这支持一个两腿、月度、无融资的候选配置，不证明分散化 Alpha。

限制：开发 2022 为 -5.33%；确认 2026 仅半年且收益 +1.24%；黄金强势可能不持续；PAXG token/发行人/赎回与 Binance 场所风险未进入 OHLC 回测；最小订单与真实月初成交未验证。确认/最终摘要 `00b3402c85ccc865c2176757eadbfeb159976a805edd251036538fa53b0e67f2` / `1208be7124b1967ff50da6f89a62023cf91cb398a70204588d192010094c89b7`。Git 外重演 6 文件、35,895 bytes，摘要全部一致。
