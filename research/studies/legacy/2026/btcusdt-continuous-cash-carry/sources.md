# 先行调研与候选筛选

访问日期 2026-07-20，且在运行连续持有结果前记录。

- He、Manela、Ross、von Wachter，[Fundamentals of Perpetual Futures](https://arxiv.org/abs/2212.06888)：原始论文推导无摩擦价格与含交易成本的无套利边界，并实证 implied arbitrage；支持检验 spot/perp 对冲，也明确费用决定可实现性。
- Ackerer、Hugonnier、Jermann，[Perpetual Futures Pricing](https://www.nber.org/papers/w32936)：原始定价论文说明 periodic funding 锚定和复制条件；不替代实际 basis、保证金与结算验证。
- Gornall、Rinaldi、Xiao，[Perpetual Futures and Basis Risk](https://ssrn.com/abstract=5036933)：受限套利资本和投机需求会造成 basis 风险；因此本题用两份 fully-funded capital、保留 basis 分解和回撤，而不称无风险套利。
- Dai、Li、Yang，[Arbitrage in Perpetual Contracts](https://ssrn.com/abstract=5262988)：原始研究指出 clamp 与持续价差不能只用手续费解释；构成“funding 收入不一定覆盖 basis”的反证。
- Binance [公开数据](https://data.binance.vision/)与 [Funding Rate History](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Get-Funding-Rate-History)：锁定 8h spot/perp OHLC 与实际 settled funding；原始时间戳仅在 1 秒内规范到最近 8h 边界。

候选为连续 BTC carry、跨场所 funding spread、动态 basis 阈值三项。连续同场所、无参数、每阶段只进出一次，最适合个人小资金快速证伪，并直接回答此前 3bp 事件策略“收益稀疏、频繁 episode 成本”的缺口；跨场所增加库存/转账/双故障，动态阈值增加搜索自由度，均淘汰。

本题不计产品策略变更，也不证明 Alpha。未覆盖腿间延迟、盘口、部分成交、mark price、保证金/清算/ADL、交易所信用、USDT 借贷收益和税务。
