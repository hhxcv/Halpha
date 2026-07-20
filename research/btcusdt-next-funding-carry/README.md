# BTCUSDT 下一结算 funding carry 候选研究

## 状态与边界

- 研究目录：`research/btcusdt-next-funding-carry/`
- 稳定产品基准提交：`de6b3052f28fe547730e89e58186d4ab397884b1`
- 固定正式策略身份：`ONE_SHOT_DONCHIAN_ATR_BREAKOUT` `1.0.0`
- 正式策略实现摘要（该提交）：`66299533bb4a7fb56efe52e2ffb9fad281d4b29f0fe9cdb47049115d3323d32e`
- 研究标的：Binance USDⓈ-M `BTCUSDT` 线性永续（Halpha 身份 `BTCUSDT-PERP`）
- 时区：UTC；研究 cutoff：`2026-07-01T00:00:00Z`
- 结论用途：比较证据，用于决定这一候选是否值得以后由项目所有者选择为产品考虑对象；不是产品策略、资金依据或真实交易授权。

本目录只使用公开数据和独立脚本，不导入产品代码，不读取产品数据库、业务数据、秘密或运行配置，不启动产品运行时，也不调用任何交易所变更端点。缓存的大型月度行情在 Git 外；目录内只保留取数身份、校验和、代码、尝试与小型结果。

## 当前缺口、候选与选择

L4 只有一个正式的 Donchian/ATR 单次突破策略，并明确记载其历史模型未包含 funding；产品当前范围排除第二个正式策略。研究因此寻找“有机制差异、可证伪、公开数据足够、适合个人小资金且可快速验证、单人项目成本可控”的候选，而不是添加产品策略。依赖大资金容量、跨场所库存、长期建仓或很长验证周期的方向不进入本轮。

| 候选 | 决策价值与现有差异 | 可证伪问题/反对结果 | 基准与数据 | 预期成本 | 取舍 |
|---|---|---|---|---|---|
| 下一结算裸 funding carry | 直接研究正式回测缺失的 funding；与价格趋势突破不同；单一永续、小名义即可验证 | 已结算 funding 的符号即使可预测，若下一结算前后的方向价格风险和成本使样本外净期望不正，则否定 | 无交易；正式 Donchian/ATR 固定参数重放代理；Binance funding API 与 1m futures klines | 低至中；一个脚本；单次反馈为相邻 funding 周期，通常数小时 | **选中** |
| 4 小时极端收益反转 | 原始研究报告中频负自相关，与突破机制相反 | 现实成本后、分期后不再为正 | 无交易、Donchian；同一 1m kline | 中；需另行固定冲击定义和退出 | 保留，未并行开展；本轮先回答项目明确缺失的 funding |
| 简单时间序列动量/EMA | 成熟、易取得数据 | 相对 Donchian 无稳定增量 | Donchian、持有；klines | 低 | 淘汰：机制和现有正式突破高度重复，当前信息增量较小 |
| funding + open interest 拥挤 | 比单一 funding 更接近杠杆拥挤 | OI 历史语义或覆盖不足，或组合不优于 funding 单变量 | 官方 metrics/OI 与 funding | 中至高 | 本轮淘汰：增加数据身份与参数选择，单变量问题尚未回答 |

选中的不是文献常见的现货—永续 delta-neutral 套利。跨腿套保会增加资金、库存、执行与维护复杂度，不符合本轮个人小资金快速验证优先级。Halpha 当前研究边界是单一 `BTCUSDT-PERP` 候选，因此本研究明确检验“裸持有的价格风险是否吞没 funding 可预测性”。单次历史/以后纸面验证在相邻 funding 周期内闭合，不需要等待月级或年级持有；这也是外部工作尚未替 Halpha 回答的适配差异。

## 先行调研（访问日 2026-07-20）

1. [Binance Public Data 官方仓库](https://github.com/binance/binance-public-data)：说明月度/日度公开档案、USD-M klines 来自 `/fapi/v1/klines`、字段含义、相邻 `.CHECKSUM` 以及档案可能修订。适用于可重取和完整性验证；没有替本研究决定策略时序、成本或历史 funding 语义。
2. [Binance USDⓈ-M Funding Rate History 官方 API](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data#get-funding-rate-history)：`GET /fapi/v1/fundingRate` 是无凭据公开市场数据，按 `fundingTime` 升序分页，返回 rate、time 和可用时的 mark price。适用于事件身份；早期 `markPrice` 为空，研究用同场所结算分钟 kline open 代理并保留差异。
3. [Binance funding 机制说明](https://academy.binance.com/en/articles/what-are-funding-rates-in-crypto-markets)：正 funding 由 long 支付 short，负 funding 反向；间隔可能变化。研究因此读取实际相邻 funding 事件而不硬编码 8 小时，也不把 funding 当交易所手续费。
4. He, Manela, Ross & von Wachter, [Fundamentals of Perpetual Futures](https://arxiv.org/abs/2212.06888)（2022）：给出 perpetual/funding 的无套利框架、交易成本边界，并强调常见 funding arbitrage 是现货—永续组合且并非无风险。适用于解释为什么 funding 可形成机制；不能支持 Halpha 的单腿方向净收益。
5. Ackerer, Hugonnier & Jermann, [Perpetual Futures Pricing](https://www.nber.org/papers/w32936)（NBER WP 32936, 2024）：说明 periodic funding 对永续—现货锚定的作用及复制条件。适用于机制和更简单的套利解释；没有回答单一 Binance BTCUSDT 的下一结算方向收益。
6. Inan, [Predictability of Funding Rates](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5576424)（2025）：在 Binance/Bybit Bitcoin funding 上报告一步预测优于 no-change，同时局部稳定性随时间变化。它影响本研究只预测“下一次”并设置独立时段；funding 可预测不等于含价格风险与成本的单腿总收益可预测。
7. De Nicola, [On the Intraday Behavior of Bitcoin](https://doi.org/10.5195/ledger.2021.213)（2021）：报告 1/2/4 小时收益负一阶自相关和极端移动后更强反转。它支持把中频反转列为备选；样本、市场与成本不等同于 Binance USD-M 当前合约。
8. Yousaf & Ali, [Intraday return predictability in the cryptocurrency markets: Momentum, reversal, or both](https://doi.org/10.1016/j.jeconbus.2022.106071)（2022）：报告 momentum 与 reversal 都随 jump、流动性和时期变化。它要求任何反转候选做状态与样本稳健性；本轮未尝试该家族。
9. Moskowitz, Ooi & Pedersen, [Time Series Momentum](https://w4.stern.nyu.edu/facdir/lpederse/papers/TimeSeriesMomentum.pdf)（JFE, 2012）：成熟的期货趋势基准。它说明趋势不是新机制；Halpha 已有 Donchian/ATR，故不再用另一个趋势指标占用首个问题。

没有外部来源直接回答本研究问题。尤其是“下一 funding 符号可预测”和“delta-neutral funding 套利可能有经济价值”都不能推出“单腿 BTCUSDT 永续在市场单和现实成本后盈利”。

## 固定问题与否定条件

问题：在 `BTCUSDT` USDⓈ-M 上，某次 funding 已结算并可观察后，若在一分钟后按“正 funding 做空、负 funding 做多”进入，并在下一次实际 funding 结算一分钟后退出，以 2021–2023 只选择绝对 funding 阈值，能否在 2024–2025 评价和 2026H1 确认中保留正的 base-cost 净期望？

- 对象：单腿、1x 初始名义敞口的下一结算 funding carry；不是对冲套利。
- 信号可知时间：只在当前 `fundingTime` 后使用当前 rate；入场推迟一个完整 1m bar。
- 持有：到实际的下一 funding 事件后一个完整 1m bar；不假设恒定 8 小时。
- funding：持仓跨越下一结算，按下一实际 rate 和结算分钟 kline open 相对入场名义计算。
- base 成本：每边 taker fee 6 bps + 不利滑点/点差代理 10 bps，即约 32 bps round trip；对应正式策略 sizing 中的 `taker_fee_rate=0.0006` 与每边 `0.0010` 代理。另报告有利 12 bps 和压力 52 bps。
- 阈值搜索：开发期只比较 `|funding| >= 1/3/5 bps`；零阈值只作简单解释。持有规则、方向、成本和评价期不搜索。
- 开发选择门：至少 60 笔，且 base-cost 平均净收益在三个开发日历年中至少两年为正；通过者按 8-trade 循环 block bootstrap 均值下界、再按均值排序。如果无人通过，仍保留最佳者进入样本外仅用于反证，并明确标记门未通过。
- `SUPPORTS_WITHIN_SCOPE`：开发门通过；评价至少 30 笔、确认至少 15 笔；base-cost 平均净收益在评价整体、评价每个日历年和确认均为正，且评价 bootstrap 95% 下界大于零。
- `DOES_NOT_SUPPORT`：样本数门满足，但评价或确认的 base-cost 平均净收益不正。
- 其他为 `INSUFFICIENT_EVIDENCE`；数据身份或实现无法判断才是 `CANNOT_DETERMINE`。

最直接的否定结果是：funding 符号有持续性或 funding 现金流为正，但裸方向价格损失加执行成本使样本外净期望不正。盈利回测本身也不构成 Alpha 证明。

## 数据边界与已查看时段

| 阶段 | 事件时间范围（end exclusive） | 用途 | 暴露状态 |
|---|---|---|---|
| development | 2021-01-01 至 2024-01-01 | 仅选择 1/3/5 bps 阈值 | 运行后标为已查看 |
| evaluation | 2024-01-01 至 2026-01-01 | 固定阈值样本外评价 | 仅在 `selection.json` 生成后运行 |
| confirmation | 2026-01-01 至 2026-07-01 | 固定阈值后续确认 | 最后运行 |

数据为 Binance 官方 USD-M 1m futures klines 月档案及公开 funding history API snapshot。`source_manifest_development.json` 封存选择前 2021–2023 的 36 个档案与当时 funding snapshot 身份；`source_manifest.json` 保存全期 66 个档案 URL、官方 SHA-256、大小、外部缓存位置和全期 funding snapshot SHA-256。`data_quality.json` 保存覆盖、缺口、重复、乱序、OHLC 与实际 funding 间隔检查。Binance 可以修订历史档案，未来重取必须以 manifest 的 SHA-256 判断是否仍是同一输入。

实际全期检查得到 2,890,080 个连续 1m bar（恰等于区间理论数量），无缺口、重复、乱序、非正价格或无效 OHLC；funding 6,021 条、无重复。`fundingTime` 有毫秒级偏移但相邻间隔均约 8 小时。3,100 条早期记录没有 `markPrice`，已按预先声明使用结算分钟同场所 kline open 代理。

## 正式策略比较基准的限制

比较代理固定使用产品提交和 1.0.0 默认参数：20×15m Donchian、2×1m 确认、EMA-ATR14 近似、1.5 ATR stop、1.5R/3R 各 50%、最长 96×15m、同一 base 成本和实际 funding。

L4 没有定义历史激活日程，所以研究只能把每次退出后的下一机会视为新独立 activation，并分别重放 LONG、SHORT；这不是产品的真实历史表现。独立脚本不导入 NautilusTrader，ATR 使用 `alpha=2/(14+1)` 的 EMA 代理；同一分钟 stop/TP 冲突按保守 stop-first。它是固定比较对象，不是正式策略资格复验，不能把差异解释成产品优劣。

## 环境、命令与产物

实际环境：Windows、Python 3.11.9，仅标准库。大型缓存预期位于：

`D:/projects/Codex/CodexHome/research-data/halpha/btcusdt-next-funding-carry/`

完整命令将在运行后按实际记录于 `attempts.md`。规范顺序为：分年 `fetch`；全期 `inspect`；仅开发期 `analyze`；`select`；固定阈值后的 evaluation 和 confirmation；最后 `combine`；再从已缓存输入完整复跑最终链路并核对 hashes/结果。

研究小型产物：

- `study.py`：取数、校验、研究、基准代理、选择和结论规则。
- `source_manifest.json`：公开数据取数身份与校验和。
- `data_quality_development.json`、`data_quality.json`：开发期与全期数据质量检查。
- `development.json`、`selection.json`、`evaluation.json`、`confirmation.json`：严格按时间顺序生成的阶段证据。
- `results.json`：机器生成的单一结论与关键指标。
- `attempts.md`：所有重要尝试、失败、条件变化与复跑记录。

## 未建模与不能推出

- 1m OHLC 无法识别 bar 内真实路径；正式策略代理同分钟冲突保守处理，但 gap、队列和部分成交仍未知。
- 10 bps/边把 spread 与滑点合为代理，没有历史 L1/L2；容量、冲击、延迟、账户级 VIP/BNB fee、保证金、强平和 ADL 未建模。
- early funding API 的 `markPrice` 为空，funding 名义使用同场所结算分钟 kline open；它不是官方 mark 的完全等价物。
- 研究没有 spot leg，所以不能评价文献中的 delta-neutral funding arbitrage。
- 研究按 1x 初始名义比较，不依赖大资金容量；小资金仍受最小名义、数量步长和账户实际手续费约束，未来如进入产品考虑必须另行用当时场所规则验证。
- 单一标的、单一场所和有限时间不能证明未来 Alpha；bootstrap 只描述已看样本，并未修复所有非平稳性或搜索偏差。
- 结果不修改正式策略、L4、产品代码、资金、凭据或真实账户。只有项目所有者明确选中后，才能另开产品任务重新实现和验证。

## 结论

`DOES_NOT_SUPPORT`

在本问题、单腿机制、时序、BTCUSDT、样本和成本范围内，不支持把“当前 funding 已结算后，站到可能收取下一 funding 的一侧并持有到下一结算”保留为值得产品考虑的候选策略。

| 阶段 | 固定/搜索范围 | 笔数 | base 平均净收益/笔 | bootstrap 95% 均值区间 | 关键结果 |
|---|---:|---:|---:|---:|---|
| development 2021–2023 | 搜索 1/3/5 bps；表中为规则选出的 1 bp | 1,846 | -0.2427% | [-0.3372%, -0.1452%] | 三个阈值均未通过开发门；1 bp 仅保留反证 |
| evaluation 2024–2025 | 固定 1 bp | 867 | -0.3316% | [-0.4285%, -0.2286%] | 2024、2025 均为负；有利 12 bps 往返成本仍为 -0.1312%/笔 |
| confirmation 2026H1 | 固定 1 bp | 18 | +0.0395% | [-0.7401%, +0.8298%] | 小样本均值转正但中位数 -0.4363%，区间跨零；不能推翻大样本反证 |

最强支持是机制确实存在：评价期当前与下一 funding 的同号率为 99.54%，且 2026H1 的 18 笔 base 均值略正。最强反证更直接：评价期 funding 现金流分量合计为 +0.1207 个初始名义单位，但价格分量 -0.2177、滑点/点差代理 -1.7363、手续费 -1.0416，合计净值 -2.8748；每笔平均和置信区间都明确为负。有利成本情景也未转正，说明失败不只来自采用了 10 bps/边的 base 滑点代理。

正式 Donchian/ATR 重放代理在评价期 base 成本下同样为负（LONG -0.3164%/笔、SHORT -0.3396%/笔）。由于其历史 activation 日程、Nautilus ATR 精确行为和 bar 内成交不可得，这只说明比较环境严苛，不能称为当前产品策略的绩效，也不能用候选与代理之间的微小差异排序策略。

结果否定的是单腿、下一结算、固定阈值这一候选，不是否定 funding 机制或 delta-neutral 套利。新证据只有在不扩大为大资金/跨场所重系统的前提下，改变可观察输入或价格风险控制，并重新预注册独立时段，才可能改变判断；不得在已暴露时段继续寻找有利阈值。
