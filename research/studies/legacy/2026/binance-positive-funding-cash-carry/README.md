# Binance 同场所正 funding 现货—永续 carry 候选研究

## 状态与边界

- 稳定产品基准提交：`de6b3052f28fe547730e89e58186d4ab397884b1`
- 固定正式策略：`ONE_SHOT_DONCHIAN_ATR_BREAKOUT` `1.0.0`
- 候选身份：`RESEARCH_BINANCE_POSITIVE_FUNDING_CASH_CARRY`
- 场所：Binance；long USDT spot + short 同标的 USDⓈ-M perpetual；两腿等初始名义。
- cutoff：BTC 评价至 `2026-01-01T00:00:00Z`；BNB 跨标的确认至同一日期。
- 用途：判断这一低频、同场所、方向近中性的 carry 家族是否有值得保留的盈利潜力；不是无风险套利证明、产品策略、资金决定或真实交易授权。

研究不读取产品业务数据、数据库、秘密或运行配置，不启动产品运行时，不调用交易所变更端点。公开大文件位于 Git 外；研究目录保存可重取身份、代码、检查点、尝试、原始小型结果和限制。

## 去重与候选选择

已有 `btcusdt-next-funding-carry` 研究否定的是单腿方向持仓：下一 funding 高度可预测，但价格敞口和成本吞没收入。本问题不重复该结论，而是直接检验它留下的差异——用同场所 spot/perp 两腿消除大部分方向价格风险后，funding 是否仍能覆盖 basis 和执行成本。

| 候选 | 未解决差异与决策价值 | 个人/小资金适配 | 取舍 |
|---|---|---|---|
| 同场所 positive funding cash-and-carry | 直接隔离 funding 与 basis；机制不同于正式趋势和失败的裸 carry | 两腿但同场所；8h 决策；可按小名义缩放 | **选中** |
| 跨场所 funding arbitrage | 可比较更高 funding | 跨场所库存、转账、双重故障和资金占用 | 淘汰 |
| 负 funding 反向 carry | 需要 short spot、借币利率和可借数量历史 | 小资金和历史数据复杂度更高 | 本轮不支持 |
| 交割合约 basis | 没有 perpetual funding，需到期曲线和滚动 | 与当前明确缺口距离更远 | 延后 |

## 先行调研（访问日 2026-07-20）

1. He、Manela、Ross、von Wachter, [Fundamentals of Perpetual Futures](https://arxiv.org/abs/2212.06888)（2022）：推导 frictionless perpetual 定价和含交易成本的无套利边界，并实证 implied arbitrage。它支持 spot/perp 对冲是比单腿 carry 更简单的机制解释，也明确交易摩擦决定可实现边界。
2. Ackerer、Hugonnier、Jermann, [Perpetual Futures Pricing](https://www.nber.org/papers/w32936)（NBER WP 32936, 2024；后续发表于 Mathematical Finance）：说明 periodic funding 的锚定作用和复制条件。它不能替代 Binance 实际费率、basis、保证金和执行验证。
3. Gornall、Rinaldi、Xiao, [Perpetual Futures and Basis Risk: Evidence from Cryptocurrency](https://ssrn.com/abstract=5036933)（2025）：把受限套利资本和 basis 风险作为 perpetual 偏离的重要解释。它要求本研究保留 basis PnL 和资本占用，而不能把策略叫无风险。
4. Dai、Li、Yang, [Arbitrage in Perpetual Contracts](https://doi.org/10.2139/ssrn.5262988)（2025）：用 Binance 数据研究 funding clamp 与 model-free bounds，说明简单费用不足以解释持续价差。它提示当前固定“上一期 funding 持续”规则只是最小可证伪版本。
5. [Binance Public Data](https://github.com/binance/binance-public-data)：spot 与 USD-M kline 字段、月档、`.CHECKSUM`，并明确 spot 自 2025-01-01 起时间戳改为微秒；脚本必须规范到毫秒后再对齐。
6. [Binance USDⓈ-M Funding Rate History](https://developers.binance.com/en/docs/derivatives/usds-margined-futures/market-data/rest-api/Get-Funding-Rate-History)：公开实际 fundingTime/rate。历史结算 rate 只在结算后用于下一持有区间，不使用未来预测字段。

## 固定问题与规则

问题：一次 funding 结算后，若已知 rate 至少为固定阈值，则按相同初始名义 long spot、short perpetual，在以后某次已结算 rate 非正时退出；这一规则能否在两腿 basis、实际后续 funding、全额两单位资本和现实成本后保留正收益，并从 BTC 迁移到未查看的 BNB？

- 事件：实际 fundingTime 归到对应 8h bar 边界；当前 rate 结算后才决定下一 funding 区间。
- 入场：不持仓且当前 rate ≥ `1/3/5 bp` 中的固定阈值时，在同一边界的 spot/perp 8h open 之后建立两腿；当前 rate 不计为收入。
- 持有：spot 与 short perp 数量在一个 episode 内固定，不按 8h 重平衡；在下一边界用实际 next rate 和两腿 open 计算增量。
- 退出：下一已结算 rate ≤ 0 时，先计该次 funding，再在对应边界退出；样本末强制退出。
- 资本：1 单位购买 spot，另保留 1 单位作为 fully-collateralized perp short 资本；所有收益除以 2。没有用杠杆放大，也不把交易所 cross-margin 当成已验证能力。
- 成本：每次建仓或退出的两腿合计，有利/base/stress 分别为一腿初始名义的 16/24/40 bp；完整 round trip 换算成两单位资本为 16/24/40 bp。
- 搜索：BTC 2021–2023 只比较 entry `1/3/5 bp`；不搜索退出、持有、重平衡、成本或标的。
- 基准：不交易为零；分解 funding、basis 和成本。正式单腿 Donchian/ATR 不具经济可比性，不运行代理。

开发门：至少 300 个 active 8h 区间，base 固定资本累计收益为正，2021–2023 至少两年为正，9-interval circular-block bootstrap active interval 均值 95% 下界大于零。通过者只按下界、再按累计收益选一个阈值；无人通过即停止，不获取 BTC spot 后期和 BNB 数据。

`SUPPORTS_WITHIN_SCOPE` 还要求：固定阈值在 BTC 2024–2025 base 累计收益为正、两年均正、active interval 均值区间下界大于零；在完全未查看的 BNB 2021–2025 至少 600 个 active 区间、五年至少三年为正、累计收益与区间下界均为正。评价累计为负则 `DOES_NOT_SUPPORT`，其余为 `INSUFFICIENT_EVIDENCE`。

## 数据暴露与启封

| 数据 | 用途 | 暴露状态 | 启封条件 |
|---|---|---|---|
| BTC spot/perp basis 2021–2023 | development | spot 与 basis 未查看；perp/funding 曾被裸 carry 查看 | 固定代码与 checkpoint 后运行 |
| BTC spot/perp basis 2024–2025 | evaluation | spot 与 basis 未查看；perp/funding 曾暴露 | 仅开发门通过后 |
| BNB spot/perp/funding 2021–2025 | cross-instrument confirmation | 完全未查看 | 固定 BTC 评价完成后最后运行 |

问题、阈值、两单位资本、成本、退出、门槛和启封规则在任何 spot 或 BNB 数据下载前固定。下载/checksum/解析/时间戳规范错误可以修复；经济规则变化必须保留旧尝试并重新判断未暴露边界。

## 未覆盖风险

历史 8h open 不能证明两腿同价同步成交；basis 在 bar 边界内的跳动、订单簿深度、部分成交、腿风险、spot 数量精度、perp 保证金、清算、ADL、资金划转、账户模式、USDT 机会成本和税务未完整建模。全额两单位资本降低但不消除 short leg 的账户级清算风险。正结果只能表述为有界候选证据，不能叫无风险套利。

## 环境与留存

Python 3.11+ 标准库；外部缓存为 `D:/projects/Codex/CodexHome/research-data/halpha/binance-positive-funding-cash-carry/`。每个 manifest 保存两类档案 URL、官方 SHA-256、大小、funding snapshot 和时间戳规则；研究内保存所有小型输出。

实际命令、失败、启封和结论在运行后追加。

## 实际结果

所有 spot、perp 与 funding 事件在 8h 边界完整对齐；BTC development/evaluation 和 BNB confirmation 分别有 3,285、2,193、5,478 个事件，无缺少边界价格。2025 spot 微秒时间戳规范到毫秒后与 futures 对齐。

BTC 开发期固定选择 `3 bp`：

| 阈值 | active 8h | episodes | 两单位资本 base 累计收益 | active mean bootstrap 95% | funding / basis / cost |
|---|---:|---:|---:|---:|---:|
| 1 bp | 2,265 | 106 | +5.24% | [-0.0019%, +0.0066%] | +29.56% / +1.12% / -25.44% |
| 3 bp | 984 | 5 | +23.13% | [+0.0183%, +0.0293%] | +24.07% / +0.26% / -1.20% |
| 5 bp | 647 | 4 | +18.87% | [+0.0229%, +0.0364%] | +19.62% / +0.21% / -0.96% |

`3 bp` 通过并按预设下界优先被固定。BTC 2024–2025 评价累计 `+5.35%`，bootstrap 下界为正，最大非复合回撤 `-0.24%`；但 473 个 active 区间全部在 2024，2025 没有入场，未满足“两年均正”。

全新 BNB 2021–2025 确认累计 `+9.04%`，active mean 区间 `[+0.0034%, +0.0292%]`，说明机制能够跨标的出现；但 55 个 episodes 只有 27.3% 为正，年度收益主要来自 2021（`+11.40%`），2023–2025 分别约 `-1.97%`、`-0.21%`、`-0.19%`，没有通过跨年份门。

## 结论

`INSUFFICIENT_EVIDENCE`

这一方向保留了明确盈利潜力：在 BTC 开发、BTC 后期评价和完全未查看的 BNB 上，固定规则的累计收益与 active interval 均值下界均为正，而且 basis 不是主要损失来源。它尚不能计作稳定可用策略，因为收益集中在高 funding 状态，BTC 2025 无机会，BNB 后四年多数为小幅负，且两腿同步成交、保证金和 USDT 机会成本未被历史 bar 证明。

最强支持是三个顺序证据集都为正且 BNB 跨标的区间下界为正；最强反证是 episode 胜率低、年度集中和现实两腿账户风险。新证据需要在另一未暴露时期证明 3 bp 机会重新出现并覆盖账户级资金占用，不能在已看数据上放宽年度门或改阈值。
