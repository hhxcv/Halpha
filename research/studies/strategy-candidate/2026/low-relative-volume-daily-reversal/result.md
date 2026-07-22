# 结果摘要

## 结论

`DOES_NOT_SUPPORT`

固定问题和六标的开发段有足够事件，但不支持把“低相对成交量 + 日级极端收益反转”保留为 Halpha 半自动一次性计划的策略候选。

| 指标 | 主配置 development 2021–2022 |
|---|---:|
| 一次性计划 | 152（90 long / 62 short） |
| funding 事件/收益和 | 399 / +2.06% 初始名义 |
| base / stress 组合复合收益 | -23.61% / -35.50% |
| base / stress 最大回撤 | -57.32% / -60.92% |
| base 每笔均值 / 中位数 / 胜率 | +0.73% / +0.79% / 54.61% |
| base 日均收益 | -0.0055% |
| base 30 日块 bootstrap 95% | [-0.1970%, +0.1734%] |
| 2021 / 2022 base | +17.09% / -34.76% |
| base 为正标的 | 5/6 |
| 相对无 volume filter 的 base 日均增量 | -0.1435pp |

逐笔均值为正而组合亏损并不矛盾：极端事件跨币集中在同一市场日期，组合在活跃日等权，正收益样本的数量权重不能消除共同尾部。对于可能并行存在的多个半自动计划，共同日期聚集和 -57% 回撤是直接风险；不能把五个开发期正标的事后拆成五个“已达门槛策略”。

无 volume filter 的简单反转 base 总收益 +18.76%，但 stress -31.21%、最大回撤 -68.61%、bootstrap 下界为负；它只是反对“低 volume 提供增量”的更简单解释，不是另一个通过候选。60 日 volume sensitivity 和 momentum 也没有改变结论。

evaluation 与 confirmation 未启封。改变判断需要新的、事前解释不同的状态变量或执行优势，再建立新问题和未见证据；不得在本已暴露开发段搜索 z、币、方向、持有期或止损。

## 留存与复现

- 规则与时间锚：`checkpoint.json`。
- 来源身份：`source_manifest.json`；Git 外 48 个官方 REST 原始页、4,319,771 bytes。
- 数据质量：`data_quality.json`；六币各 1,703 日线、5,109 funding、日线缺口 0。
- 完整主配置逐笔：`development_trades.csv`，SHA-256 `42fb9245082e095575c10ecca479b3a49be6268ac6677d4a60968e91398a0dc9`。
- 全配置、门、结论：`development.json`、`development_gate.json`、`results.json`。
- 可重演代码与实际命令：`study.py`、`attempts.md`。

研究产物当前均为工作树未跟踪文件，已留存在本工作树和固定外部缓存，但尚不是 Git 历史；未提交、未推送、未合并。

