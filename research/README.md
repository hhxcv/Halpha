# Halpha 策略研究总目录

更新于 2026-07-21，稳定产品基准提交 `de6b3052f28fe547730e89e58186d4ab397884b1`；正式策略身份固定为 `ONE_SHOT_DONCHIAN_ATR_BREAKOUT 1.0.0 / BTCUSDT-PERP`。

当前共有 32 个完成问题：3 个 `SUPPORTS_WITHIN_SCOPE`、12 个 `DOES_NOT_SUPPORT`、17 个 `INSUFFICIENT_EVIDENCE`。每个子目录保留 checkpoint、来源、数据身份、代码/命令、实际尝试、门、结果与限制；大型公开数据和重演输出在 `D:/projects/Codex/CodexHome/research-data/halpha/`。机器可读查重清单见 `catalog.json`，其中保存每个最终结果文件 SHA-256。

## 共享研究环境与框架分工

本次框架选择采用的产品基准提交为 `d6cd7faa13666bcd12c2b995dcf75459f178b2ca`（`origin/main`，核对于 2026-07-21）；它不改写上方 32 个已完成问题各自记录的历史基准。

新研究默认先使用成熟第三方框架和库，Halpha 只保留问题特有的数据转换、时间对齐、成本或资金费补充、证据门和结果导出，不自建指标库、回测撮合核心、优化器、研究数据库或任务平台。

- VectorBT `1.1.0` 是独立研究环境的首选加速框架，用于适合数组或 bar 信号表达的问题的批量候选筛选、参数与样本敏感性比较、初步组合模拟和分析；它不进入产品构建或运行时，也不是成交和执行语义权威。
- NautilusTrader 是唯一产品量化交易核心，并用于候选获选后的事件顺序、订单、成交、资金费、保证金和在线离线一致性验证。路径或执行依赖会影响结论而 VectorBT 无法可靠表达时，研究直接改用 NautilusTrader 或另一成熟专用组件。

研究环境与产品环境必须分离：VectorBT `1.1.0` 要求 pandas `>=3.0.3,<4.0`，而产品因 NautilusTrader `1.230.0` 的当前兼容边界锁定 pandas `2.3.3`。仓库只锁定 VectorBT 基础依赖，不启用可选 Rust 或 `full` 依赖：

```powershell
D:\Environment\python313\python.exe -m venv research/.venv
research/.venv/Scripts/python.exe -m pip install --require-hashes -r research/requirements.txt
research/.venv/Scripts/python.exe research/verify_vectorbt.py
```

2026-07-21 在 Windows 10 `10.0.19045`、Python `3.13.14` 上完成隔离验证：基础环境共 60 个包、约 641 MiB；微型框架验证的首次 Numba 编译约 15 秒，三个移动平均参数可一次广播计算，rolling 时间切分和 DSR 可用。同 bar 信号会在该 bar 成交，显式前移一格后成交时间随之移动；示例中加入单边 `0.1%` 费用和 `0.2%` 滑点后，总收益由 `1.9231%` 降至 `1.3134%`。这些数值只验证安装、批量与时间切分、选择偏差指标、时序和成本参数生效，不评价任何策略。验证来源为 [VectorBT v1.1.0 发布说明](https://github.com/polakowo/vectorbt/releases/tag/v1.1.0)、[官方依赖元数据](https://github.com/polakowo/vectorbt/blob/v1.1.0/pyproject.toml)、[Portfolio 官方文档](https://vectorbt.dev/api/portfolio/base/)、[splitters 官方文档](https://vectorbt.dev/api/generic/splitters/)、[DSR 官方文档](https://vectorbt.dev/api/returns/accessors/)、[官方许可证](https://github.com/polakowo/vectorbt/blob/v1.1.0/LICENSE.md) 和 [NautilusTrader 官方文档](https://nautilustrader.io/docs/latest/concepts/live/)，访问于 2026-07-21。VectorBT 使用 Apache 2.0 with Commons Clause；当前仅用于个人内部研究，如用途变为向第三方收费提供主要依赖其功能的产品或服务，必须重新检查许可或取得授权。

## 方法审计与新研究用法

2026-07-21 审计发现：32 个完成问题中，31 个已经同时保留 attempts、checkpoint、results 和 study/README，现有留出、失败留存、成本压力和数据身份原则应继续保留；但现有研究没有实际使用 VectorBT，跨问题的总搜索范围、完整候选分布和选择偏差尚未系统记录，支持候选也没有框架无关的决策轨迹可直接核对产品实现。旧研究不批量迁移或改写历史结果，新方法只用于新问题或真正需要重演的旧问题。

新研究采用最小但更深入的路径：

1. 先固定问题、策略族、资产、参数范围、成本情景、选择指标和预计总试验数；
2. 对适合 bar/数组的问题用 VectorBT 一次广播完整候选矩阵，保存全部配置结果而不是只保存最佳列；
3. 探索只做快速筛选，比较证据增加参数稳定区域、成本压力、时间和市场切片；产品考虑使用未暴露固定规则评价或 rolling/expanding walk-forward，广泛搜索时披露实际总试验数，并说明 DSR 采用的独立或有效试验数及敏感性；
4. 收盘生成的信号显式移动到下一可行动时间；单 bar 顺序、订单簿、资金费、保证金或执行反馈会改变结论时转入 NautilusTrader 或明确保守代理；
5. 只有准备供所有者选择的候选才补固定策略说明和小型输入到决策轨迹；产品不导入 VectorBT，而是在相同输入上核对纯策略决策，再由 NautilusTrader 验证订单与执行语义。

这种调整采用 VectorBT 的原生批量、时间切分和统计能力，没有新增研究数据库、服务、调度器、通用优化器或共享产品运行时。专业性来自更完整的搜索披露、独立时间证据和执行语义核对，而不是增加文件数量。

方法调整还参考了 Bailey 与 López de Prado 的 [Deflated Sharpe Ratio 原始论文](https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf) 和 Lawrence Berkeley National Laboratory 的 [Backtest Overfitting in Financial Markets](https://escholarship.org/uc/item/4hn4t174)，访问于 2026-07-21。它们说明批量试验会放大选择偏差，并支持披露试验和采用相称修正；不构成对每个小型规则强制使用复杂统计的理由。

## 当前研究资产宇宙

`market-universe/` 保存 Binance Spot、USDⓈ-M 和 COIN-M 官方公开接口的当前完整快照、Git 外原始响应身份、临时活动筛选与分类研究方法。它把原生加密、stable/fiat-relative、tokenized commodity、TradFi commodity/equity/fund/pre-market perpetual 分开，并按对象身份、工具结构、30–90 日市场质量、历史时点和策略证据五道门指引研究；24 小时档位只用于发现候选，不是产品白名单、主流/长期流动性结论或操纵认定。每个具体问题仍须在 checkpoint 中固定当时采用的 universe 版本和筛选规则。

## 三个已支持候选

1. `mature-alt-continuous-cash-carry-basket`：DOGE/XRP/ADA 等资本连续 fully-funded cash-and-carry 六腿篮子。全新 2024–2025-08 确认 base/stress +14.09%/+13.93%，stress 扣 4% 年化门后 +7.25%，回撤 -0.37%。限制：资金与六腿门槛最高；确认止于 2025-08，后续 XRP/SOL 单对研究显示 2025 后 funding 明显压缩，因此不能视为当前收益保证。
2. `trxusdt-voltarget-8pct-long`：TRX 现货 always-long，60 日已实现波动目标 8%、月度、最大 0.5x。全新 2025–2026-06 确认 base/stress +6.95%/+6.65%，stress 扣门后 +0.58%，回撤 -7.21%。限制：只有确认阶段全新、资本门后余量薄、单币/治理/场所风险集中；这是 risk-managed beta，不是 Alpha。
3. `trx-paxg-balanced-spot`：TRX/PAXG 各 25%、现金 50%，月度。全新 2025–2026-06 确认 base/stress +18.74%/+18.25%，stress 扣门后 +11.51%，回撤 -7.26%。限制：2022 为负；2026 仅半年；PAXG 发行人、黄金跟踪、兑换资格与场所风险未建模；这是一项资产配置，不是 Alpha。

这三项不是三个独立 Alpha：第 2、3 项共享 TRX beta，第 1 项属于 funding carry。所有结论仅支持锁定数据、成本与 bar 模型下继续作为候选，不改变产品策略、L4、资金或真实账户状态。

## 查重原则

- 开题前先查 `catalog.json` 与相近目录；同一资产/机制的仓位缩放、阈值或回看期变体必须声明父问题和已暴露数据。
- `DOES_NOT_SUPPORT` 不因换一个近邻参数而重开；`INSUFFICIENT_EVIDENCE` 只在出现真正新数据、独立机制或明确运营简化问题时继续。
- 以后若需产品化，必须由项目所有者明确选中并另开产品任务；先补最小订单、实时 spread/同步成交、保证金/强平、场所/发行人风险和小额 shadow/paper evidence。
