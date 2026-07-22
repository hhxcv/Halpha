# 结果：RMOM2 单腿 one-shot 转换未通过开发门

## 结论

`DOES_NOT_SUPPORT`

固定的两周日收益均值/样本波动排序、顶部五分位和 `0.5x LONG / 7d` 转换在 2023 development 没有通过全部现实成本、统计、基准、稳健性、广度与风险门。它不进入 evaluation/confirmation，不生成交易核心 handoff，也不修改正式策略、产品代码、资金或真实账户。

## 关键数值

- 交易 / entry dates / 目标：`171 / 51 / 25`。
- base / stress 扣 4% 全计划资本周门槛均值：`0.897120% / 0.718402%`。
- stress 四周 block-bootstrap 95% 区间：`[-0.746390%, 2.431882%]`。
- base date-portfolio 最大回撤：`-26.420936%`。
- 相对 MOM14 的 base 均值差：`-0.076820%`。
- gross 相对同周等权市场均值差：`0.191784%`。
- RMOM14 与 MOM14 周横截面 Spearman 中位数：`0.9130`。
- 失败门：`stress_bootstrap_lower_positive, both_halves_base_positive, date_portfolio_drawdown_above_minus_20pct, base_beats_mom14, gross_excess_bootstrap_lower_positive, largest_positive_pnl_share_at_most_20pct`。

## 边界

本结果只判断当前幸存 25 个 Binance USD-M 永续、固定单目标、零售成本和 one-shot 转换；不推翻论文的广泛币种、市值加权 long-short 因子。相同市场路径此前已被其他问题查看，本题只冻结了未见的 RMOM2 方法输出，不能称全局未见价格证据。正回测也不会证明长期 Alpha。
