# 高流动 USD-M 周级输家延续

状态：开发阶段已停止，结论 `DOES_NOT_SUPPORT`。研究身份 `RESEARCH_LIQUID_PERP_WEEKLY_BOTTOM1_SHORT_7D_0P25X_V1`。

本题服务于半自动策略计划：每周榜单形成后，用户把唯一最弱币、`SHORT` 和金额固定进一次性计划；策略最多使用计划金额 25%，周一开、下周一平，不自动再入。核心检验不仅是净收益，还包括相对六币等权市场的继续落后，防止把熊市普跌误报成选币 Alpha。

开发期 2021–2022 共 104 个周计划。虽然 bottom-1 相对等权市场的下一周选择收益平均为正，但 4 周 block-bootstrap 95% 区间跨零；单腿策略在 favorable、base、stress 下分别复合亏损 15.04%、19.38%、29.00%，并呈现 2021 年亏损、2022 年盈利的明显方向性 regime 依赖。开发门失败，因此没有打开 evaluation 或 confirmation，也没有生成产品交接包。

只写 `research/**`；只用 Binance 公开行情，不读产品数据库、账户、凭据或运行配置，不启动产品运行时、不产生交易。稳定基准 `0bdfeffa616260cebd2d2188ddc8deb9e85c77f4`。

重演入口：

```powershell
research\.venv\Scripts\python.exe research/studies/strategy-candidate/2026/liquid-perp-weekly-loser-continuation/study.py checkpoint
research\.venv\Scripts\python.exe research/studies/strategy-candidate/2026/liquid-perp-weekly-loser-continuation/study.py fetch
research\.venv\Scripts\python.exe research/studies/strategy-candidate/2026/liquid-perp-weekly-loser-continuation/study.py inspect
research\.venv\Scripts\python.exe research/studies/strategy-candidate/2026/liquid-perp-weekly-loser-continuation/study.py analyze --stage development
research\.venv\Scripts\python.exe research/studies/strategy-candidate/2026/liquid-perp-weekly-loser-continuation/study.py gate --stage development
```

Git 外缓存：`D:/projects/Codex/CodexHome/research-data/halpha/liquid-perp-weekly-loser-continuation/2026-07-22-v1/`。完整问题、搜索披露和否定门见 `preregistration.md`，结论见 `result.md`，每次重要尝试见 `attempts.md`。
