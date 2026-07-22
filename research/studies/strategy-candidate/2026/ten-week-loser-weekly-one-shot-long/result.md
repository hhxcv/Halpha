# 结果：10 周输家 one-shot LONG

## 结论

`DOES_NOT_SUPPORT`

固定的 MOM70 底部 30%、`0.25x LONG / 7d` 转换在 `development` 阶段未通过预注册门，因此不再打开后续阶段，不生成交易核心 handoff，也不修改正式策略、产品代码、资金或真实账户。

## 关键数值

- 交易 / entry dates / 目标：`429 / 96 / 25`
- base / stress 扣 4% 全计划资金门槛后的周日期均值：`-0.050416% / -0.132918%`
- stress 4 周 block-bootstrap 95% 区间：`[-0.603669%, 0.353244%]`
- base 日期组合最大回撤：`-21.840274%`
- 相对一周输家 / 十周赢家 / 无筛选做多的 base 差：`-0.035242% / -0.004320% / 0.093970%`
- gross 相对等权市场差：`0.037571%`
- 失败门：`base_after_hurdle_positive, stress_after_hurdle_positive, both_halves_base_positive, date_portfolio_drawdown_above_minus_15pct, base_beats_mom7, base_beats_winner70, at_least_two_of_three_neighbors_stress_nonnegative, at_least_half_selected_targets_positive, at_least_four_categories_positive, largest_positive_pnl_share_at_most_20pct, stress_bootstrap_lower_positive, gross_market_excess_bootstrap_lower_positive`

## 解释边界

这只否定或限制当前 25 个幸存 USD-M 永续、固定单目标、零售成本和 one-shot 转换；不推翻论文的广泛现货、point-in-time、分散 long-short 组合。正回测也不会证明长期盈利，本次失败更不能靠挑选诊断窗口补救。
