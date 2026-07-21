# 多资产持续正 funding 单币轮动 cash-and-carry 研究

## 状态与边界

- 稳定产品基准提交：`de6b3052f28fe547730e89e58186d4ab397884b1`
- 固定正式策略：`ONE_SHOT_DONCHIAN_ATR_BREAKOUT` `1.0.0`
- 候选身份：`RESEARCH_MULTI_ASSET_PERSISTENT_POSITIVE_FUNDING_CARRY`
- 机制：同一 Binance 场所、一次只在一个币上 long spot / short 等初始名义 USDⓈ-M perpetual，两单位 fully-funded capital。
- 开发/评价宇宙：`DOGEUSDT`、`XRPUSDT`、`ADAUSDT`；跨标的确认：`LTCUSDT`、`LINKUSDT`。
- cutoff：`2026-01-01T00:00:00Z`；不使用不完整 2026 年来制造机会。
- 用途：解决上一 carry 研究 `INSUFFICIENT_EVIDENCE` 留下的年度集中与短 episode 成本问题；若支持只计一个 carry 候选，不与既有单币研究重复计数。

公开研究数据与代码独立于产品；不读产品数据库、业务数据、秘密或运行配置，不启动产品运行时，不调用交易所变更端点。结果不授权产品、L4、资金或真实交易变化。

## 继承证据、候选与选择

`research/studies/legacy/2026/binance-positive-funding-cash-carry/` 固定 3 bp 在 BTC 开发 +23.13%、BTC 评价 +5.35%、BNB 确认 +9.04%，但 BTC 2025 无交易、BNB 后四年小负，结论 `INSUFFICIENT_EVIDENCE`。它说明方向对冲与阈值有潜力，也说明单次高 funding 入场会产生许多不足以覆盖 round trip 的短 episode。

| 候选 | 未解决差异 | 个人/小资金适配 | 取舍 |
|---|---|---|---|
| 连续两次 ≥3 bp、五币分两组、一次一币 | 过滤瞬时尖峰；增加机会来源但不并发多仓 | 同场所两腿；最多一组；可按小名义缩放 | **选中** |
| 同时持有所有高 funding 币 | 分散单币 basis | 多腿、资本和故障面扩大 | 淘汰 |
| 每个结算点切换到最高币 | 捕捉相对机会 | 8h 高频换手，两腿成本过高 | 淘汰 |
| 跨场所 funding spread | 机会更多 | 双场所库存、转账与故障 | 淘汰 |
| 事后改为 5 bp | 既有 BTC 看起来更强 | 明确参数后见；不采用 | 淘汰 |

## 先行联网调研（访问日 2026-07-20）

1. He、Manela、Ross、von Wachter，[Fundamentals of Perpetual Futures](https://arxiv.org/abs/2212.06888)：含摩擦无套利边界支持 spot/perp 对冲，但交易成本决定能否实现。
2. Ackerer、Hugonnier、Jermann，[Perpetual Futures Pricing](https://www.nber.org/papers/w32936)：periodic funding 的锚定与复制条件，不能替代实际 basis/保证金验证。
3. Gornall、Rinaldi、Xiao，[Perpetual Futures and Basis Risk](https://ssrn.com/abstract=5036933)：受限套利资本和 basis 风险解释偏离，要求保留全额资本与 basis PnL。
4. Inan，[Predictability of Funding Rates](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5576424)（2025）：Binance/Bybit BTC 下一期 funding 有样本外可预测性但稳定性随时间变化；它支持检验简单 persistence，而不授权复杂模型。
5. Zhang，[Funding Rate Mechanism in Perpetual Futures](https://ssrn.com/abstract=6185958)（2026）：funding 是反馈规则并诱导 basis 均值回归，但危机跳跃会产生大幅负 basis 与慢恢复。
6. [Binance Public Data](https://github.com/binance/binance-public-data) 与 [Funding History](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Get-Funding-Rate-History)：spot/perp 8h 官方归档、checksum、2025 spot 微秒时间戳和 settled funding 来源。

## 固定问题、规则和否定条件

问题：若某币最近两次已结算 funding 均 ≥3 bp，且当前是固定宇宙中 rate 最高者，则在当前结算后建立 long spot / short perp；持有至该币以后某次 settled rate ≤0。一次只持一个币。这一规则能否在两腿 basis、实际 funding、两单位资本和现实成本后，于 2021–2023 开发、2024–2025 独立评价及 LTC/LINK 2021–2025 跨标的确认中保持正收益？

- 入场只用当前及前一次已结算 rate；当前 rate 不计收入。若多个合格，选当前 rate 最高，字母序破同值。
- 持有中不因其他币 rate 更高切换；selected rate ≤0 后先计该次 funding，再退出；样本末强退。
- episode 内 spot/perp 数量固定；basis PnL 用各腿相对入场价的增量；全额两单位资本，收益除以 2。
- 每次入场或退出两腿合计有利/base/stress 为一腿名义 16/24/40 bp；完整 round trip 换算两单位资本同为 16/24/40 bp。
- 固定 3 bp 和两次 persistence 均在新 basis/funding 数据前确定；不搜索阈值、次数、退出、币或成本。
- 基准为现金零收益；正式 Donchian/ATR 不具经济可比性。

开发门：所有事件/价格完整对齐；base 与 stress 非复合累计收益均正；至少 10 episodes、100 active 8h；episode 中位数为正、胜率 ≥50%；base 最大非复合回撤 > -10%。失败即停止。

评价门：base/stress 收益均正；至少 3 episodes、30 active 8h；episode 中位数非负、最大回撤 > -10%。没有机会（零 episode）是 `INSUFFICIENT_EVIDENCE`，不能当盈利。

`SUPPORTS_WITHIN_SCOPE` 还要求 LTC/LINK 确认 base/stress 均正；至少 10 episodes、100 active 8h；两币均至少被选择一次；episode 中位数非负、最大回撤 > -10%。评价或确认 base 为负则 `DOES_NOT_SUPPORT`；其他未过支持门为 `INSUFFICIENT_EVIDENCE`。盈利回测不证明无风险套利或 Alpha。

## 数据暴露与启封

五币 spot 日线价格曾在 long-only 研究查看，但 8h spot/perp basis、funding 和本机制结果均未查看；因此是机制新数据，不是价格方向全新。所有 spot/perp/funding 在 checkpoint 与代码固定后才下载。

| 数据 | 用途 | 状态 | 启封 |
|---|---|---|---|
| DOGE/XRP/ADA 2021–2023 | development | 已运行；正但 episode 不足 | checkpoint/代码后 |
| DOGE/XRP/ADA 2024–2025 | evaluation | **未查看、未下载** | 开发门失败，保持封存 |
| LTC/LINK 2021–2025 | cross-instrument confirmation | **未查看、未下载** | 开发门失败，保持封存 |

Python 3.11+ 标准库；外部缓存：`D:/projects/Codex/CodexHome/research-data/halpha/multi-asset-persistent-funding-carry/`。单次 8h open 无法证明两腿同步成交；订单簿、部分成交、腿风险、保证金/ADL、资金划转、USDT 机会成本、税务和场所故障未建模。

## 实际结果

216 个 spot/perp 月档通过官方 checksum，9,855 条 funding。XRP futures 月归档缺 2022-02-26 至 28、2022-04-01 至 02 的 15 个 8h 边界；官方 USD-M Kline REST 全部返回，补数 SHA-256 `fd0df4962a1c40d851f0bf5043d92a107659c0c4608f625768a8cc9134e3cc34`，不覆盖原档。修复后所有三币 funding 事件与 spot/perp open 完整对齐。

| 开发指标 | 结果 |
|---|---:|
| active 8h / episodes | 827 / **5** |
| base / stress 非复合收益 | **+69.06% / +68.26%** |
| funding / basis / base cost | +70.54% / -0.27% / -1.20% |
| episode 中位数 / 胜率 | +2.74% / 80% |
| active mean block-bootstrap 95% | [+0.0569%, +0.1143%] |
| 最大非复合回撤 | -1.77% |
| 入选次数 DOGE / XRP / ADA | 3 / 2 / **0** |

一个 DOGE episode 贡献约 +62.46%，五个 episode 的收益依次约 -0.12%、+62.46%、+2.83%、+2.74%、+1.17%。证据方向很强，但低于预注册 10 episodes，且资产覆盖不足；大部分收益来自单一 episode，不能形成稳定可用结论。

## 结论

`INSUFFICIENT_EVIDENCE`

该规则保留为高价值、明确盈利潜力的 carry 候选，但当前样本稀疏，不能计作已获支持策略，也不能为了打开 holdout 事后降低 episode 门槛。研究不改变产品策略、L4、资金或真实账户状态。

原始缺数尝试、修复后命令、缓存与 digests 见 `attempts.md`；机器汇总见 `development_backfilled.json`、`selection_backfilled.json`、`results.json`。
