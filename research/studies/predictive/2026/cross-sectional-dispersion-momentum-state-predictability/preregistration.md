# 事前注册：分散度 × 动量状态

## 固定定义

每个完整 UTC 日 `d`：

1. 可选目标需有 61 个连续完整日线，过去 30 日中位 quote volume ≥ 1,000 万 USDT；至少 20 个目标；
2. `D_d = std_i(r_i,d)`，其中 `r_i,d` 为当天 close-to-close log return；
3. `D*_d` 为从 2021-01-01 到 `d` 的有效 `D` 扩展中位数，至少 252 个有效日；`x_d = log(D_d/D*_d)`；
4. 控制变量：同一可选集等权市场收益的 30 日 realized volatility，以及当前可选集过去 60 日收益矩阵的平均非对角相关；
5. 论文式连续缩放诊断 `g_d=min(1,max(0.10,D*_d/D_d))`，不把其历史业绩当作 Halpha 策略。

每周一为未来计划日：信号截止前一周周六 close，周日完整冷却。对截止日可选目标按过去 20 日累计 log return 排序，`ceil(20%)` 为 top/bottom；目标为周一 open 到下周一 open。主周度响应是 `top-minus-bottom` 超额 spread，另报告 top 标的收益、top 相对当周等权市场超额收益。

低分散状态：`x<=0`；高分散状态：`x>0`。这是论文 exposure 开始下降的固定边界，不根据结果改分位点。

## 阶段

- development：`2022-01-03` 至 `2024-01-01`（右端不含）。
- evaluation：2024，仅 development 全硬门 PASS 才允许读取本题条件结果。
- 底层价格路径已在其他问题暴露，但 checkpoint 前未计算本题逐日 dispersion、条件 spread 或回归；因此只防止本地调参，不冒充真正未见市场数据。

## 推断与基准

- 4 周 circular block bootstrap，5,000 次，seed `20260722`；状态均值差按完整周序列分块重采样后重算。
- OLS/HAC（Bartlett，4 lags，小样本修正）：`spread ~ const + x`，以及 `spread ~ const + x + market_vol30 + avg_corr60`；连续变量在 development 内标准化。主系数必须为负，单侧 p<0.05。
- 强基准：无条件 MOM20 top；状态门把高分散周视为现金。经济代理按未来 0.25x 计划计算：行动周扣 underlying round-trip 52 bp，所有周扣 4%/52 全计划资金门槛；不含 funding，所以只决定是否值得进入完整策略研究。
- 固定邻近反证：MOM14、MOM30；高尾 `x>log(Q75/median)`。不择优、不改变主定义。

## development 全通过门

1. 数据质量 PASS；≥80 行动周，低/高状态各 ≥30 周；
2. 低分散 MOM20 spread、top 超额均 >0 且各自 block-bootstrap 95% 下界 >0；
3. `low spread - high spread >0`，95% 下界 >0；
4. 无控制与控制回归的 `x` 系数均 <0，单侧 HAC p<0.05；
5. 低分散 top 标的周均收益 >0.827692%；
6. 低分散行动/高分散现金的全日程 0.25x proxy 扣 52bp 和 4% 年度门后均值 >0、95% 下界 >0；并相对无条件 MOM20 proxy 的差 >0、95% 下界 >0；
7. 2022/2023 各自 `low-high spread >0`，低分散 spread 和 top 超额均 >0；
8. MOM14、MOM30 和高尾反证均保持“分散度更高、动量更弱”的方向；
9. 低分散 top 至少覆盖 15 个目标，至少 50% 被选目标的平均超额收益为正，最大正贡献占比 ≤40%。

任一失败：`DOES_NOT_SUPPORT` 本适配，evaluation 与策略题封存，不搜索平滑、阈值、窗口、币种、方向或不同状态。全通过：最多 `SUPPORTS_WITHIN_SCOPE` 预测关系，允许另开含实际 funding 与 VectorBT 的策略研究，不生成 handoff。

## 复现命令

```powershell
$researchPython = (Resolve-Path "research/.venv/Scripts/python.exe")
$dispersionStudy = "research/studies/predictive/2026/cross-sectional-dispersion-momentum-state-predictability/study.py"
& $researchPython $dispersionStudy self-test
& $researchPython $dispersionStudy checkpoint
& $researchPython $dispersionStudy prepare --stage development
& $researchPython $dispersionStudy analyze --stage development
& $researchPython $dispersionStudy gate --stage development
& $researchPython $dispersionStudy validate
```
