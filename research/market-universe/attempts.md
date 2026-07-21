# 实际尝试

1. 扫描既有 `research/**`：已有 PAXG、TRX/PAXG 和若干单币/篮子研究，但没有全市场当前名单；`catalog.json` 是研究问题查重，不是交易对象宇宙。
2. 先考虑仅使用当前产品的 Binance USDⓈ-M。官方快照能识别 TradFi，但会漏掉 Spot token 与 COIN-M 的不同结构，因此改为三个核心公开市场。
3. 检查官方 `exchangeInfo`：确认 USDⓈ-M 对 TradFi 提供 `TRADIFI_PERPETUAL` 和 `COMMODITY/EQUITY/KR_EQUITY/HK_EQUITY/PREMARKET`；Spot 没有相称资产分类或 onboard date，因此没有从 symbol 名称大规模猜测。
4. 检查 24 小时 ticker 与 book ticker：能够提供一次性 quote volume、trade count、bid/ask，但不足以代表长期市场质量，故只生成临时分位标签。
5. 放弃把 `LOW_LIQUIDITY + MEME + NEW` 命名为“操纵”：改为 `manipulation_risk_proxy`，并在每行明确 `NOT_A_FINDING`。
6. 将 PAXG/XAUT token 与 XAU/XAG TradFi perpetual 分开；后者是现金结算衍生品，不是 token 或实物所有权。
7. 选择 CSV + JSON + Git 外原始响应，而不是数据库或定时服务。刷新是显式命令，适合当前一人维护规模。
8. 首次生成 `2026-07-21T063807Z` 快照后发现 stable/fiat-relative 对象落入通用未分类桶；补充独立研究桶后生成第二版，没有修改官方源数据。曾尝试在最终离线重演后清理两份分钟级中间原始响应，但递归删除被本地安全策略拒绝，未绕过；三份快照目前合计约 60 MiB，只有 `2026-07-21T064230Z` 被当前 manifest 引用。
9. 复核 DOGE 发现 Spot 没有官方 subtype、USDⓈ-M 有 `Meme`，会造成同一 underlying 跨工具分类不一致。第三版保留逐 instrument 原字段，另增加带来源的 asset-level classification subtype；只有当前 USDⓈ-M 同 underlying 可核对时才继承。
10. 第三版显示 DOGE 的继承标签为 `Meme|USDC`，说明官方 subtype 混有合约 quote 标记。最终分类过滤已知 `USDC/Cross Pair` 非经济标记，并从第三版 `2026-07-21T064230Z` 原始缓存离线重建，验证无需重新下载即可得到同一官方截面。
11. 当时曾将 Meme 从一律 speculative 改为“流动性桶 + 正交主题风险”，DOGE 保持 liquid alt 并增加事件/拥挤反证；后续第 12–18 项复审进一步发现“liquid”本身仍超出单日数据证据，因此该中间方案已被临时 activity bucket 取代。
12. 再次方法审计发现上述“流动性桶”仍过度表达数据：修订前 CSV（SHA-256 `d4284afb113b8bf7f8569d3f81c20dd7e83669b1b77c5c06e9353865b647bcb3`）中，590 个非 dollar-like 或不可比 quote 当前对象有 534 个进入 `CRYPTO_SPECULATIVE_OR_THIN`；COIN-M 30 行全部没有 `quoteVolume`，其中 24 个非 BTC/ETH 对象被错误分流。没有统一单位不等于薄弱或投机。
13. 同次审计发现 Spot 的 1,366 个当前对象全部缺少官方 onboard date，却有 304 个被命名为 `CRYPTO_LIQUID_ALT`；另有仅 3 个对象的 USD-M/USD1 小组仍被机械分位。结论降级：单个 24 小时成交额分位只能称为 activity discovery tag，不能称 liquidity、mainstream 或长期 market quality。
14. 检查 COIN-M 官方字段和原始响应：ticker 具有 `volume/baseVolume`，exchangeInfo 具有 `contractSize`。改用 `volume × contractSize` 作为带来源的 USD face-notional activity proxy；其他无法换算 quote 保持 `MARKET_QUALITY_UNRATED`，不再推断 speculative/thin。dollar-like quote 在同一 market 内共同分位，并增加 20 个对象的最小比较组门槛。
15. `manipulation_risk_proxy` 即使带 `NOT_A_FINDING` 仍可能诱导后续研究，故改为 `market_integrity_review`：只表达标准、增强或法证级尽调要求。任何值都不构成操纵认定。
16. Spot 缺少官方资产 taxonomy，原先默认 `CRYPTO_NATIVE` 没有逐行来源。新增 `economic_exposure_source`，把官方字段、显式映射和 exclusion-based fallback 分开；根据发行人/协议官方资料补充 RLUSD、EURI、U、USDS 的稳定/法币相对映射。
17. TradFi 官方 `EQUITY/KR_EQUITY/HK_EQUITY` 仍不能可靠区分单股、普通 ETF、杠杆/反向 ETF。没有从 ticker 猜测；126 个当前 equity/fund perpetual 全部增加 `REFERENCE_PRODUCT_IDENTITY_AND_30_90D_MARKET_QUALITY_REQUIRED_BEFORE_STRATEGY_RESEARCH` 硬门。
18. 对标 Amihud 类价格冲击、crypto liquidity/market efficiency、wash-trading 交易分布与 crypto survivorship/delisting 研究后，固定五门顺序：经济对象身份、工具结构、30–90 日市场质量、历史时点、策略证据。当前名单只通过前两门的部分字段并提供第三门的临时发现输入，不能承担历史横截面或 Alpha 结论。
