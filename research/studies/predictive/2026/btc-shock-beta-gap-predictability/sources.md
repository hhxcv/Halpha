# 先行调研与来源

访问日期均为 2026-07-21。优先记录原始论文、同行评审论文、交易场所官方资料和官方源码；来源只建立研究先验，不替代本题独立数据结果。

| 来源 | 证据与采用方式 | 适用性 | 未覆盖差异/限制 |
|---|---|---|---|
| Kurihara & Matsumoto (2026), [Price Transmission from Bitcoin to Altcoins](https://link.springer.com/article/10.1007/s10690-026-09589-z) | Binance 1m 数据；报告大/中币近同步、小币与低 trade-count 币存在数分钟 BTC→ALT 延迟，并用 cross-correlation、Granger/VAR 和交易规则验证 | 直接支持“先测冲击后的延迟传导”与按活动度反证 | 选定 2024–2025 市况与小币，只有很短 OOS；费用假设、spread/slippage/depth 和个人延迟不完整，不能移植收益 |
| Guo, Sang, Tu & Wang (2024), [Cross-cryptocurrency return predictability](https://doi.org/10.1016/j.jedc.2024.104863) | 2019–2021 Binance 分钟数据、top 30；adaptive LASSO/PCA 均发现跨币预测，解释为共同冲击加有限注意下的信息慢扩散 | 说明 BTC/其他币 lagged return 是成熟可检验问题，并要求简单基准与 OOS | 样本较旧、模型和 long-short 组合更复杂；论文 after-cost 结果不能替代当前永续、下一 open 与个人成本 |
| Makarov & Schoar (2020), [Trading and Arbitrage in Cryptocurrency Markets](https://doi.org/10.1016/j.jfineco.2019.07.001)；[MIT 开放稿](https://dspace.mit.edu/server/api/core/bitstreams/a3b4b145-a125-4d4d-add5-8bd452d2869d/content) | 共同 signed order flow 可解释大部分 BTC 价格变化；交易所特有买压与相对价差相关，强调资本与摩擦 | 支持“共同流量/套保/套利者”比“机构固定比例买入”更可靠的机制先验 | 研究核心是 BTC 跨交易所且样本较早，不识别本题 15 个山寨币的实际买方，也不能由 Kline 推断因果 |
| Kogan, Makarov, Niessner & Schoar (2023/2026), [Are Cryptos Different? Evidence from Retail Trading](https://www.nber.org/papers/w31317) | eToro 个体数据发现同一批散户在 crypto 更像追涨，在股票/黄金更逆向 | 为共同注意、采用叙事和动量型需求提供替代机制 | 不是 Binance 订单身份数据，也不能确定冲击后是谁买每个币 |
| Pindza & Mba (2026), [Adaptive copula-based pairs trading with market overlay](https://doi.org/10.3934/QFE.2026016) | 10 个 Binance USDT 永续、2021–2023 小时数据；cointegration/copula 市场中性策略在 0.08% round-trip 后为负 | 作为较慢残差/配对候选的现实反证，避免直接上复杂模型 | 标的、频率、成本与规则不同；不能否定所有 beta-residual 预测 |
| Schmitz & Hoffmann (2025), [Wish or reality? On the exploitability of triangular arbitrage](https://doi.org/10.1016/j.frl.2024.106508) | Binance 高频研究找到 4,879 个表面机会，但费用、滑点与订单簿量消除盈利 | 强化“统计偏差/价差不等于个人可成交 Alpha”与成本停止门 | 三角套利不同于跨币信息传导；只作执行现实基准 |
| Han, Kang & Ryu (2023, rev. 2026), [Momentum in the Cryptocurrency Market under Realistic Assumptions](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4675565) | 纳入日内波动、费用与 liquidation 后，多数 crypto momentum 组合不具盈利；TSMOM 证据强于 cross-sectional | 支持保留成本、尾部、short/liquidation 与简单解释，不把均值收益当盈利证明 | SSRN 工作稿；不是 lead-lag 事件研究 |
| [Binance Public Data 官方仓库](https://github.com/binance/binance-public-data) | 官方日/月归档、USD-M Kline 字段、支持 5m、同目录 SHA-256 CHECKSUM；归档可能因问题被替换 | 本题唯一结果数据源；每个文件校验和与实得 hash 写入 manifest | Kline 无买卖方身份、盘口、标记价、逐笔延迟和跨所流量；不能识别因果或真实成交 |
| Liu, Tsyvinski & Wu (2022), [Common Risk Factors in Cryptocurrency](https://doi.org/10.1111/jofi.13119) | crypto market、size、momentum 等共同因子说明高相关可来自共同风险暴露 | 要求先去 BTC beta，再讨论残差预测 | 日频/横截面因子不等同于 5m 冲击传导 |

## 调研后形成的机制假设

BTC 上涨时“谁在同时买其他币”没有单一答案。现有证据更支持多个并行通道：共同风险需求和系统化 basket/指数暴露、BTC 先完成价格发现后套利/做市库存调整、永续套保和清算触发、散户注意与追涨、以及跨场所买压。仅靠 5m Kline 无法识别参与者身份；本题只检验这些机制共同可能留下的**时间顺序预测痕迹**。

若成熟高活动币在下一 open 后没有显著 beta-gap catch-up，最合理更新不是“机会必然被机构全部赚走”，而是：在这一场所、频率和个人可行动延迟下，价格传导已足够快或毛幅度不足。若只在低活动币出现，也必须优先解释为 spread/depth/坏成交代理，而非可获利 Alpha。

