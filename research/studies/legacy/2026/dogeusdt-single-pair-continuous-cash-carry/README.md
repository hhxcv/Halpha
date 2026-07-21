# DOGEUSDT 单对连续 cash-and-carry

问题：在父篮子覆盖期之后，DOGE 单对连续 fully-funded cash-and-carry 能否以两腿维持足以覆盖 40bp round-trip 和 4% 年化全资本门槛的收益？

- 基准 `de6b3052f28fe547730e89e58186d4ab397884b1`；正式背景 `ONE_SHOT_DONCHIAN_ATR_BREAKOUT 1.0.0 / BTCUSDT-PERP`。
- 候选 `RESEARCH_DOGEUSDT_SINGLE_PAIR_CONTINUOUS_CASH_CARRY`。
- 它与已支持篮子同属 carry 机制，但运营形态是两腿单对，资本下限更低、集中风险更高。

大数据目录：`D:/projects/Codex/CodexHome/research-data/halpha/dogeusdt-single-pair-continuous-cash-carry/`。研究目录保留所有身份、命令、结果与重演信息。

## 结果

结论：`INSUFFICIENT_EVIDENCE`。

新确认在 base/stress 下仍为 +0.5271%/+0.3671%，且两个年份切片均正，但扣 4% 年化资本门后为 -2.9498%，bootstrap 下界也略低于零。它保留“若资本可产生额外安全收益则可能值得再研究”的未知，但当前完全资本化个人账户模型不支持列为已验证可用策略。

确认/最终内容摘要 `2a8c19f2b255c5a5aa7d227d47a1555a1d929d6f64ff4eaf273fc5e2fac88e96` / `335caca77b99c84c89d09be732878a0c071e520e3c4217a06e44990113d731a9`；Git 外重演 2 文件、7,718 bytes，摘要一致。
