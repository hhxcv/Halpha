# 先行调研与来源

检索日期：2026-07-22。选题前优先核对论文正式页面、机构保存的出版版本和本项目既有否定研究；二手页面没有用于冻结经济规则。

## 1. 经典残差动量定义

- Blitz, Huij & Martens (2011), *Residual Momentum*, Journal of Empirical Finance 18(3), 506–521, DOI `10.1016/j.jempfin.2011.01.003`。
  - Erasmus University 出版版本：https://pure.eur.nl/ws/files/46882404/ResidualMomentum-2011.pdf
  - 论文对股票用过去 36 个月因子回归，以过去 12-1 月残差收益并除以同期残差标准差排序；排序信号不纳入估计 alpha。作者报告其相对总收益动量具有更低动态因子暴露、更低风险和更稳定的历史表现。
  - 适用性：支持“先去共同因子，再检验特异收益延续”和标准化残差的机制与统计定义。
  - 未覆盖差异：股票、月频、Fama-French 三因子、长历史、长短组合；不直接支持加密永续、单一等权市场因子、14 日形成、7 日持有或 long-only 半自动计划。

## 2. 更新的加密异常证据

- Li & Zhu (2026), *Taming crypto anomalies: A Lasso-type factor model*, Research in International Business and Finance 83, 103298, DOI `10.1016/j.ribaf.2026.103298`。
  - 出版商正式页面：https://www.sciencedirect.com/science/article/pii/S0275531926000255
  - 论文用 2014–2023 年日收盘价、市值和美元成交额重新检验 49 个加密异常；公开页面称只有 13 个在全样本显著，并以市场、两周动量、残差动量构造 DS3，另报告样本外解释力比较。
  - 适用性：说明更新加密样本中残差动量与两周动量仍值得作为独立候选，而不能只沿用旧的宽泛异常清单。
  - 未覆盖差异：公开页面没有可审核的 RMOM 精确公式；其 CoinMarketCap 跨场所价格、市值加权五分组、长短因子与 Halpha 固定 Binance 永续、等权、long-only 计划不同。本研究不得声称复现 DS3 或使用其未公开细节。

## 3. 加密普通动量的行为机制线索

- Fracassi & Kogan (2022), *Pure Momentum in Cryptocurrency Markets*, SSRN 4138685。
  - 作者页面：https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4138685
  - 利用 24/7 市场“过去 24 小时收益展示”机械变化研究无新增基本信息时的投资者反应，给出加密动量可源于迟缓/机械反应的行为证据。
  - 适用性：支持把普通动量作为强而简单的解释与基准。
  - 未覆盖差异：研究的是展示窗口和短期行为，不证明本题的周度残差动量可交易。

## 4. 现实约束与异常衰减

- Li & Zhu (2026) 正式页面同时报告旧样本中的部分异常在更新样本消失，说明不能把已发表显著性外推为当前 Alpha。
- 本项目既有 `risk-adjusted-two-week-momentum-one-shot-long` 已对相邻的风险调整总收益动量给出 `DOES_NOT_SUPPORT`；`btc-neutral-alt-residual-reversal` 已否定无状态小时级残差反转。二者作为重复研究边界，而非本题结果来源。

## 5. 成熟统计实现

- statsmodels 0.14.6 `OLS` 官方文档：https://www.statsmodels.org/stable/generated/statsmodels.regression.linear_model.OLS.html
- statsmodels 0.14.6 `multipletests` 官方文档：https://www.statsmodels.org/stable/generated/statsmodels.stats.multitest.multipletests.html
- 本题用前者估计每周留一法市场 beta，用后者执行依赖检验下更保守的 Benjamini-Yekutieli 多重比较。两者只负责既定统计计算，不决定信号、样本或结论门。

## 候选筛选

同轮还比较了：横截面分散度择时动量、风险管理动量、配对/stat-arb、下行风险、tokenized TradFi 趋势。它们分别需要日频多资产动态权重、提高杠杆、双腿同步执行/更复杂选对、与已失败高波动/MAX 家族高度重叠，或历史过短。残差动量以基础日线即可计算、单次预测门成本低、能直接反证“只是市场 beta 的普通动量”，且若通过可自然映射为每周半自动 long-only 计划，因此优先。

## 解释上限

即使 development 与 evaluation 均通过，也只支持固定定义、固定 25 币、固定场所历史中的增量预测关系；还需独立的策略成本研究和冻结后的前向证据。论文或盈利回测均不能证明长期必然盈利。
