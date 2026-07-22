# 事前注册：短周期加密残差动量

## 单一主问题

固定 `RMOM_90_14`：每个周六 UTC 收盘后，以当周可用且满足流动性/连续性条件的目标构造每日留一法等权市场收益；对每个币最近 90 个完整日收益回归 `r_i = alpha_i + beta_i * r_market_ex_i + epsilon_i`。信号为最近 14 日 `sum(r_i - beta_i*r_market_ex_i) / std(r_i - beta_i*r_market_ex_i)`，遵循经典研究不把估计 alpha 加入残差动量排序。周日为完整冷却，预测周一 open 至下周一 open。

主检验在每个行动周按信号分五分位：最高五分位为 top，最低五分位为 bottom。主要目标是 top 的下一周等权币种收益、top 相对当周可选市场的超额收益，以及 top-minus-bottom 超额收益。所有周先聚合再推断，避免同周多币伪增样本。

## 数据与时间顺序

- 固定当前成熟目标 25 个；冻结名单及分类身份来自研究 universe，不按结果删币。
- 过去 30 日中位 quote volume 至少 1,000 万 USDT；每个信号周需要至少 20 个可排序目标。
- 信号计算至少 121 个连续完整 UTC 日收盘；不插值。目标期 open 缺失视为数据质量失败，而不是事后删除该币。
- development：2022-01-03 至 2024-01-01（右端不含）；evaluation：2024，仅 development 全门通过才解封。
- 研究者已经在其他问题看过这些价格路径，但未在 checkpoint 前计算本题 RMOM 排名或目标条件收益。因此 development 不是真正未见数据；冻结只防止本地看结果改规则。

## 简单基准与固定反证

- 硬基准：同一周、同一可选集的普通 14 日总收益动量 `RAW_MOM14` top 五分位。
- 零基准：top 超额收益、top-minus-bottom spread 和周度 rank IC 为零。
- 固定邻近反证（不可择优）：`RMOM_60_14`、`RMOM_120_14`、`RMOM_90_7`、`RMOM_90_21`。
- 报告主信号与普通动量的周度横截面 Spearman 相关、每币选中结果、类别结果、上下半期、尾部和贡献集中度。

## 经济量级

预测研究不模拟 funding 或成交，但主 top 的标的层毛收益必须达到 `0.827692%/周`：stress round-trip 代理 `52 bp`，加上把 4% 年度全计划资金门槛换算到 0.25x 单标的所需的 `30.7692 bp/周`。这只是进入策略成本研究的最低毛空间，不是净收益估计；后续还必须使用实际 funding、手续费、spread/slippage 和执行语义。

## 推断

- 4 周 circular block bootstrap，5,000 次，固定 seed `20260722`，报告周度均值 95% 区间。
- 周度横截面 Spearman IC 也按周做同样 block bootstrap。
- 每币“被主 top 选中时的下一周超额收益”只作诊断，并以 Benjamini-Yekutieli FDR 控制依赖下的多重比较；不以单币显著性救活总体失败。

## development 全通过门

1. 数据质量 `PASS`；至少 80 个行动周、每半期至少 35 周；
2. 主 top 标的毛收益均值 `> 0.827692%`，其 block-bootstrap 95% 下界 `> 0`；
3. 主 top 超额收益均值和 top-minus-bottom spread 均 `> 0`，两者 95% 下界均 `> 0`；
4. 主 top 相对 `RAW_MOM14` top 的同周标的收益差 `> 0`，95% 下界 `> 0`；
5. 周度 rank IC 均值 `> 0`，95% 下界 `> 0`；
6. 上下半期的主 top 标的收益均超过经济量级，且 top 超额、spread、IC 均为正；
7. 至少 15 个不同币进入主 top；被选币中至少 50% 的币平均超额收益为正；最大单币正收益贡献不超过全部正贡献的 40%；
8. 四个固定邻近定义的 top 超额和 spread 均为正；
9. 主信号与普通动量的周度横截面 Spearman 中位数绝对值 `< 0.90`，且第 4 条增量门通过。

任一失败：development 结论 `DOES_NOT_SUPPORT`，evaluation 保持封存；不搜索方向、窗口、阈值、币种、市场定义、状态或持有期救结果。全通过：development 最多为 `SUPPORTS_WITHIN_SCOPE` 的预测关系并解封 evaluation，仍不得称策略可用。

## 复现命令

```powershell
$researchPython = (Resolve-Path "research/.venv/Scripts/python.exe")
$rmomStudy = "research/studies/predictive/2026/short-horizon-crypto-residual-momentum-predictability/study.py"
& $researchPython $rmomStudy self-test
& $researchPython $rmomStudy checkpoint
& $researchPython $rmomStudy prepare --stage development
& $researchPython $rmomStudy analyze --stage development
& $researchPython $rmomStudy gate --stage development
& $researchPython $rmomStudy validate
```

只有 `development_gate.json` 为 `PASS` 才允许对 evaluation 执行 prepare/analyze/gate。全部命令只读公开研究缓存；不启动产品、不连接产品数据库、不调用交易所变更端点。
