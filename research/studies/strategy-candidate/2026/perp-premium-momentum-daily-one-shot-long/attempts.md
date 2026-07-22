# 实际尝试与失败记录

## 2026-07-22 checkpoint 前

1. 第 10 题正 premium top3 次日 SHORT 在 2024 base/stress 为 `-0.1634%/-0.2185%`，gross price 腿均值 `-0.1673%`；它只用于产生相反的需求延续假设，不进入本题 gate。
2. 联网核对原始研究：Xuan 提供 funding 正向预测的直接但分钟级、成本后无利润证据；Cao 等把 basis 与 price-volume 识别为永续 total return 的系统驱动；Chi 等则提供高 premium LONG 不等于其 basis 多头的强反证。
3. 淘汰 5–10 分钟 BTC lead-lag（量级/自动化不匹配）、两腿 carry（核心契约不匹配）、OI/order-flow 反转（超出用户数据边界）和做市/RL（持续自动化与基础设施过重）。
4. 在查看 2025/2026 输出前固定 premium1>0 top3、日频 0.25x LONG、one-shot 冷却、实际 funding、三成本、三个邻域、三个简单基线和全部顺序门。
5. `py_compile` 与命令入口通过。合成排名验证：25 个可排名目标中正 premium 第一名触发，第四名以后和非正 premium 不触发；evaluation 可打开而 confirmation 在没有 evaluation `PASS` 时被拒绝。
6. 合成 `100 -> 105` LONG 验证三成本下 VectorBT 与独立线性公式最大误差 `5.03e-17`；正 funding stress 成本乘 1.5，负 funding stress 收益只留 0.5，符号符合 LONG 现金流。
7. 合成日历验证：3 个入选目标在 2025-01-01/03/05/07 共 12 笔，同目标严格间隔两日；每笔只计 `entry < event < exit` 的 1 个 funding，入口/出口时刻事件均排除，实际正 funding 现金流为 `-0.00025`/单位计划资本。
8. 合成汇总验证至少 5 笔口径：5、5、4 笔三目标只纳入前两者，正目标占比 0.5，类别与回撤口径一致。结构审计确认两段独立空仓、evaluation 失败即停止、两段全部通过前不生成 handoff。

## checkpoint 后

9. evaluation 获取并锁定 652 个去重公开缓存文件；DQ 25/25 `PASS`，每目标 411 根日线、1,230 根 8h premium，funding 1,095–1,999 条且 mark 缺失为 0。行数差异来自实际 funding 频率变化，逐事件计费。
10. 固定主配置形成 273 笔、196 entry days、22 目标和 6 类。favorable/base/stress 日期扣门均值为 `-0.1160%/-0.1659%/-0.2216%`；stress 14 日块 95% 区间 `[-0.3252%,-0.1214%]`，完整位于零下。
11. gross price 逐笔均值已为 `-0.0252%`，实际 funding 再贡献 `-0.0038%`；失败首先来自 2025 的价格延续消失/反向，并非只因 fee 或 funding。
12. premium3、premium5、premium1/top5 三邻域的 stress 日期均值为 `-0.1496%/-0.1619%/-0.2254%`。funding1、winner5、scheduled long 的 base 为 `-0.1192%/-0.1028%/-0.0982%`；主配置没有胜过任何基线。
13. 只有 3/9 个至少 5 笔目标为正，六个类别均负，最大正目标贡献 34.51%。evaluation gate 失败 11 项；按顺序门不下载 2026、不生成 handoff，结论 `DOES_NOT_SUPPORT`。
14. 完整 analyze/gate 重演后七个 trade CSV 哈希、关键统计和 11 个失败项全部稳定；最终机器结果摘要 `22da46b9530684423558b7cb38d4beb89feb09b5b6990c677dff71b1ebaedfd9`。
