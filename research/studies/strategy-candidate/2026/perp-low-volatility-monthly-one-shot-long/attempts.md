# 实际尝试与失败记录

## 2026-07-22 checkpoint 前

1. 完成上一项 `past-month-max-weekly-one-shot-long`，其 development gate 失败并封存为 `DOES_NOT_SUPPORT`；没有从 MAX21 或 LAST1 诊断事后挑选主规则。
2. 全库查重发现现货低波组合、趋势过滤低波、TRX 波动目标和多种 momentum/carry 已运行，但没有“当前流动 USD-M 横截面低波排名 → 用户固定单腿月度 one-shot”的问题。
3. 联网比较短期流动赢家、90 日低波、negative-funding squeeze 和 BTC 残差动量。短期赢家虽有早期支持，但 2026 survivor-coin 论文给出强反证且与已失败动量家族相邻；funding squeeze 缺少无需阈值搜索的成熟定义；残差动量更接近已失败 BTC-neutral 家族。低波方向有 2026 Binance 432 币的直接新证据、项目内强现货线索和明确的合约适配缺口，因此选中。
4. 在查看任何本题 signal 或收益前，固定 25 目标、VOL90/bottom3、月末决策/月初行动、0.25x LONG、持有一月、one-shot 冷却、三种成本、实际 funding、三个邻域、三个简单对照和三段顺序门。
5. 上一题已暴露相同 2022–2023 日线/funding 字节；本题不冒充全新价格期。exact VOL90 选择和收益尚未计算；若 development 通过，2024 与 2025–2026H1 仍按顺序分别打开。
6. checkpoint 前审计结构上限：24 个 development 月、bottom3 和禁止连续月份使排名稳定时理论仅约 36 笔，且低波对象本来可能长期集中。原拟 40 笔/10 目标/25% 贡献门会把“低波持续性”机械误判为无样本或不可能集中度；在结果未查看前固定为 30 笔、6 目标、至少三类、最大正贡献 40%，后段按可用月份同比收缩。仍保留 stress 区间下界、年份、简单基线和目标回撤等更强经济门。
7. 使用独立 `research/.venv`（Python 3.13.14 / VectorBT 1.1.0）通过 `py_compile`；以内存合成 74 对日线得到 37 笔、24 个 entry months，并断言月首入退、28–31 日持有、同目标不连续月份、25 个可排名对象、低波 rank3 触发而 rank4 不触发。该测试只验证实现，不是收益证据。

## 2026-07-22 checkpoint 后

8. 生成环境与方法绑定 checkpoint `5db477a87791683afa77ae1c356b3c5211fa33b548fa7451b55858a3b369457d`。后续只允许预注册列明的取数、解析、身份、完整性、确定性统计或实现缺陷修复。
9. development fetch 复用 1,200 份 funding/8h mark 和 57 份 gap-only 1m mark 官方归档，新增 74 份覆盖 120 日邻域暖启动的日线页；独立 manifest 为 `033504dcebaab0a36efff9038f53db837d38124c1dc8390daba8702d079c79d1`，数据质量 `PASS`。
10. 首次完整 analyze 得到 37 笔、21 个 entry months、7 个目标。base/stress 扣门槛日期队列均值为 +0.3198%/+0.1245%；development gate 因排除比例、stress 区间下界、年份一致性和 SCHEDULED_LONG 四项失败，结论为 `INSUFFICIENT_EVIDENCE`。按顺序门不打开后段。
11. 固定缓存完整重跑 analyze/gate；主交易和六个诊断 CSV 全部逐字节一致，经济摘要和四项失败门一致。前后摘要保存在 `validation.json`。
