# 来源与适用边界

访问日均为 2026-07-22。

1. [Binance USDⓈ-M Funding Rate History 官方 API](https://developers.binance.com/en/docs/derivatives/usds-margined-futures/market-data/rest-api/Get-Funding-Rate-History)：公开返回实际 `fundingTime`、`fundingRate` 和可用时的 `markPrice`。本研究只用已结算事件，并复用已有 snapshot 身份；不把未来 premium index 或预测 funding 当作可知事实。
2. [Binance Public Data 官方仓库](https://github.com/binance/binance-public-data)：提供 USD-M 1m kline 档案、字段、校验和与修订边界，支持已有输入重取和完整性核对。
3. He、Manela、Ross、von Wachter，[Fundamentals of Perpetual Futures](https://arxiv.org/abs/2212.06888)（2022）：说明 funding 是期货—现货锚定和拥挤成本机制，并在高频事件研究中观察到正 funding 附近的价格调整会侵蚀 carry。它支持把 funding 当作状态输入，也提示价格反应是最强反解释；不直接支持单腿 Donchian 过滤后的盈利。
4. Inan，[Predictability of Funding Rates](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5576424)（2025）：报告 Bitcoin 下一期 funding 水平和方向具有样本外可预测性，但局部稳定性时变。它与 Halpha 既有研究的符号持续结果一致；本研究仍只用最新已结算值，不训练预测模型。
5. Zhang，[Funding Rate Mechanism in Perpetual Futures](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6185958)（2026）：把 funding 描述为受限套利者与动量投机者之间的反馈规则，并讨论均值回复 basis、更新间隔和尾部。它支持“funding 同时含拥挤与锚定反馈”的解释，但不能给出 Halpha 的方向门槛或收益结论。
6. 仓库既有 `btcusdt-next-funding-carry`：当前与下一 funding 同号率很高，但单腿追逐下一结算在 development/evaluation base 均值为负；说明符号持续不等于方向盈利。本题只检验它能否作为已有突破的过滤器。
7. 仓库既有 `multi-asset-funding-sign-hysteresis-carry`：两腿累计收益被少数早期 episode 主导，典型 episode 和回撤门失败；本题不重做 cash-and-carry 或符号持续阈值。

费用固定为父研究的 4 bps/边 taker 假设，并另加 2/10/15 bps 不利成交。真实账户费率、撮合角色与滑点未知，任何通过结果仍需项目所有者选择和产品侧重新核对。
