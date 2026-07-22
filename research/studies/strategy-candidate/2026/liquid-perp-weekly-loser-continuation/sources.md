# 先行调研来源与适用性

访问日期 2026-07-22。

1. Fičura, [Impact of size and volume on cryptocurrency momentum and reversal](https://wp.ffu.vse.cz/artkey/wps-202301-0003.php)，Prague University of Economics and Business Working Paper 2023。其 2017-06 至 2022-12 动态横截面显示：小/低流动币周级反转，而大/高流动币呈 1–2 周动量；1 周 high-momentum 对大/高流动币更强，并报告动量主要来自 short loser 腿。它是最直接问题来源，但不是同行评审终局，也没有回答固定六币、Binance 永续、实际 funding 和个人一次性计划。
2. Tzouvanas, Kizys & Tsend-Ayush, [Momentum trading in cryptocurrencies: Short-term returns and diversification benefits](https://doi.org/10.1016/j.econlet.2019.108728)，Economics Letters 2020。同行评审研究在 12 币日线中发现短 formation/hold 的动量较强、长期消失；样本较早且组合实现与本题不同。
3. Liu, Tsyvinski & Wu, [Common Risk Factors in Cryptocurrency](https://doi.org/10.1111/jofi.13119)，Journal of Finance 2022。原始研究支持 market/size/momentum 是 crypto 横截面重要基准，要求本题显式控制六币等权市场，而不是把做空 beta 当选币 Alpha。
4. Cakici et al., [Revisiting seasonality in cryptocurrencies](https://doi.org/10.1016/j.frl.2024.105429)，Finance Research Letters 2024。500 币大样本没有稳健收益季节性，支持不优先周末/星期规则。
5. Binance Developer Docs, [Kline/Candlestick Data](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Kline-Candlestick-Data)、[Funding Rate History](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Get-Funding-Rate-History) 与 [Mark Price Kline](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Mark-Price-Kline-Candlestick-Data)。用于公开无凭据日线、settled funding 和历史 funding 响应缺 mark 时的官方 8h mark close。
6. VectorBT, [Portfolio from orders](https://vectorbt.dev/api/portfolio/base/#vectorbt.portfolio.base.Portfolio.from_orders)。用于固定数量 short 的逐计划 fee/slippage 回报复核；不作为保证金、清算或产品执行权威。

未覆盖：历史 L1/L2、真实 spread、队列、部分成交、账户 fee tier、保证金/清算/ADL、突发下架、API 故障、税务、真实计划金额、动态市值与退市样本。固定六个当前幸存且活跃合约服务于当前可执行性，带来幸存者偏差，不能外推全市场。
