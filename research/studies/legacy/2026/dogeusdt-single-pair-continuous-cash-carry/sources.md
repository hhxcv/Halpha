# 先行来源与限制

访问日期 2026-07-20。沿用并再次明确本轮联网调查：

- Gornall, Rinaldi & Xiao, [Perpetual Futures and Basis Risk](https://ssrn.com/abstract=5036933)：约束资本与投机需求造成 basis 风险，不允许“无风险”表述。
- Chitra et al., [Exploring Risk and Return Profiles of Funding Rate Arbitrage on CEX and DEX](https://doi.org/10.1016/j.bcra.2025.100354)：多场所、多资产实证支持把 funding arbitrage 视为需逐资产检验的策略，而非机械保证。
- Binance [Public Data](https://github.com/binance/binance-public-data) 与 [Funding Rate History](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Get-Funding-Rate-History)：官方 checksum kline 与 settled funding 身份。

未覆盖同步成交、盘口/冲击、最小订单、mark/强平/ADL、保证金转移、场所信用、DOGE 特有事件跳跃和容量。高历史 funding 可能只补偿这些未建模风险。
