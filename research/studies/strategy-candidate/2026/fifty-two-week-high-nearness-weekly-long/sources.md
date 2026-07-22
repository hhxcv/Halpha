# 来源、访问时间、假设与适用边界

访问日期均为 2026-07-22。

## 直接研究来源

1. Yuecheng Jia, Betty Simkins, Shu Yan, Hongyu Zhang, Jiangyu Zhao, *Psychological anchoring effect and cross section of cryptocurrency returns*, Journal of Banking & Finance 182 (2026), 107592, DOI `10.1016/j.jbankfin.2025.107592`，官方页面：<https://www.sciencedirect.com/science/article/pii/S0378426625002122>。
   - 原始主张：每周末按 Nearness52 排序，下一周收益随接近度提高；价值加权高减低十分位组合约 `1.3%/周`，等权/价值加权结果与因子调整均显著。
   - 原文还报告：13–100 周定义、短中期动量、市场状态、流动性和价差控制后关系仍在；较差市场状态下反而较弱，更接近行为锚定而非风险补偿解释。
   - 原始数据：CoinMarketCap 聚合的日开高低收、成交量、市值，按每年 52 周形成周收益；point-in-time 宽市场现货横截面，周频重排，等权/市值加权多空组合。
   - 未覆盖：Binance 单场所 USD-M 永续、settled funding、个人 taker 成本、固定当前幸存目标、单腿绝对收益、0.25x 计划资本、周日完整间隔、同目标 one-shot 冷却、人工激活延迟与真实盘口。
   - 重要暴露边界：论文在 2025 年已修订/发表，且 Halpha 其他问题已看过 2024–2025 市场路径；历史通过也不是独立的发表后 Alpha 证明。本题将任何历史全通过结论封顶为 `INSUFFICIENT_EVIDENCE`。

2. Thomas J. George, Chuan-Yang Hwang, *The 52-Week High and Momentum Investing*, Journal of Finance 59(5), 2004, DOI `10.1111/j.1540-6261.2004.00695.x`。
   - 传统资产中的原始锚定/高点接近度方法来源。股票制度、月度组合与公司基本面不等同于 24/7 加密永续，只用于定义和替代解释。

3. Liu, Tsyvinski, Wu, *Common Risk Factors in Cryptocurrency*, Journal of Finance 77(2), 2022, DOI `10.1111/jofi.13119`，可核查摘要与书目信息：<https://ideas.repec.org/a/bla/jfinan/v77y2022i2p1133-1177.html>。
   - 市场、规模和动量能够解释大部分加密货币横截面收益。因此本题必须同时比较 52 周累计动量与等权市场长仓，不能把高点接近度的绝对正收益直接称为 Alpha。

## 选题前反证与被拒候选

4. Zhang, Zhao, *Good volatility, bad volatility, and the cross section of cryptocurrency returns*, International Review of Financial Analysis 89 (2023), 102712；公开工作论文：<https://cirforum.org/cirf2022/forum_files/papers/CIRF-306.pdf>。
   - 原文用 5 分钟成交构造 `RSJ=(RV+−RV−)/RV`，每天排序并交易下一天；价值加权高减低毛价差约 `-34bp/日`。
   - 本项目压力往返 fee+slippage 约 52bp，且半自动人工计划不适合每日轮换。它在取数、维护、成本和操作频率上均劣于本题，因此只留作候选筛除依据，不运行策略回测。

5. Zhang, Li, *Is idiosyncratic volatility priced in cryptocurrency markets?*, Research in International Business and Finance 54 (2020), 101252，官方页面：<https://www.sciencedirect.com/science/article/pii/S0275531920301926>；以及 Ahmad, Talpsepp, Shahzad, *Is idiosyncratic risk diversifiable in a cryptocurrency market?*, SSRN 6110597 (2026)：<https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6110597>。
   - 前者报告宽市场高 IVOL 正溢价，后者报告非微盘币为负且溢价随分散化消失。本地已有低波动 LONG、高波动 SHORT 和波动极值双向研究，均未过资格门；残差化近邻不足以构成新的独立机制，故不重复搜索。

6. Grobys, Sapkota, *Cryptocurrencies and momentum*, Economics Letters 180 (2019), 6–10，DOI `10.1016/j.econlet.2019.03.028`；Klaus Grobys 等后续 survivor momentum 反证见 Finance Research Letters 92 (2026), 109602。
   - 传统动量在不同样本中不显著、对幸存者和删尾高度敏感。它支持把动量作为竞争基准并对固定当前名单的幸存偏差降级，而非支持再次开一个普通动量问题。

7. *Revisiting seasonality in cryptocurrencies*, Finance Research Letters (2024)，官方页面：<https://www.sciencedirect.com/science/article/pii/S1544612324004598>。
   - 报告收益季节性不稳健，Bitcoin 周一效应在 2015 年后不持续。因而日历策略在决策价值上低于本题。

## 行情与框架来源

8. Binance 官方 USD-M [Kline/Candlestick Data](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Kline-Candlestick-Data)、[Funding Rate History](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Get-Funding-Rate-History) 与 [binance-public-data](https://github.com/binance/binance-public-data)。
   - 本题只复用此前已校验的公开 1d OHLCV、settled funding 与 funding mark；manifest 保留 URL、bytes、checksum/SHA-256。无凭据、账户或产品数据库。

9. VectorBT 1.1.0 官方 [Portfolio.from_orders](https://vectorbt.dev/api/portfolio/base/#vectorbt.portfolio.base.Portfolio.from_orders)。
   - 只用于固定两单 LONG 的 fee/slippage 现金流重演，并与独立手工公式核对。信号、funding、冷却、顺序门和资格结论由本题最小代码补充；它不代表产品 NautilusTrader 验证。

## 本题可回答与不可回答

- 可回答：固定目标在锁定时期、成本、funding、周频单腿规则下，Nearness52 是否有绝对净收益，是否显著胜过同日 MOM52 与市场长仓，是否跨分期、邻域、目标和类别稳定。
- 不可回答：原论文宽市场多空因子是否可完整复现、退市币是否保持效应、真实盘口成交质量、人工延迟、保证金/强平/ADL、未来长期盈利或因果上唯一由锚定心理驱动。
