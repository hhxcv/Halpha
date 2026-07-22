# 预注册

checkpoint 前不计算本题任何精确信号或目标结果。checkpoint 后不允许因结果更改方向、时期、名单、形成期、分组、控制、成本、门槛或停止规则。

## 固定样本与时间顺序

- 25 个固定 Binance USD-M mature perpetual，成员和分类继承公开数据父研究；当前幸存者偏差明示保留。
- 正式入场日期是每个 UTC 月的第一个日线 open。development `2022-01-01 <= entry < 2024-01-01`；evaluation `2024-01-01 <= entry < 2025-01-01`。
- 信号 cutoff = entry - 2 个 UTC 日，只使用截止 cutoff 收盘的完整日线；entry - 1 日为完整冷却日。
- target = entry open 至下一 UTC 月第一日 open 的 simple return。目标价缺失导致当月数据质量失败，不通过删除该标的改变分组。
- 标的需要最近 121 个连续完整日线，且 cutoff 时 30 日 median quote volume >= 10m USDT；当月至少 20 个可排名标的，否则全局 `NO_ACTION`。

## 固定特征

1. 对每个可排名标的，用过去 `L` 个日对数收益回归 `r_i = alpha_i + beta_i * r_market_ex_i + epsilon_i`，其中市场是当月合格名单排除自身后的等权日收益。
2. `IVOL_L = sample_std(epsilon_i)`；主规格 `L=90`，不年化也不影响排名。固定邻域为 `L=60` 和 `L=120`。
3. 控制：`TVOL90 = sample_std(r_i)`、`MAX28 = max(last 28 daily returns)`、`MOM90 = sum(last 90 log returns)`、`BETA90`、`LOG_VOLUME30 = log(30d median quote volume)`。
4. 每月对所有交叉特征做横截面 z-score；标准差为 0 的月份数据质量失败。

## 固定检验

- 主分组：按 IVOL90 升序，`ceil(N*20%)` 为 low tail，同样数量为 high tail；主 spread = low 下月收益 - high 下月收益。
- 每月 Spearman rank IC：IVOL90 与下月相对当月等权市场收益，事前方向为负。
- Fama–MacBeth：每月横截面 OLS，然后对月度 IVOL 系数均值用 HAC `maxlags=3`。无控制式只含 IVOL90；控制式同时含 TVOL90、MAX28、MOM90、BETA90、LOG_VOLUME30。负向单侧 p 由双侧 p/2 与系数方向固定计算。
- 不确定性：3 个月 circular block bootstrap，5,000 次，seed `20260722`；以 entry month 为推断单位。
- 简单解释：将 IVOL high tail 与 TVOL90 high tail 的下月收益比较；要求 IVOL 选择的负向收益有增量，而不是改名总波动。同时报告 IVOL 与 TVOL/MAX 的横截面 Spearman。
- 经济代理：仅作是否值得后续策略研究的粗门。high-IVOL SHORT proxy = `0.25 * (-high_tail_asset_return - 0.0052) - 0.04 * days/365`；0.52% 是标的层面双边压力交易成本。funding 未加入，因此即使代理通过也不是策略结论。

## development 硬门

以下全部必须 PASS，否则结论 `DOES_NOT_SUPPORT`、封存 evaluation 并禁止策略转换：

1. 数据质量 PASS；24 个计划月中至少 21 个 ACTION，每个 ACTION 月至少 20 标的，不存在未来目标缺失。
2. IVOL90 low-minus-high 均值 > 0，且 bootstrap 95% 下界 > 0。
3. rank IC 均值 < 0，且 bootstrap 95% 上界 < 0。
4. 无控制与完整控制 Fama–MacBeth IVOL 系数均 < 0，且各自负向单侧 HAC p < 0.05。
5. high-IVOL SHORT 经济代理月均 > 0，且 bootstrap 95% 下界 > 0；这只是毛余量门。
6. `TVOL90 high return - IVOL90 high return` 均值 > 0，且 bootstrap 95% 下界 > 0，证明 IVOL high 比原始 high-vol 更差。
7. 2022 和 2023 的 low-minus-high 均值均 > 0、rank IC 均值均 < 0、SHORT proxy 均值均 > 0。
8. IVOL60 和 IVOL120 的 low-minus-high 均值、SHORT proxy 均值均 > 0，且 rank IC 均值均 < 0。邻域只检查方向，不反选最佳。
9. high-IVOL 入选至少覆盖 8 个 symbol 和 3 个 category；至少两次入选的 symbol 中 >=50% 的平均下月收益 < 0；最大正 SHORT 贡献不超过全部正贡献 35%。

## 阶段、停止与结论

- development 任一门失败：`DOES_NOT_SUPPORT`，evaluation 不打开，不得换方向、子组、时期、因子模型或截断再搜索。
- development 全部通过：只打开预先封存的 2024 evaluation，重复同一门方向；任一失败为 `DOES_NOT_SUPPORT`，全部通过才可 `SUPPORTS_WITHIN_SCOPE`。
- 无论预测结论如何，本目录不产生交易指令、产品策略、资金建议或真实账户动作。
