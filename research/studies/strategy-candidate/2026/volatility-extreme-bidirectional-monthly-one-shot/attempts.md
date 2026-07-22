# 实际尝试、失败与修复

## 2026-07-22：选题冻结

- Q17 无条件中期反转和 Q18 高波条件反转均为 `DOES_NOT_SUPPORT`，按 family stop rule 不再追反转邻域。
- 比较低频双向波动、同星期季节性和价格路径连续性后，选择月频双向波动极端。原因是它直接回答现有单腿研究没有解决的相对波动差，并可表达为固定目标的单一方向/不行动提议。
- 明确披露 2024 是已暴露选择回放；不把它称为未触碰开发样本。2025 精确双向输出在 checkpoint 前未计算，2026H1 保持封存。

## 2026-07-22：checkpoint、自检与 2024 选择回放

- checkpoint digest：`b07ead78a7aab58fd0805814ca59136395d0060b8917ab49c268eb491fdfa242`；source reuse digest：`cd7b791922ddda5eba0bff778fc9653617fe6959bd24a84d9bbbacffcbf822dc`。
- VectorBT/手工 LONG、SHORT 单笔自检通过，最大误差 `1.734723475976807e-17`；funding stress 方向自检通过。
- 2024 数据质量 PASS，最低可排名目标 20。主规则 44 笔、11 个实际 entry months；base/stress 扣门槛 cohort 均值 `+3.045343% / +2.800615%`，LONG/SHORT stress `+3.042754% / +0.153357%`。development gate 仅作为选择回放 PASS。

## 2026-07-22：amendment-001——NO_ACTION 不是整段数据失败

- 首次 2025 prepare 发现 2025-07-01 只有 19 个目标达到 10m quote-volume 门。冻结规则规定该月全部 `NO_ACTION`，但实现错误地让整个 stage FAIL；`build_panel` 本来已正确跳过该月。
- 原 study SHA-256 `d800a8ee404de95b93cd17dddd6da91a2be147252fd29b63a3ec9c6d7705420e`，修正后 `e53a9474dc3cc2417b29283e55d14670f03261c600309b46ec36990b46a477cf`；amendment digest `6fca05879379a360afc7e5d9ce1a3a0be05abaa680a1afcaad3912488c16d67d`。经济规则未改变，19 个目标和六个成交额不足对象仍留在数据质量证据。

## 2026-07-22：2025 evaluation 反证

按顺序执行 `prepare -> analyze -> gate`：

- 43 笔、10 个 entry months、17 个目标、5 类；无 missing-mark/funding 排除。
- base/stress 扣门槛 cohort 均值 `-2.752366% / -3.077873%`；stress 95% 区间 `[-7.220883%, +0.062787%]`。
- LONG base/stress `+0.046439% / -0.149041%`；SHORT base/stress `-5.208043% / -5.786291%`。高波做空是主要失败来源，但低波做多在 stress 下也未过零。
- H1/H2 base `-0.893773% / -4.610959%`；相对 reverse/momentum90 为 `-4.680500% / -6.083609%`；三个邻域 stress 全负；只有一个正类别。
- evaluation gate FAIL，结论 `DOES_NOT_SUPPORT`；未授权 confirmation fetch，2026H1 没有获取或查看。

## 2026-07-22：amendment-002——不得漏掉少笔数尾部风险

- ZECUSDT 2025-10 SHORT 从 `74.14` 到 `403.61`，使两笔 target base 累计 `-117.617333%`、回撤 `-112.265330%`。复用汇总原先只在至少三笔的目标中计算最差回撤，错误漏掉这一尾部。
- 原 study SHA-256 `e53a9474dc3cc2417b29283e55d14670f03261c600309b46ec36990b46a477cf`，修正后 `34937583909cb140a0d04409275f8812f85869ec39e6c9722c5cd1e1d9455f25`；amendment digest `e2c53116b4f4f6f27cee940c3a14eae456bf34eea0b076cdc5031cfb099ff7a7`。只扩大风险汇总到所有实际交易目标，没有添加保护、排除交易或改变收益。
- 该路径进入未建模的保证金/强平区，VectorBT 与无强平手工模型最大差 `0.00029878310011555165`；精确核对门和最差回撤门均正确失败。

## 2026-07-22：独立重跑与留存

- 修正后 development evidence digest 两次均为 `a1033a7a086a35ac3c813acdc162c8bd45283bd146b7977f5905bb73621ce760`；evaluation 两次均为 `29ca89836fa1dacb2004607c461c6e629812d347d374107c0615a2aae82fb5f6`。
- 两阶段各 8 个交易 CSV，共 16 个 SHA-256 映射逐项一致。
- `validate` PASS：checkpoint、amendment chain、11 个 JSON 内容摘要和 16 个交易 CSV 均通过。
- 本目录保留候选筛选、来源、已知暴露、数据身份、代码、命令、两次实现修正、所有诊断交易、结果和反证；后续不得重复研究固定邻域或把 2024 正回放包装成候选。
