# 实际尝试与失败记录

## 2026-07-22 checkpoint 前

1. 单独负 premium LONG 在 2022–2023 明确失败；单独正 premium SHORT/LONG 又在 2024/2025 发生方向翻转。它们表明 premium 单因子不稳定，但没有计算“上涨且负 premium”的 conjunction。
2. 联网核对 Chi、Cao、Zhang、Han、Xuan：basis 与 price-volume 应联合检验，但普通 momentum 统计力弱、basis-momentum 可被 basis 解释、现实路径和成本会大幅削弱结果，故本题必须胜过两个单因子基线。
3. 选择单腿 LONG 以贴近论文 long-leg 证据并避免同时引入 SHORT squeeze 风险；固定 5 日 winner top3、premium1<0、次日 0.25x LONG、持有一天、one-shot 冷却。
4. 固定四段顺序门，只有 2026H1 是相对干净的最终确认；不允许根据前三段改窗口、rank、方向、成本或门槛。
5. `py_compile` 与命令入口通过。合成排名验证：正 winner 第一名且 premium<0 触发，rank>3、premium≥0 或 winner≤0 均不触发；development 可打开，后三阶段均被前门封存。
6. 合成 `100→105` LONG 的三成本 VectorBT 与独立公式最大误差 `5.03e-17`。合成日历的三个目标在 2022-01-01/03/05/07 共 12 笔，同目标严格间隔两日。
7. 每笔只计 `entry < event < exit` 的一个 funding，入口/出口事件排除；负 funding 对 LONG 的实际收益为 `+0.00025`/单位计划资本。汇总继续使用至少 5 笔目标/类别和 14 日块口径。
8. 结构审计确认主配置、三个邻域、三个单因子/定时基线不可择优；任何阶段失败不下载下一段，四段全过前不生成 handoff。

## checkpoint 后

9. development 获取并锁定 1,332 个去重公开缓存文件；DQ 25/25 `PASS`。历史 funding mark 有 143 个缺失事件，均低于单目标 0.5% 上限；实际主配置排除 3/974 = 0.31%。
10. 主配置形成 971 笔、522 entry days、25 目标、6 类。favorable/base/stress 日期扣门均值为 `+0.0210%/-0.0291%/-0.0850%`；stress 14 日块 95% 区间 `[-0.1950%,+0.0263%]`。
11. gross price 与实际 funding 逐笔均值分别为 `+0.0520%/+0.0047%`，说明 conjunction 有方向和 carry 增量；但 0.25x 下双边 16/26 bp 零售假设与资金门槛足以使 base/stress 转负。
12. 2022/2023 base 分别为 `-0.0695%/+0.0203%`；只有 44% 目标和 2 类为正，最大正目标贡献 28.33%。三个邻域 stress 全负。
13. 主配置 base 优于 winner5 `-0.0354%`、premium bottom3 `-0.0723%` 与 scheduled long `-0.0854%`，但“优于亏损基线”不替代绝对收益、置信区间和跨年门。development 失败 8 项，结论 `DOES_NOT_SUPPORT`；2024–2026 未打开，handoff 未生成。
14. 完整 analyze/gate 重演后七个 trade CSV 哈希、关键统计和失败项全部稳定；最终机器摘要 `90027e5cd999c59e072244bcb8ea0e6fad76b85d9bc68ceb51b5efbed21004e7`。
