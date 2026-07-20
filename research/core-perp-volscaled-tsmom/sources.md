# 先行调研与候选筛选

访问日期 2026-07-20，数据下载和结果运行前记录。

- Moskowitz、Ooi、Pedersen，[Time Series Momentum](https://doi.org/10.1016/j.jfineco.2011.11.003)：传统期货 1–12 个月方向延续的成熟原始证据；不能证明单一 crypto 场所或本参数有效。
- Kim、Tse、Wald，[Time series momentum and volatility scaling](https://doi.org/10.1016/j.finmar.2016.05.003)：同行评审反证指出大量 TSMOM alpha 可能来自 volatility scaling/risk parity，而非方向预测；因此连续 0.5x 多头是必要简单基准。
- Harvey et al., [The Impact of Volatility Targeting](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3175538)：资产与组合 volatility scaling 可改善风险和尾部概率，但不消除模型/跳跃风险。
- Grobys et al., [Cryptocurrency momentum has (not) its moments](https://doi.org/10.1007/s11408-025-00474-9)：crypto momentum 会出现单币驱动的严重 crash；vol 管理改善收益但厚尾仍使传统推断不稳。这是固定低 gross、单币 cap 和 adverse 门的直接依据与反证。
- Binance USD-M [Funding History](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Get-Funding-Rate-History) 与 [Public Data](https://github.com/binance/binance-public-data)：公开实际 funding 和 checksum 日线档案。

候选池包含 BTC 单币 vol-scaled trend、BTC/ETH/BNB core 组合、更多 alt 组合。选 core 三币，因为它相对正式单 BTC 策略回答跨标的与显式风险预算的缺口，又避免多 alt 的上市/流动性/尾部维护成本。固定 180/60 日来自成熟月度趋势与约三月风险估计；120/240 只作事前稳健性，不择优。
