# Q18：高波动半区内的 10 周输家一周做多

## 身份与问题

- 类型：`STRATEGY_CANDIDATE`
- 稳定产品基准：Git `0bdfeffa616260cebd2d2188ddc8deb9e85c77f4`
- 正式比较策略：`ONE_SHOT_DONCHIAN_ATR_BREAKOUT 1.0.1 / BTCUSDT-PERP`
- 候选：`RESEARCH_RV28_HIGH_HALF_MOM70_BOTTOM30_WEEKLY_LONG_0P25X_V1`
- 当前状态：尚未运行；不是可用策略或盈利证明

问题：在固定 25 个当前 Binance USD-M 永续中，先选 28 日已实现波动率最高的一半，再选其中 70 日收益最低的 30%；owner 已固定的目标只有同时入选时，才在下一 UTC 周一以计划资金 `0.25x` LONG、持有 7 日。该条件是否在真实 funding、零售成本、4% 全计划资金门槛、无条件输家/同波动组/赢家/市场基准、邻域、广度、风险以及 2024→2025→2026Q2 顺序证据后仍成立？

它是对 Q17 无条件中期输家转换的最后一个机制条件测试，不是结果驱动换窗口。外部 2026 工作论文在 Q17 运行前已称 8–10 周反转集中于较高波动资产；Q18 在未查看本条件的 2024 输出前冻结。若失败，不再继续换 high-vol cutoff、size、币种或形成期。

## 规则摘要

- 每个完整周日：过去 30 日 quote volume 中位数至少 1,000 万 USDT；连续 85 日输入完整；至少 20 个目标可排名。
- `RV28 = std(过去 28 个完整日 log return, ddof=1) * sqrt(365)`。
- RV28 降序取 `ceil(0.5*N)`；在该组按 `MOM70=close[t]/close[t-70]-1` 升序取 `ceil(0.30*high_vol_N)`。
- 周一 open 代理入场，7 日后周一 open 代理退出；退出后空一整 UTC 日，所以同目标不能连续周入场。
- 0.25x、单仓、不加仓、无盘中止损；数据无效、少于 20 个、未入选、方向非 LONG 或 cooldown 时 `NO_ACTION`。

详细成本、诊断、阶段和否定门见 `preregistration.md`。来源差异见 `sources.md`。公开原始数据只放 Git 外缓存；本目录保存 manifest、逐笔机会、结果、hash 和失败。

## 顺序命令

```powershell
research/.venv/Scripts/python.exe research/studies/strategy-candidate/2026/high-volatility-ten-week-loser-weekly-one-shot-long/study.py self-test
research/.venv/Scripts/python.exe research/studies/strategy-candidate/2026/high-volatility-ten-week-loser-weekly-one-shot-long/study.py checkpoint
research/.venv/Scripts/python.exe research/studies/strategy-candidate/2026/high-volatility-ten-week-loser-weekly-one-shot-long/study.py prepare --stage development
research/.venv/Scripts/python.exe research/studies/strategy-candidate/2026/high-volatility-ten-week-loser-weekly-one-shot-long/study.py analyze --stage development
research/.venv/Scripts/python.exe research/studies/strategy-candidate/2026/high-volatility-ten-week-loser-weekly-one-shot-long/study.py gate --stage development
```

development PASS 后才可把 stage 改为 `evaluation`。evaluation PASS 后才允许：

```powershell
research/.venv/Scripts/python.exe research/studies/strategy-candidate/2026/high-volatility-ten-week-loser-weekly-one-shot-long/study.py fetch --stage confirmation
research/.venv/Scripts/python.exe research/studies/strategy-candidate/2026/high-volatility-ten-week-loser-weekly-one-shot-long/study.py prepare --stage confirmation
research/.venv/Scripts/python.exe research/studies/strategy-candidate/2026/high-volatility-ten-week-loser-weekly-one-shot-long/study.py analyze --stage confirmation
research/.venv/Scripts/python.exe research/studies/strategy-candidate/2026/high-volatility-ten-week-loser-weekly-one-shot-long/study.py gate --stage confirmation
research/.venv/Scripts/python.exe research/studies/strategy-candidate/2026/high-volatility-ten-week-loser-weekly-one-shot-long/study.py validate
```

三门全过才生成框架无关 handoff，且只表示可进入未来核心资格验证，不授权产品修改、资金或实盘，也不保证长期盈利。
