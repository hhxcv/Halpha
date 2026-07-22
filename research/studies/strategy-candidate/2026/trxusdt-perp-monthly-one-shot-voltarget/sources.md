# 先行调研、来源与适用性

访问日期均为 2026-07-22。

1. Moreira & Muir, [Volatility-Managed Portfolios](https://doi.org/10.1111/jofi.12513)，Journal of Finance 2017。原始同行评审研究说明在预期收益没有随波动同比例上升时，逆波动缩放可能改善风险调整结果。它覆盖传统因子而非 TRX 或永续，不证明本候选。
2. Cederburg et al., [On the performance of volatility-managed portfolios](https://doi.org/10.1016/j.jfineco.2020.04.015)，Journal of Financial Economics 2020。对 103 个股票策略的实时样本外反证表明，波动管理并不系统性优于未管理策略，结构不稳定会使可实施样本外版本更差。本题因此保留顺序门、简单 0.5 倍基准和邻近参数，不以原论文作为盈利证明。
3. He, Manela, Ross & von Wachter, [Fundamentals of Perpetual Futures](https://arxiv.org/abs/2212.06888)。原始理论和实证研究说明永续没有到期强制收敛，funding 是多空之间的周期现金流，合约—现货偏离、交易成本、保证金和随机退出风险均不可忽略。本题据此不把现货结果直接映射为永续收益。
4. Binance Developer Docs, [Get Funding Rate History](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Get-Funding-Rate-History)。官方端点 `/fapi/v1/fundingRate` 返回 `fundingRate`、`fundingTime` 与相关 `markPrice`，按时间升序分页；本题保存每个原始响应的 URL、字节数和 SHA-256。
5. Binance Developer Docs, [Mark Price Kline/Candlestick Data](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Mark-Price-Kline-Candlestick-Data)。历史 funding 响应未全量携带 `markPrice` 时，使用同一官方来源的 8h mark close，并以一分钟内最近结算边界匹配；不以成交价或日收盘猜填。
6. Binance Developer Docs, [Exchange Information](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Exchange-Information)。官方元数据提供合约状态、onboard date、数量/价格过滤器与最小名义等当次事实；它只支持当前最小可实施性检查，不回填历史规则。
7. VectorBT, [Portfolio from orders](https://vectorbt.dev/api/portfolio/base/#vectorbt.portfolio.base.Portfolio.from_orders)。用于逐个一次性计划以固定数量、双边 fee 和 slippage 复核价格/成本回报；funding 作为官方 settled 现金流独立合并。VectorBT 不是成交、保证金或产品运行时权威。
8. 本地父研究 `research/studies/legacy/2026/trxusdt-voltarget-8pct-long/`。其固定规则为 TRXUSDT spot、60 日 realized volatility、8% 年化目标、月度、最大 0.5 倍，只有 2025–2026-06 是全新确认。本题明确记录该依赖和已经暴露的价格证据，不声称独立复现。

未覆盖差异：历史 order book、真实 bid/ask、队列、部分成交、账户 fee tier、保证金模式、清算/ADL、API 故障、历史过滤器变更、税务、USDT 信用与真实个人计划金额。1d open 加压力 slippage 仍只是成交代理。
