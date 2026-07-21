# AVAX/DOT/NEAR 永续月度低杠杆 time-series momentum 研究

## 状态与边界

- 稳定产品基准提交：`de6b3052f28fe547730e89e58186d4ab397884b1`
- 固定正式策略：`ONE_SHOT_DONCHIAN_ATR_BREAKOUT` `1.0.0`
- 候选身份：`RESEARCH_AVAX_DOT_NEAR_PERP_MONTHLY_TSMOM_0P5X`
- 固定标的：Binance USDⓈ-M `AVAXUSDT`、`DOTUSDT`、`NEARUSDT` 永续；UTC 日线；总 gross 0.5x。
- cutoff：`2026-07-01T00:00:00Z`。
- 用途：判断一个三腿、月频、低名义、可同时适应牛熊方向的组合趋势候选，是否有范围内支持；不是第二产品策略、收益保证、资金决定或真实交易许可。

只用公开数据与独立研究代码；不读产品数据库、业务数据、凭据或运行配置，不启动产品运行时，不调用交易所变更端点。大数据在 Git 外，Git 内留存 manifest、代码、命令、结果和失败。

## 去重、候选与选择

已有单标的 ETH/SOL 趋势与五币现货 long-only momentum 均未获支持。正式策略属于 Donchian/ATR one-shot breakout；本题仍属广义 trend 家族，因此若获支持只计一个“多标的低杠杆 time-series momentum”候选，不与任何趋势变体重复计数。关键未解决差异是：固定三标的分散、对每个标的允许 long/short、月频低换手、0.5x gross、实际 funding，以及完全新数据。

| 候选 | 决策价值 | 现实成本/风险 | 取舍 |
|---|---|---|---|
| 三币 90 日方向、月频、0.5x gross | 熊市可 short；三腿仍可个人维护；新数据 | 永续 funding、short squeeze、保证金风险 | **选中** |
| 20 币 Donchian ensemble | 文献证据较强、分散更好 | 与正式策略更重叠，数据/运维/换手过大 | 淘汰 |
| 单币 1x long/short | 最简单 | 集中与清算风险过高；SOL 已失败 | 淘汰 |
| 每日/每周调仓 | 反馈更快 | 交易频率和成本更高 | 淘汰 |
| volatility-targeted 多参数组合 | 风险更平滑 | 当前问题先检验固定 0.5x 的更简单解释 | 后置 |

## 先行联网调研（访问日 2026-07-20）

1. Moskowitz、Ooi、Pedersen，[Time Series Momentum](https://doi.org/10.1016/j.jfineco.2011.11.003)（JFE, 2012）：跨流动期货的过去收益方向延续，为独立逐标的 long/short 提供成熟先验；传统期货分散和风险缩放不能替代三种 crypto 永续证据。
2. Liu、Tsyvinski，[Risks and Returns of Cryptocurrency](https://doi.org/10.1093/rfs/hhaa113)（RFS, 2021）：报告 crypto time-series momentum；样本与执行不同。
3. Han、Kang、Ryu，[realistic crypto momentum](https://doi.org/10.2139/ssrn.4675565)：现实成本、日内波动和 liquidation 会否定表面显著收益，且 time-series 证据强于 cross-sectional；本题据此固定低 gross、actual funding、日内 adverse 与分段门槛。
4. Zarattini、Pagani、Barbon，[Catching Crypto Trends](https://doi.org/10.2139/ssrn.5209907)（2025）：survivorship-bias-free crypto trend、费用和波动 sizing 提供近年正面证据；其 20 币、多 Donchian ensemble 明显比本题复杂，不能移植业绩。
5. [Liquidation, Leverage and Optimal Margin in Bitcoin Futures Markets](https://arxiv.org/abs/2102.04591)：高杠杆强平显著，研究估计降低杠杆可大幅降低 margin-call 风险；本题总 gross 固定 0.5x，但仍不声称不会清算。
6. [Binance Public Data](https://github.com/binance/binance-public-data)、[USD-M Kline](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Kline-Candlestick-Data) 与 [Funding History](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Get-Funding-Rate-History)：官方归档/checksum、公开补缺和 settled funding 来源。

## 固定问题、规则与否定条件

问题：每月第一个 UTC 日开盘，对三个永续分别按前一日 close 相对 90 日前 close 的符号持 `+1/6` 或 `-1/6` 初始资本名义（总 gross 0.5），能否在 2021–2022 开发、2023–2024 独立评价、2025–2026H1 确认中，于实际 funding 和成本后保持正复合收益，并将最大回撤与单日最差 intraday adverse 控制在个人候选可接受范围？

- 信号只使用调仓日前已收盘数据；月内固定合约数量，不日内再平衡；阶段独立从现金/零仓位开始。
- 90 日为主规则；60/120 日只作预注册邻域反证，不用于选择。
- 每个标的目标绝对名义 1/6，gross 0.5；不做波动率缩放、不加仓、不择币。
- 有利/base/stress 单位绝对名义换手成本 6/16/26 bp；首尾与方向翻转均收费。
- funding 按官方实际 settled rate 日内合计，以当日 close 名义代理；正 rate 时 long 支付、short 收取。
- 账户日内 adverse 用当日 open 到 long 的 low / short 的 high 的三个腿合计最差 PnL 除以当日开盘前权益；它不能确定同一时刻联合极值，作为保守压力检查。
- 基准为三个永续各 +1/6 固定合约数量的 0.5x long，计相同首尾成本与 funding；现金为零收益。
- 不搜索标的、窗口、gross、调仓日、成本、止损或权重。

开发门：数据 `PASS`；90 日 base/stress 总收益为正；2021/2022 均为正；最大回撤 > -35% 且小于 0.5x long；最差单日 intraday adverse > -20%；60/120 日 base 均为正；turnover <= 30。失败即停止且不下载 holdout。

评价门：90 日 base/stress 总收益为正；2023/2024 均为正；最大回撤 > -35% 且小于 0.5x long；adverse > -20%；60/120 日 base 均为正。失败不下载确认。

`SUPPORTS_WITHIN_SCOPE` 还要求确认：90 日 base/stress 总收益为正、最大回撤 > -35% 且小于 0.5x long、adverse > -20%、60/120 日 base 均非负。评价或确认主规则 base 总收益为负则 `DOES_NOT_SUPPORT`；其余未过支持门为 `INSUFFICIENT_EVIDENCE`。正回测仍不证明 Alpha。

## 时间启封与数据

| 区间 | 用途 | 状态 | 暖启动/启封 |
|---|---|---|---|
| 2021-01-01 至 2023-01-01 | development | 已运行；风险与稳健性门失败 | checkpoint/代码固定后；另取 2020-09 起暖启动 |
| 2023-01-01 至 2025-01-01 | evaluation | **未查看、未下载** | 开发门失败，保持封存 |
| 2025-01-01 至 2026-07-01 | confirmation | **未查看、未下载** | 开发门失败，保持封存 |

三个标的的 Kline、funding 与结果此前未在 `research/**` 使用。数据来自官方 USD-M 月归档、checksum 和 funding REST；归档缺日时仅用官方公开 Kline REST 填缺失 timestamp，不覆盖归档。

Python 3.11.9、pandas 2.3.3、numpy 2.4.6；外部缓存：`D:/projects/Codex/CodexHome/research-data/halpha/avax-dot-near-perp-monthly-tsmom/`。不修改产品依赖。

日线无法重建订单簿、mark price、bar 内极值先后、逐仓/全仓、maintenance margin、ADL、部分成交或税务；fixed 0.5x 也不保证不清算。固定幸存币与单所限制外推。

## 实际结果

开发期三个标的均为 730/730 日、0 funding 缺日、每币 2,190 条 funding，`data_quality=PASS`。暖启动中官方归档共 83 个，官方 REST 只填补 5 个归档缺失日；AVAX/NEAR 的上市前暖启动日期没有伪造补数，详见 manifest。

| 开发指标 | 固定 90 日 | 60 日扰动 | 120 日扰动 | 0.5x continuous long |
|---|---:|---:|---:|---:|
| base 总收益 | +27.41% | **-60.50%** | **-50.29%** | -85.30% |
| favorable / stress | +28.75% / +26.08% | — | — | — |
| 2021 / 2022 | **-33.10%** / +90.45% | — | — | — |
| 最大回撤 | **-82.87%** | — | — | -98.22% |
| 最差单日 intraday adverse | **-63.99%** | — | — | — |
| turnover | 10.45 | — | — | 约 1.0 |

30 日 block-bootstrap 日均 95% CI [-0.1647%, +0.3901%] 跨零。总收益为正主要来自 2022 short 趋势，无法覆盖 2021 反向与 short squeeze；60/120 日两个事前扰动均大幅亏损。初始 gross 0.5 不代表月内风险恒定：固定合约数量在被 short 的币暴涨时会迅速放大相对权益名义，日线 adverse 已足以否定个人可用性。

## 结论

`DOES_NOT_SUPPORT`

固定三币、月度 90 日方向、0.5x 初始 gross 的规则未通过开发年的稳定性、回撤、单日 adverse 和邻域稳健性门；不支持列为可用候选。2023–2026 未下载、未查看。研究保留为“低初始 gross 仍不能替代动态风险控制”的反证，不改变产品策略、L4、资金或真实账户状态。

可重演命令、两次上市前数据边界失败、代码修订、manifest 和缓存见 `attempts.md`；机器结果见 `development.json`、`selection.json`、`results.json`。
