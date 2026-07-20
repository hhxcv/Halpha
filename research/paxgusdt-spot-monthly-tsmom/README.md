# PAXGUSDT 月度时间序列动量候选

问题：PAXGUSDT 现货在 180 日收益为正时每月持有 0.5x、否则现金，能否在顺序隔离的 2023–2024 与 2025–2026-06 阶段，经过 60bp/换手压力成本和 4% 年化全资本机会成本后仍为正，同时比 0.5x 被动持有具有更浅回撤？

- 稳定基准：`de6b3052f28fe547730e89e58186d4ab397884b1`。
- 正式背景：`ONE_SHOT_DONCHIAN_ATR_BREAKOUT 1.0.0`、`BTCUSDT-PERP`；不同资产/合约，不做虚假同口径比较。
- 候选：`RESEARCH_PAXGUSDT_SPOT_POSITIVE_180D_0P5X`。
- 仅研究候选；不更改产品策略、L4、资金或账户。

大型公开数据目录：`D:/projects/Codex/CodexHome/research-data/halpha/paxgusdt-spot-monthly-tsmom/`。本目录持续保留选题、来源、预注册、manifest、代码、命令、所有门、重要结果、失败和重演摘要，供以后查重与参考。

## 结果

结论：`DOES_NOT_SUPPORT`。

开发期 180 日 base/stress -8.43%/-9.53%，90/270 日 -3.46%/-3.24%，2021 与 2022 均为负。虽然最大回撤 -8.43% 浅于 0.5x 被动的 -11.20%，但候选没有实现正收益，故在获取任何 holdout 前停止。它否定的是锁定 Binance PAXGUSDT、成本、时期与执行模型下的简单规则，不否定黄金趋势研究，也不评价 PAXG 未来收益。

开发/门内容摘要为 `3c5895e7a3b3511d9b055512f37764597b4a984a942c13a32873a9f066e7f365` / `799e9fe6bf25c4990ab3198aebcd61a7192f2841a56e99191f3bff2094ba652a`。Git 外重演目录 `D:/projects/Codex/CodexHome/research-data/halpha/paxgusdt-spot-monthly-tsmom-repro/` 有 2 文件、13,161 bytes，内容摘要一致。
