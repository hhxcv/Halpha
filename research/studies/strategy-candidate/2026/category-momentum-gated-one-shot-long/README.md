# 类别动量门控单腿 one-shot LONG 研究

状态：已完成；结论 `DOES_NOT_SUPPORT`。development 门失败，evaluation/confirmation 未打开，未生成产品 handoff。

固定问题：当用户已在 Halpha 半自动 one-shot 计划中固定一个 Binance USD-M 工具、`LONG` 方向和金额后，若该工具所属类别（排除目标自身）的 7 日共同收益为正且位于七个固定类别前二，下一日以 0.5x 入场并持有七天，能否在零售级费用、spread/slippage、实际 funding、4% 年化资本门和顺序留出后，产生正的平均单次计划净收益，并优于自身 7 日动量及无条件定期 long？

这不是论文原策略的复现。原研究选择赢家/输家类别并持有多腿；本题刻意固定工具且只做一腿，用来判断类别效应是否能适配当前产品语义。当前分类快照、已存活对象和较少类别会产生幸存者与分类历史限制，不能用正回测掩盖。

规则、候选、否定条件、阶段门和未覆盖事实见 `preregistration.md`；来源见 `sources.md`；实际命令和失败见 `attempts.md`；结论与反证见 `result.md`；复算身份见 `validation.json`。大型公开输入放在 Git 外：

`D:/projects/Codex/CodexHome/research-data/halpha/category-momentum-gated-one-shot-long/2026-07-22-v1/`

本目录只写研究证据，不修改或动态依赖产品代码、数据库、凭据、运行配置或交易端点。

从仓库根目录复现 development：

```powershell
research/.venv/Scripts/python.exe research/studies/strategy-candidate/2026/category-momentum-gated-one-shot-long/study.py checkpoint
research/.venv/Scripts/python.exe research/studies/strategy-candidate/2026/category-momentum-gated-one-shot-long/study.py fetch --stage development
research/.venv/Scripts/python.exe research/studies/strategy-candidate/2026/category-momentum-gated-one-shot-long/study.py inspect --stage development
research/.venv/Scripts/python.exe research/studies/strategy-candidate/2026/category-momentum-gated-one-shot-long/study.py analyze --stage development
research/.venv/Scripts/python.exe research/studies/strategy-candidate/2026/category-momentum-gated-one-shot-long/study.py gate --stage development
```
