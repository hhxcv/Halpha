# 重要尝试与失败日志

## 2026-07-22：方向筛选

- 审计 16 个 current strategy-candidate、4 个 predictive、BTC correlation opportunity frontier 及 legacy 结果。
- 排除日历季节性、重复短周期动量/反转、重复 low/high-vol、MAX 与当前难以表达的两腿 carry；没有因为实现容易或局部指标漂亮而选择。
- 选择尚未直接检验的中期输家长腿；主窗口 10 周来自同行评审论文的长期反转区间与 2026 Binance 工作论文的 8–10 周摘要，不来自本地结果扫描。
- 固定底部 30% 以贴近 2023 论文；8/12 周、底部 20% 只作不可升级邻域。

## 2026-07-22：原始资料留存

- 从 HSE 官方会议文件端点取得 PDF，确认 `%PDF-`；547,976 bytes，SHA-256 `a97eeda242f1ba863ed4006a7f0854d5356cf80d84adda697ae1eeb183d839b6`。
- SSRN 2026 工作论文全文获取不稳定；只记录原始摘要页明确披露的范围，不据此猜测未披露成本、持有期或构造细节。

## 运行日志

尚未运行 outcome。checkpoint 前只允许 self-test；checkpoint 后所有实现修复必须先记录旧/新 SHA-256、原因以及 `economic_rule_changed=false` 的 amendment。

## 2026-07-22：development prepare 首次失败与实现修复

- checkpoint：`55bf5a197669f6d84f2dbc49c51100a273136ee3acdc9e9d83fab721b5d4ac8a`。
- 首次 `prepare --stage development`：`FAIL`；唯一失败目标为 ENS，要求区间有 9 个早期日线缺口；父数据质量仍为 `PASS`，funding 最大间隔约 8 小时。
- 发现两个实现层错误：把“单目标数据不足则 NO_ACTION、横截面至少 20 个”错误写成全部 25 个目标全阶段零缺口；`shift(70/84)` 还按观察行而非 UTC 日历日偏移。
- `amendment-001.json` 绑定旧 study SHA-256 `3f390ba9f127f16544543cca7bf331aefc786c2c251e69c96403e99168004ee2` 和新 SHA-256 `325d93903f110be175a556850871c2ad49c54cf469491feecafd28bfd6c42865`。
- 修复：UTC 日历重建、连续 85 日完整窗口、缺口目标显式 NO_ACTION、每个决策日仍需至少 20 个完整目标。未改变任何经济规则、参数、名单、成本、阶段、基准或门槛。
- 修复后合成 self-test 再次 `PASS`；VectorBT/手工误差仍为 `1.7347e-17`。

## 2026-07-22：development 正式结果

- 修复后 `prepare --stage development`：`PASS`。每个决策日输入完整目标为 24–25 个，低于 20 的日期为 0；没有 OHLCV 插值。
- `analyze --stage development`：主规则 429 笔、96 个 entry dates、25 个实际目标；证据 digest `76961c816aeb43ffc779c2acef6df102d0cdd6152fae6df991397b144ccabd7a`。
- base 净收益在扣 hurdle 前周日期均值仅 `+0.026296%`，低于 `4% * 7/365 = 0.076712%`；扣门槛后为 `-0.050416%`。stress 扣门槛为 `-0.132918%`，四周 circular block-bootstrap 95% 区间 `[-0.603669%, +0.353244%]`。
- base 日期组合最大回撤 `-21.840274%`，超过事前 `-15%` 风险界限；最大正 PnL 目标占比 `25.3765%`，超过 20%。
- 主规则相对 MOM7 输家、MOM70 赢家的 base 日期均值差分别为 `-0.035242%`、`-0.004320%`；没有出现文献转换所需的“中期输家胜过短期输家和中期赢家”。
- 它点估计胜过有 cooldown 的无筛选 LONG `+0.093970%`；gross 相对每周等权市场 LONG 为 `+0.037571%`，但 95% 区间 `[-0.132755%, +0.217631%]` 跨零。这不足以补救绝对压力净值、风险、邻域和分解门失败。
- development gate `FAIL`：base/stress、双半段、日期回撤、MOM7/赢家基准、2/3 邻域、目标/类别广度、集中度、stress 区间下界和 gross 市场超额区间下界等 12 项失败。
- 按顺序门没有打开 2024 evaluation 或 2025 confirmation，没有生成 handoff；结论 `DOES_NOT_SUPPORT`。该结论只否定当前 25 个幸存永续的单目标 one-shot 转换，不推翻广泛 point-in-time 现货分散组合论文。

## 2026-07-22：复演与完整性

- 从相同 checkpoint、amendment 与公共缓存重新运行 development analyze。
- 重演 evidence digest 仍为 `76961c816aeb43ffc779c2acef6df102d0cdd6152fae6df991397b144ccabd7a`；8 个交易 CSV 的 SHA-256 map 逐项一致。
- `validate` 检查 6 个稳定 JSON digest、8 个交易 CSV、阶段封印和无 handoff 条件，结果 `PASS`；最终枚举为 `DOES_NOT_SUPPORT`。
