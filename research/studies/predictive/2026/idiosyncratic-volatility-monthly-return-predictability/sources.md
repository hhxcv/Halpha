# 先行调研与数据来源

检索与核对日期：2026-07-22（Asia/Shanghai）。优先使用论文作者页、DOI 出版页、开放原文和 Binance 官方数据身份。

## 原始研究

1. Zhang and Li, *Is idiosyncratic volatility priced in cryptocurrency markets?*, Research in International Business and Finance 54 (2020), 101252, DOI [10.1016/j.ribaf.2020.101252](https://doi.org/10.1016/j.ribaf.2020.101252)。广泛 crypto 横截面中 IVOL 与预期收益正相关，且作者报告市值、momentum、liquidity、volume 和 price 不能完全解释；但时间序列预测不显著。适用性：提供早期正向对立假设；差异：广泛现货/小币市场、早期样本，非当前单场所成熟 perpetual。
2. Ozdamar, Akdeniz and Sensoy, *Lottery-like preferences and the MAX effect in the cryptocurrency market*, Financial Innovation 7, 74 (2021), [开放原文](https://doi.org/10.1186/s40854-021-00291-9)。作者报告 IVOL 与 MAX 高度相关，控制 MAX 后 IVOL 效应消失，而 MAX 关系仍在。适用性：直接决定本题必须控制 MAX28；差异：原文使用 2014–2020 大型市值过滤现货横截面和价值/等权组合。
3. Ahmad, Talpsepp and Shahzad, *Is idiosyncratic risk diversifiable in a cryptocurrency market?*, SSRN 6110597 (posted 2026-01-21), [作者页](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6110597)。三因子 crypto 模型下，微型币 IVOL premium 为正，非微型币为负，且随组合分散而减弱。适用性：为本项目的成熟非微型标的提供事前负向预期；局限：SSRN 工作论文、未经同行评议，三因子定义与本题 leave-one-out 市场模型不同。
4. *Revisiting the low-volatility anomaly in cryptocurrency markets*, Finance Research Letters 97 (2026), 109851, DOI [10.1016/j.frl.2026.109851](https://doi.org/10.1016/j.frl.2026.109851)。作者在 post-2017 现货样本报告低总波动组合高于高波动，2–3 个月形成/一个月持有最强。适用性：支持 60/90/120 日邻域和月频目标；差异：这是总波动而非 IVOL，且现货 low-minus-high 不等于 perpetual 单腿策略。

相互矛盾的论文结果不是择一引用的理由，而是本题的问题来源。只有当“成熟非微型、近期、单场所 perpetual”下的负向关系能在 MAX/总波动控制后经受住本题门槛，才值得进入策略转换。

## 公开数据与实现身份

- Binance, [binance-public-data](https://github.com/binance/binance-public-data)：官方公开数据存储格式、路径与 checksum 说明。本题不新建数据仓，复用父研究已按官方 URL/checksum/SHA-256 校验的 USD-M 1d kline 缓存。
- 直接数据身份链：`../cross-sectional-dispersion-momentum-state-predictability/checkpoint.json`、`source_reuse_manifest.json`、`data_quality_development.json`；这些文件继续指向 Git 外公开缓存和原始官方文件哈希。
- 固定对象与分类：`research/market-universe/universe.csv`。该文件只是当前名单与分类输入，不是历史 point-in-time universe。

## 未覆盖差异

- 没有历史市值，不能复制 size 因子；使用固定成熟名单和 30 日 quote-volume 门，并把这个差异降低为适用范围限制。
- 没有 point-in-time 退市/新币总体，不判断微型币的正 IVOL premium。
- 没有 L1/L2、真实历史 spread/depth、队列、部分成交或人工激活延迟；预测阶段只用保守代理判断毛幅度是否值得进一步建模。
- 预测阶段不使用 funding；高 IVOL SHORT 的真实 funding 支出/收入只能在后续策略研究中按事件加入。
