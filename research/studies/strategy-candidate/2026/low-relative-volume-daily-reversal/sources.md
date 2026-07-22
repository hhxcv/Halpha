# 来源与适用性

访问日期均为 2026-07-22。

1. Bianchi, Babiak, Dickerson, [Trading volume and liquidity provision in cryptocurrency markets](https://doi.org/10.1016/j.jbankfin.2022.106547), *Journal of Banking & Finance* 142 (2022), 106547；可访问作者版本：https://eprints.lancs.ac.uk/172093/1/Babiak_Trading_Volume.pdf 。论文使用 2017-03 至 2022-03、多场所、动态最多 100 个至少有 365 日历史的加密货币对；以过去 30 日趋势构造标准化 volume shock，并报告低 volume 组的次日 reversal 更强。适用于机制、30 日窗口、次日持有和简单反转基准。未覆盖 Halpha 的固定六个 Binance perpetual、单标的时间序列阈值、实际 funding、下一开盘成交或一次性计划；论文也明确价值加权、成本后结果更弱，收益主要集中在较小、较难交易资产。
2. Bianchi, Babiak, Dickerson 作者版本附录：60 日 volume window 得到定性相近结果。仅作为事前敏感性，不用于选择主配置。
3. Binance, [USDⓈ-M Kline/Candlestick Data](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Kline-Candlestick-Data)：公共 `GET /fapi/v1/klines` 返回 open time、OHLC、volume、close time、quote volume、trade count 和 taker-buy 字段。本题固定 1d interval、UTC open time；REST snapshot 可修订，因此保存原始页 hash，而不只记录 URL。
4. Binance, [Get Funding Rate History](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Get-Funding-Rate-History)：公共 `GET /fapi/v1/fundingRate` 按 fundingTime 返回已结算 rate。用于真实结算事件；不假设始终为 8 小时，也不把当前预测 rate 当已实现现金流。
5. Binance, [binance-public-data](https://github.com/binance/binance-public-data)：说明官方公开档案、时间戳与 checksum/revision 语义。当前题使用官方 REST 原始页 snapshot 而非月 ZIP；未来重取必须比较 manifest SHA-256，不能默认为同一输入。
6. VectorBT, [Portfolio from signals](https://vectorbt.dev/api/portfolio/base/#vectorbt.portfolio.base.Portfolio.from_signals)：用于把固定 long/short entry/exit、fees 和 slippage 转为独立一次性计划的收益，不用于模拟 order book、margin 或 venue feedback。
7. Bailey and López de Prado, [The Deflated Sharpe Ratio](https://doi.org/10.3905/jpm.2014.40.5.094), *Journal of Portfolio Management* 40(5) (2014)：说明多重试验和非正态会夸大 Sharpe。本题不按最高 Sharpe选择参数，公开一个主配置、一个文献敏感性和两个简单解释；主判断使用顺序 holdout、完整配置和块 bootstrap，而不是用 DSR 挽救弱经济结果。

直接未覆盖差异：历史 top-of-book、订单冲击、真实账户费率、强平/ADL、存续期完整市场、下架对象和产品级 NautilusTrader 事件/成交语义。无可靠数据时这些保持未知。

