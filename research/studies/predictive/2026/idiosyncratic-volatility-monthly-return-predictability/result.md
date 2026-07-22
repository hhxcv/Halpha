# 结果：特质波动率与下月收益

## 结论

`DOES_NOT_SUPPORT`

按预注册停止；评估期保持封存，不允许策略转换或事后换参。

## 主要证据

- 阶段 / ACTION months：`development / 24`。
- IVOL90 low-minus-high 均值：`0.949767%`；95% block-bootstrap `[-5.389805%, 6.695842%]`。
- rank IC 均值：`-0.115377`；95% block-bootstrap `[-0.198869, -0.023633]`。
- 完整控制 Fama–MacBeth IVOL 系数：`-0.336865%`；负向单侧 HAC p `0.488016`。
- high-IVOL SHORT 粗经济代理月均：`-0.515538%`；95% block-bootstrap `[-2.982859%, 1.828056%]`。
- TVOL-high 减 IVOL-high 下月收益：`-0.092414%`；正值才表示 IVOL-high 更差。

## 失败门

- `low_minus_high_bootstrap_lower_positive`
- `uncontrolled_ivol_slope_negative_significant`
- `controlled_ivol_slope_negative_significant`
- `short_proxy_mean_positive`
- `short_proxy_bootstrap_lower_positive`
- `ivol_increment_vs_tvol_mean_positive`
- `ivol_increment_vs_tvol_bootstrap_lower_positive`
- `all_calendar_years_directionally_pass`
- `all_fixed_neighbors_directionally_pass`

## 边界

固定当前幸存者名单缺历史市值/退市币，不代表微型币总体。日线预测没有 funding、真实历史盘口、保证金路径或人工激活延迟。任何正回测都不证明长期 Alpha，本题不修改正式策略、产品代码、资金或账户。
