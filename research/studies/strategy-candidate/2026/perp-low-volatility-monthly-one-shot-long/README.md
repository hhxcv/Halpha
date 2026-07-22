# 低波动月频单腿 USD-M one-shot LONG

状态：已完成；结论 `INSUFFICIENT_EVIDENCE`。development 门失败，evaluation/confirmation 未打开，未生成产品 handoff。

固定问题：用户已固定一个 Binance USD-M 工具、`LONG` 和计划金额时，如果该工具在至少 20 个当前流动目标中的 90 日实现波动率排名最低三名，是否值得在下一 UTC 月初 open 使用最多 0.25x 计划资本入场、持有到下月月初，并在实际 funding、零售成本、全计划资本门、one-shot 冷却和顺序留出下产生稳定正收益？

这不是既有现货低波组合的继续运行。父研究持有三个现货并共享 0.5x 总权重，本题是用户固定单个永续、每次完整退出、实际 funding 和单腿路径风险的可移植性审计。外部论文的低减高组合收益也不能直接证明 long-only 低波腿有绝对 Alpha。

规则、候选、否定条件和阶段门见 `preregistration.md`；原始来源见 `sources.md`；实际尝试见 `attempts.md`；结果与反证见 `result.md`；重演身份见 `validation.json`。大型公开输入放在 Git 外并由本目录 manifest 锁定。本目录不修改产品代码、数据库、配置、凭据、L4、资金或真实账户状态。

从仓库根目录复现 development：

```powershell
research/.venv/Scripts/python.exe research/studies/strategy-candidate/2026/perp-low-volatility-monthly-one-shot-long/study.py checkpoint
research/.venv/Scripts/python.exe research/studies/strategy-candidate/2026/perp-low-volatility-monthly-one-shot-long/study.py fetch --stage development
research/.venv/Scripts/python.exe research/studies/strategy-candidate/2026/perp-low-volatility-monthly-one-shot-long/study.py inspect --stage development
research/.venv/Scripts/python.exe research/studies/strategy-candidate/2026/perp-low-volatility-monthly-one-shot-long/study.py analyze --stage development
research/.venv/Scripts/python.exe research/studies/strategy-candidate/2026/perp-low-volatility-monthly-one-shot-long/study.py gate --stage development
```
