# 半自动策略候选资格前沿审计

## 审计问题

截至稳定基准 `0bdfeffa616260cebd2d2188ddc8deb9e85c77f4`，现有研究是否已经提供“多个”可进入交易核心资格验证的候选；如果没有，哪些结果最接近、缺口是什么、哪些家族不应继续重复搜索？

主要类型：`COMPARATIVE_OR_MECHANISM`。本题不重新回测、不改变历史结论，只按冻结证据身份、当前 L4 产品边界和研究 handoff 门做资格核对。

## Answer first

`DOES_NOT_SUPPORT`

当前有 3 项 legacy 研究得到 `SUPPORTS_WITHIN_SCOPE`，但没有一项满足当前“新方法研究证据 + 框架无关 handoff + 可进入交易核心资格验证”的完整门槛；当前及 legacy `studies/**` 中 `handoff*.json` 数量为 0。它们不能被表述成多个已可用、具备长期盈利能力的策略。

- 六腿 cash-and-carry 篮子有最强结构性收益证据，但个人小资金门槛、同步成交、现货/永续双腿和后期 funding 压缩使它不是当前最小核心候选。
- TRX 现货波动目标是单腿、低换手的 risk-managed beta；转成当前 USD-M one-shot 后，新方法结论为 `INSUFFICIENT_EVIDENCE`，不能沿用现货结论。
- TRX/PAXG 是两腿现货资产配置，不是独立 Alpha；工具、组合状态和当前 Binance USD-M 核心不同。
- CTREND、PPC、高波动月度 short 是近期最接近的单腿永续候选，但均未通过预注册的统计/稳健/广度门，按规则不能生成 handoff。
- 本轮 52 周高点、前景理论价值、短周期残差动量等新增方向均已留下否定证据，不能再以邻近参数换名。

完整逐项状态、证据 SHA-256 和资格理由见 `frontier.json`；判断标准见 `checkpoint.md`；命令与实际核验见 `attempts.md`。

本审计只写 `research/**`，不修改产品、策略注册、L4、配置、资金或真实账户。
