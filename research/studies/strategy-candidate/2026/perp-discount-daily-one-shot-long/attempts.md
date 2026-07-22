# 实际尝试与失败记录

## 2026-07-22 checkpoint 前

1. 完成上一题 `high-volatility-monthly-one-shot-short`：2024 base/stress 为正，但 stress bootstrap 下界跨零且三个参数邻域 stress 全负，结论 `INSUFFICIENT_EVIDENCE`；2025+ 未打开。
2. 联网比较 funding、basis、动量、做市和两腿套利。Chi et al. (2023) 显示 basis 强于动量、收益主要来自 long leg、日频强于周/月频；He et al. (2022) 提供永续价差收敛机制，但主要是两腿策略。故选择可交付的折价单腿 LONG，同时明确它不是套利。
3. 淘汰 cash-and-carry（当前核心不能直接接收两腿）、做市/RL（自动化与基础设施过重）、普通 winner（内部多个动量诊断弱）和纯 funding 阈值（文献对方向收益不足）。
4. 查看本题任何输出前固定 25 目标、premium1<0 bottom3、日频 0.25x LONG、one-shot 冷却、实际 funding、三种成本、三个邻域、三个简单对照和全部阶段门。
5. 使用 `research/.venv` 完成无真实行情的信号测试：负 premium 按升序选 bottom3，非负 premium 即使 rank 在前三也不触发；rankable 少于门槛不触发。
6. 已知价 LONG 100→105、0.25x 的 base 价格与成本收益为 `0.011680007500000034`，VectorBT 与独立线性公式三种成本最大误差 `5.0306980803327406e-17`。
7. 固定合成路径产生 1,095 笔、365 个 entry days；所有入场为 UTC 00:00，同目标入场至少间隔两天，funding 排除为 0。这只验证时序/冷却，不进入经济证据。
8. 结构可行性审计：两年主配置理论上最多约 2,190 笔，合成路径即使 bottom3 长期不轮换也有 1,095 笔；150 笔与 120 日期并非逻辑不可能。12 目标和跨类别门会主动否定长期只集中在三个工具的信号，未因合成结果放宽。

## checkpoint 后

9. 初次 development inspect 仅 ENSUSDT 失败：其 2021-11-30 上市晚于通用 fetch start 13 日，导致旧检查错误要求上市前也有 daily/premium rows；正式信号尚未运行，未产生或查看任何交易、收益、诊断或 gate 输出。正式期 2022-01-01 前已有 32 个完整日，满足 30 日流动性暖启。
10. 依预注册允许的“数据完整性/实现缺陷修复”保留原 checkpoint，并新增 `checkpoint_amendment_001.json`：只把质量必需区间固定为阶段开始前 30 日，锁定修复前后代码哈希；信号、目标、成本、参数、阶段、对照和门槛均未改变。
11. 第一次 analyze 在 304 秒命令上限处终止；已写出七个中间 trade CSV，但没有 `development.json`、gate 或 results。只检查了文件名、大小和时间，没有读取 CSV 内容或任何收益值。
12. 新增 `checkpoint_amendment_002.json`：在单次进程内复用七个配置完全相同的输入矩阵，并跳过复用月频引擎中随后会被丢弃的 3-period bootstrap，只计算预注册的 14 日块、5,000 次 bootstrap。公式、RNG seed、交易、输出和门槛不变；从头重跑覆盖中间 CSV。
13. 新增控制流 amendment 003，使 `checkpoint` 重跑校验并报告 amendment 链，而不是把任何允许修复都误报为篡改；不触及研究计算。
14. 完整 development 得到 1,662 笔、710 entry days、25 目标、6 类；favorable/base/stress 日期扣门均值为 `-0.0223%/-0.0723%/-0.1291%`，stress 14 日块 95% 区间 `[-0.2055%, -0.0542%]`。gross price 逐笔均值 `-0.0089%`，实际 funding `+0.0093%`，两者近乎抵消，零售摩擦和资金门槛后明确为负。
15. development gate 失败 10 项：base/stress、stress 下界、两个年份、目标/类别广度、funding 与 momentum 基线、邻域和集中度；仅胜过更弱的全体定时 LONG。按顺序门停止，未下载 2024 或 2025+，handoff 未生成，结论 `DOES_NOT_SUPPORT`。
16. 完整 analyze 确定性复跑后，主表与六个诊断 trade CSV 七个 SHA-256 全部不变；gate 仍失败相同 10 项。最终机器结果摘要 `8fe63289eaf5a4f6b575e82f15cd05ee4c5b9aa7a6ed614c0ace469d3b308ba7`。
