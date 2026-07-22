# 先行来源

访问日期 2026-07-21。

1. Gatev, Goetzmann & Rouwenhorst, [Pairs Trading: Performance of a Relative-Value Arbitrage Rule](https://www.nber.org/papers/w7032)（NBER 1999；RFS 2006）：用标准化价格距离形成 pairs，并用随机 pairs bootstrap 区分一般均值回复；作者同时提示部分收益可能来自 microstructure。本题借鉴“相对而非绝对价格”和明确替代解释，不移植股票日频收益。
2. Avellaneda & Lee, [Statistical Arbitrage in the U.S. Equities Market](https://math.nyu.edu/~avellane/AvellanedaLeeStatArb071108.pdf)（2008/2009）：用 PCA 或 sector ETF 剥离共同因子，把 residual 建模为 mean reverting；绩效在后期下降且与市场周期相关。本题采用最简单的单 BTC factor，不做 PCA/OU 选择。
3. Fil & Kristoufek, [Pairs Trading in Cryptocurrency Markets](https://doi.org/10.1109/ACCESS.2020.3024619)（IEEE Access, 2020）：26 个 Binance 流动币、5m/1h/日频；策略总体不优于经典基准，结果高度依赖参数、费用与执行窗口，高频相对更好。它既提供 crypto 先验，也要求本题固定完整搜索和 next-open/cost 门。
4. Pindza & Mba, [Adaptive copula-based pairs trading with market overlay](https://doi.org/10.3934/QFE.2026016)（2026）：10 个 Binance USDT 永续、2021–2023 小时数据；市场中性 copula 规则在 0.08% round-trip 后净收益为负。它是对“更复杂一定更好”的直接反证。
5. [ArbitrageLab PCA approach 官方源码/文档](https://github.com/hudson-and-thames/arbitragelab/blob/master/docs/source/other_approaches/pca_approach.rst)：公开实现说明 factor decomposition、residual 与 beta-neutral 组合的关系。只作为公式核对；本题不引入该额外依赖或通用优化框架。
6. [Binance Public Data](https://github.com/binance/binance-public-data)：官方 5m Kline 字段与 checksum。开发期直接复用父问题已校验的 240 个官方文件；数据不含订单簿、真实对冲成交、funding 与参与者身份。

这些来源说明 residual mean reversion 是成熟研究方向，但没有证明当前 Binance 永续、当前成本或个人执行仍有 Alpha。尤其不能从历史相关性推导长期稳定的经济关系或 cointegration。

