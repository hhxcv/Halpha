# 先行调研来源与适用性

访问日期 2026-07-22。

1. Kim & Hansen, [The Quarter-Hour Effect: Periodic Algorithmic Trading and Return Predictability in Cryptocurrency Futures](https://arxiv.org/abs/2607.09426v2)，arXiv v2，2026-07-16，CC BY 4.0。原始研究使用 Binance 六个 USDT 永续 2021-01 至 2024-10 的逐笔成交，发现边界前 10 秒主动买卖失衡与未来 4–12h 收益相关，8–12h 更强；同时明确 aggregate trades 不能直接识别机构、算法或因果，论文没有给出完整净成本策略验证。它是本题的直接问题来源，不是 Alpha 证明。
2. 同一论文的数据与稳健性：六币为 BTC/ETH/XRP/SOL/DOGE/ADA；`isBuyerMaker` 用于识别主动方向；结果排除 funding 结算边界、改用失衡 sign、控制短期 bid-ask reversal 后仍保留。论文主要关系是重叠 forward-return 回归，且 12h 的 public-signal 分量经济量级约 16.9 bp；这与个人 taker round-trip 成本同量级，所以本题必须建立唯一可行仓位时间轴并检验成本，而不能把回归系数当收益。
3. Binance, [Public Data repository](https://github.com/binance/binance-public-data)。官方说明 USD-M 1m Kline 文件来自 `/fapi/v1/klines`，包含 OHLC、quote volume、trade count、taker-buy base/quote volume；每个 archive 提供 `.CHECKSUM`，历史文件可能因数据问题更新。本题保存压缩文件、官方 checksum、访问时间和本地 SHA-256。
4. Binance Developer Docs, [Kline/Candlestick Data](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Kline-Candlestick-Data)、[Funding Rate History](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Get-Funding-Rate-History) 与 [Mark Price Kline](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Mark-Price-Kline-Candlestick-Data)。用于字段语义、settled funding 与结算 mark；无凭据公共读取。
5. VectorBT, [Portfolio from orders](https://vectorbt.dev/api/portfolio/base/#vectorbt.portfolio.base.Portfolio.from_orders)。用于每个 LONG/SHORT 一次性计划的固定数量、双边 fee 与 slippage 复核；funding 独立合并。VectorBT 不是保证金、清算或真实成交权威。

未覆盖：精确 10 秒逐笔信号、历史 bid/ask、L1/L2、队列、部分成交、账户 fee tier、保证金/清算/ADL、真实人工激活延迟、税务、下架和跨场所验证。1m proxy 减少数据与运行复杂度，也可能把只存在于前 10 秒的效应平均掉；这是本题最重要的适用性边界。
