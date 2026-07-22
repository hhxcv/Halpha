# 实际尝试与失败

## 2026-07-22：Q17 后选题

- Q17 无条件 MOM70 loser 已按门得到 `DOES_NOT_SUPPORT`，没有从其 rv/mid-size 子样本挑结果；Q17 根本未计算高波动条件。
- 高波动条件在 Q17 outcome 前已由 2026 原始摘要明确提出，且有 2026 低波动异常论文作为相反先验。因此允许只做一次明确机制检验，而非持续追参。
- 主定义固定为 28 日实现波动最高一半、其中 MOM70 底部 30%；21/42 日和 MOM56 只作不可升级邻域。
- 2024 精确条件输出未查看；2025 与 2026Q2 严格封存。若 development 失败，后两段不运行；若本题失败，中期反转条件家族关闭。

## 运行日志

### 2026-07-22：development outcome

按预注册顺序执行：

```powershell
research/.venv/Scripts/python.exe research/studies/strategy-candidate/2026/high-volatility-ten-week-loser-weekly-one-shot-long/study.py prepare --stage development
research/.venv/Scripts/python.exe research/studies/strategy-candidate/2026/high-volatility-ten-week-loser-weekly-one-shot-long/study.py analyze --stage development
research/.venv/Scripts/python.exe research/studies/strategy-candidate/2026/high-volatility-ten-week-loser-weekly-one-shot-long/study.py gate --stage development
research/.venv/Scripts/python.exe research/studies/strategy-candidate/2026/high-volatility-ten-week-loser-weekly-one-shot-long/study.py validate
```

- 数据质量门通过；每个决策日至少 20 个完整目标，主规则产生 `125` 笔交易、`50` 个 entry dates、`21` 个目标。
- base / stress 扣 4% 全资金门槛后的 entry-date 周均值为 `0.620030% / 0.530429%`；stress 4 周块 bootstrap 95% 区间为 `[-0.464572%, 1.754131%]`，跨过零。
- base MDD 为 `-12.647372%`；H1 / H2 扣门槛均值为 `0.055209% / 1.141404%`，但收益明显偏向 H2。
- 主规则相对无条件输家、低波输家、高波赢家和 gross 市场的均值差分别为 `+0.253732% / +0.535328% / +0.235444% / +0.292492%`；这些差异的 95% 区间均跨过零。
- 决定性反证：主规则相对同一高波动半区的无筛选 `highvol_scheduled` 为 `-0.015853%`，所以 MOM70 输家筛选没有证明增量；正收益类别只有 `3/5`，最大单一正 PnL 贡献占 `29.005335%`，超过 `25%` 上限。
- development gate 因 `base_beats_highvol_scheduled`、`minimum_positive_categories`、`positive_pnl_concentration_below_limit` 三项失败；结论固定为 `DOES_NOT_SUPPORT`。未打开 evaluation、未获取 confirmation 数据、未生成 handoff。
- 按预注册 family stop rule，关闭中期反转的 size、波动 cutoff、窗口、币种和方向邻域，不因 2024 绝对收益漂亮继续追参。

### 2026-07-22：独立重跑与留存核对

再次执行 development `analyze`，随后执行 `validate`：

- evidence digest 两次均为 `969f8c43da83eaf4b814f6cfb9854ffd1ea5c1f3b3aef2d2cf09da62c957eeae`；
- 9 个交易 CSV 的 SHA-256 映射逐项一致；
- `validate` 为 `PASS`，核对 6 个 JSON 内容摘要与 9 个交易 CSV；
- checkpoint digest 为 `e55ade04b3f464e1347884d4c3da6c295d3b6a176fd28a1d24299f48a0760d05`；
- 所有结果和失败证据均保存在本研究目录，后续不得把这一次失败包装为策略候选，也无需重复研究同一家族邻域。
