# BTCUSDT 现货多周期 long/cash ensemble 研究

## 状态与问题

- 基准提交 `de6b3052f28fe547730e89e58186d4ab397884b1`；正式 `ONE_SHOT_DONCHIAN_ATR_BREAKOUT 1.0.0` on BTCUSDT-PERP。
- 候选 `RESEARCH_BTCUSDT_SPOT_MULTIHORIZON_LONG_CASH_0P5X`；若支持只计一个 BTC 趋势家族候选。
- 最终结论：`DOES_NOT_SUPPORT`。全新确认 base -10.81%、stress -11.03%，确认收益负触发直接否定。
- 已暴露的单窗口证据：2021–2022 的 60/90/180 日分别 +5.27%/+22.95%/+7.25%；2023–2024 分别 +60.97%/+73.13%/+70.06%。90 日研究因评价回撤比 0.5x BTC 深 1.17pp 为 `INSUFFICIENT_EVIDENCE`；2025–2026H1 未下载。
- 问题：不选择单一赢家，每个 60/90/180 日正信号固定贡献 1/6 BTC 权重，能否在已暴露阶段降低窗口依赖并在全新确认段保持资本与整体盈利？

## 先行依据与选择

访问日 2026-07-20。[Zarattini/Pagani/Barbon](https://ssrn.com/abstract=5209907) 在 crypto 趋势中使用多 Donchian 周期 ensemble 与风险 sizing；本题只借鉴等权聚合思想，不复制其多币、Donchian 或优化。[Liu/Tsyvinski](https://www.nber.org/papers/w24877)、[Moskowitz/Ooi/Pedersen](https://doi.org/10.1016/j.jfineco.2011.11.003) 提供方向延续先验；动量崩溃与上一题相对风险失败是反证。

选择 180 日单窗口会利用已见评价赢家；给窗口动态权重会增加自由度；三符号等权是唯一不挑赢家的最小后续。它仍与正式 BTC 趋势高度相关，不视为机制分散。

## 固定规则、门槛与数据边界

- 每月首个 UTC 日开盘；以之前 close 计算 60/90/180 日 BTC 收益。每个正信号贡献 1/6，gross 为 0、1/6、2/6 或 3/6；余量现金。
- 有利/base/stress 单位换手 6/16/26 bp；阶段末退出。基准为持续 0.5x BTC；单窗口只作预注册诊断。
- 开发门：base/stress 正；最大回撤 >-30% 且比基准改善至少 15pp；turnover≤20。
- 评价门：base/stress 正；最大回撤 >-20%，且不比基准深超过 2pp；三个单窗口均正。
- 支持门：确认 base/stress 非负；最大回撤 >-18%，且不比基准深超过 3pp；三个单窗口均非负；评价+确认复合正。确认或合并负为 `DOES_NOT_SUPPORT`，其他失败为 `INSUFFICIENT_EVIDENCE`。

| 区间 | 状态 | 启封 |
|---|---|---|
| 2021–2022 development | 已运行并通过：+12.66%/-26.55% | checkpoint 后复用 manifest |
| 2023–2024 evaluation | 已运行并通过：+68.43%/-11.69% | 开发门通过后复用 manifest |
| 2025–2026H1 confirmation | 已启封：-10.81%/-18.61% | 评价门通过后下载 |

开发/评价复用锁定缓存；确认缓存 `D:/projects/Codex/CodexHome/research-data/halpha/btcusdt-spot-multihorizon-long-cash/`。单币/单所/现货/现金零收益和规则级留出限制结论；盈利回测不证明 Alpha，结果不授权产品、资金或交易。

## 结果、反证与留存

- 开发 base/stress +12.66%/+12.23%，最大回撤 -26.55%，较 0.5x BTC 改善 22.10pp；开发门通过。
- 评价 base/stress +68.43%/+67.64%，最大回撤 -11.69%，评价日均 block-bootstrap 95% 区间下界略高于零；评价门通过。
- 确认 base/stress -10.81%/-11.03%，2025 -3.64%、2026H1 -7.45%，最大回撤 -18.61%；持续 0.5x BTC -18.69%/-30.32%。60/90/180 日确认收益全部为负（-19.51%/-12.48%/-0.34%），说明 ensemble 不是被单一坏窗口拖累。
- 评价+确认复合仍 +50.22%，但预注册确认收益门直接否定。最强支持是相对持续 BTC 的资本保存；最强反证是后期所有窗口失效，无法列为可用盈利候选。
- 确认缓存 50 个文件、103,103 bytes（48 个归档 + 2 个零补数文件）；manifest SHA-256 `181bddb2468eea567ef2f4ed31934452074f3d7b307fbb65bc6022b16187771e`，逐文件身份可重取。
- 开发/评价/确认/合并内容摘要依次为 `37496622bcf115018789db068c7903246c736f138c17ae0b6f0919d44b454cd2`、`1a7828ca5379808cc359afa995d1bcfa7709ded6066ece527841e1c444e72b5f`、`9808864f3af094eb8afe3b032fc83fecb4cf3e94fb54e30d1d5b654d5d9ffc57`、`825b406b1068ac673ed1a2c8a0759af86ee3e16dc57e8532bafa138e3c770c86`。
