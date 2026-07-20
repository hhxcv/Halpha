# ETHUSDT 日线 SMA200 长仓/现金候选研究

## 状态与基准

- 稳定产品基准提交：`de6b3052f28fe547730e89e58186d4ab397884b1`
- 固定正式策略：`ONE_SHOT_DONCHIAN_ATR_BREAKOUT` `1.0.0`
- 候选身份：`RESEARCH_ETHUSDT_DAILY_SMA200_LONG_CASH`
- 标的：Binance USDⓈ-M `ETHUSDT` 线性永续；UTC 日线；1x 初始名义。
- cutoff：`2026-07-01T00:00:00Z`。
- 研究用途：判断一个低换手、个人可维护的长仓/现金风险过滤规则是否值得保留为产品候选；不证明 Alpha，不改变产品、资金或真实交易状态。

本研究只写入 `research/**`，公开行情的大文件放在 Git 外。它不读取产品业务数据、数据库、秘密或运行配置，不启动产品运行时，不调用交易所变更端点。

## 去重、候选与选择

已有 BTC funding carry 和 ETH 2h 反转分别得到 `DOES_NOT_SUPPORT`；后者只查看到 2023 年，2024–2026 ETH 仍未下载或暴露。SMA200 候选已在反转研究运行前列入候选表，因此不是看到反转失败后从同一开发结果临时挖出的规则。它使用同一标的但机制、频率、持有期和决定用途都不同：目标是用极低换手减少长期下跌暴露，而不是预测下一根 bar。

本轮比较的少量方向：

| 候选 | 决策价值 | 现实成本与维护 | 取舍 |
|---|---|---|---|
| ETH 日线 SMA200 long/cash | 单标的、低换手、解释简单；可检验是否用较小维护成本改善持有风险 | 一天一次判断；单腿；小资金可执行 | **选中** |
| 12 个月收益符号 long/cash | 原始 time-series momentum 定义清楚 | 与 SMA200 经济含义接近 | 不并行搜索，避免同义参数挑选 |
| 多周期 Donchian ensemble | 当前论文证据更贴近 crypto | 与正式 Donchian 重复，参数和组合更多 | 淘汰 |
| 横截面 momentum | 可能提高收益 | 动态币池、幸存者与换手复杂度 | 淘汰 |

## 先行调研（访问日 2026-07-20）

1. Meb Faber, [A Quantitative Approach to Tactical Asset Allocation](https://ssrn.com/abstract=962461)（Journal of Wealth Management, 2007；2013 更新）：使用约 10 个月简单均线在多类资产中进行持有/现金过滤，目标是改善风险调整表现和回撤。适用于固定一个低自由度长期规则；原研究不是 crypto、不是永续，也没有 funding。
2. Moskowitz、Ooi、Pedersen, [Time Series Momentum](https://doi.org/10.1016/j.jfineco.2011.11.003)（JFE, 2012）：在 58 个液态期货上报告过去 1–12 个月收益持续性及更长期反转。它提供趋势机制先验，但多资产组合证据不能直接成为单一 ETH 结论。
3. Han、Kang、Ryu, [Momentum in the Cryptocurrency Market: A Comprehensive Analysis under Realistic Assumptions](https://doi.org/10.2139/ssrn.4675565)（2024，2026 修订）：报告 crypto 的 time-series momentum 证据强于 cross-sectional momentum，同时指出厚尾、日内波动、清算和均值指标会夸大可用性。它要求报告 compounding、回撤、分年和 1x 边界。
4. Zarattini、Pagani、Barbon, [Catching Crypto Trends](https://doi.org/10.2139/ssrn.5209907)（Swiss Finance Institute RP 25-80, 2025）：在 survivorship-bias-free crypto 数据上研究多周期 Donchian ensemble、波动率 sizing 和换手控制。它支持 crypto 趋势值得检验，也说明其完整方法对当前单标的个人项目过重且与正式策略重叠。
5. [Binance Public Data](https://github.com/binance/binance-public-data) 和 [USDⓈ-M Funding Rate History](https://developers.binance.com/en/docs/derivatives/usds-margined-futures/market-data/rest-api/Get-Funding-Rate-History)：提供官方日线 kline 身份、相邻 `.CHECKSUM` 和实际 funding rate；档案可能修订，必须按 manifest hash 判断同一输入。

## 固定问题与规则

问题：若只在前一 UTC 日收盘高于其当日已知的 200 日简单移动平均时，于下一 UTC 日持有 ETHUSDT 1x long，否则持有现金，这一固定规则能否在实际 funding、每次进出各 16 bp 基准成本后，产生正复合收益并相对持续持有明显降低回撤？

- SMA：包含信号日 close 的最近 200 个日 close；不足 200 日不交易。
- 执行：信号在日 close 后已知；下一日 open 建立或结束 long，持有到该日 close；连续 long 不重复收费。
- funding：long 日内实际 rate 总和按初始名义扣除；没有精确历史 mark，保留代理差异。
- 成本：每次 cash↔long 转换按有利 6 bp、基准 16 bp、压力 26 bp；完整 round trip 分别为 12/32/52 bp。阶段首尾都平仓计费。
- 不使用杠杆放大、不做空、不搜索 SMA 长度、缓冲带、止损、仓位或成本。
- 基准：现金；同阶段持续持有 1x ETH 永续并计 funding 与首尾成本。当前正式策略没有公平精确重放，标记未运行。

开发资格门：2021–2023 基准成本后复合收益为正，三个日历年至少两个为正，最大回撤绝对值至少比持续持有小 20%，且 Calmar 高于持续持有。没有参数排序；失败即停止。

`SUPPORTS_WITHIN_SCOPE` 还要求：2024–2025 总复合收益为正、两个日历年均非负、最大回撤至少比持续持有小 15%、Calmar 更高；2026H1 复合收益为正。评价总收益为负时为 `DOES_NOT_SUPPORT`；其余不能满足强结论时为 `INSUFFICIENT_EVIDENCE`。

## 数据暴露与启封

| 区间 | 用途 | 暴露状态 | 启封规则 |
|---|---|---|---|
| 2021-01-01 至 2024-01-01 | development | 已被前一 ETH 反转研究作为价格开发数据查看；本规则尚未计算 | 允许探索与资格判断，不称独立确认 |
| 2024-01-01 至 2026-01-01 | evaluation | 未下载、未查看 | 仅本固定规则通过开发门后 |
| 2026-01-01 至 2026-07-01 | confirmation | 未下载、未查看 | 固定 evaluation 完成后最后运行 |

问题、单一规则、成本、资格门和启封条件在下载新留出数据前固定。只允许修复下载、解析、完整性或不改变经济规则的实现错误。

## 环境与留存

- Python 3.11.9、pandas 2.3.3、numpy 2.4.6；不修改产品依赖锁。
- 外部缓存：`D:/projects/Codex/CodexHome/research-data/halpha/ethusdt-daily-sma200-long-cash/`。
- 研究内保留代码、checkpoint、manifest、实际尝试、分期原始指标和最终结论。

实际运行结果和限制在开发门执行后追加。

## 实际结果

所有阶段数据质量通过。开发、评价、确认分别有 1,095、731、181 个连续 UTC 日，无重复、缺口或无效 OHLC；日 open 相对前一 close 的最大差异在评价期为 `0.0080%`。全期 66 个官方日线档案和 6,021 条 funding 记录均有 manifest 身份。

| 阶段 | 策略基准净复合收益 | 持续持有基准净收益 | 策略最大回撤 | 持续持有最大回撤 | 暴露/换向 |
|---|---:|---:|---:|---:|---:|
| 2021–2023 development | +96.94% | +94.27% | -33.82% | -79.97% | 41.28% / 10 次 |
| 2024–2025 evaluation | +24.18% | +8.39% | -39.02% | -67.37% | 57.73% / 20 次 |
| 2026H1 confirmation | 0.00% | -47.38% | 0.00% | -53.25% | 0% / 0 次 |

评价分年为 2024 `+32.11%`、2025 `-6.00%`；持续持有同期为 `+28.10%`、`-15.39%`。策略的评价期 Calmar `0.293` 高于持续持有 `0.061`，但 30 日 block bootstrap 日均区间仍跨零。2026H1 因始终低于 SMA200 而完全持有现金，提供了显著防御证据，但没有满足预设的正收益确认门。

## 结论

`INSUFFICIENT_EVIDENCE`

这一固定规则有明确的个人项目候选价值：低换手、单腿、在开发和评价都实现正总收益并明显减小回撤，确认期还避免了大幅下跌。它暂不能计作得到支持的盈利策略，因为 2025 单年为负、评价日均区间跨零、2026H1 没有正收益。最强支持是跨开发与评价的正复合收益和持续回撤改善；最强反证是收益依赖市场趋势、现金期不产生收益且样本只有一个标的。

结论不等于可进入产品。未来若项目所有者认为“降低回撤而允许长现金期”有直接价值，可用新的未暴露时期或另一高流动标的确认；不得在已暴露 ETH 时段搜索新的均线长度来升级结论。

未建模项包括 USDT 现金收益、保证金方式、精确 funding mark、历史盘口、部分成交、税务和资金机会成本。1x 初始名义不保证无清算风险；若进入产品考虑必须重新核对当时场所规则和账户边界。
