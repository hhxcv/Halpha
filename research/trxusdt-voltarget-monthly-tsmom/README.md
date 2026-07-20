# TRXUSDT 波动目标月度趋势

问题：在 TRX 180 日正趋势规则上，用 60 日已实现波动把年化风险目标固定为 15%、仓位封顶 0.5x，能否修复固定仓位的过大回撤，并跨未打开的 2023–2026-06 保持成本和资本门后正收益？

基准 `de6b3052f28fe547730e89e58186d4ab397884b1`；候选 `RESEARCH_TRXUSDT_VOL60_TARGET15_TSMOM180_MAX0P5X`；正式策略仅固定背景。大数据在 `D:/projects/Codex/CodexHome/research-data/halpha/trxusdt-voltarget-monthly-tsmom/`，开发复用父 manifest/cache并记录身份。

## 结果

结论：`INSUFFICIENT_EVIDENCE`。

开发回撤降到 -18.86% 并过门；评估收益 +78.88%，但最大回撤 -21.25% 未过 -15%，且没有优于同风险 always-long。确认未获取。结果支持进一步研究更简单的波动目标多头，不支持当前趋势过滤候选。

开发/评估摘要 `a9ccb372bdd9c55e99a28c2c707255dab65d520ca30518003b078d058c5c1ea0` / `9da922ce9615100140742d2ed7888af7ddd410b7cb559a600404adcd95af7567`；Git 外重演 4 文件、26,430 bytes，摘要一致。
