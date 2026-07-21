# Binance 研究资产宇宙与方法分类

问题：Binance 官方公开市场元数据能否形成一份可重取、可审计的当前交易对象名单，并用不依赖主观“主流/垃圾币”判断的标签，为不同对象选择相称研究方法？

结论：`SUPPORTS_WITHIN_SCOPE`。截至本目录 `source_manifest.json` 记录的时间，Spot、USDⓈ-M 与 COIN-M 官方 `exchangeInfo` 足以固定交易对象、状态、合约与部分资产类型；结合公开 24 小时 ticker 和最优报价可以形成**临时候选筛选**。它不能证明操纵、长期流动性、资产市值、真实成交质量或历史时点可交易性，因此这些标签只用于对象发现与研究设计，不直接允许回测、交易或形成 Alpha 结论。复审详情和修订前量化证据见 `methodology-review.md` 与 `methodology_audit.json`。

## 范围与取舍

候选范围：

| 候选 | 优点 | 缺点 | 决定 |
|---|---|---|---|
| 仅当前产品使用的 USDⓈ-M | 最小，直接包含 TradFi perpetual | 漏掉现货基准和币本位合约，无法看见同一资产的不同结构 | 不选 |
| Binance Spot、USDⓈ-M、COIN-M | 覆盖当前主要现货与线性/反向合约；官方接口一次可重取；仍适合个人维护 | 不包括 Options、Earn、链上和其他场所 | 选中 |
| Binance 所有产品与多场所全市场 | 最完整 | 产品语义不同、维护和去重成本远超当前研究价值 | 不选 |

`universe.csv` 保留官方接口返回的当前和非当前记录，当前研究初筛使用 `currently_trading=true`。保留非交易记录有助于提示幸存者偏差，但单个当前快照不能重建过去任一日的真实可交易名单。Options 不是普通交易对且要求另一套波动率曲面和到期结构研究，暂不纳入。

## 标签不是单一等级

名单把对象拆成四类正交信息：

1. **经济暴露**：原生加密、BTC/ETH anchor、代币化商品、TradFi 商品 perpetual、TradFi 股票或基金 perpetual、指数、pre-market。
2. **交易工具**：Spot、USDⓈ-M perpetual/delivery、COIN-M perpetual/delivery；它决定 funding、保证金、清算和基差模型。
3. **临时活动代理**：同一市场内可换算为近似 USD notional 的 24 小时活动分位、交易数、一次最优买卖价差、上市时间和当前状态。Spot/USDⓈ-M 使用 dollar-like quote volume 并明确记录平价假设；COIN-M 使用官方 contract volume × contract size。它刻意不叫“流动性档位”。
4. **风险标志**：新上市、低或未知活跃度、宽价差、官方 Meme/Alpha subtype、pre-market、非美元类 quote、TradFi 参考资产与闭市跳空、token 发行人/储备/赎回风险。

`market_integrity_review` 只表示标准、增强或法证级尽调要求。它不能认定某个币或交易对受到操纵；公开 OHLCV、24 小时量和单次盘口都不足以做这种认定。

“主流山寨币”不作为永久人工名单，因为当前官方元数据和单日成交不能准确支持该事实。加密对象只按 `HIGHER/MID/LOWER 24H ACTIVITY PROVISIONAL` 或 `MARKET_QUALITY_UNRATED` 进入候选研究通道；真正研究前必须用至少 30–90 日中位 dollar-notional volume、交易日覆盖、spread/price impact、预期订单规模成本和跨期稳定性重新确认。这个短窗口只服务个人/小资金的快速市场质量筛选，不足以验证跨周期 Alpha。Meme/Alpha 等主题是正交风险标志，不能直接触发“操纵”或“投机币”结论。Spot 本身没有 subtype 时，可以继承当前 USDⓈ-M 同一 underlying 的官方 subtype；原字段、派生字段和来源分别保存，且继承标签只增加反证，不单独改变研究资格。

`economic_exposure_source` 说明每行经济分类来自官方字段、显式映射还是 `DEFAULT_CRYPTO_NATIVE_AFTER_EXPLICIT_EXCLUSIONS`。最后一种只是 Spot 缺少官方 taxonomy 时的保守默认，不是资产身份的官方证明。BTC/ETH 的 anchor 也只是模型中的参考角色，不代表安全或低风险。

## 不同类型采用不同研究倾向

| 分类 | 优先问题与方法 | 必须增加的反证或成本 | 默认限制 |
|---|---|---|---|
| `CRYPTO_ANCHOR_REFERENCE` | 时间序列、跨市场、funding/basis、作为市场 beta 参考 | 多市场状态、funding、费用和延迟 | 参考用途允许；策略用途仍要通过 30–90 日市场质量和成本门，不把 beta 当 Alpha |
| `CRYPTO_ALT_HIGHER_ACTIVITY_PROVISIONAL` | 通过历史门后的横截面与时间序列；VectorBT 批量比较 | crypto market beta、size、momentum、liquidity、单币集中度和主题风险 | 不是“主流/高流动”结论；资产和参数选择均计入试验数 |
| `CRYPTO_ALT_MID_ACTIVITY_PROVISIONAL` | 通过历史门后选择性研究趋势、carry、事件和相对价值 | 更高 spread/slippage、容量、下架与短历史压力 | 必须有稳健区域，不接受单点最优 |
| `CRYPTO_ALT_LOWER_ACTIVITY_PROVISIONAL` | 先研究上市事件和市场质量 | trade/book 或保守价格冲击代理、跳空、极端成本、单次事件支配、幸存者偏差 | 在市场质量证据前只做探索，bar 回测盈利不足以进入产品考虑 |
| `CRYPTO_ALT_MARKET_QUALITY_UNRATED` | 先完成 quote 换算和可比活动单位 | 不完整单位、跨 quote 成本与基准误差 | 未评级不等于薄弱或投机；不能直接选择策略方法 |
| `TOKENIZED_COMMODITY` | 同时研究原始商品基准与 token 跟踪 | 发行人、储备、赎回资格、场所与 quote 风险 | 不能把 token 等同于金条或传统期货 |
| `STABLE_OR_FIAT_RELATIVE` | peg、储备或外汇相对价值 | depeg 尾部、quote 换算、场所分割和发行人风险 | 不与方向性 crypto beta 混池 |
| `TRADFI_COMMODITY_PERP` | 原始商品基准/交易日历 + Binance perp basis/funding | 闭市跳空、指数/EWMA 机制、合约规格变化 | 不与 24/7 crypto bar 直接混池 |
| `TRADFI_EQUITY_OR_FUND_PERP` | 先确认单股、普通基金、杠杆/反向基金等身份，再用原证券价格、交易日历、财报/公司行动 + Binance basis/funding | 股票闭市、公司行动、ETF 杠杆重置、周末价格发现 | 身份未确认前禁止策略研究；Binance 合约是 USDT 结算衍生品，不是股票所有权 |
| `TRADFI_PREMARKET_PERP` | 事件与价格发现研究 | 缺少公开上市历史和可靠公允价值、极短样本 | 默认仅探索 |

贵金属存在两种不同对象：PAXG/XAUT 是带发行人和赎回结构的 token；XAUUSDT/XAGUSDT 等是 Binance USDT 结算、跟踪传统资产参考价格的 perpetual derivative。二者不能合并成同一“黄金”数据列。

## 数据与重演

规范化名单与重要验证数据：

- `universe.csv`：所有官方返回记录、当前状态、原始市场字段、筛选标签和方法倾向。
- `summary.json`：数量、分类分布、CSV 哈希和边界。
- `source_manifest.json`：每个公开 endpoint、访问时间、原始响应 Git 外位置、字节数和 SHA-256。
- `methodology-review.md`：分类准确性、严重问题、专业门槛和不同对象的方法指引。
- `methodology_audit.json`：修订前证据、当前画像、剩余限制与自动检查结果。
- Git 外原始响应：`D:/projects/Codex/CodexHome/research-data/halpha/market-universe/<snapshot-id>/`。

重演命令：

```powershell
D:\Environment\python313\python.exe research/market-universe/refresh_universe.py --cache-root D:/projects/Codex/CodexHome/research-data/halpha/market-universe
```

从当前 manifest 指向的原始响应离线重建完全相同的市场截面：

```powershell
D:\Environment\python313\python.exe research/market-universe/refresh_universe.py --raw-cache-dir D:/projects/Codex/CodexHome/research-data/halpha/market-universe/2026-07-21T064230Z
D:\Environment\python313\python.exe research/market-universe/validate_universe.py
D:\Environment\python313\python.exe research/market-universe/audit_methodology.py
```

刷新会更新当前 `universe.csv`、`summary.json` 和 `source_manifest.json`，并新建不可覆盖的时间戳原始缓存。Git 提交历史用于保留规范化名单的历史版本；如果未提交，只能称为保留在当前工作树。

## 否定条件与剩余未知

- 若官方接口不再提供稳定 symbol/status/contract/underlying 字段，当前分类不能自动延续，应降低为 `CANNOT_DETERMINE`，而不是猜测映射。
- 若一个策略依赖长期流动性或历史全市场横截面，必须取得历史点时名单或逐期重建上市/下架状态；本快照不能消除幸存者偏差。
- 24 小时活动分位、一次价差和官方 subtype 只能分流研究成本，不能证明“主流”、长期流动、安全、无操纵或可长期盈利。
- 非 dollar-like quote 在换算和 30–90 日确认前保持 `MARKET_QUALITY_UNRATED`；未知不能再自动解释为薄弱或投机。
- Meme、Alpha 或其他主题标签与市场质量分层正交；任何一个主题标签都不能单独触发“被操纵”或不可研究结论。
- stable/fiat 资产集合是代码中显式的小型映射；Binance 增加新 quote 或参考资产时必须人工核对，不能仅凭 symbol 名称静默扩展。
- Binance `underlyingSubType` 同时包含资产主题与 `USDC/Cross Pair` 等合约标记；分类字段过滤已知非经济标记，CSV 仍保留逐 instrument 官方原字段和派生来源，未知新标记必须复核。
- TradFi 具体对象是单一股票、普通 ETF、杠杆/反向 ETF、商品或 pre-market reference，必须在每项研究中用官方合约和原始市场资料再次确认。
