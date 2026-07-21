# AVAX/DOT/NEAR 现货多周期 ensemble long/cash 研究

## 状态与继承

- 稳定基准：`de6b3052f28fe547730e89e58186d4ab397884b1`；正式策略 `ONE_SHOT_DONCHIAN_ATR_BREAKOUT 1.0.0`。
- 候选：`RESEARCH_AVAX_DOT_NEAR_SPOT_MULTIHORIZON_LONG_CASH_0P5X`。
- 最终结论：`DOES_NOT_SUPPORT`。确认段基础成本收益 -19.61%，触发预注册的 `<-10%` 否定条件；这项失败已保留，不能再以相同问题重复开题或把前两段盈利当成支持。
- 继承失败：同三币单窗口 long/cash 在 2021–2022 的 60/90/120 日 base 为 +65.21%/+96.65%/-15.45%，说明挑单一窗口不稳健；2023–2026 仍未查看。
- 本题不选择赢家，而把 60/90/120 三个正动量信号事前等权合成：每币每个正信号贡献 1/18，单币最多 1/6、组合最多 0.5，余量现金。
- 若获支持，只计一个“多周期现货 trend ensemble”候选，不与单窗口失败或正式 Donchian 重复计数。

## 选题与外部依据

Zarattini、Pagani、Barbon [Catching Crypto Trends](https://doi.org/10.2139/ssrn.5209907) 使用多 Donchian 周期 ensemble 与风险 sizing，说明预先聚合周期可降低单参数依赖；本题只借鉴 ensemble 原理，使用更简单的三收益符号、三币、long/cash、月频。Moskowitz 等 [Time Series Momentum](https://doi.org/10.1016/j.jfineco.2011.11.003)、Liu/Tsyvinski [Risks and Returns of Cryptocurrency](https://doi.org/10.1093/rfs/hhaa113) 提供方向延续先验；Han 等 [realistic crypto momentum](https://doi.org/10.2139/ssrn.4675565) 与 Grobys 等 [crypto momentum crash](https://doi.org/10.1007/s11408-025-00474-9) 提供成本、尾部和稳健性反证；[Binance Public Data](https://github.com/binance/binance-public-data) 是官方数据来源。访问日均为 2026-07-20。

其他候选：挑 60/90 日是事后选择，淘汰；加权优化三个窗口自由度过高，淘汰；加入 short 重现清算风险，淘汰；多周期等权是当前失败的最小成熟修复。

## 固定问题、规则和门槛

问题：三币每月首个 UTC 日开盘，以前一日 close 分别计算 60/90/120 日收益；每个正信号给该币 1/18 spot 权重，负信号为现金。该固定 ensemble 能否在未查看的 2023–2024 正盈利，并在 2025–2026H1 保存资本，使整个未查看期复合收益为正？

- 月频、前一日已知 close、月内固定数量；阶段独立从现金开始。
- 权重只能为 0、1/18、2/18、3/18；组合 gross 0–0.5；不做 short、funding 或杠杆。
- 单位换手成本有利/base/stress 6/16/26 bp；首尾收费；现金收益零。
- 基准为三币各 1/6、月度再平衡的 0.5x long，计同成本。
- 不搜索窗口、权重、币、调仓日、成本或止损；单窗口只作解释，不参与选择。

已暴露开发门：数据 `PASS`；ensemble base/stress 总收益正；最大回撤 >-40% 且比基准至少改善 15 个百分点；turnover <=20。

独立评价门：base/stress 总收益正；至少一个年份正；最大回撤 >-40% 且小于基准。

`SUPPORTS_WITHIN_SCOPE`：确认 base/stress 均 ≥-10%，最大回撤 >-25% 且小于基准；评价+确认复合连接总收益正。确认 base <-10% 或合并收益负为 `DOES_NOT_SUPPORT`，其余未过门为 `INSUFFICIENT_EVIDENCE`。这是防守型盈利候选门，不把现金或小亏本身称为 Alpha。

| 区间 | 用途 | 状态 | 启封 |
|---|---|---|---|
| 2021–2022 | exposed development | 已运行：base +44.32%，最大回撤 -31.52% | checkpoint 后复用锁定 manifest |
| 2023–2024 | independent evaluation | 已启封：base +38.78%，stress +38.34%，最大回撤 -27.07% | 开发门通过后启封 |
| 2025–2026H1 | confirmation | 已启封：base -19.61%，stress -19.81%，最大回撤 -27.42% | 评价门通过后启封 |

只用公开 spot 数据；不读产品数据/凭据/配置，不启动产品运行时或变更端点。开发复用外部缓存 `.../avax-dot-near-spot-long-cash/`，holdout 缓存 `D:/projects/Codex/CodexHome/research-data/halpha/avax-dot-near-spot-multihorizon-long-cash/`。固定幸存币、单所、日线和现金零收益限制外推；结果不授权产品或资金变化。

## 结果、反证与限制

- 开发段通过：base +44.32%，stress +43.93%，最大回撤 -31.52%；同期 0.5x 三币 long 基准最大回撤 -62.54%。
- 独立评价段通过：base +38.78%，stress +38.34%；2023 +37.68%、2024 +0.80%；最大回撤 -27.07%，低于基准 -37.53%。60/90/120 日诊断也都为正。
- 确认段反证：base -19.61%，stress -19.81%；2025 -19.78%、2026H1 +0.21%；最大回撤 -27.42%。三个单窗口确认段收益也全部为负（60/90/120 日分别 -5.63%/-29.58%/-22.96%），说明不是简单的投票平均稀释了一个持续有效窗口。
- 评价与确认复合仍为 +11.56%，且优于同期 0.5x long 基准，但确认段同时越过收益和回撤门槛，因此不能用合并盈利覆盖时变失效。日均收益 block-bootstrap 95% 区间在三段均跨零，统计证据也不强。
- 数据质量三段均 `PASS`；结论只适用于固定幸存币、Binance 现货日线、月频、0–0.5x、现金零收益和 6/16/26 bp 成本假设。未覆盖限价单成交、税务、交易所故障和不同币池选择偏差。

## 数据身份与复现

- 官方来源为 Binance Public Data 月度 spot 日线归档；evaluation manifest SHA-256 `9a08e29ef29816ef0f17cac07e0875bf7bc38e69dc4474066cc9f8dcdcef7e4`，confirmation manifest SHA-256 `31e13487487791c7c0ca5730a06f12c525b1a4b894eeada0ba629697580cc857`。
- holdout 外部缓存共 144 个文件、245,306 bytes（含 6 个复现输出）；原始归档逐文件 URL、大小和 SHA-256 均在两个 manifest 中，能够删除后重取。大型/可重取数据不进入 Git。
- 保留结果内容摘要：development `aef53dc74685966959514d0a03b5cd773a7acae9e6c0c2aa959b967a110105bd`、evaluation `a489f2853bfd979633f845a4d56c038cb9929069fa44332bb94ed6a8c6401acf`、confirmation `213e67a65fcd6fd858ab62f1d4d13bd7212d43c186272ec20137aabca1105875`、combined `b054a7918a2231eb7ed00ea10997860c8f93efbd738e031ec0370beb17389785`。独立重跑四项摘要全部一致。
