# development 结果摘要

## Answer first

`DOES_NOT_SUPPORT`

固定 RMOM_90_14 的 top 周均标的收益为 `0.4420%`，top 超额收益为 `0.4436%`，top-minus-bottom spread 为 `0.5927%`，周度 rank IC 为 `-0.0315`。相对普通 MOM14 top 的同周收益增量为 `0.0069%`。

经济筛选线为 `0.8277%`；失败硬门：`top_asset_mean_above_economic_floor, top_asset_bootstrap_lower_positive, top_excess_bootstrap_lower_positive, spread_bootstrap_lower_positive, increment_vs_raw_bootstrap_lower_positive, rank_ic_mean_positive, rank_ic_bootstrap_lower_positive, both_halves_pass, positive_symbol_breadth, all_fixed_neighbors_positive, signal_not_raw_clone`。

本结论只回答增量预测性。即使 PASS 也不是策略、可交易 Alpha 或长期盈利证明；FAIL 时 evaluation 保持封存，不做参数救援。完整数值见 `development.json`，逐周和逐币派生证据见同目录 CSV。
