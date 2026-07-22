# 来源与适用边界

访问日均为 2026-07-21。

1. [Binance Public Data 官方仓库](https://github.com/binance/binance-public-data)：USD-M futures klines 来自 `/fapi/v1/klines`，说明 1m/15m 字段、日/月档案、相邻校验和以及历史档案可能修订。它支持公开数据身份与重取，不替研究决定策略时序或成本。
2. [Binance USDⓈ-M Funding Rate History 官方 API](https://developers.binance.com/en/docs/derivatives/usds-margined-futures/market-data/rest-api/Get-Funding-Rate-History)：提供实际 `fundingTime`、`fundingRate` 和可用时的 mark price。本研究只在持仓实际跨越事件时计入，不硬编码 8 小时间隔。
3. [Moskowitz、Ooi、Pedersen，Time Series Momentum](https://w4.stern.nyu.edu/facdir/lpederse/papers/TimeSeriesMomentum.pdf)（JFE, 2012）：为期货趋势延续提供成熟先验，同时显示主要证据来自跨资产、月级周期，不能直接支持单一 BTC 的分钟级突破。
4. [Zarattini、Pagani、Barbon，Catching Crypto Trends](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5209907)（2025）：在更广的 crypto universe 上采用多个 Donchian 周期 ensemble、波动 sizing 和费用控制。它支持检验参数稳健性和成本敏感性，也反向说明单一 BTC、单一短周期和一次激活不能移植其组合业绩。
5. Bailey 与 López de Prado，[The Deflated Sharpe Ratio](https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf)：批量试验会放大选择偏差。本问题因此保存完整 72 配置结果、限制一次固定搜索、采用顺序时间门，并在没有通过者时停止。

费用不是从公开页面假定为个人账户承诺：研究把 4 bps/边作为固定 taker 假设，并另加 2/10/15 bps 的不利执行情景。真实 VIP、BNB 折扣、撮合角色和滑点可能不同，候选若通过仍必须在当时账户与 Demo 事实中重新核对。
