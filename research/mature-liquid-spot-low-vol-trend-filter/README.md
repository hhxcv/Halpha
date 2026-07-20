# 成熟币低波动选择 + 正趋势过滤研究

## 状态、继承和问题

- 稳定基准 `de6b3052f28fe547730e89e58186d4ab397884b1`；正式策略 `ONE_SHOT_DONCHIAN_ATR_BREAKOUT 1.0.0`。
- 候选 `RESEARCH_MATURE_LIQUID_SPOT_LOW_VOL_POSITIVE_TREND_90D_0P5X`；若支持，只计一个低波动家族候选，不与纯低波失败版重复。
- 最终结论：`INSUFFICIENT_EVIDENCE`。过滤后开发最大回撤仍为 -32.95%，未达到 `>-30%`，相对父规则只改善 3.40pp、未达到 5pp。
- 继承反证：纯低波版开发 base +166.78%，但最大回撤 -36.36% 未过 `>-35%` 门；其 evaluation/confirmation 未启封。
- 固定问题：每月先选 90 日实现波动最低三币，再只保留其中自身 90 日收益为正者（每币 1/6，未通过者为现金），能否在不优化止损的前提下把开发回撤降到 -30% 内，并在后两段保持成本后盈利？

## 依据与候选筛选

访问日 2026-07-20。低波动依据与反证沿用 [Burggraf/Rudolf 2021](https://doi.org/10.1016/j.frl.2020.101683)、[Kaya/Mostowfi 2022](https://doi.org/10.1016/j.frl.2021.102422)、[Pyo/Jang 2026](https://doi.org/10.1016/j.frl.2026.109851)。[Liu/Tsyvinski](https://www.nber.org/papers/w24877) 在 BTC、ETH、XRP 报告强 time-series momentum；[Moskowitz/Ooi/Pedersen](https://doi.org/10.1016/j.jfineco.2011.11.003) 在 58 个传统期货上报告 1–12 月方向延续。它们提供“负自身趋势切现金”的独立先验，但不能代替本题验证。

失败修复候选中：把 0.5x 直接降到 0.4x 会机械改善开发回撤且源于事后边界，淘汰；论文止损有样本内阈值优化，淘汰；动态波动率 targeting 增加估计与维护，后置；与低波排序同一 90 日的正/负符号过滤是最小、可解释、无需新参数的修复，选中。

## 固定规则、门槛和数据边界

- 固定与父研究相同的 13 币、月初 UTC 开盘、60/90/180 日邻域、最低三币、每币 1/6、最大 gross 0.5、6/16/26 bp 成本；只新增“该币同窗口收益必须为正”，不把空出的权重重分配。
- 比较基准一：未过滤的纯低波规则（更简单解释）；基准二：13 币月度 0.5x 等权。现货、无杠杆/short/funding，现金收益零。
- 开发门：90 日 base/stress 正；最大回撤 >-30% 且比纯低波至少改善 5pp；60/180 日 base 正；turnover≤30。
- 评价门：90 日 base/stress 正、至少一年正；最大回撤 >-30% 且低于纯低波；60/180 日 base 正。
- 支持门：确认 90 日 base/stress 正；最大回撤 >-25% 且低于纯低波；60/180 日 base 非负；评价+确认复合正。确认或合并收益负为 `DOES_NOT_SUPPORT`，其他失败为 `INSUFFICIENT_EVIDENCE`。

| 区间 | 用途 | 状态 | 启封 |
|---|---|---|---|
| 2021–2022 | exposed development | 已运行；风险修复门失败 | checkpoint 后复用锁定 manifest |
| 2023–2024 | rule-level independent evaluation | 本规则未运行、父研究未下载 | 开发门通过 |
| 2025–2026H1 | confirmation | 本规则未运行、父研究未下载 | 评价门通过 |

开发复用父研究外部缓存；holdout 缓存固定 `D:/projects/Codex/CodexHome/research-data/halpha/mature-liquid-spot-low-vol-trend-filter/`。固定幸存币、单所、日线与成本带限制外推；结果不授权产品或交易。

## 结果与反证

- 数据质量 `PASS`。90 日 base/stress +179.82%/+178.22%，turnover 5.74，最大回撤 -32.95%；父纯低波为 +166.78%/-36.36%，0.5x 等权为 +123.57%/-51.13%。
- 60/180 日 base 也为 +156.65%/+138.79%，但回撤为 -32.00%/-35.97%。正趋势过滤降低换手并提高收益，却没有把任何邻域都带入适合本题的资本保护范围。
- 最强支持是收益与成本稳健性；最强反证是预注册的两个回撤条件同时失败。不能把高收益回测表述为可用 Alpha，也不再围绕相同父策略微调 gross、频率或阈值。
- 开发内容摘要 `f949e4f31b550a1f6a441515b47e85fc247aec88e447618ef93ab70b499f9f62`；selection 摘要 `8db0e3966703db6424e198f00a6240a3adff5744c52c9b8d3da4411f52ef35ec`。数据身份沿用父研究锁定 manifest。
