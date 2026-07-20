# 先行调研、来源与适用性

访问日期 2026-07-20；先于新数据获取。

- Gornall, Rinaldi & Xiao, [Perpetual Futures and Basis Risk: Evidence from Cryptocurrency](https://ssrn.com/abstract=5036933) (2025)：约束套利资本与波动投机需求会造成 basis 偏离，直接反对“无风险套利”表述。
- Chitra et al., [Exploring Risk and Return Profiles of Funding Rate Arbitrage on CEX and DEX](https://doi.org/10.1016/j.bcra.2025.100354) (2025)：含 Binance、XRP 等资产的 60 个 funding arbitrage 场景，支持独立检验 XRP，但论文场景、杠杆、成本与本题不完全相同。
- Ackerer et al., [Perpetual Futures Pricing](https://doi.org/10.1111/mafi.70018), *Mathematical Finance* (2026)：永续没有到期收敛约束，价格锚定依赖 funding 设计；不能把 futures/spot basis 当作到期必然收敛。
- Binance [Public Data](https://github.com/binance/binance-public-data) 与 [Funding Rate History](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Get-Funding-Rate-History)：官方 checksum 8h spot/USDM kline 和已结算 funding；REST 均为公开 market-data，不需凭据。

本题仍未覆盖：两腿同步/部分成交、真实 bid-ask 与冲击、最小订单、保证金计价和维持率、mark price、强平/ADL、资金跨钱包、账户级容量、场所信用和冻结、税务。40bp stress round trip 只是成本代理；全额 spot 加等额 futures 保证金和 4% 年化全资本门槛是保守模型，不是场所保证。
