# 来源与适用性

访问日均为 2026-07-22。

1. Pengfei Luo, *Three Essays on Futures Expected Returns: From Dated Futures to Perpetual Futures*, University of Edinburgh PhD thesis, 2025 repository record / 2024 thesis text: <https://era.ed.ac.uk/items/ed3909ca-1fc6-4e44-9c49-89c9ed77f5b9/full>；PDF：<https://era.ed.ac.uk/bitstreams/1da6437c-a50f-4d48-add9-fdf5158c1e8b/download>。
   - 采用：Chapter 4 把类别动量与个币动量分离；数据为 CoinMarketCap 类别/市值与 Binance 永续价格，样本约 2019-10 至 2024-07；主要结果使用 30 个较分散类别，典型 `L=7d`，并检查多形成/持有期、交易摩擦、lead-lag、市场/size/个币 momentum/basis/price-volume 因子。
   - 对本题的影响：固定 7 日主窗口、显式比较自身动量、优先 LONG 和较大额成交对象，并把 2025 以后作为论文外时间确认。
   - 未覆盖：论文的类别来源、point-in-time 市值、30 类、top/bottom 多腿、每日重平衡与低机构成本都不等于 Halpha 的七类当前快照、固定单币、one-shot、0.5x 和零售成本。论文不是本题盈利证据。

2. Tobias J. Moskowitz and Mark Grinblatt, “Do Industries Explain Momentum?”, *Journal of Finance* 54(4), 1999, DOI <https://doi.org/10.1111/0022-1082.00146>。
   - 采用：行业共同成分需要和个体 momentum 分开，并检验更简单解释。
   - 未覆盖：股票行业定义、月度频率、样本与交易制度不能移植到 crypto 永续。

3. Yukun Liu, Aleh Tsyvinski and Xi Wu, “Common Risk Factors in Cryptocurrency”, NBER WP 25882 / *Journal of Finance* 77(2), <https://www.nber.org/papers/w25882>。
   - 采用：crypto market、size、momentum 是共同解释；本题不能把 market beta、成交额或自身 momentum 当成类别增量。
   - 未覆盖：原研究主要是广泛 crypto 横截面和因子组合，不是 Binance USD-M 固定单腿 one-shot。

4. Binance USDⓈ-M Kline/Candlestick Data：<https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Kline-Candlestick-Data>。
   - 采用：`/fapi/v1/klines` 的 UTC open time、OHLC、quote asset volume 和公开分页；日线只在 close 后可用，入场显式移动到下一日 open。
   - 未覆盖：历史盘口、spread、深度、部分成交和 bar 内路径。

5. Binance USDⓈ-M Funding Rate History：<https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Get-Funding-Rate-History>。
   - 采用：settled funding 字段语义；不硬编码固定 8 小时间隔。
   - 未覆盖：未来 funding、账户级结算差异、保证金或强平。

6. Binance Public Data 官方仓库与归档：<https://github.com/binance/binance-public-data>、`https://data.binance.vision/data/futures/um/monthly/fundingRate/`、`https://data.binance.vision/data/futures/um/monthly/markPriceKlines/`。
   - 采用：monthly fundingRate、8h markPriceKlines、缺口月份的 1m markPriceKlines、归档 SHA-256 `.CHECKSUM` 和可重取身份。REST 在本次批量请求中被 WAF 403 阻断后，官方归档成为同场所 settled rate 的稳定取得通道。Binance 官方仓库说明公开市场数据可按月取得、Kline 支持 1m/8h 等间隔且相邻 checksum 用于完整性校验。
   - 未覆盖：fundingRate 归档没有逐事件 `markPrice`；本题先以 funding 时点最近 1 分钟内的官方 8h mark open 作为名义代理，仅在 8h 缺整日或 funding 间隔缩短时使用同源 1m open 补足，并保留与真实结算名义的差异。2022-10-02 与 2023-02-24 的 1m mark 也缺整日，Funding Rate REST 对相应事件返回空 `markPrice`，因此跨缺失事件的交易只能整笔排除。归档可能修订，未来重取必须按已存 checksum 判断输入是否变化。

7. Binance USDⓈ-M Exchange Information：<https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Exchange-Information>；本地冻结快照为 `research/market-universe/universe.csv`。
   - 采用：当前合约身份、onboard time 和官方 `underlyingSubType` 派生分类。
   - 未覆盖：接口返回当前状态，不是历史 point-in-time 分类或退市全量档案。不得把当前标签倒写成历史事实。

8. VectorBT `1.1.0` Portfolio 文档：<https://vectorbt.dev/api/portfolio/base/>；版本来源：<https://github.com/polakowo/vectorbt/releases/tag/v1.1.0>。
   - 采用：固定两笔订单的方向、手续费和滑点重演，并与独立手工公式逐笔核对。
   - 未覆盖：settled funding、真实订单簿、保证金、NautilusTrader 事件顺序和产品在线行为；这些明确作为补充或后续资格验证。

外部论文均只决定候选与方法，不直接移植收益、显著性或策略资格。当前分类的历史修订、退市对象和 CoinMarketCap point-in-time 类别因不使用第三方凭据/付费数据而保持未覆盖；若它们足以改变判断，结论降级，不猜测跨过。
