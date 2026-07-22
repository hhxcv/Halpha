# 来源、时间、假设与适用性

核查日期：2026-07-22（Asia/Shanghai）。外部来源只决定候选、公式和反证，不把论文收益直接移植为 Halpha 结论。

## 原始研究

1. Woong Bae Kim, *Price Path Continuity and the Cross-Section of Cryptocurrency Returns*, SSRN 6871159，30 页版本，文稿日期 2026-06-02、发布 2026-06-23，<https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6871159>。
   - 本地 Git 外 PDF：`D:/projects/Codex/CodexHome/research-data/halpha/_sources/price-path-continuity-kim-2026-v2.pdf`；356,354 bytes；SHA-256 `61eed44eb1a6fe3904eecf3ec6b80a587cdcd0b960b75fe1fd56422313f2bb69`。
   - 方法：CMC 历史快照构造 2020-01 至 2026-04 的生存偏差缓解样本；排除 stablecoin、wrapped token、NFT 等，要求正市值、非零成交量和价格至少 0.001 美元，收益 1%/99% winsorize。每周用前 14 日收益、Rank-Weighted PPC、控制变量做 Fama-MacBeth，并独立双重 tercile 排序；形成窗口与持有期之间留一日 gap。
   - 公式：绝对日收益越小权重越大（14 至 1），日收益符号的加权平均再乘累计 14 日收益方向。
   - 支持线索：完整控制的 `PastRet × PPC` 系数 0.0224、t=4.36；equal-weight continuous winner-minus-loser 周收益 1.18%、t=5.26；替代形成/持有期和连续性定义方向一致。
   - 强反证：continuous winners 自身周收益 0.94%、t=1.37，CAPM alpha 0.07%、t=0.18；全样本 value-weighted continuous-minus-discrete 的差分只有 0.33%、t=0.61。论文更支持条件交互或多空价差，不直接支持本题单腿多头。
   - 未覆盖差异：Binance 单一永续场所、当前幸存者 25 目标、零售手续费、spread/slippage、settled funding、cooldown、单目标计划、保证金与清算。论文是 2026 新工作论文且无独立复现，样本覆盖本题两个历史阶段。

2. Zhi Da, Umit G. Gurun, Mitch Warachka, *Frog in the Pan: Continuous Information and Momentum*, Review of Financial Studies 27(7), 2014，SSRN <https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2370931>。
   - 原始机制：信息逐步而非离散到达时，有限注意可能产生更慢价格调整；支持把“路径结构”与累计收益幅度分开。
   - 未覆盖：股票现金流新闻、较长动量形成期和股票做空/组合，与 crypto 永续、14 日 PPC、零售执行不等价；不能证明因果机制或 Halpha 策略。

3. Long et al., *Seasonality in the Cross-Section of Cryptocurrency Returns*, 2020 工作论文。Git 外 PDF：`D:/projects/Codex/CodexHome/research-data/halpha/_sources/seasonality-cross-section-crypto-long-et-al-2020.pdf`，SHA-256 `1ddbdf7ef7329079a734e907a30f4b2d78a683afad6334823f76c78b75ae37fa`。
   - 只作未选候选线索；日频换手与当前半自动维护成本更高。

4. Mueller et al., *Revisiting seasonality in cryptocurrencies*, Finance Research Letters 2024, DOI <https://doi.org/10.1016/j.frl.2024.105778>。
   - 约 500 币的大样本未支持稳健普通收益季节性，是不优先日历规则的反证。

## 场所和数据源官方资料

5. Binance USD-M Futures REST，Kline/Candlestick Data，<https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Kline-Candlestick-Data>。
   - 使用 UTC 1d open time、OHLC、quote asset volume；只在 bar 完成后进入形成窗口，下一可行动时间显式后移。

6. Binance USD-M Futures REST，Get Funding Rate History，<https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Get-Funding-Rate-History>。
   - 使用已结算 `fundingTime/fundingRate/markPrice`；不使用预测 rate，不调用账户或交易端点。

7. Binance Public Data，<https://data.binance.vision/>。
   - mark-price/funding 官方月档用于缺口校验与低负载重取；源 manifest 记录 URL、bytes 和 SHA-256。

## 成熟框架

8. VectorBT `Portfolio.from_orders` 官方文档，<https://vectorbt.dev/api/portfolio/base/>；本研究环境版本 `1.1.0`。
   - 采用：把每个固定入退场计划作为独立列，广播计算价格、费用和滑点；与手工现金流逐笔核对。
   - 不采用为权威：funding、信号截止点、缺口、cooldown、保证金、清算与真实场所成交。

## 数据边界总结

- 2024 与 2025 底层数据已经被本项目其他问题查看，Kim 论文也覆盖这两个时期；顺序门只阻止本题根据后段结果调参，不能制造真正新市场证据。
- 当前目标名单存在幸存者偏差；论文使用数千币历史快照，而本题是流动性和长期可维护性优先的 25 个永续目标。若关系依赖小币或广泛截面，本题应失败或降级，不能放宽名单救回。
- 不使用 L2、OI、liquidation、新闻或舆情；本题只检验基础日线是否已足够承载该特定路径关系，不声称完整理解市场。

