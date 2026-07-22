# 实际尝试与失败记录

## 2026-07-22 开题前

1. 重新读取 `research-halpha` 与证据方法；核对当前 L2/L3 one-shot 契约、L4 基准、`research/README.md`、当前 studies 与 33 项 legacy catalog。
2. 查重确认累计 momentum、top-2、类别 momentum、周频输家延续、日内/日级反转、BTC lead-lag、funding 与 carry 已暴露；没有过去一月 MAX→下一周的 Halpha 问题。
3. 联网比较五个候选。日内 skewness/MAX 次日 reversal 的预期经济幅度相对零售成本偏薄；ML 数据/搜索/维护过重；52 周 anchoring 与 MA/breakout 接近既有趋势族。选中 MAX28 周度 continuation，因为原始周度报告幅度大、定义单一、可直接对照累计/单日 momentum，且存在相反方向论文可强力证伪。
4. 在查看任何本题信号或收益前固定 25 目标、MAX28/top3、周日决策/周一行动、7 日持有、one-shot 冷却、成本/funding、三个简单基准、三个不可择优邻域、顺序阶段和全部门槛。
5. development 原始日线/funding 字节已被上一题查看，不冒充全新价格时期；本题输出尚未查看。计划复用同一 Git 外公共缓存但生成独立 manifest/checkpoint，避免复制约 62 MB 数据。
6. checkpoint 前做结构上限审计：周频 top3 在 development/evaluation 理论最多分别约 312/156 笔，one-shot 冷却还会减少成交；原拟 300/150 笔门槛几乎等同于要求无重复入选，不能合理度量证据量。结果未查看前将分段门槛固定为 150/75/100 笔，并保留 20/15/15 个目标和 40/20/30 个 entry dates 的独立广度约束；同时把从日频研究机械继承的 28 个日期 bootstrap block 修正为预注册所述四个周频 entry-date block。
7. checkpoint 前通过 `python -m py_compile`，并用完全内存合成的 74 对日线执行语义测试：产生 176 笔主规则交易、100 个 entry dates；断言仅周一入场、固定持有七日、同目标入场至少相隔 14 日、rankable targets 为 25、top3 触发而 rank4 不触发。该测试只验证实现语义，不是经济证据，也未读取产品数据。

## 2026-07-22 checkpoint 后

8. 生成不可变方法检查点 `76958413c3bd9325b44619d101998ce5f42b60dcbba6d8d24677aa6815b065fa`；从此只允许预注册列明的取数、解析、身份、完整性、确定性统计或实现缺陷修复。
9. development fetch 完全复用已存官方字节，校验 1,200 份 funding/8h mark 月归档和 57 份 gap-only 1m mark 月归档，并生成本题独立 source manifest `5ff0a4f6d589842463b57d2a931fc6e8bfbfc5034c82bd507204d967bf338907`；74 个日线对象与 25 个目标 funding 数据质量为 `PASS`。
10. 首次完整 analyze 得到 176 笔、93 个 entry dates、24 个实际触发目标。base 日期队列均值为 +0.1010%，stress 为 -0.0971%；development gate `FAIL`，九项事前门失败，`results.json` 结论为 `DOES_NOT_SUPPORT`。按顺序门不打开 evaluation/confirmation，也不生成 handoff。
11. 从固定缓存完整重跑 analyze 和 gate；主交易 CSV 与六个诊断 CSV 的 SHA-256 全部逐字节一致，经济摘要与九项失败门一致。JSON 只因生成时间改变摘要；前后身份保存在 `validation.json`。
12. 结果整理时发现预注册正文把 VectorBT 版本写成 `1.1.0`，而 checkpoint 和实际运行环境明确为 `1.0.0`。不在结果后改写已绑定的预注册文件；将差异作为流程缺陷保留。逐笔 VectorBT/手工公式最大误差为 `1.67e-16`，不影响本题负结论。
