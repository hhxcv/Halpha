# 过去一月 MAX 门控周频单腿 LONG

状态：已完成；结论 `DOES_NOT_SUPPORT`。development 门失败，evaluation/confirmation 未打开，未生成产品 handoff。

固定问题：用户已在 Halpha one-shot 计划中固定 Binance USD-M 工具、`LONG` 和交易金额后，如果该工具过去 28 个完整 UTC 日中“最大单日 close-to-close 收益”在固定 25 个流动目标中排名前三，是否值得在下一 UTC 周一 open 用 0.5x 计划金额入场、七天后退出，并在现实零售成本、实际 funding、4% 年化资本门和独立时间闸门下优于无条件周频 LONG、28 日累计动量和上一日收益排名？

这不是一般 momentum 的参数替换。原始外部研究声称 MAX 在控制累计 momentum、短期 reversal、流动性、波动和偏度后仍有正的下一周横截面关系；另一项日内高阶矩研究却发现正向极端收益对下一日回报为负。本题检验这种方向和幅度能否在当前流动永续、固定工具和一次性计划语义中成立。

大型公开输入复用上一题已校验的 Binance USD-M 公共缓存；每个阶段仍生成本题自己的 manifest 和结果身份：

`D:/projects/Codex/CodexHome/research-data/halpha/category-momentum-gated-one-shot-long/2026-07-22-v1/`

规则、候选、搜索、闸门和失效条件见 `preregistration.md`；来源见 `sources.md`；实际命令与失败见 `attempts.md`；结论与反证见 `result.md`；重演身份见 `validation.json`。本目录不修改产品代码、数据库、配置、凭据、L4、资金或真实账户状态。

从仓库根目录使用 checkpoint 记录的 Python 环境复现 development：

```powershell
python research/studies/strategy-candidate/2026/past-month-max-weekly-one-shot-long/study.py checkpoint
python research/studies/strategy-candidate/2026/past-month-max-weekly-one-shot-long/study.py fetch --stage development
python research/studies/strategy-candidate/2026/past-month-max-weekly-one-shot-long/study.py inspect --stage development
python research/studies/strategy-candidate/2026/past-month-max-weekly-one-shot-long/study.py analyze --stage development
python research/studies/strategy-candidate/2026/past-month-max-weekly-one-shot-long/study.py gate --stage development
```
