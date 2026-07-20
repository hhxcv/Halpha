# Halpha 策略研究总目录

更新于 2026-07-21，稳定产品基准提交 `de6b3052f28fe547730e89e58186d4ab397884b1`；正式策略身份固定为 `ONE_SHOT_DONCHIAN_ATR_BREAKOUT 1.0.0 / BTCUSDT-PERP`。

当前共有 32 个完成问题：3 个 `SUPPORTS_WITHIN_SCOPE`、12 个 `DOES_NOT_SUPPORT`、17 个 `INSUFFICIENT_EVIDENCE`。每个子目录保留 checkpoint、来源、数据身份、代码/命令、实际尝试、门、结果与限制；大型公开数据和重演输出在 `D:/projects/Codex/CodexHome/research-data/halpha/`。机器可读查重清单见 `catalog.json`，其中保存每个最终结果文件 SHA-256。

## 三个已支持候选

1. `mature-alt-continuous-cash-carry-basket`：DOGE/XRP/ADA 等资本连续 fully-funded cash-and-carry 六腿篮子。全新 2024–2025-08 确认 base/stress +14.09%/+13.93%，stress 扣 4% 年化门后 +7.25%，回撤 -0.37%。限制：资金与六腿门槛最高；确认止于 2025-08，后续 XRP/SOL 单对研究显示 2025 后 funding 明显压缩，因此不能视为当前收益保证。
2. `trxusdt-voltarget-8pct-long`：TRX 现货 always-long，60 日已实现波动目标 8%、月度、最大 0.5x。全新 2025–2026-06 确认 base/stress +6.95%/+6.65%，stress 扣门后 +0.58%，回撤 -7.21%。限制：只有确认阶段全新、资本门后余量薄、单币/治理/场所风险集中；这是 risk-managed beta，不是 Alpha。
3. `trx-paxg-balanced-spot`：TRX/PAXG 各 25%、现金 50%，月度。全新 2025–2026-06 确认 base/stress +18.74%/+18.25%，stress 扣门后 +11.51%，回撤 -7.26%。限制：2022 为负；2026 仅半年；PAXG 发行人、黄金跟踪、兑换资格与场所风险未建模；这是一项资产配置，不是 Alpha。

这三项不是三个独立 Alpha：第 2、3 项共享 TRX beta，第 1 项属于 funding carry。所有结论仅支持锁定数据、成本与 bar 模型下继续作为候选，不改变产品策略、L4、资金或真实账户状态。

## 查重原则

- 开题前先查 `catalog.json` 与相近目录；同一资产/机制的仓位缩放、阈值或回看期变体必须声明父问题和已暴露数据。
- `DOES_NOT_SUPPORT` 不因换一个近邻参数而重开；`INSUFFICIENT_EVIDENCE` 只在出现真正新数据、独立机制或明确运营简化问题时继续。
- 以后若需产品化，必须由项目所有者明确选中并另开产品任务；先补最小订单、实时 spread/同步成交、保证金/强平、场所/发行人风险和小额 shadow/paper evidence。
