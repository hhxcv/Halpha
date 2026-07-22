# 预注册

## 固定问题

在 25 个成熟 Binance USD-M 永续中，前 28 个完整 UTC 日的 15 分钟对数收益平方和 `RV28`，是否负向预测从下一个周一 `00:00 UTC` 到再下一个周一 `00:00 UTC` 的收益；且这种关系相对用日线收益估计的 `DVOL28` 仍有增量，并为 `0.25x` 单目标高 RV SHORT 在压力成本和完整计划资本门后留下正的粗经济空间？

预测器身份：`RESEARCH_RV15M28_HIGH_NEXT_WEEK_V1`。

## 冻结样本与时间顺序

- universe：继承固定 25 个成熟、当前仍交易的 Binance USD-M perpetual；不因结果增删标的。
- development：`[2022-03-26, 2023-07-01)` 的信号资料；第一个可行动 entry 为具有完整 28 日窗口的周一。
- evaluation：`[2023-07-01, 2025-01-01)`；development 全门通过才允许获取和分析。
- confirmation：`[2025-01-01, 2026-07-20)`；evaluation 全门通过才允许获取和分析。
- 每周六 `00:00 UTC` 为 decision：只使用 `[decision-28d, decision)` 的 15 分钟收盘；周一 `00:00 UTC` entry，下一周一 `00:00 UTC` exit。信号与目标至少相隔 48 小时。
- 当周至少 20 个标的同时有完整 15 分钟信号、entry/exit 和 30 日中位 quote volume；只保留中位日 quote volume 不低于 10m USDT 的标的。

## 主定义

- `RV28 = sum(r_15m^2)`，其中 `r_15m` 为连续 15 分钟 close 的对数差。
- 主排序：每周按 `RV28` 升序分为底部/顶部 `ceil(N/3)`；主预测量为 `high_minus_low`，预期为负。
- rank IC：每周 `Spearman(RV28, next_week_return)`，预期为负。
- 控制回归：每周横截面 OLS，下一周收益对标准化 `RV28`、`DVOL28`、`MOM28`、`MAX28`、`BETA84`、`log(volume30)`；对周度系数均值使用 HAC。
- 简单基准：相同 universe、相同目标周，按日线 `DVOL28` 选顶部 tercile。
- 固定邻域：`RV21` 和 `RV35`，只验证方向和粗代理，不替换主定义。
- 粗策略代理：每周只取主规则顶部 RV 的一个固定目标（按 `RV28` 最高，symbol 字母顺序打破并列），`0.25x SHORT`；从标的空头收益扣除 `52 bp` 往返压力成本，再扣完整计划资本 `4%/52` 周门。预测阶段不含 funding，因此即使通过也必须另开策略候选题。

## development 硬门

所有项目同时通过：

1. 数据质量 `PASS`；至少 52 个有效 action weeks，且每周至少 20 个可排名标的。
2. `high_minus_low` 均值 < 0，四周循环 block-bootstrap 95% 上界 < 0，负值周比例至少 52%。
3. rank IC 均值 < 0，HAC 单侧 p < 0.05。
4. 控制回归 `RV28` 系数 < 0，HAC 单侧 p < 0.05。
5. 高 RV 单目标 SHORT 粗代理均值 > 0，四周 block-bootstrap 95% 下界 > 0。
6. 主代理相对 `DVOL28` 高波 SHORT 的均值增量 > 0，bootstrap 95% 下界 > 0。
7. 前后半段的主粗代理均为正；每个完整日历年方向为正。
8. `RV21`、`RV35` 的 high-minus-low 和高 RV SHORT 粗代理方向均与主规则一致。
9. 主代理至少覆盖 10 个 symbol；有至少两次机会的 symbol 中至少 50% 的平均 SHORT 粗收益为正；最大正贡献不超过全部正贡献的 35%。

evaluation 和 confirmation 使用同一规则、同一门；不得参考后段结果修改参数。只有三段全部 `PASS`，才把结论定为 `SUPPORTS_WITHIN_SCOPE` 并允许另开策略候选题。

## 否定条件和解释边界

- development 任一硬门失败：结论 `DOES_NOT_SUPPORT`，后段和策略转换封存。
- 数据身份或时间顺序无法确定：`CANNOT_DETERMINE`。
- 方向为正但统计、基准、时期、邻域或广度不足：`INSUFFICIENT_EVIDENCE` 或按预注册 gate 的 `DOES_NOT_SUPPORT`，不得称为 Alpha。
- 不允许事后加入 positive jump、jump-robust variance、流动性/市值子样本、市场状态、方向反转、别的分位数/窗口、止损或标的白名单；这些都需要独立机制和新问题。
- 本题不建模真实 bid/ask、排队、部分成交、账户费率、funding、保证金、清算/ADL、人工延迟和场所故障。通过仅表示值得另开完整策略候选验证，不表示长期盈利。
