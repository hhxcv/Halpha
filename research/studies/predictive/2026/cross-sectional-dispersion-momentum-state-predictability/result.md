# development 结果摘要

## Answer first

`DOES_NOT_SUPPORT`

低/高分散状态分别有 `91/13` 周；MOM20 spread 分别为 `0.6737%` / `-0.1814%`，低减高为 `0.8551%`。控制市场波动和平均相关后的标准化 dispersion 系数为 `-0.004780`，单侧 HAC p=`0.2200`。

低分散行动、高分散现金的 0.25x 粗略成本/资金门代理周均为 `-0.1588%`。失败硬门：`minimum_high_state_weeks, low_spread_bootstrap_lower_positive, low_top_excess_bootstrap_lower_positive, low_minus_high_spread_bootstrap_lower_positive, uncontrolled_dispersion_slope_negative_significant, controlled_dispersion_slope_negative_significant, low_top_asset_above_conditional_floor, gated_proxy_mean_positive, gated_proxy_bootstrap_lower_positive, gated_beats_unconditional_mean, gated_beats_unconditional_bootstrap_lower_positive, all_calendar_years_directionally_pass, all_fixed_neighbors_directionally_pass`。

本题不包含实际 funding 或策略执行；FAIL 时 evaluation 与策略转换保持封存，不按结果调整分散度或动量定义。
