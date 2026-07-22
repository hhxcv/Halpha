# 高波动月频单腿 USD-M one-shot SHORT

状态：已完成并在 development 封闭；结论 `INSUFFICIENT_EVIDENCE`。2022–2023 只作为发现证据，2024 是本题唯一打开的正式证据；2025 evaluation 与 2026H1 confirmation 未下载、未查看。

固定问题：用户固定一个 Binance USD-M 工具、`SHORT` 和计划金额时，如果该工具 90 日实现波动在至少 20 个当前流动目标中排名最高三名，是否值得在下一 UTC 月初 open 使用 0.25x 计划资本做空并持有一个月，从而独立实现外部 low-minus-high 波动率溢价的高波空腿？

上一题只检验 low-vol LONG；其预注册 HIGHVOL90-LONG 对照在 2022–2023 为负，仅用于发现本题。Q8 从尚未查看的 2024 开始，不把已知诊断当作通过证据。

方法、顺序门和否定条件见 `preregistration.md`；来源见 `sources.md`；实际尝试见 `attempts.md`。研究只写本目录及 Git 外公开缓存，不修改产品代码、L4、数据库、凭据、资金或真实账户状态。

2024 的 24 笔交易在 base/stress 下扣 4% 年化门槛后的日期均值为 `+0.7709%/+0.5440%`，但 stress 三月块 bootstrap 95% 区间为 `[-0.8139%, +2.3318%]`，且三个不可择优邻域的 stress 均值全部为负。故该精确规格不能视为稳健候选，也不能送入核心资格验证。完整结果见 `result.md`、机器可读证据见 `development.json`、`development_gate.json` 与 `results.json`。
