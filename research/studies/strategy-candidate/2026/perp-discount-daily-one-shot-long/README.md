# 永续折价日频单腿 USD-M one-shot LONG

状态：已完成并在 development 封闭；结论 `DOES_NOT_SUPPORT`。2024 evaluation 与 2025–2026H1 confirmation 未下载、未查看。

固定问题：在至少 20 个当前流动 Binance USD-M 永续目标中，若某工具过去一个完整 UTC 日的官方 premium index 均值为负且位列最低三名，用户固定该工具、`LONG` 和计划金额时，是否值得在下一 UTC 日开盘使用 0.25x 计划资本做多并持有一天？

该题是期现基差信号向当前单腿半自动计划的受限转换，不是现金套利。纯 cash-and-carry 需要同时交易现货和永续两腿，当前核心计划无法原样接收；本题承担方向风险，必须独立证明实际 funding 和零售成本后仍有绝对收益。

方法、候选筛选、顺序门与否定条件见 `preregistration.md`；外部依据和差异见 `sources.md`；重要尝试与失败见 `attempts.md`。研究只写本目录和 Git 外公开缓存，不修改产品代码、L4、配置、数据库、凭据、资金或真实账户。

development 有 1,662 笔、710 个 entry days、25 个目标，但 favorable/base/stress 日期扣门均值均为负：`-0.0223%/-0.0723%/-0.1291%`；2022 与 2023 也分别为负。结果说明文献中的期货基差因子和两腿收敛机制不能直接转换成当前单腿零售 LONG 计划。完整证据见 `result.md`、`development.json`、`development_gate.json`、`results.json` 与 `validation.json`。
