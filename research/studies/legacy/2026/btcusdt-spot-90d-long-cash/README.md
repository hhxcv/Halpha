# BTCUSDT 现货 90 日 long/cash 研究

## 状态、继承和问题

- 基准提交 `de6b3052f28fe547730e89e58186d4ab397884b1`；正式 `ONE_SHOT_DONCHIAN_ATR_BREAKOUT 1.0.0` on BTCUSDT-PERP。
- 候选 `RESEARCH_BTCUSDT_SPOT_POSITIVE_90D_0P5X`；若支持，只计一个 BTC 趋势家族候选，不与双动量失败版或正式策略重复。
- 最终结论：`INSUFFICIENT_EVIDENCE`。开发通过、评价盈利且邻域为正，但评价回撤略深于持续 0.5x BTC 基准，确认保持封存。
- 本规则在双动量研究运行前已预注册为更简单比较；已暴露开发 90 日 +22.95%、最大回撤 -27.07%。60/180 日、本规则独立评价和确认均未运行。
- 问题：每月仅在 BTC 前 90 日收益为正时持有 0.5x spot，否则现金，能否跨邻域和后续规则级留出保持成本后盈利与资本保护？

## 依据、取舍与固定规则

访问日 2026-07-20。[Liu/Tsyvinski](https://www.nber.org/papers/w24877) 提供 BTC/ETH/XRP time-series momentum 原始证据；[Moskowitz/Ooi/Pedersen](https://doi.org/10.1016/j.jfineco.2011.11.003) 提供跨资产方向延续先验；[Daniel/Moskowitz](https://www.nber.org/papers/w20439) 警告动量崩溃。相对选择已失败，BTC-only 是当时预注册的最简单解释，故选中；不按已暴露结果改窗口、gross、调仓日或成本。

- 每月首个 UTC 日开盘，用前一日 close 与 90 日前 close；正则 BTC 0.5、否则现金。60/180 日是固定邻域。
- 有利/base/stress 单位换手 6/16/26 bp；阶段独立从现金开始、末日退出；基准为持续 BTC 0.5x、月度复位。
- 开发门：data `PASS`；90 日 base/stress 正；回撤 >-30% 且低于基准；60/180 日 base 正；turnover≤20。
- 评价门：base/stress 正；回撤 >-25% 且低于基准；60/180 日 base 正。
- 支持门：确认 base/stress 非负；回撤 >-20% 且低于基准；60/180 日 base 非负；评价+确认复合正。确认或合并负为 `DOES_NOT_SUPPORT`，其他失败为 `INSUFFICIENT_EVIDENCE`。

| 区间 | 状态 | 启封 |
|---|---|---|
| 2021–2022 development | 已运行并通过 | checkpoint 后复用双动量 manifest |
| 2023–2024 evaluation | 已运行；相对回撤门失败 | 开发门通过后启封 |
| 2025–2026H1 confirmation | 本规则未运行、未下载到本缓存 | 评价门通过 |

开发复用双动量缓存；holdout 缓存 `D:/projects/Codex/CodexHome/research-data/halpha/btcusdt-spot-90d-long-cash/`。单币、单所、spot 与现金零收益限制外推；它和正式 perp Donchian 同属 BTC 方向风险但执行/频率不同，不作伪等价回放。盈利回测不是 Alpha 证明，结果不授权产品或交易。

## 实际结果、反证与留存

- 开发 data `PASS`：60/90/180 日 base +5.27%/+22.95%/+7.25%；90 日 stress +22.51%、回撤 -27.07%、turnover 2.77；持续 0.5x BTC 为 -14.56%/-48.65%。开发门通过。
- 评价 data `PASS`：60/90/180 日 base +60.97%/+73.13%/+70.06%；90 日 stress +72.37%、回撤 -14.70%；持续 0.5x BTC +155.52%、回撤 -13.53%。
- 评价主规则虽盈利且绝对回撤受控，但回撤比更简单基准深 1.17pp，违反事前门；同时收益远低于持续 BTC。最强支持是两阶段及三个邻域均正；最强反证是 2023–2024 的趋势过滤没有提供相对风险或收益优势。
- evaluation 外部缓存 62 个文件、126,882 bytes；60 个官方归档 checksum 通过、补数 0。evaluation manifest SHA-256 `97136148d53d1985811310640d851ffef7b2302a6ed5382d77ffb303ba46a64a`；逐文件身份在 manifest。
- 开发/开发 gate/评价/评价 gate 内容摘要依次为 `39b42e3a6c4848f8f4147406cd234589531e5ea45383bb0325c0c0e840f87a2b`、`a58db457d07c0bcddfa9957079bc68699ce44a92f36d64ef1201c15b416d8b5a`、`de6f908badbbcbbd9db7864e531f08804cc42b5adea0753b8a3b4846cfd87248`、`191a91378d172c0f7adf047c15a923edbc0242fc8e4cbfeaeca419563986c687`；确认未下载，不得把评价盈利表述为 Alpha 证明或完整支持。
