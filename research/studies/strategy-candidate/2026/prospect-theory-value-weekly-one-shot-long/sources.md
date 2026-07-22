# 先行调研、来源与适用差异

检索与核查时间：2026-07-22 UTC。优先使用同行评审原文、作者机构存档和官方数据资料。

## 选中问题的原始依据

1. Rongxin Chen、Gabriele M. Lepori、Chung-Ching Tai、Ming-Chien Sung，*Explaining cryptocurrency returns: A prospect theory perspective*，Journal of International Financial Markets, Institutions and Money 79 (2022), 101599，DOI `10.1016/j.intfin.2022.101599`。作者机构页：<https://eprints.soton.ac.uk/458065/>；开放 accepted manuscript：<https://eprints.soton.ac.uk/458065/1/AcceptedManuscript.pdf>。
   - 1,573 个 Coincodex 币，2014-01-01 至 2020-12-31；数据包含主动与退市对象，降低但没有消除幸存者偏差。
   - 将最近 52 个周收益相对市值加权加密市场参考排序，使用 `alpha=beta=0.88, lambda=2.25, gamma=0.61, delta=0.69` 的累积前景理论价值与概率权重。
   - 更高 PTV 的下一周相对收益更低；一个横截面标准差对应约 `-0.71%`。低减高 PTV 的 value-weighted long-short 毛均值约 `5.9%/周`，论文以总计 2% 的周调仓成本做敏感度。
   - 结果对零、无风险收益和自身历史均值参考点报告为稳健，且不是只由微盘贡献；但等权效应明显更大，限制套利较强对象的效应也更强。
   - 未覆盖 Binance 永续、funding、固定当前存续名单、单腿绝对收益、用户固定目标、冷却或真实人工计划延迟。

2. Tversky、Kahneman，*Advances in Prospect Theory: Cumulative Representation of Uncertainty*，Journal of Risk and Uncertainty 5 (1992)。本题不重新估计偏好参数，只复现 Chen 等固定的实验参数和累积权重方向。

## 强制反证与相邻文献

3. Liu、Tsyvinski、Wu，*Common Risk Factors in Cryptocurrency*，Journal of Finance 77 (2022)；NBER 开放稿：<https://www.nber.org/papers/w25882>。市场、规模和动量能解释大量横截面差异，因此本题必须比较简单 52 周相对动量与市场多头。
4. Chen 等原文报告 PTV 与过去收益、偏度正相关，与波动率负相关。本题把最低相对动量、最低偏度和最高波动率分别作为不可择优简单基准，防止把普通输家或风险暴露重命名为 PTV Alpha。
5. Jia、Liu、Yan，*Higher moments, extreme returns, and cross-section of cryptocurrency returns*，Finance Research Letters 39 (2021), 101536，DOI `10.1016/j.frl.2020.101536`。5 分钟日级偏度和极端收益存在横截面预测，但其日频成本与本题 52 周分布不同；只作为偏度替代解释。

## 官方数据与项目适用边界

6. Binance Public Data：<https://github.com/binance/binance-public-data>。已有 Git 外缓存来自官方 USD-M 日 Kline、funding 与 mark 归档并带官方 checksum/本地 SHA-256；本题只读复用，不下载评价期直到开发门通过。
7. Binance USD-M Kline 官方资料：<https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Kline-Candlestick-Data>。日线提供 UTC OHLCV/quote volume，不提供交易者身份、盘口、队列或 point-in-time 市值。

关键差异不可被结论遗漏：当前 25 个永续幸存者不是论文宽市场点时对象；等权流动永续参考不是市值加权 Coincodex 指数；周六截止/周一行动不同于论文 Friday-to-Friday；本题收益含 funding 但不含真实 L1/L2、保证金、强平、ADL、部分成交和人工延迟。盈利回测不是 Alpha 或长期盈利证明。
