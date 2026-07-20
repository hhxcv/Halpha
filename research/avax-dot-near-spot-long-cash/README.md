# AVAX/DOT/NEAR 现货月度正动量 long/cash 防守研究

## 状态、继承与边界

- 稳定产品基准提交：`de6b3052f28fe547730e89e58186d4ab397884b1`
- 固定正式策略：`ONE_SHOT_DONCHIAN_ATR_BREAKOUT` `1.0.0`
- 候选身份：`RESEARCH_AVAX_DOT_NEAR_SPOT_MONTHLY_LONG_CASH_0P5X`
- 固定标的：Binance Spot `AVAXUSDT`、`DOTUSDT`、`NEARUSDT`；每币最多 1/6，组合最多 0.5x，余量 USDT 现金。
- 本题继承 `avax-dot-near-perp-monthly-tsmom` 的开发失败：裸 long/short 初始 0.5x 仍有 -82.87% 回撤和 -63.99% 单日 adverse。2021–2022 方向数据已暴露，只作设计/实现集；2023–2026 未查看、未下载。
- 用途：检验适合个人小资金的“参与正趋势、负趋势现金”防守策略；不是产品策略、收益保证、资金决定或真实交易许可。

只用公开 spot 数据和独立研究代码；不读产品数据库、业务数据、秘密或运行配置，不启动产品运行时，不调用交易所变更端点。研究写入仅在 `research/**`，大数据放 Git 外。

## 候选筛选与外部研究

| 候选 | 与已知失败的关系 | 个人适配 | 取舍 |
|---|---|---|---|
| 三币独立 90 日正动量，负则现金 | 直接移除 short squeeze；最多 0.5x | 现货、月频、0–3 币 | **选中** |
| short 权重降到 0.05 | 仍保留熊市收益 | 仍有清算/funding/跳涨尾险，参数事后 | 淘汰 |
| 每日重平衡 short | 控制名义漂移 | 日频三腿永续和成本不适合个人 | 淘汰 |
| 止损 | 截断损失 | bar 内顺序和参数自由度 | 淘汰 |

联网来源（访问日 2026-07-20）：Faber [A Quantitative Approach to Tactical Asset Allocation](https://ssrn.com/abstract=962461) 提供低自由度 long/cash 均线先验；Liu、Tsyvinski [Risks and Returns of Cryptocurrency](https://doi.org/10.1093/rfs/hhaa113) 提供 crypto time-series momentum 先验；Han 等 [realistic crypto momentum](https://doi.org/10.2139/ssrn.4675565) 要求成本和日内/清算现实；Grobys 等 [Cryptocurrency momentum has (not) its moments](https://doi.org/10.1007/s11408-025-00474-9) 证明 crash 与尾部风险不可由均值掩盖；[Binance Public Data](https://github.com/binance/binance-public-data) 提供 spot 日线、checksum、2025 微秒时间戳和公开补缺边界。

## 固定问题、规则和门槛

问题：每月首个 UTC 日开盘，对每币以前一日 close 相对 90 日前 close 的符号决定 `+1/6` spot 或现金，能否在未查看的 2023–2024 获得正收益，并在 2025–2026H1 控制损失，使 2023–2026 合并仍正、回撤明显小于 0.5x long？

- 每月一次；只用前一日及更早 close；月内固定数量；阶段独立从现金开始。
- 90 日主规则；60/120 日只作预注册邻域反证。
- 每个正动量资产 1/6，最多 0.5x；负/零为现金；现金收益固定 0。
- 单位绝对名义换手有利/base/stress 6/16/26 bp；首尾收费。
- 基准为三币各 1/6、月度再平衡 0.5x long，计相同成本；现金为零。
- 不搜索币、窗口、名义、调仓日、成本、权重或止损。

已暴露开发实现门：数据 `PASS`；90 日 base/stress 总收益为正；最大回撤 > -40% 且比 0.5x long 至少改善 15 个百分点；60/120 日 base 均正；turnover <=20。失败即停止。

独立评价门：90 日 base/stress 总收益为正；2023/2024 至少一年正；最大回撤 > -40% 且小于 0.5x long；60/120 日 base 均正。

`SUPPORTS_WITHIN_SCOPE` 的确认目标是资本保存而非每段收益最大化：2025–2026H1 90 日 base/stress 均 ≥-5%，最大回撤 >-25% 且小于 0.5x long，60/120 日 base 均 ≥-5%，并且评价与确认复合连接后的总收益为正。确认 base <-5% 或合并收益为负则 `DOES_NOT_SUPPORT`；其余未过门为 `INSUFFICIENT_EVIDENCE`。支持仍不证明 Alpha；现金期零收益不是盈利。

## 时间和数据

| 区间 | 用途 | 状态 | 启封 |
|---|---|---|---|
| 2021-01-01 至 2023-01-01 | exposed development | 已运行；120 日扰动否定 | checkpoint 后；2020-11 起暖启动，早期信号不足则现金 |
| 2023-01-01 至 2025-01-01 | independent evaluation | **未查看、未下载** | 开发门失败，保持封存 |
| 2025-01-01 至 2026-07-01 | confirmation | **未查看、未下载** | 开发门失败，保持封存 |

Python 3.11.9、pandas 2.3.3、numpy 2.4.6；外部缓存 `D:/projects/Codex/CodexHome/research-data/halpha/avax-dot-near-spot-long-cash/`。固定幸存币、单所、USDT 零收益和日线执行限制外推；未建模订单簿、部分成交、停牌、过滤器、资金收益和税务。

## 实际结果与结论

78 个官方月归档通过 checksum，0 补数；三币开发期各 730/730 日，`data_quality=PASS`。

| 指标 | 60 日 | 固定 90 日 | 120 日 | 0.5x long |
|---|---:|---:|---:|---:|
| base 总收益 | +65.21% | **+96.65%** | **-15.45%** | +105.39% |
| 90 日 stress | — | +95.96% | — | — |
| 90 日 2021 / 2022 | — | +103.83% / -3.52% | — | — |
| 最大回撤 | — | -31.52% | — | -62.54% |
| 90 日 turnover / invested days | — | 3.49 / 49.73% | — | — |

90 日降低回撤且成本带为正，但 120 日邻域大幅为负；单一窗口的方向和退出速度决定结果，未过预注册稳健性门。结论：`DOES_NOT_SUPPORT`。2023–2026 未下载；后续只能把三个窗口事前合成为新问题，不能在当前结果上挑选赢家。

命令与身份见 `attempts.md`，机器证据见 `results.json`。研究不改变产品、L4、资金或账户。
