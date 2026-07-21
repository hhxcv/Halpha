# 先行来源、假设与差异

访问日期 2026-07-20，运行 SOL 数据前。

- Chitra et al., [Exploring Risk and Return Profiles of Funding Rate Arbitrage on CEX and DEX](https://doi.org/10.1016/j.bcra.2025.100354)：研究明确包含 BTC、ETH、XRP、BNB、SOL 和 Binance 场景，发现 funding arbitrage 风险收益取决于资产、场所与杠杆。支持单独检验 SOL，不保证本题结果。
- Gornall, Rinaldi & Xiao, [Perpetual Futures and Basis Risk](https://ssrn.com/abstract=5036933)：约束套利资本和投机需求可造成 basis 风险，要求全额资本、路径回撤和 basis 贡献门。
- Ackerer et al., [Perpetual Futures Pricing](https://doi.org/10.1111/mafi.70018)：永续无到期收敛，funding 设计是锚定关键；连续 carry 不能宣称锁定到期价差。
- Binance [Public Data](https://github.com/binance/binance-public-data) 与 [Funding History](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Get-Funding-Rate-History)：官方 checksum spot/USDM 8h kline 与 settled funding。

固定全额 spot 加等额 futures 保证金；16/24/40bp round trip；4% 年化全资本门。未覆盖同步/部分成交、mark price、维持保证金/强平/ADL、实时价差、冲击、最小订单、跨钱包和场所信用。
