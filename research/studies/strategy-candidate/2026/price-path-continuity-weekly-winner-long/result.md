# 结果与决定

## 结论

`INSUFFICIENT_EVIDENCE`

固定 PPC14 + MOM14 双顶部三分位单目标周频 LONG 在 2024 development 有正的平均经济方向，但没有通过统计下界、半年一致性、相对简单基准、类别/目标广度和收益集中门。2025 evaluation 按顺序门保持未打开；没有生成产品 handoff，也没有修改核心交易代码、L4、资金或账户。

这不是“PPC 没有信息”。PPC 与 MOM14 的周截面 Spearman 中位数只有 -0.0238，说明它不是简单重写动量；主规则在 base/stress 扣 4% 全计划资本门后的日期队列周均仍为 +0.5997%/+0.5057%，base 相对普通 MOM14 均值差为 +0.2623%，gross 相对等权市场 LONG 均值差为 +0.4718%。但这些点估计不稳定、下界跨零，并集中于少数目标和 2024 下半年，不能称为可用策略或长期盈利证据。

## 实际规则、数据与样本

- checkpoint：`d1173deb1f62dca2e90a37a9031d0232c524e29263d0190ae87a652911cbabce`；产品基准 Git `0bdfeffa616260cebd2d2188ddc8deb9e85c77f4`；正式策略 `ONE_SHOT_DONCHIAN_ATR_BREAKOUT 1.0.1 / BTCUSDT-PERP`。
- 25 个冻结当前 Binance USD-M 永续目标；公开 1d OHLCV、settled funding 和官方 mark 数据。2024 有 51 个可排名周；2024-11-04 只有 19 个合格目标，按冻结未知输入规则全局 `NO_ACTION`。
- 信号截至周六完成日线，完整跳过周日，周一 open 入场；PPC14 和 PastRet14 同时位于顶部 `ceil(N/3)` 且 PastRet14 > 0；`0.25x LONG`，七天后 open 退出，同目标连续下一周因一整日 cooldown 跳过。
- 主规则原计划机会 109 个，cooldown 跳过 21 个，最终 88 笔、40 个入场周、24 个目标；missing funding/mark 排除均为 0。
- 每边 fee 6 bp；base/stress 再加 10/20 bp slippage；实际 funding，stress 放大正 funding 成本并缩小负 funding收益；4% 年化门按完整计划资本扣除。

## 主要证据与反证

| 指标 | 2024 development | 门判断 |
|---|---:|---|
| base 扣门日期周均 | +0.5997% | 正 |
| stress 扣门日期周均 | +0.5057% | 正 |
| stress 四周块 bootstrap 95% | [-0.9884%, +2.6665%] | **失败：下界跨零** |
| H1 / H2 base 扣门均值 | -0.6768% / +2.0107% | **失败：只在下半年为正** |
| base 相对 MOM14 均值差 | +0.2623% | 点估计正 |
| base 相对 MOM14 bootstrap 95% | [-0.4079%, +1.1145%] | **失败：增量下界跨零** |
| gross 相对等权市场 LONG 均值差 | +0.4718% | 点估计正 |
| gross 市场差 bootstrap 95% | [-0.4375%, +1.7110%] | **失败：下界跨零** |
| base 日期队列最大回撤 | -13.46% | 通过 |
| 最差单目标 base 路径回撤 | -8.56% | 通过 |

四个冻结邻域中，formation7、inverse-max-share 和 Directional Smoothness 的 stress 扣门均值为正，formation21 为负，因而邻域门本身通过；这说明结果不是只靠 PPC14 唯一公式。但广度反证明显：

- 六个类别中只有 Layer-1 和 Layer-2 为正；Layer-2 只有 XLM 四笔，不能视为独立类别广度。
- 至少两笔机会的目标只有 40% 为正，低于 50% 门。
- XLM 占全部正贡献 35.43%，HBAR 再占 28.32%；最大目标超过 25% 门，两个目标合计约 63.75%。
- H1 为负而 H2 很强；这与少数后期行情/目标驱动的更简单解释一致。

论文自身也预示了这项限制：显著结果主要是 continuous winner-minus-loser 和交互项，continuous winner 多头自身 CAPM alpha 接近零。Halpha 的结果表明，在不引入裸空和多腿组合的半自动约束下，PPC 可能提供筛选信息，但当前证据不足以把它升级为策略。

## 失败门、后续与未知

失败项：`stress_bootstrap_lower_positive`、`both_halves_base_after_hurdle_positive`、`base_increment_vs_mom14_bootstrap_lower_positive`、`gross_excess_vs_market_bootstrap_lower_positive`、`four_positive_categories`、`half_targets_positive`、`largest_positive_pnl_share_at_most_25pct`。

按 family stop rule，不查看 2025 精确规则输出，不改用事后更好的目标、类别、半年、tercile/quintile、形成期、gap、持有期、成本、funding、金额或 market-state filter。若未来冻结规则自然积累至少 26 个有效周并覆盖两个市场状态，可另开前向问题；在此之前，PPC 仅作为避免重复研究和后续机制参考保留。

未建模事实仍包括真实 order book、激活延迟、部分成交、账户 fee tier、保证金/清算/ADL、场所故障和幸存者 universe。正点估计不是 Alpha 证明，更不能支持长期盈利承诺。
