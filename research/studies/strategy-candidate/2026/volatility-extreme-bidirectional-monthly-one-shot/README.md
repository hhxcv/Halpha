# 波动率极端双向月频 one-shot 候选

状态：研究中。只写 `research/**`，不修改产品、正式策略、资金、账户或真实交易状态。

## 问题

在固定的 25 个当前流动 Binance USD-M 目标中，配置到单一目标的策略能否在每个 UTC 月首前，依据完整的 90 日实现波动横截面排名，对最低三名提议 `0.25x LONG`、最高三名提议 `0.25x SHORT`、其他目标 `NO_ACTION`，并在次月月首退出后，经现实费用、实际 funding、压力滑点、4% 全计划资本门槛、方向分解、稳健性、风险与顺序时间证据，达到未来交易核心资格验证门槛？

这不是一个同时提交六笔订单的组合策略。正式交接若产生，只描述“一个固定配置目标怎样依据同一冻结横截面产生一个方向提议”；不同目标的计划、金额与激活仍各自独立。

## 为什么选它

已有单腿研究留下了一个没有回答的项目差异：2022–2023 的低波动 `LONG` 和 2024 的高波动 `SHORT` 都有正绝对线索，但单腿结论分别被市场多头解释、样本与邻域不稳健压住。外部研究真正关心的是低波相对高波的横截面差，而不是把任一单腿的市场 beta 当 Alpha。月频动作、公开基础数据和单目标方向提议也比日频横截面季节性更适合个人小资金半自动计划。

候选筛选、已知暴露、来源适用性和反证见 `preregistration.md` 与 `sources.md`。

## 顺序证据

- `development`：2024，**已暴露选择回放**，不能独立支持候选；只验证固定双向表达、数据、成本和两条腿符号。
- `evaluation`：2025，首个未计算的精确规则门；只有 PASS 才允许获取/打开下一段。
- `confirmation`：2026H1；只有 evaluation PASS 才从 Binance 官方公开来源获取。
- 只有 evaluation、confirmation 及其合并门全部通过才生成 `handoff.json` 和 `SUPPORTS_WITHIN_SCOPE`。

## 命令

```powershell
research/.venv/Scripts/python.exe research/studies/strategy-candidate/2026/volatility-extreme-bidirectional-monthly-one-shot/study.py checkpoint
research/.venv/Scripts/python.exe research/studies/strategy-candidate/2026/volatility-extreme-bidirectional-monthly-one-shot/study.py self-test
research/.venv/Scripts/python.exe research/studies/strategy-candidate/2026/volatility-extreme-bidirectional-monthly-one-shot/study.py prepare --stage development
research/.venv/Scripts/python.exe research/studies/strategy-candidate/2026/volatility-extreme-bidirectional-monthly-one-shot/study.py analyze --stage development
research/.venv/Scripts/python.exe research/studies/strategy-candidate/2026/volatility-extreme-bidirectional-monthly-one-shot/study.py gate --stage development
research/.venv/Scripts/python.exe research/studies/strategy-candidate/2026/volatility-extreme-bidirectional-monthly-one-shot/study.py prepare --stage evaluation
research/.venv/Scripts/python.exe research/studies/strategy-candidate/2026/volatility-extreme-bidirectional-monthly-one-shot/study.py analyze --stage evaluation
research/.venv/Scripts/python.exe research/studies/strategy-candidate/2026/volatility-extreme-bidirectional-monthly-one-shot/study.py gate --stage evaluation
# 仅 evaluation PASS 后：
research/.venv/Scripts/python.exe research/studies/strategy-candidate/2026/volatility-extreme-bidirectional-monthly-one-shot/study.py fetch --stage confirmation
research/.venv/Scripts/python.exe research/studies/strategy-candidate/2026/volatility-extreme-bidirectional-monthly-one-shot/study.py prepare --stage confirmation
research/.venv/Scripts/python.exe research/studies/strategy-candidate/2026/volatility-extreme-bidirectional-monthly-one-shot/study.py analyze --stage confirmation
research/.venv/Scripts/python.exe research/studies/strategy-candidate/2026/volatility-extreme-bidirectional-monthly-one-shot/study.py gate --stage confirmation
research/.venv/Scripts/python.exe research/studies/strategy-candidate/2026/volatility-extreme-bidirectional-monthly-one-shot/study.py validate
```

