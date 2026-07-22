# 结果：高流动 USD-M 周级输家延续

## 结论

`DOES_NOT_SUPPORT`

固定六币、2021–2022 开发样本和预注册成本范围内，前周最弱币做空一周没有成为可供交易核心资格验证的策略。evaluation 与 confirmation 按顺序门保持未打开，产品交接包未生成，产品和真实账户状态没有变化。

## 主要证据

| 证据 | 结果 | 判定 |
|---|---:|---|
| 周计划 | 104 | 样本数量门通过 |
| favorable / base / stress 复合收益 | -15.04% / -19.38% / -29.00% | 绝对净收益门失败 |
| base 年化 / 日级最大回撤 | -10.24% / -41.82% | 资本与风险门失败 |
| 2021 / 2022 base | -35.74% / +25.46% | 跨年一致性失败 |
| 相对等权市场 gross selection mean | +0.434%/周 | 方向与外部研究一致 |
| selection 4 周 bootstrap 95% | [-0.138%, +1.114%] | 不能排除零 |
| 六币等权 short base | -50.50% | bottom-1 排名改善相对表现，但不能证明绝对 Alpha |
| 14 日 formation / bottom-2 base | -19.45% / -24.28% | 预注册诊断没有稳健支持 |

选币后的 gross short 价格腿复合 -21.46%。实际 funding 的算术贡献约 +10.70%，减轻但没有逆转亏损；在 favorable 成本下仍亏损 15.04%，因此结论不依赖 base 滑点是否略偏保守。

## 解释与反证

相对选择效应为正，是一个值得保留的机制线索：被选出的前周输家随后比六币等权市场更弱。但区间跨零，且单腿 short 同时暴露于整个 crypto 市场方向；2021 牛市显著亏损、2022 下跌阶段盈利。数据更支持“可能存在弱的横截面延续，同时被市场 beta、成本和 funding 淹没”，而不是“可长期盈利的单腿策略”。

以下事实反驳把本题包装成可用策略：

- favorable 成本仍为负，不能只通过降低成本假设救回；
- 分年符号相反，收益强依赖市场 regime；
- 相对效应的预注册 bootstrap 下界未大于零；
- base 回撤达到 -41.82%，远超 -15% 门槛；
- 正 PnL 贡献集中度略高于 50% 门槛，且 BNB/XRP 贡献显著为负；
- 固定当前幸存六币有幸存者偏差，不能外推全市场。

市场中性 `long winner / short loser` 可能隔离部分方向 beta，但它是两腿同步执行、不同资金占用与失效模型，不是本题失败后的可选参数，也不符合当前一次只固定单 instrument/direction 的最小闭环。若项目未来愿意接受两腿计划，应另题预注册并首先检验真实同步执行和双腿成本。

## 数据、重演与限制

- 数据：Binance USD-M 六币连续日线、settled funding、官方 8 小时 mark price；每币 1,654 根日线、4,962 条 funding。
- 外部缓存：`D:/projects/Codex/CodexHome/research-data/halpha/liquid-perp-weekly-loser-continuation/2026-07-22-v1/`，66 文件、7,669,925 bytes；`source_manifest.json` 保存逐文件 SHA-256 和重取参数。
- 稳定交易明细：`development_trades.csv` SHA-256 `5364f5d672da25e0a0c75f888d69d774d14c97bfbb649a9c05a4b5d8502a4ed0`。
- 复核：VectorBT 与独立手算最大差异 `6.94e-17`；重复 analyze/gate 得到相同交易 CSV。
- 未覆盖：L1/L2、真实 spread/队列/部分成交、账户 fee tier、保证金/清算/ADL、下架、税务、动态 point-in-time 全市场和真实人工计划延迟。遗漏这些通常不会把本题的显著负收益转成可靠正收益。

本结论只否定这一个固定表达，不否定所有 crypto momentum、所有多腿横截面策略或其他频率。盈利回测即使出现也不会是 Alpha 证明；本题更没有达到那一步。
