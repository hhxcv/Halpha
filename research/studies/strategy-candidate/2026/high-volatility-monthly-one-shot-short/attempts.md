# 实际尝试与失败记录

## 2026-07-22 checkpoint 前

1. 完成 `perp-low-volatility-monthly-one-shot-long`：主 low-vol LONG base/stress 为正但未优于 SCHEDULED_LONG、区间跨零、2022 为负，结论 `INSUFFICIENT_EVIDENCE`；后段保持未打开。
2. 该题事前对照 HIGHVOL90-LONG 在 2022–2023 base/stress 为负，且外部 2026 论文原始对象是 low-minus-high 价差。全库查重未发现高波 top3 月频 USD-M 单腿 SHORT。
3. 固定本题只从 2024 开始：2024 development、2025 evaluation、2026H1 confirmation。已知 2022–2023 结果只作 discovery，不参与收益、样本、年份、bootstrap 或参数选择。
4. 查看任何 2024 结果前固定 25 目标、VOL90/top3、月频 0.25x SHORT、one-shot 冷却、实际 funding、三种成本、三个邻域、LOWVOL90/LOSER90/SCHEDULED_SHORT 三个对照和所有门槛。
5. 再次联网核对原始文献身份与结论边界：Pyo & Jang (2026) 是截面低波溢价而非高波空腿绝对盈利证明；Burggraf & Rudolf (2021) 对 2013–2019 得出相反证据。两者共同要求把本题当作可证伪外推，而不是文献复刻成功。
6. 以 `research/.venv`（Python 3.13.14、VectorBT 1.1.0、pandas 3.0.3、NumPy 2.4.6、SciPy 1.18.0）完成已知价做空核对：100→90、0.25x，base 价格与成本收益 `0.02424001500000003`，VectorBT 与独立 SHORT 线性公式最大误差 `1.3877787807814457e-17`；正 funding 收益 stress 乘 0.5，负 funding 成本乘 1.5。
7. 完成无真实行情的固定随机合成路径测试：21 笔、7 目标、11 个 entry months，所有入场均为月首、同目标至少隔一个整月、funding 排除为 0，三种成本最大逐笔核对误差 `6.245004513516506e-17`。这只验证实现，不进入经济证据。
8. 结构可行性审计：12 个月每月最多选 3 个目标，one-shot 冷却仍可产生超过 15 笔；合成路径实际达到 21 笔、7 目标和 11 个月，因此 development/evaluation 的 15 笔、6 目标、8 个月门槛不构成逻辑不可能。confirmation 的 6 个月同理可达到 8 笔、4 目标、4 个月。未因该测试调整任何经济规则。

## checkpoint 后

9. 检查点摘要为 `e5cd5bd597c66d52de154eb8d08658c662c9a3772d9bfcc79a44754d02e6e009`；锁定本题代码、复用引擎、预注册、来源和环境。第一次 development 下载因命令 124 秒等待上限中止；只留下已校验的不可变缓存，没有清单或结果。第二次续跑复用已有文件并完成 600 个 funding/8h mark 档案、74 个日线输入；这是运行等待失败，不是方法变更。
10. development 数据质量 `PASS`：74/74 symbols 通过，25 个目标共 27,450 个 funding events，missing mark 为 0，最大 funding 间隔约 8 小时；清单内容摘要 `58fe1b8aae70c7a552789eca6bfe80fa5ef440f54109d180bda86eee7d7d46af`。
11. 主规格得到 24 笔、12 个 entry months、10 个目标、6 类。base/stress 扣门日期均值为 `+0.7709%/+0.5440%`；gross price 与实际 funding 的逐笔均值为 `+1.9129%/+0.3172%`；VectorBT 最大逐笔核对误差 `5.5511e-17`；缺 mark 排除为 0。
12. development gate 失败两项：stress 三月块 95% 区间 `[-0.8139%, +2.3318%]` 跨零；VOL60、VOL120、VOL90/top5 的 stress 日期均值分别为 `-0.1727%/-2.0760%/-2.5344%`，没有 2/3 为正。其余样本、年份、广度、基线、集中度和回撤门通过。
13. 严格停止：未下载或查看 2025 evaluation、2026H1 confirmation，未生成 handoff，结论 `INSUFFICIENT_EVIDENCE`。不能用后验观察到的 VOL90/top3 正均值继续调邻域或降低置信门。
14. 在相同缓存上重跑 analyze，主表与六个诊断 trade CSV 的七个 SHA-256 全部保持不变；随后重跑 gate 仍只失败相同两项。最终机器结果摘要为 `c8e02efc6bb56e2d73f3e7ac94c86addbaafb80b67960c440507c08d03993d7f`。
