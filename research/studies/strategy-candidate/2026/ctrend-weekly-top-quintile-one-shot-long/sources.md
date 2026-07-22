# 先行调研与来源

检索和核对时间：`2026-07-22`。优先原始论文、正式出版页、官方附录、官方场所与框架文档；二手页面未用于固定模型。

## 主假设与精确方法

1. Fieberg, Liedtke, Poddig, Walker, Zaremba, *A Trend Factor for the Cross-Section of Cryptocurrency Returns*, Journal of Financial and Quantitative Analysis, DOI `10.1017/S0022109024000747`。正式 PDF：<https://www.cambridge.org/core/services/aop-cambridge-core/content/view/4C1509ACBA33D5DCAF0AC24379148178/S0022109024000747a.pdf/div-class-title-a-trend-factor-for-the-cross-section-of-cryptocurrency-returns-div.pdf>
   - 数据：CoinMarketCap 日线 OHLC、volume、market cap，3,000 多币，2015-04 至 2022-05。
   - 方法：28 个技术指标先做横截面秩；52 周滚动的单变量 Fama–MacBeth 预测；`l1_ratio=0.5` elastic net 以 corrected AIC 选择正贡献预测，再等权组合。
   - 报告：value-weighted long-short 约 3.87%/周；最大/最流动子集中仍显著；顶部 long leg 在 top-100 中约 3.78%/周；30/40 bp 及更高成本后仍正，最长四周持有仍显著。
   - 适用性：为基础 OHLCV、多信号聚合、流动对象和周频提供强先验。
   - 未覆盖：Halpha 是单目标永续 one-shot、实际 funding、当前幸存名单和成交额代理权重；原结果不能直接移植。

2. 同文官方 Online Appendix：<https://static.cambridge.org/content/id/urn%3Acambridge.org%3Aid%3Aarticle%3AS0022109024000747/resource/name/S0022109024000747sup001.pdf>
   - 给出 RSI、stochastic RSI/K/D、CCI、7 个价格 SMA、MACD、7 个 volume SMA、volume MACD、Chaikin、4 个 Bollinger 指标的精确定义。
   - 披露 27,648 个研究设计组合与变量选择频率。这个宽搜索空间是重要反证：Halpha 不搜索主配置，只保留少量不可选择稳健性。

3. SSRN 早期版本与版本身份：<https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4601972>，2023-11-09 发布、2023-11-30 修订。用于确认论文假设在本题 2023 全年结果被查看前已经公开；正式出版版拥有更高权威。

## 反证与方向筛选

4. Eichel & Aharon, *Revisiting seasonality in cryptocurrencies*, Finance Research Letters 64 (2024), DOI `10.1016/j.frl.2024.105429`：<https://www.sciencedirect.com/science/article/pii/S1544612324004598>
   - 约 500 币上没有稳健收益季节性；早期 BTC Monday 效应 2015 后不持续。用于淘汰简单日历策略。

5. Garfinkel, Hsiao, Hu, *Disagreement and returns: The case of cryptocurrencies*, Financial Management (2025), DOI `10.1111/fima.12491`：<https://doi.org/10.1111/fima.12491>
   - Binance 2018–2021；异常 turnover 在不可做空币中预测更低次日收益，但 margin/可做空激活后关系为零。用于否定把该机制直接转成永续 SHORT。

6. Chen et al., *Can salience theory explain investor behaviour?*, International Review of Financial Analysis 84 (2022), DOI `10.1016/j.irfa.2022.102419`：<https://www.sciencedirect.com/science/article/pii/S1057521922003696>
   - salience 效应局限于 micro-cap，并受套利限制调节；不适合当前流动、低维护风险对象。

7. Kiefer & Nowotny, *Reversal in Cryptocurrency Returns*, SSRN `6703498` (2026)：<https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6703498>
   - 8–10 周反转集中于中盘高波对象；70 币 long-short，后扩展至更宽集合。低换手但风险对象、组合语义和验证周期与当前单腿 one-shot 不如 CTREND 匹配，暂缓。

## 官方数据与研究框架

8. Binance USD-M Futures Kline 官方 API：<https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Kline-Candlestick-Data>
   - 公共、无需凭据；日线 OHLCV、quote volume、成交笔数与 taker-buy volume。Halpha 只使用 OHLCV/quote volume。

9. Binance 官方公共历史数据与校验：<https://github.com/binance/binance-public-data/>，归档入口 <https://data.binance.vision/?prefix=data/futures/um/monthly/>
   - fundingRate 和 markPriceKlines 月归档及 `.CHECKSUM`；不调用交易或变更端点。

10. scikit-learn `ElasticNet` 官方文档：<https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.ElasticNet.html>
    - 固定 `scikit-learn 1.9.0`、`l1_ratio=0.5`、显式 alpha 网格、sample weights 与确定性迭代限制。库只承担优化器，不决定经济问题或门槛。

11. VectorBT `Portfolio.from_orders` 官方文档：<https://vectorbt.dev/api/portfolio/base/#vectorbt.portfolio.base.Portfolio.from_orders>
    - 用于独立重演固定两单的价格与费用现金流；funding 显式补充。VectorBT 不代表真实盘口、保证金、Nautilus 或交易核心语义。

## 固定假设与未知

- Binance quote volume 是可执行活动代理，不是历史 market cap；这是与论文最重要的数据差异。
- 当前 25 币是 2026 幸存且当前流动的名单，不是历史 point-in-time universe。
- 论文的强收益经历大量研究设计检验；即使正式发表，也必须以 Halpha 冻结转换、现实成本和论文后时段独立否证。
- 无可靠证据时不猜测为何某个指标被 elastic net 选择；只报告频率、稳定性和结果集中度。
