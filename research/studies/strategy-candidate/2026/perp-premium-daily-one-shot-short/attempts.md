# 实际尝试与失败记录

## 2026-07-22 checkpoint 前

1. 上一题负 premium 日频 LONG 在 2022–2023 以 1,662 笔明确亏损；该结果不允许简单取负，因为 SHORT 的滑点、funding、squeeze 和时期完全不同。
2. 联网核对：He et al. 报告正 funding 事件附近价格回落，但主要为分钟级两腿；Chi et al. 的 basis short leg 不显著；Xuan 在 XAUUSDT 发现 funding 单独更像 momentum，只有与 order flow 交互才 reversal。证据冲突使本题具有决策价值且可被明确否定。
3. 固定从 2024 开始，不把 2022 熊市作为任何收益证据。固定 premium1>0 top3、日频 0.25x SHORT、one-shot 冷却、实际 funding、三成本、三邻域、三基线和全部阶段门。
4. 冻结前审计发现复用汇总默认以至少 10 笔定义可评估目标/类别，而本题预注册门槛为至少 5 笔；在查看任何本题输出前加入本题局部汇总覆盖。合成汇总验证 5、5、4 笔三目标时仅前两者入组，正目标占比 0.5，类别口径一致。
5. `py_compile` 与命令入口通过。合成排名验证：25 个可排名目标中正 premium 第一名触发，第四名以后和非正 premium 不触发。
6. 合成 `100 -> 90` SHORT 验证三种成本下 VectorBT 与独立线性公式最大误差 `1.39e-17`；正 funding stress 乘 0.5，负 funding stress 乘 1.5，符号符合 SHORT 现金流。
7. 合成日历验证：3 个入选目标在 2024-01-01/03/05/07 共 12 笔，严格执行退出后一整日冷却；每笔只计 `entry < event < exit` 的 1 个 funding，入口和出口时刻事件均排除。
8. 结构门审计确认：阶段只能顺序开放；每阶段单独写 manifest、DQ、逐笔 CSV、汇总与 gate；开发失败不会获取 evaluation；三阶段全部通过前不会生成 handoff。

## checkpoint 后

9. development 获取 25 个目标、共 650 个去重公开缓存文件；DQ 25/25 `PASS`，各目标 412 根日线、1,233 根 8h premium、1,098 条 funding，缺日线/premium、非法 OHLCV 和 funding mark 缺失均为 0。
10. 固定主配置形成 515 笔、256 个 entry days、25 目标和 6 类。favorable/base/stress 日期扣门均值为 `-0.1133%/-0.1634%/-0.2185%`；stress 14 日块 95% 区间 `[-0.3859%,-0.0633%]`，完整位于零下。
11. gross price 逐笔均值 `-0.1673%`，实际 funding 收益均值 `+0.0108%`；正 funding 收益明显不足以抵消价格腿延续，更不能覆盖双边 fee、spread/slippage 和资金门槛。
12. premium3、premium5、premium1/top5 三个邻域的 stress 日期均值分别为 `-0.1919%/-0.1551%/-0.2239%`；funding1、winner5、scheduled short 的 base 分别为 `-0.1119%/-0.1132%/-0.1616%`，主配置没有胜过任一基线。
13. development gate 失败 12 项；至少 5 笔的正目标占比仅 1/3，只有 1/6 类为正，最大正目标贡献 45.27%，最差目标路径回撤 -26.98%。按顺序门停止，2025/2026 未下载，handoff 未生成，结论 `DOES_NOT_SUPPORT`。
14. 完整 analyze/gate 重演后，主表与六个诊断 trade CSV 的七个 SHA-256 全部稳定，关键统计和 12 个失败项不变；最终机器结果摘要为 `2a557ba497355a4ce688ab4038f756cf9906fc59173aaef18a2ae63927f972e7`。
