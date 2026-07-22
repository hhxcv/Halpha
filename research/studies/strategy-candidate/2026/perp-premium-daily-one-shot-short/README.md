# 永续溢价日频单腿 USD-M one-shot SHORT

状态：已完成并在 2024 development 封闭；结论 `DOES_NOT_SUPPORT`。2025 evaluation 与 2026H1 confirmation 未下载、未查看。

固定问题：在至少 20 个当前流动 Binance USD-M 永续目标中，若某工具过去一个完整 UTC 日的官方 premium index 均值为正且位列最高三名，用户固定该工具、`SHORT` 和计划金额时，是否值得在下一 UTC 日开盘使用 0.25x 计划资本做空并持有一天？

该题检验“拥挤多头/正 funding/溢价收敛”的单腿实现，不是把上一题亏损机械取反，也不是现货—永续套利。为避免利用已知 2022 熊市，本题不使用 2022–2023 作为 gate，从 2024 开始。

固定规则、顺序门和否定条件见 `preregistration.md`；来源和候选理由见 `sources.md`；实际尝试见 `attempts.md`。研究只写本目录和 Git 外公开缓存，不修改核心交易、L4、配置、数据库、凭据、资金或真实账户。

development 有 515 笔、256 个 entry days、25 个目标和 6 类；favorable/base/stress 日期扣门均值均为负：`-0.1133%/-0.1634%/-0.2185%`，stress 14 日块 95% 区间为 `[-0.3859%,-0.0633%]`。正 funding 收益不足以覆盖价格延续和零售摩擦，三个邻域也全部失败。完整证据见 `result.md`、`development.json`、`development_gate.json`、`results.json` 与 `validation.json`。
