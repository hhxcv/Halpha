# 来源与适用性

访问与核对日期：2026-07-22。

1. Pyo & Jang, *Revisiting the low-volatility anomaly in cryptocurrency markets*, Finance Research Letters 97 (2026), 109851, <https://doi.org/10.1016/j.frl.2026.109851>。
   - 采用：432 个 Binance 现货、2018-01 至 2025-11；低波 quintile 相对高波 quintile 的收益为正，2–3 月形成和 1 月持有最强；Fama–MacBeth 波动率价格为负。
   - 未覆盖：高波 SHORT 腿单独是否绝对盈利、USD-M funding、当前幸存 25 目标、0.25x one-shot 和零售执行。
2. Kaya & Mostowfi, *Low-volatility strategies for highly liquid cryptocurrencies*, Finance Research Letters 46 (2022), 102422, <https://doi.org/10.1016/j.frl.2021.102422>；开放全文 <https://digitalcollection.zhaw.ch/server/api/core/bitstreams/5c4ee9d5-59bd-44fc-9934-d7a996d0ed96/content>。
   - 采用：高流动币、集中低波组合、现实费用和较长形成期；支持把流动性和成本列为必要边界。
   - 未覆盖：论文 long-only 与止损不能推出高波空腿；不移植其优化止损。
3. Burggraf & Rudolf, *Cryptocurrencies and the low volatility anomaly*, Finance Research Letters 38 (2021), 101683, <https://doi.org/10.1016/j.frl.2020.101683>。
   - 强反证：2013–2019 没有低波异常且高波收益更高；若关系依赖较新时期，必须顺序分年验证。
4. Binance, *Public Data*, <https://github.com/binance/binance-public-data>；USD-M public monthly archive <https://data.binance.vision/?prefix=data/futures/um/monthly/>。
   - 采用：公开 1d Kline、settled funding、mark 与 checksum；无凭据和账户。
5. VectorBT `Portfolio.from_orders`, <https://vectorbt.dev/api/portfolio/base/>。
   - 采用：SHORT 开/平、fee/slippage 的框架复算并与独立线性公式核对；不代表真实 borrow、margin、liquidation 或 NautilusTrader 事件。

项目内发现证据：`../perp-low-volatility-monthly-one-shot-long/` 的预注册 HIGHVOL90-LONG 对照在 2022–2023 base/stress 日期均值为 -0.6173%/-0.8318%，16 个目标、45 笔。该时期已经暴露，只能提出本题，不能计入任何 Q8 gate。
