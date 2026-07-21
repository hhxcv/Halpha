# 来源与适用性

访问日期均为 2026-07-21。

## Binance 官方市场资料

- Binance Developer，USDⓈ-M [Exchange Information](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Exchange-Information) 及公开 `https://fapi.binance.com/fapi/v1/exchangeInfo`：提供 symbol、status、contractType、onboardDate、underlyingType/subType、精度与过滤器。用于 USDⓈ-M 名单和官方资产大类；不证明长期流动性、真实成交或参考资产等价。
- Binance Developer，Spot [Exchange Information](https://developers.binance.com/docs/binance-spot-api-docs/rest-api/general-endpoints#exchange-information) 及公开 `https://api.binance.com/api/v3/exchangeInfo`：提供 Spot symbol、status、权限和过滤器。Spot 不提供可靠 onboard date 或资产经济分类，因此相应字段保持未知或只对少数已核对 token 使用有界映射。
- Binance Developer，COIN-M [Exchange Information](https://developers.binance.com/docs/derivatives/coin-margined-futures/market-data/rest-api/Exchange-Information)、[24hr Ticker](https://developers.binance.com/docs/derivatives/coin-margined-futures/market-data/rest-api/24hr-Ticker-Price-Change-Statistics) 及公开 endpoint：`exchangeInfo` 提供 `contractSize`，ticker 提供 `volume` 与 `baseVolume` 而不提供 USDⓈ-M/Spot 同义的 `quoteVolume`。当前实现把 `volume × contractSize` 记录为 USD face-notional activity proxy，并逐行标明来源；它是可比筛选代理，不是成交额审计或流动性结论。COIN-M 与 USDⓈ-M 的结算、保证金和收益单位仍不能混成同一回测列。
- 同三个官方市场的公开 24 小时 ticker 和 book ticker：仅用于访问时点活动度与最优报价筛选。单日量和一次 top-of-book 不能支撑长期流动性、容量或操纵结论；因此修订后字段使用 `activity_tier_24h` 而不是 `liquidity_tier`。
- Binance Academy，[How to Trade Stock Perpetual Contracts on Binance](https://academy.binance.com/en/articles/how-to-trade-stock-perpetual-contracts-on-binance)：官方说明 stock/TradFi perps 是跟踪传统资产的 USDT 结算 perpetual，不代表股票所有权；还说明传统市场闭市、公司行动/财报造成的价格跳空，以及 2026-05 后 equity/commodity TradFi perps 的 Orderbook EWMA index 模式。适用于确定 TradFi 必须单独研究 reference、闭市、basis 和 funding；不证明 Binance 合约始终精确复制原资产。
- Binance Academy，[TradFi Assets You Can Trade on Binance Futures](https://academy.binance.com/en/articles/tradfi-assets-you-can-trade-on-binance-futures) 与 [How to Trade Gold and Silver on Binance Futures](https://academy.binance.com/en/articles/how-to-trade-gold-and-silver-on-binance-futures)：确认股票、ETF/指数和商品 exposure 以及 XAU/XAG 是现金结算 perpetual，而非实物金属。文章列举不是机器可重演的完整名单，实际名单仍以 `exchangeInfo` 快照为准。
- Paxos，[PAXG 官方说明](https://www.paxos.com/pax-gold) 与 [PAX Gold 条款](https://www.paxos.com/terms-and-conditions/pax-gold-terms-conditions)：发行人说明每枚 PAXG 对应一金衡盎司 London Good Delivery gold，但赎回、账户资格、最低实物交付量和处理时间受条款约束。用于把 PAXG 标为 tokenized commodity 并要求发行人/赎回风险，不能把 Binance 二级市场余额等同于用户可立即提取金条。
- Tether Gold，2026-03-31 [储备鉴证](https://gold.tether.to/docs/reports/attestations/ISAE_3000R_-_Opinion_TGRR_31.03.2026_RC187322026DV0089.pdf)：鉴证结论覆盖每枚 XAU₮ 至少一金衡盎司黄金的储备主张。它支持 XAUT 的 tokenized commodity 分类；不替代当前持有人资格、赎回、场所托管和二级市场跟踪检查。
- Ripple，[RLUSD 官方文档](https://docs.ripple.com/products/stablecoin/overview/rlusd)：说明 RLUSD 目标为 1:1 USD 支持的稳定币，并说明储备、机构赎回和合规条件。用于显式 stable/fiat-relative 映射，不代表 Binance 二级市场始终维持 1 美元或个人可直接赎回。
- Eurite，[EURI 官方资料](https://www.eurite.com/)：说明 EURI 是 Banking Circle 发行、1:1 EUR 对应的 e-money token。用于显式 stable/fiat-relative 映射；研究仍须纳入 EUR 汇率、发行人和场所风险。
- United Stables，[U 官方资料](https://www.u.tech/)：说明 U 是 USD-pegged stablecoin，并披露发行与监管边界。用于把 U 从默认 `CRYPTO_NATIVE` 改为显式 stable/fiat-relative；它不证明 peg 或储备在研究期内持续有效。
- Sky Protocol，[USDS 官方文档入口](https://developers.sky.money/guides/)：用于确认 USDS 属于 Sky Protocol 稳定币体系。当前分类只确认经济用途，具体 collateral、转换和治理风险必须在相关研究中另行核对。

## 研究方法依据

- Liu, Tsyvinski and Wu, [Common Risk Factors in Cryptocurrency](https://www.nber.org/papers/w25882)，NBER Working Paper 25882，后发表于 *Journal of Finance* 77(2)：crypto market、size 和 momentum 能解释其样本中的横截面收益。它支持 liquid alt 研究控制市场、规模和动量；不能证明这些因子在当前 Binance 单场所、成本后仍可交易。
- Wei, [Liquidity and market efficiency in cryptocurrencies](https://doi.org/10.1016/j.econlet.2018.04.003)，*Economics Letters* 168：456 个 crypto 样本中，流动性越高，收益可预测性和波动越低。它支持按流动性分层而非把全部币混池；样本与当前 derivatives/TradFi 不同。
- Amihud, [Illiquidity and stock returns: cross-section and time-series effects](https://doi.org/10.1016/S1386-4181(01)00024-6)，*Journal of Financial Markets* 5(1)：用绝对收益与 dollar volume 的比例构造日频 illiquidity measure。它支持在只有基础 bar 数据时使用价格冲击代理，并说明单看 volume 不是流动性度量；股票结果不能直接移植为 crypto Alpha。
- Dhawan and Putniņš, [A New Wolf in Town? Pump-and-Dump Manipulation in Cryptocurrency Markets](https://doi.org/10.1093/rof/rfac051)，*Review of Finance* 27(3)：355 个 pump-and-dump 案例显示显著价格扭曲和财富转移。它支持对薄弱/事件驱动资产提高证据门；不允许仅凭 Meme、低量或新上市标签认定某个 Binance symbol 被操纵。
- Cong, Li, Tang and Yang, [Crypto Wash Trading](https://www.nber.org/papers/w30783)：用交易分布而非单纯报告 volume 检测交易所 wash trading。它支持“公开 24 小时量不足以证明市场质量”的限制；其跨交易所结论不能直接当作 Binance 当前单币认定。
- Ammann, Burdorf, Liebi and Stöckl, [Survivorship and Delisting Bias in Cryptocurrency Markets](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4287573)：在 2014–2021 年 3,904 个 crypto 样本中量化了幸存/下架偏差，并显示 equal-weighted 组合和部分因子关系会显著受影响。它直接支持“当前快照不得构造历史横截面”的硬门；工作论文的具体估计不直接替代本项目的点时名单验证。

## 未采用的替代

- 不引入市值聚合站来制造静态“前十/前五十主流币”名单：映射、供应量、修订和历史成分需要额外数据治理，且单一名次不能决定研究方法。
- 不使用社交媒体或新闻标签判定“操纵币”：这些数据可用于具体事件问题，但不是当前全市场基础名单的必要输入。
- 不从名称猜测所有 TradFi equity 记录究竟是股票、普通 ETF、杠杆 ETF 或 pre-market reference；官方 `exchangeInfo` 未完整表达时，保留逐研究核对要求。
