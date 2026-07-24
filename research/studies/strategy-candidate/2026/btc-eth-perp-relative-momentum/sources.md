# 外部证据与反证

- Liu 与 Tsyvinski, *Risks and Returns of Cryptocurrency*：BTC、ETH 等 crypto 存在强 time-series momentum，为相对比率延续提供方向性先验。<https://www.nber.org/papers/w24877>
- Moskowitz, Ooi, Pedersen, *Time Series Momentum*：1–12 月方向延续和预先固定的时间序列动量框架。<https://doi.org/10.1016/j.jfineco.2011.11.003>
- Tadi 与 Kortchmeski, *Evaluation of Dynamic Cointegration-Based Pairs Trading Strategy in the Cryptocurrency Market*：crypto 配对均值回归的支持依赖动态协整、OU half-life、分钟盘口与更大币池，说明静态 BTC/ETH z-score 不足以作为本项目的简单替代。<https://arxiv.org/abs/2109.10662>
- Stoikov et al., *Pairs Trading in Crypto*：近期配对研究同样先做 500+ 币稳定关系选择，再微调执行；其结果不能外推到固定 BTC/ETH。<https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6188418>
- Binance 官方公共数据与 funding history：两标的日线、mark-price Kline、逐文件 CHECKSUM 与实际 funding。<https://data.binance.vision/> <https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Get-Funding-Rate-History>
- Bailey 与 López de Prado, *The Deflated Sharpe Ratio*：多重尝试校正。<https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551>

本研究选择相对动量而非均值回归，且不同时运行两者后选择赢家。
