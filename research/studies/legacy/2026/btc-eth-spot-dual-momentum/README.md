# BTC/ETH 现货月度双动量研究

## 状态与价值

- 稳定基准 `de6b3052f28fe547730e89e58186d4ab397884b1`；正式策略 `ONE_SHOT_DONCHIAN_ATR_BREAKOUT 1.0.0`、`BTCUSDT-PERP`，只作固定背景。
- 候选 `RESEARCH_BTC_ETH_SPOT_POSITIVE_TOP1_90D_0P5X`。
- 最终结论：`INSUFFICIENT_EVIDENCE`。开发主规则盈利但回撤越界，60 日邻域亏损，后续保持封存。
- 目标：验证个人/小资金可执行的两币现货月频规则，而不是给产品增加第二策略。最多持有 BTC 或 ETH 一种、gross 0.5，负趋势时现金，无杠杆、short、funding 或清算。

## 先行调研与候选筛选

访问日 2026-07-20。[Liu/Tsyvinski](https://www.nber.org/papers/w24877) 在 BTC、XRP、ETH 上报告强 time-series momentum；[Moskowitz/Ooi/Pedersen](https://doi.org/10.1016/j.jfineco.2011.11.003) 在 58 个传统期货上报告 1–12 月方向延续；[Han/Kang/Ryu](https://ssrn.com/abstract=4675565) 强调现实成本下 time-series 强于 cross-sectional，收益主要来自 winner，loser short 有重大损失；[Daniel/Moskowitz](https://www.nber.org/papers/w20439) 是动量崩溃反证。Binance 官方 Public Data/Spot REST 提供日线。

候选中：BTC 单币长仓/现金与正式 BTC 趋势过近，仅作更简单比较；BTC/ETH long-short 增加清算与 loser 反弹，淘汰；多币 top-k 已在山寨币研究失败；BTC/ETH 正绝对动量中选相对更强者，数据和维护最小，选中。

## 固定规则、门槛和否定条件

- 每月首个 UTC 日开盘，以前一日 close 相对 90 日前 close 计算 BTC/ETH 收益；选收益更高且为正者，权重 0.5，否则现金。月内数量固定，阶段末退出。
- 60/180 日为预注册邻域；不搜索窗口、权重、调仓日或成本。有利/base/stress 单位换手 6/16/26 bp。
- 基准：BTC/ETH 各 0.25 月度再平衡；另报告 BTC-only 同符号规则。正式 Donchian 因 perp/一次激活契约不同不做伪代理回放。
- 开发 2021–2022：data `PASS`；90 日 base/stress 正；最大回撤 >-35% 且低于两币基准；60/180 日 base 正；至少 6 个持仓月；turnover≤30。
- 评价 2023–2024：90 日 base/stress 正；最大回撤 >-30% 且低于基准；60/180 日 base 正；至少 6 个持仓月。
- 支持：确认 2025–2026H1 base/stress 非负；最大回撤 >-25% 且低于基准；60/180 日 base 非负；评价+确认复合正。确认或合并收益负为 `DOES_NOT_SUPPORT`，其他失败为 `INSUFFICIENT_EVIDENCE`。

| 区间 | 状态 | 启封 |
|---|---|---|
| 2021–2022 development | 已运行；风险/邻域门失败 | checkpoint 后取 2020-07 起暖启动 |
| 2023–2024 evaluation | 本规则未运行/未下载到本缓存 | 开发门通过 |
| 2025–2026H1 confirmation | 本规则未运行/未下载到本缓存 | 评价门通过 |

外部缓存 `D:/projects/Codex/CodexHome/research-data/halpha/btc-eth-spot-dual-momentum/`。规则级留出不等于价格从未被其他研究使用；单所、USDT、现金零收益、日线和成本带限制外推。盈利回测不是 Alpha 证明，结果不授权产品或交易。

## 实际结果与反证

- BTC/ETH 均 730/730 开发日，0 gap/duplicate/invalid OHLC；60 个官方月归档全部 checksum 通过，REST 补数 0。
- 90 日 base/stress +31.22%/+30.52%，turnover 5.37、14 个持仓月，但最大回撤 -42.64%；两币 0.5x 基准 +20.08%/-47.07%。
- 60 日邻域 -4.61%/-43.24%，180 日 +70.64%/-35.21%，显示结果强烈依赖窗口。预注册 BTC-only 简单比较为 +22.95%/-27.07%，说明 ETH 相对选择提高收益但大幅恶化风险，并非不可替代的解释。
- 最强支持是主规则成本后盈利且略降基准回撤；最强反证是绝对回撤失败、60 日亏损、简单 BTC-only 风险明显更低。不得启封后续或从 180 日赢家反选新主窗口。
- 外部缓存 62 个文件、129,100 bytes；manifest SHA-256 `ce2064e1a5d12f74b53f632bebba4c61a9297df541c797c476df9c7005f2e4eb`；开发/selection 内容摘要 `e9211438687416670d8b4bb870ba3d86cff1158631151aac2de14328f66e50ef` / `a19460946bf0bcdef9988454f9b90375f3e239ccd3c86de29bbe5276861e0fa2`。
