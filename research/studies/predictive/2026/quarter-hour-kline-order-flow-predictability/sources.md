# 来源与适用性

核查日期均为 2026-07-22（Asia/Shanghai）。二手页面只用于候选发现；本题设计以原始论文和 Binance 官方资料为主。

## 主要假设来源

1. Chan Kim, Peter Reinhard Hansen, *The Quarter-Hour Effect: Periodic Algorithmic Trading and Return Predictability in Cryptocurrency Futures*, arXiv:2607.09426v2, 2026-07-16，<https://arxiv.org/html/2607.09426v2>。
   - 原研究使用 Binance BTC、ETH、XRP、SOL、DOGE、ADA USDT 永续的 aggregate trades，2021-01-01 至 2024-10-31。
   - 订单方向来自 `isBuyerMaker`，核心窗口是每个 15 分钟边界后的前 10 秒。论文把订单失衡与未来 4/8/12 小时累计收益联系起来，明确解释为预测关联而非结构冲击或因果。
   - 论文的联合 4 日 moving-block bootstrap、真边界对伪相位、排除 funding 开口、排除 top-of-hour、符号失衡等检验直接影响本题的反证设计。
   - 论文公开状态成分的 IQR effect 在 8/12 小时约 9.8/16.9 bp；短时开盘预测的可预测毛幅度小于标准交易成本，作者未给出净成本独立策略。因此它只是问题来源，不是 Alpha 或盈利证明。
   - 未覆盖差异：1m Kline taker-buy 代理、下一分钟动作、BNB/LINK/UNI/FIL 跨资产泛化、完整成本后持仓策略。

2. Peter Reinhard Hansen, Chan Kim, Wade Kimbrough, *Periodicity in Cryptocurrency Volatility and Liquidity*, arXiv:2109.12142 / Journal of Financial Econometrics, <https://arxiv.org/abs/2109.12142>。
   - 提供加密市场分钟、五分钟、15 分钟与小时边界周期性的先行证据。
   - 适用性：支持把时钟相位当作真实研究对象；不支持可交易性、方向预测或本题的 1m 代理。

## 官方数据与字段

3. Binance, `binance-public-data`, <https://github.com/binance/binance-public-data>。
   - 官方说明 USD-M Kline 文件来自 `/fapi/v1/klines`，字段含 open time、OHLC、base/quote volume、trade count、taker-buy base/quote volume；aggregate trades 字段含时间、价格、数量与 buyer-maker 标识。
   - 本题只下载公开 Kline ZIP 与 `.CHECKSUM`，不需要 API key，不调用账户或变更端点。月文件存在已记录的完整日缺口时，只允许用同一官方归档中的日文件及 checksum 补齐，且保留双重来源身份。
   - 官方历史根：<https://data.binance.vision/?prefix=data/futures/um/monthly/klines/>。

4. Binance USD-M Futures Kline/Candlestick Data 官方文档，<https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/market-data/rest-api/Kline-Candlestick-Data>。
   - 用于核对 Kline 是按开盘时间唯一标识的时间区间及返回字段语义。
   - 本题不调用实时接口；历史 ZIP 是明确允许的公开数据来源。

## 候选筛选所用外部工作

5. *Trading volume and liquidity provision in cryptocurrency markets*, Journal of Banking & Finance 2022, <https://doi.org/10.1016/j.jbankfin.2022.106547>。低去趋势成交量状态下的短期反转更多集中于小、不活跃、高波动资产；它削弱该方向对个人稳健执行的优先级。
6. *Cryptocurrency seesaw momentum*, Journal of Empirical Finance 2023, <https://doi.org/10.1016/j.jempfin.2023.101449>。跨币负向 lead-lag 的成本后幅度很薄且依赖自动化速度，故淘汰。
7. *Cross-cryptocurrency return predictability*, Journal of Economic Dynamics and Control 2024, <https://doi.org/10.1016/j.jedc.2024.104864>。支持跨币慢速信息扩散可能存在，但方法与执行复杂度高于本轮单腿问题。
8. *Pairs trading in cryptocurrency markets: a comparative study of statistical methods*, Investment Analysts Journal 2024, <https://doi.org/10.1080/10293523.2024.2374543>。提示 60 分钟距离法可能有价值，但双腿、funding 与短样本使其暂缓。
9. *Revisiting seasonality in cryptocurrencies*, Finance Research Letters 2024, <https://doi.org/10.1016/j.frl.2024.105778>。约 500 币的大样本未支持稳健收益季节性，反对把普通日历规则列为首选。

## 未覆盖与未知

- 1m Kline 不能区分首 10 秒与后 50 秒，不能恢复逐笔订单尺寸、buyer-maker 序列、bid/ask、队列或市场冲击。
- Binance 历史文件可能有极少缺口或后来修订；本题以下载时官方 checksum 和实际 hash 固定身份。
- 实际完整性检查确认 `FILUSDT` 2022-02 官方月文件缺少最后三天、2022-04 缺少最前两天；2026-07-22 在未计算任何方向/收益前，登记对应五份官方日文件为唯一修复来源。其余 94 个月文件的时间戳网格完整。
- Kline 的 taker-buy base volume 是按成交聚合的代理；它能支持方向性成交量失衡，但不能识别交易者身份、机构策略或因果机制。
- 预测研究不纳入手续费、spread/slippage、funding、mark price、保证金和清算；只有通过后另开的策略候选题才允许评价成本后权益。
