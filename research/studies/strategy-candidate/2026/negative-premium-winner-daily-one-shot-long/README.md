# 负溢价赢家日频 USD-M one-shot LONG

状态：已完成并在 2022–2023 development 封闭；结论 `DOES_NOT_SUPPORT`。2024–2026 各后续阶段未下载、未查看。

固定问题：在至少 20 个当前流动 Binance USD-M 永续目标中，若用户固定的工具过去 5 个完整 UTC 日收益位列最高三名且为正，同时前一完整 UTC 日 official premium index 均值为负，是否值得在下一 UTC 日开盘用 0.25x 计划资本 LONG 并持有一天？

经济假设是“价格已经上涨，但永续持仓/基差仍偏空，继续顺价格并站在收 funding 的一侧”，而不是把负 premium 单独视为反转。规则、阶段门和否定条件见 `preregistration.md`；来源与候选筛选见 `sources.md`；实际尝试见 `attempts.md`。研究只写本目录和 Git 外公开缓存，不修改核心交易、L4、配置、数据库、凭据、资金或真实账户。

development 有 971 笔、522 个 entry days、25 目标和 6 类。conjunction 的确胜过三个简单基线，但 favorable/base/stress 日期扣门均值为 `+0.0210%/-0.0291%/-0.0850%`，stress 95% 区间跨零，且 2022/2023 为负/正。它是“弱增量、不可交易”的研究线索，不是策略候选。完整证据见 `result.md` 与机器文件。
