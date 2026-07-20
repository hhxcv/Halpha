# ETHUSDT 两小时极端收益反转候选研究

## 状态与固定边界

- 研究目录：`research/ethusdt-2h-extreme-reversal/`
- 稳定产品基准提交：`de6b3052f28fe547730e89e58186d4ab397884b1`
- 固定正式策略身份：`ONE_SHOT_DONCHIAN_ATR_BREAKOUT` `1.0.0`
- 研究标的：Binance USDⓈ-M `ETHUSDT` 线性永续（Halpha 身份 `ETHUSDT-PERP`）
- 时区：UTC；研究 cutoff：`2026-07-01T00:00:00Z`
- 结论用途：比较证据，用于判断这一候选是否值得以后由项目所有者选择；不是产品策略、资金依据或真实交易授权。

本目录只使用公开数据和独立标准库脚本，不导入产品代码，不读取产品数据库、业务数据、秘密或运行配置，不启动产品运行时，也不调用交易所变更端点。大型公开行情缓存在 Git 外；目录内保留可重取身份、代码、检查点、尝试和小型结果。

## 既有研究去重与候选选择

已扫描 `research/**`。现有 `btcusdt-next-funding-carry` 研究的是 BTCUSDT、下一 funding 单腿 carry、2021–2026，结论为 `DOES_NOT_SUPPORT`；它与本问题标的、信号和持有机制不同，但其完整时段已暴露，不能再充当本问题的独立 BTC 留出证据。因此本研究改用此前未读取的 ETHUSDT 数据。

| 候选 | 相对当前工作的差异与价值 | 否定条件 | 数据/运行复杂度 | 取舍 |
|---|---|---|---|---|
| ETHUSDT 2h 极端收益反转 | 与正式突破策略方向相反；原始论文报告 2h 反转最强；单一高流动永续、小名义、两小时闭环 | 滚动历史波动率定义下，32 bp 往返成本后开发期无稳定正期望 | 官方 2h kline 与 funding；一个脚本；低 | **选中** |
| 单标的日线趋势/风险过滤 | 低换手、个人易维护 | 相对持有和正式突破没有独立增量 | 日线公开数据；低 | 保留；机制与当前正式策略同属趋势，当前信息增量次之 |
| 固定时段/星期收益 | 实现很简单 | 跨年不持续或成本后消失 | 小 | 淘汰；原始跨交易所研究明确报告收益模式不持久 |
| BTC/ETH 配对均值回归 | 市场方向敞口较低 | 关系不稳定或两腿成本吞没 | 两腿、动态 hedge、更多成交假设；中高 | 延后；个人维护和执行复杂度高于单腿快速问题 |
| 多币横截面动量 | 文献有长多组合证据 | 幸存者偏差、换手或容量使结果消失 | 动态币池和历史成分；高 | 淘汰；当前需要的数据治理和产品扩展不相称 |

选择理由不是容易或指标新颖，而是它直接检验与当前正式趋势机制相反、文献已有明确先验、数据全新且低成本可证伪的单标的规则。它不依赖规模资本、跨场所库存、低延迟或长持有验证。

## 先行调研（访问日 2026-07-20）

1. Giacomo De Nicola, [On the Intraday Behavior of Bitcoin](https://doi.org/10.5195/ledger.2021.213)（Ledger, 2021）：在 2015–2018 Bitstamp 数据上报告 1h、2h、4h 收益的一阶负自相关，2h 在大波动后最强；简单策略在上一期大涨后做空、大跌后做多并持有一期。论文按全样本标准差、主要报告毛收益，作者也明确要求在更成熟时期和杠杆场所复验。它决定本研究的 2h、反向、持有一期骨架，但不能支持当前 Binance ETHUSDT 成本后收益。
2. Imran Yousaf、Shoaib Ali, [Intraday return predictability in the cryptocurrency markets: Momentum, reversal, or both](https://doi.org/10.1016/j.najef.2022.101733)（North American Journal of Economics and Finance, 2022）：报告日内 momentum 与 reversal 会随跳跃、流动性和时期变化。它要求分期、成本和状态稳健性，不能直接移植具体阈值。
3. Dirk Baur 等, [Bitcoin time-of-day, day-of-week and month-of-year effects](https://doi.org/10.1016/j.frl.2019.04.023)（Finance Research Letters, 2019）：七个交易所的成交活动存在时段差异，但收益模式跨时间不持久。它使固定日历规则不优先。
4. Masood Tadi、Irina Kortchmeski, [Evaluation of Dynamic Cointegration-Based Pairs Trading Strategy in the Cryptocurrency Market](https://arxiv.org/abs/2109.10662)（2021）：用动态协整、OU half-life、盘口与成交约束研究配对/篮子。它说明相对价值可能有用，也显示公平复现需要两腿、动态选择和微观成交数据，本轮成本不相称。
5. Han、Kang、Ryu, [Momentum in the Cryptocurrency Market: A Comprehensive Analysis under Realistic Assumptions](https://doi.org/10.2139/ssrn.4675565)（2024，2026 修订）：报告时间序列动量证据强于横截面动量，并强调厚尾、日内波动与清算会让均值指标失真。它支持保留低频趋势候选，并要求本研究报告分布、回撤而不只看均值。
6. [Binance Public Data 官方仓库](https://github.com/binance/binance-public-data)：说明 USD-M kline 来自 `/fapi/v1/klines`、字段、月度档案和相邻 `.CHECKSUM`；档案可能修订。用于输入身份和可重取性，不替代策略时序与成本判断。
7. [Binance USDⓈ-M Funding Rate History 官方 API](https://developers.binance.com/en/docs/derivatives/usds-margined-futures/market-data/rest-api/Get-Funding-Rate-History)：公开、无需凭据，按 `fundingTime` 升序返回历史 rate。用于持仓跨结算时的现金流；不等于手续费或价格收益。

## 固定问题、规则与否定条件

问题：在 `ETHUSDT` USDⓈ-M 上，以前一根 2h 收益相对此前 90 日 2h 收益波动达到固定阈值后反向持有下一根 2h，阈值只用 2021–2023 在 `2/3/4σ` 中选择，能否在 funding、每边 6 bp taker fee 与 10 bp spread/slippage 代理后保持可重复正期望？

- 信号：完整 2h bar 的 close-to-close 简单收益；滚动波动率只用此前 1,080 根 2h 收益，不含当前冲击。
- 入场：信号 bar 完成后的下一根 2h open；正冲击做空、负冲击做多。
- 退出：该下一根 2h close；不设止损、止盈或盘中路径假设。
- funding：使用实际 rate，把毫秒级 `fundingTime` 归到对应 2h 结算边界；只计入 `entry_time < settlement_boundary <= exit_time`，边界价格用该 trade bar close 代理 mark notional；正 rate 时 long 支付、short 收取。
- 成本：有利 12 bp、基准 32 bp、压力 52 bp 往返；支持结论必须通过 32 bp 基准。
- 搜索：只有 `2σ`、`3σ`、`4σ`；不搜索 timeframe、lookback、方向、持有期或成本。
- 简单基准：不交易为零；同一信号顺势持有一期作为最强相反解释。正式 Donchian/ATR 无法在不维护第二实现的前提下公平重演，标为未运行，不用代理强行排序。

开发门：2021–2023 至少 60 笔，32 bp 后平均净收益为正，三个日历年至少两个为正，8-trade circular-block bootstrap 95% 均值下界大于零。通过者只按下界、再按均值选择；无人通过即停止，不打开留出期。

`SUPPORTS_WITHIN_SCOPE` 还要求：2024–2025 至少 40 笔、整体及每年基准净均值为正、bootstrap 下界大于零；2026H1 至少 10 笔且基准净均值为正。评价为负则 `DOES_NOT_SUPPORT`；样本门不足或确认不能区分则 `INSUFFICIENT_EVIDENCE`；数据或实现身份无法确定才是 `CANNOT_DETERMINE`。

盈利回测不证明未来 Alpha。最直接反证是论文所述负自相关在更成熟的 Binance ETH 永续上消失，或 gross reversal 存在但 funding 与现实成本吞没它。

## 留出启封检查点

本节在下载或查看任何 ETHUSDT 历史价格结果前写入。

| 区间 | 用途 | 当前状态 | 启封规则 |
|---|---|---|---|
| 2021-01-01 至 2024-01-01 | development；只选 2/3/4σ | 未查看 | 代码与输入身份固定后可运行 |
| 2024-01-01 至 2026-01-01 | evaluation | 未查看 | 仅开发门通过且生成 `selection.json` 后 |
| 2026-01-01 至 2026-07-01 | confirmation | 未查看 | 固定阈值的 evaluation 完成后最后运行 |

已搜索范围、问题、阈值、时间段、成本、允许修复和启封规则已固定。启封前只允许修复下载、解析、数据完整性或显然不改变上述经济规则的实现错误；任何规则变化必须保留旧尝试并重新开始尚未暴露的研究。代码身份在首次 fetch 前记录到 `checkpoint.json`。

## 预期环境、命令与留存

- Python 3.11+ 标准库；不修改产品依赖。
- 外部缓存：`D:/projects/Codex/CodexHome/research-data/halpha/ethusdt-2h-extreme-reversal/`
- 小型 Git 内材料：本说明、`study.py`、`checkpoint.json`、manifest、数据质量、分期结果、最终结果和 `attempts.md`。
- 月度档案必须通过官方 `.CHECKSUM`；manifest 记录 URL、SHA-256、大小和缓存相对路径。外部缓存可删除但必须可按同一身份重取。

实际命令、失败、是否启封、复跑和最终结论在运行后补充。

当前无法精确复原结算瞬间 mark、bar 边界订单先后、历史盘口和部分成交；这些差异必须在最终限制中保留，不能由正结果消除。

## 实际结果与结论

开发数据质量通过：2021–2023 共 13,140 根连续 2h bar、3,285 条 funding，无缺口、重复、乱序或无效 OHLC。输入内容身份为 `83420cc3465abf9b13c8a046bf11d09508d47d36abd6ec7c9824308f2bf6b977`。

| 固定阈值 | 笔数 | gross 均值/笔 | 有利成本净均值 | 32 bp 基准净均值 | bootstrap 95% 均值区间 | 开发年结果 |
|---|---:|---:|---:|---:|---:|---|
| 2σ | 673 | +0.0195% | -0.0992% | -0.2992% | [-0.4111%, -0.1871%] | 2021、2022、2023 均负 |
| 3σ | 221 | +0.0012% | -0.1154% | -0.3154% | [-0.5331%, -0.0901%] | 2021、2022、2023 均负 |
| 4σ | 82 | +0.2546% | +0.1426% | -0.0574% | [-0.3906%, +0.2772%] | 仅 2023 略正 |

`DOES_NOT_SUPPORT`

在固定开发范围内，不支持把这一 2h 极端反转规则保留为可用候选。最强支持是 4σ 的 gross 与有利成本情景为正，说明极端冲击后存在有限反转潜力；最强反证是它在 Halpha 的 32 bp 基准成本后转负、区间跨零且三个开发年只有一年略正，2σ/3σ 则在每个开发年都为负。同期 2h 收益 lag-1 相关仅 `-0.0203`，远弱于早期论文机制。

开发门输出为 `NO_VARIANT_PASSED_DEVELOPMENT_GATE_STOP`。因此没有下载或查看 2024–2026 档案，没有生成 evaluation/confirmation，未暴露留出期。正式 Donchian/ATR 比较按预注册标为未运行；强行维护代理不会改变当前否定决定。

结果只否定当前 ETHUSDT、2h、90 日滚动波动率、持有一期和成本范围，不否定所有中频反转。若以后有更低的实际可核对成交成本或不同的非价格输入，需要作为新问题重新预注册；不能在本开发期继续搜索阈值来制造正结果。
