# 持续 UP–UP 状态下的大型永续周赢家单腿 LONG

状态：已完成；结论 `INSUFFICIENT_EVIDENCE`。development 门失败，evaluation/confirmation 未打开，未生成产品 handoff。主要研究类型为 `STRATEGY_CANDIDATE`；本题没有修改产品代码、正式策略、资金或真实账户状态。

固定问题：在六个持续交易且当前高活动的 Binance USD-M 永续中，若截至周一开盘前的六币等权市场连续两个“四周累计状态”均为正，并且上一完整周的横截面赢家自身收益为正，那么下一周一 open 以计划资本 `0.25x` LONG 该赢家、持有七天，能否在实际 funding、零售级费用与 spread/slippage、4% 年化全资本门、简单市场多头基准和顺序时间证据下保持正净收益？

本题来源于“crypto momentum 集中于持续 UP–UP 状态”的成熟状态转换研究，同时正面面对“固定幸存币 momentum 不显著”的近期反证。它不是正式 Donchian/ATR 的参数变体：信号是周频横截面排名与广义市场状态，不使用价格通道或 ATR；若仍只复现普通 beta，则不得作为 Alpha 候选。

规则、候选筛选、否定条件和时间边界见 `preregistration.md`；原始来源见 `sources.md`；实际命令和失败见 `attempts.md`。大型公开数据不复制进 Git，本题只复用并逐文件核验既有官方 Binance 缓存：

`D:/projects/Codex/CodexHome/research-data/halpha/liquid-perp-weekly-loser-continuation/2026-07-22-v1/`

预定命令：

```powershell
research/.venv/Scripts/python.exe research/studies/strategy-candidate/2026/persistent-up-state-weekly-winner-long/study.py checkpoint
research/.venv/Scripts/python.exe research/studies/strategy-candidate/2026/persistent-up-state-weekly-winner-long/study.py inspect
research/.venv/Scripts/python.exe research/studies/strategy-candidate/2026/persistent-up-state-weekly-winner-long/study.py analyze --stage development
research/.venv/Scripts/python.exe research/studies/strategy-candidate/2026/persistent-up-state-weekly-winner-long/study.py gate --stage development
```

底层 2021–2025H1 市场路径已被父数据研究查看，因此即使精确规则输出按阶段顺序打开，也不能称为真正未暴露市场证据。若历史阶段全部通过，本题最多得到 `INSUFFICIENT_EVIDENCE` 并固定未来前向验证规则，不生成产品 handoff。

实际 development 在绝对收益上为正，但落后同状态六币等权市场、2022 为负、资本门/不确定性/回撤/邻域/集中度均失败；详细结果见 `result.md`。顺序门按预注册停止，后两段没有运行。

