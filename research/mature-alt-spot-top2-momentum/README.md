# 成熟山寨币现货月度 top-2 动量候选研究

## 状态与边界

- 稳定产品基准提交：`de6b3052f28fe547730e89e58186d4ab397884b1`
- 固定正式策略：`ONE_SHOT_DONCHIAN_ATR_BREAKOUT` `1.0.0`
- 候选身份：`RESEARCH_MATURE_ALT_SPOT_TOP2_ABSOLUTE_RELATIVE_MOMENTUM`
- 固定标的：Binance Spot `XRPUSDT`、`ADAUSDT`、`LTCUSDT`、`LINKUSDT`、`DOGEUSDT`，UTC 日线。
- cutoff：`2026-07-01T00:00:00Z`。
- 用途：判断一个个人可维护、只做多或现金、月度最多持有两种成熟币的低频轮动规则，是否有独立区间内的盈利与防守证据；不是产品策略、收益保证、资金决定或真实交易许可。

研究只用公开市场数据与独立代码；不读取产品数据库、业务数据、凭据或运行配置，不启动产品运行时，不调用交易所变更端点。生成数据放在 Git 外，Git 内保留可重取身份、命令、机器结果、失败和结论。

## 已有研究去重与候选筛选

已有研究覆盖 BTC funding carry、ETH 极端反转、ETH long/cash 趋势、BTC/BNB 现货永续 cash-and-carry、SOL 双向趋势；本题首次使用上述五种现货资产，并检验“固定小篮子内相对排名 + 自身正动量过滤”，不把单标的趋势变体重复计数。

| 候选 | 项目决策价值 | 现实成本/可证伪性 | 取舍 |
|---|---|---|---|
| 五币现货 top-2，90 日正动量，月度 | 无 short/funding/跨所；最多两种币；月频 | 单一固定规则，费用、回撤、年份、60/120 日扰动与独立区间均可否定 | **选中** |
| 纯横截面 winner-minus-loser | 文献常见 | loser 腿反弹、做空和清算风险；现实研究认为证据弱 | 淘汰 |
| 周末/星期效应 | 最简单、反馈快 | 大样本论文认为收益季节性不稳健，且进出成本占比高 | 淘汰 |
| 动态全市场轮动 | 可减轻固定篮子偏差 | 需要历史成分、上市/退市和流动性点时数据，超出个人最小验证 | 后置 |
| ML 预测与阈值交易 | 可适应非线性 | 自由度、维护和过拟合成本过高 | 淘汰 |

固定宇宙是 2026 视角的存活成熟币，存在 survivorship/selection bias；它只能支持这五个仍可交易的标的，不能外推到“所有山寨币”。

## 先行联网调研（访问日 2026-07-20）

1. Liu、Tsyvinski、Wu，[Common Risk Factors in Cryptocurrency](https://doi.org/10.1111/jofi.13119)（Journal of Finance, 2022）：市场、规模和动量可解释 crypto 横截面收益，为相对强弱提供原始学术先验；其广泛、点时横截面与本研究固定五币小篮子不同。
2. Han、Kang、Ryu，[Time-Series and Cross-Sectional Momentum in the Cryptocurrency Market: A Comprehensive Analysis under Realistic Assumptions](https://doi.org/10.2139/ssrn.4675565)（2023/2024）：计入成本与日内波动后，time-series 证据强于 cross-sectional；收益集中于 winners，losers 常反弹并引发重大损失。因此本题只持有正绝对动量 winners，不做 loser short，并明确检查成本和日内/日线回撤。
3. Liu、Tsyvinski，[Risks and Returns of Cryptocurrency](https://doi.org/10.1093/rfs/hhaa113)（Review of Financial Studies, 2021）：报告强 time-series momentum，为“只有自身过去收益为正才持有”提供机制先验；不能替代本题的固定交易场所验证。
4. Platanakis 等，[Revisiting seasonality in cryptocurrencies](https://doi.org/10.1016/j.frl.2024.105429)（Finance Research Letters, 2024）：500 币样本未发现稳健收益季节性，支持淘汰周末/星期候选。
5. [Binance Public Data](https://github.com/binance/binance-public-data) 与 [官方 Spot REST Kline 文档](https://github.com/binance/binance-spot-api-docs/blob/master/rest-api.md#klinecandlestick-data)：官方月归档、checksum、2025 年起 spot 时间戳微秒变化以及公开只读补缺接口边界。

## 固定问题、规则与否定条件

问题：每月第一个 UTC 日开盘，按前一日 close 相对 90 个日历日前 close 的收益排序，只在正收益资产中持有 top-2 等权（只有一个则全仓一个；没有则现金），能否在 2021–2022 开发、2023–2024 独立评价和 2025–2026H1 确认中，在现实费用后保持正复合收益并降低固定五币等权买入持有的回撤？

- 信号只使用调仓日前已收盘日线；不使用当日 close 或未来成分。
- 每月最多调仓一次；持有期间不日内再平衡。现金收益固定为零。
- 有利/base/stress 单位绝对风险资产换手成本为 6/16/26 bp；现金到满仓换手 1，A 全切 B 换手 2，期末退出收费。
- 现货无 funding、short 或清算；盘口冲击未直接重放，成本带为手续费、spread/slippage 合并代理。
- 主规则固定 90 日；60/120 日只作预注册邻域扰动，不用于挑选主规则。
- 基准为五币各 20% 于阶段首日开盘买入并持有至期末，计首尾相同成本；另有现金零收益。
- 不搜索币种、持有数、窗口、调仓日、费用、止损或权重。

开发门：数据质量 `PASS`；90 日 base 与 stress 总收益为正；两年中至少一年为正；最大回撤比等权买持改善至少 10 个百分点；60/120 日 base 总收益均为正；两年总换手不超过 50。任一失败即停止且不下载后续区间。

评价门：固定 90 日 base 与 stress 总收益为正；2023/2024 至少一年为正；最大回撤小于等权买持；60/120 日 base 总收益均为正。失败即停止且不下载确认区间。

`SUPPORTS_WITHIN_SCOPE` 还要求确认区间固定 90 日 base 与 stress 总收益均不为负、最大回撤小于等权买持、60/120 日 base 均不为负。评价或确认的固定 90 日 base 总收益为负则 `DOES_NOT_SUPPORT`；其他未过支持门情形为 `INSUFFICIENT_EVIDENCE`。即使支持，也只是固定资产/场所/时间/成本范围内的候选证据，不是 Alpha 证明。

## 时间启封与数据边界

| 区间 | 用途 | 状态 | 暖启动/启封规则 |
|---|---|---|---|
| 2021-01-01 至 2023-01-01 | development | 已运行；未过风险门 | checkpoint 与代码固定后；只另取 2020-09 起信号暖启动 |
| 2023-01-01 至 2025-01-01 | evaluation | **未查看、未下载** | 开发门失败，保持封存 |
| 2025-01-01 至 2026-07-01 | confirmation | **未查看、未下载** | 开发门失败，保持封存 |

数据使用 Binance 官方 spot 1d 月归档与 checksum；若归档在请求区间缺 open time，仅用官方公开 market-data REST Kline 补缺，并把补数记录与哈希纳入 manifest，不覆盖归档。每个阶段独立从现金启动，避免跨阶段继承隐含仓位。

## 环境、缓存与限制

Python 3.11.9、pandas 2.3.3、numpy 2.4.6；外部缓存：`D:/projects/Codex/CodexHome/research-data/halpha/mature-alt-spot-top2-momentum/`。不修改产品依赖。

日线无法重建订单簿、排队、部分成交、交易过滤器、停牌/维护或账户税务；固定幸存资产选择、单一交易所和 USDT 现金零收益均限制外推。

## 实际结果

五个标的开发区间均为 730/730 日、0 gap、0 invalid OHLC，`data_quality=PASS`；140 个月归档全部通过官方 checksum，无需 REST 补数。

| 开发指标 | 60 日扰动 | 固定 90 日 | 120 日扰动 | 五币等权买持 |
|---|---:|---:|---:|---:|
| base 总收益 | +96.01% | **+243.96%** | +428.63% | +278.74% |
| stress 总收益 | +92.17% | +239.27% | +420.93% | — |
| 最大回撤 | -91.21% | **-85.70%** | -78.02% | -90.57% |
| turnover | 19.75 | 13.69 | 14.62 | 2.00 |

固定 90 日的 2021/2022 收益为 +421.79% / **-34.08%**，30 日 block-bootstrap 日均 95% CI 为 [-0.1417%, +0.9387%]。它确实有高总收益、成本带稳健和最低约 850 万 USDT/日的所选资产 quote-volume，但最大回撤相对基准只改善 4.87 个百分点，未达到预注册的 10 个百分点；这不是适合个人小资金的可用风险轮廓。高收益主要暴露于 2021 牛市，不能越过风险否定条件。

## 结论

`DOES_NOT_SUPPORT`

在固定范围内，不支持把这项月度 top-2 规则列为已获支持的可用策略；它作为“盈利指标漂亮但风险不可接受”的负面结果保留。2023–2026 未下载、未查看，不用 holdout 修改规则。结果不改变产品策略、L4、资金或真实账户状态。

可重演命令和缓存身份见 `attempts.md`，机器结果见 `development.json`、`selection.json` 和 `results.json`。
