# 交易对象分类与研究方法复审

复审问题：当前交易对象分类是否准确表达可得数据，且能否专业地把不同对象路由到相称的研究方法，而不把临时筛选误当成资产事实、可交易性或 Alpha 证据？

结论：`SUPPORTS_WITHIN_SCOPE`。修订后的名单适合“当前对象发现、研究选题分流和输入身份固定”，不适合作为历史时点横截面名单，也不能单独判断长期流动性、操纵、容量、策略可执行性或盈利能力。审计评级为 `READY_FOR_DISCOVERY_ROUTING_WITH_CAVEATS_NOT_READY_AS_A_HISTORICAL_RESEARCH_UNIVERSE`。

## 固定基准与审计输入

- 产品/研究基准提交：`d6cd7faa13666bcd12c2b995dcf75459f178b2ca`。
- 工作分支：`codex/vectorbt-research-framework`；本复审不依赖同工作树其他未提交产品修改。
- 官方市场快照：`2026-07-21T064230Z`，访问截止 `2026-07-21T06:42:30Z`。
- 原始公开响应：`source_manifest.json` 所列 9 个 Binance endpoint；Git 外不可覆盖缓存位于 `D:/projects/Codex/CodexHome/research-data/halpha/market-universe/2026-07-21T064230Z/`。
- 修订前规范化 CSV：SHA-256 `d4284afb113b8bf7f8569d3f81c20dd7e83669b1b77c5c06e9353865b647bcb3`。修订前画像保存在 `methodology_audit.json`，避免以后重复发现同一问题。
- 当前规范化 CSV 和审计身份以 `summary.json`、`validation.json`、`methodology_audit.json` 为准。

## 发现、影响与处理

| 严重度 | 发现与量化证据 | 对研究的影响 | 处理 |
|---|---|---|---|
| 高 | 修订前 590 个非美元类或不可比报价对象中，534 个自动进入 `CRYPTO_SPECULATIVE_OR_THIN`；其中 COIN-M 的 30 个 ticker 全部没有 `quoteVolume`，24 个非 anchor 合约被判为 speculative/thin | 把“没有统一换算单位”错误解释为“薄弱或投机”，会错误排除 COIN-M 和 BTC/ETH/BNB 报价对 | 非可比 quote 改为 `MARKET_QUALITY_UNRATED`；COIN-M 使用官方 `volume × contractSize` 生成 USD face-notional activity proxy。30 个 ticker 与 `baseVolume × weightedAvgPrice` 交叉核对的最大相对差约 0.018%，结果与来源留存在审计 JSON |
| 高 | 修订前 `liquidity_tier_24h` 只使用一个滚动 24 小时成交额分位；Spot 1,366 个当前对象全部缺官方上市时间，却有 304 个直接命名为 `CRYPTO_LIQUID_ALT` | 单日活动、缺失历史和一次盘口不能支持“流动”或“主流”判断，会放宽回测成本与样本门槛 | 字段改为 `activity_tier_24h`，所有档位明确 `PROVISIONAL_24H`；研究资格统一要求 30–90 日持续性、成本和订单规模门槛 |
| 中 | USD-M/USD1 仅 3 个对象仍被强制分出高、中、低档 | 小组分位看似精确，实际由样本个数机械决定 | 所有 dollar-like quote 先转换为同一近似美元活动单位，并在同一 market 内比较；少于 20 个对象时保持 `UNRATED_SMALL_COMPARISON_GROUP` |
| 中 | `manipulation_risk_proxy` 虽声明不是认定，名称仍把低量、新币、Meme 与操纵风险绑定 | 容易让后续研究把筛选信号当作完整性结论 | 改为 `market_integrity_review`，只表达标准、增强或法证级证据要求；任何档位都不是操纵发现 |
| 中 | `CRYPTO_NATIVE` 是 Spot 缺少官方 taxonomy 后的默认值，但此前没有逐行来源 | 稳定币、新类别或 ticker 复用可能被误当作原生加密资产 | 新增 `economic_exposure_source`；默认值明确为 exclusion-based fallback，并增加风险标志；稳定/法币映射继续小规模显式维护 |
| 中 | 126 个当前 TradFi equity/fund perpetual 只有宽泛官方类型，不能可靠区分单股、普通 ETF、杠杆/反向 ETF 等 | 公司行动、杠杆重置、跟踪误差和基准选择完全不同，混池研究会失真 | 全部设置 `REFERENCE_PRODUCT_IDENTITY_AND_30_90D_MARKET_QUALITY_REQUIRED_BEFORE_STRATEGY_RESEARCH`，身份和市场质量未核对前禁止进入策略研究 |
| 高（未消除） | 当前只有一个 exchangeInfo 快照 | 历史横截面会产生幸存者和下架偏差，当前名单不能回填过去 | 任何资产选择、轮动或横截面研究必须另取 point-in-time membership；否则只允许固定 instrument 的探索，不能声称全市场证据 |

## 正确的研究分流顺序

分类本身不直接授权回测。每个问题按以下顺序过门；前一门未知时不应靠后续漂亮指标跨过。

1. **经济对象身份门**：确认是原生加密、稳定/法币相对、发行人支持的 tokenized commodity，还是 TradFi reference derivative。TradFi 还要确认单股、普通基金、杠杆/反向基金、指数或商品的具体参考产品。
2. **工具结构门**：分别处理 Spot、USDⓈ-M 线性合约、COIN-M 反向/交割合约和 TradFi perpetual；固定结算资产、合约面值、funding、到期、保证金、价格指数与闭市语义。
3. **市场质量门**：当前 24 小时档位只能产生候选。真正研究前至少用 30–90 日中位 dollar-notional volume、有效交易日覆盖、spread 或 bar 可得的 Amihud 类价格冲击代理、波动/跳空、预期订单规模成本及其跨期稳定性复核。30–90 日是面向个人、小资金、快速验证的项目筛选窗口，不是跨周期 Alpha 验证期；窗口选择本身要记录。用户不采用 L2 时，不强制建设深度数据；但低活动对象因此只能停留在探索，不能作精确可执行/容量结论。
4. **历史时点门**：横截面、选币和轮动必须用当时可知的上市/下架状态与字段；单个当前快照只适合当前发现，不能构造历史 universe。
5. **策略证据门**：再选择 VectorBT 时间序列或横截面实验，并纳入手续费、funding、spread/slippage、下一可行动时间、试验总数、walk-forward/留出、市场 beta、size、momentum、liquidity 和更简单解释。通过研究不等于产品交付；候选仍需框架无关 fixture 和 NautilusTrader 执行验证。

## 各研究桶的专业用途

| 研究桶 | 可以做什么 | 不可以据此推出什么 |
|---|---|---|
| `CRYPTO_ANCHOR_REFERENCE` | BTC/ETH 市场基准、时间序列、跨工具 basis/funding；也可在单独通过市场质量门后成为候选 | “安全资产”“低风险”或所有 BTC/ETH 工具均有相同流动性 |
| `CRYPTO_ALT_HIGHER_ACTIVITY_PROVISIONAL` | 通过 30–90 日门后做时间序列或横截面，控制 crypto market、size、momentum、liquidity 和单币集中 | 主流币、长期流动、可盈利或可直接上线 |
| `CRYPTO_ALT_MID_ACTIVITY_PROVISIONAL` | 选择性趋势、carry、事件研究；使用更高成本、下架和 regime stress | 与高活动对象相同的成本和容量 |
| `CRYPTO_ALT_LOWER_ACTIVITY_PROVISIONAL` | 市场质量、上市/事件机制探索；只有更强 trade/book 证据才讨论执行 | 低活动就是 Alpha、就是操纵，或 OHLCV 盈利即可交易 |
| `CRYPTO_ALT_MARKET_QUALITY_UNRATED` | 先做 quote 换算与可比活动单位；可研究固定对象机制 | 因未评级而推断薄弱、投机或低质量 |
| `STABLE_OR_FIAT_RELATIVE` | peg、depeg、发行/赎回、FX 与 quote 风险；按参考币种换算 | 与方向性 crypto beta 混池 |
| `TOKENIZED_COMMODITY` | 原始商品基准 + token 发行人、储备、赎回、tracking 和 venue 风险 | token 与金条、传统期货或 TradFi perp 等价 |
| `TRADFI_COMMODITY_PERP` | 原商品数据/日历 + Binance basis、funding、指数/EWMA 与闭市跳空 | 24/7 Binance 价格等同于原市场连续可交易价格 |
| `TRADFI_EQUITY_OR_FUND_PERP` | 身份门通过后，按具体产品使用原市场价格、日历、公司行动/杠杆重置，再研究 Binance basis/funding | USDT 合约代表证券所有权，或单股与 ETF 可用同一方法混池 |
| `TRADFI_PREMARKET_PERP` | 极短期价格发现与事件探索 | 有足够历史、公允价值或可长期验证的策略证据 |

## 对标专业方法后的判断

- **准确性**：经济暴露与工具结构由官方字段、显式映射及逐行来源支撑，适合当前 discovery；Spot 默认 `CRYPTO_NATIVE`、稳定币映射和跨市场 subtype 继承仍是有标记的研究近似，不是官方完整 taxonomy。
- **市场质量**：当前只达到专业流程的低成本第一筛。专业可执行性研究通常还看持续成交额、spread、价格冲击/深度和预期订单规模；本项目选择基础数据时可以用 OHLCV、trade count、best bid/ask 和保守成本代理覆盖大部分筛选，但要放弃对低活动市场的精确容量和操纵结论。
- **换算单位**：dollar-like quote volume 只是近似 USD activity proxy；每个研究仍须检查 quote 平价、depeg 和基准币种。非 dollar-like quote 未换算时保持未评级，不以缺失代替低流动判断。
- **横截面**：当前名单不具备 point-in-time 历史，这是最重要的剩余差距。若问题只研究固定 instrument 的时间序列，影响可控；若做选币、轮动、因子排序，必须补齐后才有专业意义。
- **结论强度**：名单能提高“研究什么、用什么门槛”的准确性，不能提高回测本身的独立证据强度，更不能把盈利回测升级为真实 Alpha 证明。

## 重演

```powershell
D:\Environment\python313\python.exe research/market-universe/refresh_universe.py --raw-cache-dir D:/projects/Codex/CodexHome/research-data/halpha/market-universe/2026-07-21T064230Z
D:\Environment\python313\python.exe research/market-universe/validate_universe.py
D:\Environment\python313\python.exe research/market-universe/audit_methodology.py
```

本复审没有下载 OHLCV/L2/订单流、没有运行策略、没有读取产品数据，也没有产生任何交易动作。`SUPPORTS_WITHIN_SCOPE` 仅支持分类与研究分流，不是任何候选策略的研究结论。
