# 结果：波动率极端双向月频 one-shot

## 结论

`DOES_NOT_SUPPORT`

固定 VOL90 最低三名 LONG、最高三名 SHORT 规则在 `evaluation` 未通过预注册门。失败项：`vectorbt_reconciled, base_after_hurdle_positive, stress_after_hurdle_positive, long_stress_positive, short_base_positive, short_stress_positive, stress_bootstrap_lower_positive, both_half_years_base_positive, beats_reverse, beats_momentum90, two_of_three_neighbors_stress_positive, minimum_positive_categories, worst_target_drawdown_above_minus_30pct`。后续不打开，handoff 不生成；2024 正选择回放不能覆盖后续反证。

- trades / months / targets：`43 / 10 / 17`
- base / stress 扣门槛 cohort 均值：`-2.752366% / -3.077873%`
- LONG / SHORT stress：`-0.149041% / -5.786291%`

## 决定性反证

- 2024 已暴露选择回放为正：44 笔，base/stress 为 `+3.045343% / +2.800615%`；但 SHORT stress 仅 `+0.153357%`，主要由低波 LONG 驱动，不能作为独立支持。
- 2025 首个精确规则顺序样本反向：stress 95% 三月块区间 `[-7.220883%, +0.062787%]`，H1/H2 base 分别为 `-0.893773% / -4.610959%`。
- 主规则相对反向波动和普通 90 日动量分别低 `4.680500% / 6.083609%`；RV60、RV120、extreme5 的 stress 分别为 `-2.520624% / -0.065548% / -1.721429%`，三个邻域无一为正。
- 只有 `1` 个类别为正。集中度 `21.493558%` 和一般目标的中位回撤不是主要问题；关键尾部是 ZECUSDT 2025-10 SHORT 从 `74.14` 到 `403.61`，该目标两笔 base 累计 `-117.617333%`、回撤 `-112.265330%`。
- 这条 ZEC 路径超过一单位计划资本，真实执行会进入保证金、强平/ADL 与保护语义；无强平手工收益与 VectorBT 的最大差为 `0.0002987831`，因而同时触发精确核对门和最差目标回撤门。没有事后添加止损、剔除 ZEC 或改做多。

## 数据、复现与边界

- 2024/2025 只读复用已有 Binance 官方公开 1d kline、settled funding 与 mark 数据 manifest；source reuse digest `cd7b791922ddda5eba0bff778fc9653617fe6959bd24a84d9bbbacffcbf822dc`。
- 2025-07 只有 19 个目标满足成交额门，按冻结规则整月 `NO_ACTION`；因此实际 10 个 entry months。修复记录见两个 checkpoint-bound amendment。
- 2026H1 confirmation 未获取、未查看；未生成 handoff。
- 独立重跑后 development/evaluation evidence digest 及全部 16 个 CSV SHA-256 映射逐项一致；`validate` 为 PASS。
- 结论否定固定的 `VOL90 / bottom3 LONG / top3 SHORT / monthly / 0.25x` 当前幸存目标方案；不否定不同数据、带事前保护或真正组合保证金模型，但这些都必须是新问题，不能用来改写本次失败。
