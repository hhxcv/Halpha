# 永续正溢价延续日频 USD-M one-shot LONG

状态：已完成并在 2025 evaluation 封闭；结论 `DOES_NOT_SUPPORT`。2026H1 confirmation 未下载、未查看。

固定问题：在至少 20 个当前流动 Binance USD-M 永续目标中，若某工具过去一个完整 UTC 日的官方 premium index 均值为正且位列最高三名，用户固定该工具、`LONG` 和计划金额时，是否值得在下一 UTC 日开盘使用 0.25x 计划资本做多并持有一天？

本题是第 10 题“高 premium 做空”失败后透明注册的方向性延续假设。2024 已暴露为发现期，不进入任何资格门；仅未打开的 2025 和 2026H1 能授予候选资格。它不是 funding 套利：LONG 支付正 funding，并承担完整价格、保证金和 squeeze 反向风险。

固定规则、顺序门和否定条件见 `preregistration.md`；原始研究与候选筛选见 `sources.md`；所有实际尝试见 `attempts.md`。研究只写本目录和 Git 外公开缓存，不修改核心交易、L4、配置、数据库、凭据、资金或真实账户。

evaluation 有 273 笔、196 个 entry days、22 个目标和 6 类；favorable/base/stress 日期扣门均值均为负：`-0.1160%/-0.1659%/-0.2216%`，stress 14 日块 95% 区间为 `[-0.3252%,-0.1214%]`。2024 发现期的价格延续在 2025 反向，三个邻域与三个简单基线也全部不支持。完整证据见 `result.md`、`evaluation.json`、`evaluation_gate.json`、`results.json` 与 `validation.json`。
