# BTC 冲击后的中等活动币 beta-gap

## 状态、父问题与独立差异

- 类型：`PREDICTIVE`；开题日期 2026-07-21。
- 产品基准：Git `0bdfeffa616260cebd2d2188ddc8deb9e85c77f4`；`ONE_SHOT_DONCHIAN_ATR_BREAKOUT 1.0.1 / BTCUSDT-PERP` 仅固定身份。
- 父问题：`../btc-shock-beta-gap-predictability/` 在 15 个成熟/高活动永续上得到 +2.08 bp、未击败简单基准且低于成本，`DOES_NOT_SUPPORT`。
- 本题不是改窗口或阈值：信号、目标、时序、8 个配置、统计门和 12/32/52 bp 参照全部沿用父题；唯一研究差异是**事前固定的中等活动对象层**。这是父题明确未覆盖、也是外部论文报告延迟更可能出现的对象范围。

只用公开数据，不读产品数据库/业务数据/凭据/运行配置，不启动产品运行时，不调用交易所变更端点。大型 ZIP 继续写入 Git 外共享 cache，本题保留完整 source manifest。

## 事前对象选择

从固定市场快照 `2026-07-21T064230Z` 的 Binance USD-M 行中，在查看本题 5m 结果前应用：

1. 当前 `TRADING` 的 `PERPETUAL`、`CRYPTO_NATIVE`、USDT quote；
2. `CRYPTO_ALT_MID_ACTIVITY_PROVISIONAL`；只表示当前 24h 临时活动层，不代表长期流动性；
3. age `>= 1100` 日，确保 2023-10 暖启动前已上市；
4. 当前一次 best bid/ask 相对 spread `<= 3.5 bp`；
5. 无 `OFFICIAL_MEME_SUBTYPE`，symbol 不以数字开头，排除 `BTCDOMUSDT` 等非普通单币指数；
6. 按当前 24h activity-notional proxy 降序取前 12。

固定结果：`BELUSDT`、`ANKRUSDT`、`JASMYUSDT`、`ZENUSDT`、`TRBUSDT`、`MANAUSDT`、`QTUMUSDT`、`QNTUSDT`、`ENJUSDT`、`CFXUSDT`、`EGLDUSDT`、`IOTAUSDT`；anchor 为 `BTCUSDT`。

选择标准刻意避开最新上市、官方 meme、明显宽当前 spread 和最低活动层，但仍有幸存者偏差、单日活动偏差与中等活动币的尾部/下架风险。不能把它们称为“安全主流币”。开发结果必须同时报告历史 quote volume/trade count 与个币集中度，不从结果删币。

## 固定问题与方法

问题：对上述 12 个币，已收盘 5m BTC shock 后的同 bar beta 欠反应，能否从下一 5m open 起预测随后 15m 的同方向 BTC-neutral residual，并达到个人项目的最低经济相关幅度？

定义完全继承父题锁定代码：

- beta：截至前一 bar 的 30 日滚动 beta；shock：截至前一 bar 的 30 日绝对 BTC return `97.5%` 分位；BTC event 冷却 30m。
- `gap = beta * btc_return - alt_return`，只选与 BTC 同号的欠反应。
- 目标：`t+1 open` 到 `t+3 close` 的 alt return 减 beta×BTC return；同一 BTC event 先跨币等权。
- 主配置外只报告 beta 7/90d、shock 95/99%、目标 5/30m、额外 5m 延迟 7 项固定扰动。
- 同事件 BTC 方向、币自身方向与零为简单基准；UTC 日 cluster CI；个币 BY-FDR；2024H1/H2 和 BTC 正/负冲击均报告。
- development 最少 300 个事件、平均至少 8 个可用币；主均值及 CI 下界 >0、两半年均值 >0、击败两基准、无一冲击方向显著反向。
- 只有主均值 `>=12 bp` 且预测门全部通过才下载 2025；32/52 bp 是 base/stress 参照。正回测仍不是净利润，因为 Kline 没有历史 spread/depth、部分成交、funding、mark price、保证金或强平。

数据阶段与父题相同：2023Q4 暖启动、2024 development、2025 evaluation、2026H1 confirmation。与父题不同的 12 个币在本题 checkpoint 前未下载/查看 5m 结果；BTC 文件复用但在本题 manifest 再校验。

## 为什么这是该方向的最后一个直接 lead-lag 层

外部研究把明显的数分钟延迟主要归于小市值/低 trade-count，而成熟币接近同步。本题已下探到中等活动、但仍保留个人可研究的历史长度与当前窄价差。再下探最低活动/新币，历史 spread、depth、下架、跳空和操纵/市场完整性风险会主导；仅靠 OHLCV 无法可靠估净收益，也违背本项目优先个人、小资金、可快速验证且不碰高风险币的取舍。若本题失败，不继续用更差对象或更快 1m 延迟追逐论文收益。

## 实际结果

195/195 个官方月文件通过 checksum（BTC 15 个复用、12 币 180 个新增），每标的 131,904 根完整对齐 5m bar。主配置有 1,470 个事件，平均 8.31 个欠反应币、12 个可用币。

| 指标 | 中等活动币 | 父题成熟/高活动币 |
|---|---:|---:|
| 主均值 | **+2.41 bp** | +2.08 bp |
| 95% UTC 日 cluster CI | [-0.39,+5.21] bp | [+0.02,+4.13] bp |
| BTC sign / own sign 基准 | +2.36 / +2.68 bp | +2.34 / +2.37 bp |
| 最低继续门 | 12 bp | 12 bp |

下探一个活动层没有产生数量级变化；主均值不显著、不优于币自身方向，只有最低成本门的 20%。2024H1 为 +0.08 bp、H2 +4.63 bp，效应仍集中在后半年。

固定扰动进一步显示传导很短且没有经济余量：5m 目标为 +1.98 bp、CI [+0.44,+3.52]，但低于 own-sign +2.04 bp；30m 目标降到 +0.64 bp；额外等待一根 5m bar 后仅 +0.25 bp。q95/q99 分别 +0.33/+1.96 bp，beta 7/90d 均约 +2.5 bp。12 个币 BY-FDR 后无一显著；最高 ANKR +3.64 bp，q=0.748。

开发期每币中位 5m quote volume 约 21,720 至 237,504 USDT，说明结果不是由缺 bar 造成，但这些成交量仍不能代替历史 spread/depth 或保证按小资金无冲击成交。

## 结论

`DOES_NOT_SUPPORT`

固定中等活动、长历史且当前窄 spread 的币没有展示比成熟币更大的个人可行动 BTC lead-lag；可见的 1–3 bp 短效应在额外 5m 延迟后基本消失，且不能覆盖最低 12 bp 代理。2025–2026 不下载、不查看。

结合父题，本项目用基础 Kline、下一 5m open、成熟至中等活动币直接追 BTC→ALT 数分钟传导的空间已基本证伪。外部论文的小币 1m 结果可能仍存在，但继续下探最低活动/新币会把历史盘口、滑点、下架和市场完整性风险置于 OHLCV 能力之外，也不符合本项目个人、小资金、避开高风险对象的优先级；本轮不继续。

机器结果见 `development.json`，数据身份见 `source_manifest_development.json`，复算见 `attempts.md`。不改变产品策略、L4、资金或真实账户状态。
