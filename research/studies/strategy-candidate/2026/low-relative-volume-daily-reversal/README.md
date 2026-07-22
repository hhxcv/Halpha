# 低相对成交量条件下的日级极端收益反转

## 状态、问题与边界

- 研究类型：`STRATEGY_CANDIDATE`。
- 研究身份：`RESEARCH_LOW_RELATIVE_VOLUME_DAILY_REVERSAL_30D_1P5Z_V1`。
- 稳定产品基准：`0bdfeffa616260cebd2d2188ddc8deb9e85c77f4`。
- 固定正式策略：`ONE_SHOT_DONCHIAN_ATR_BREAKOUT` `1.0.1`、`BTCUSDT-PERP`；仅作当前产品背景，不把研究代理称为正式策略历史绩效。
- 决策用途：判断一个与突破趋势不同、适合个人小资金和一次性策略计划的流动性供给假设，是否值得保留为以后由项目所有者选择的候选。
- 写入范围仅为 `research/**`；不读取产品业务数据、数据库、凭据或运行配置，不启动产品运行时，不调用交易所变更端点，不产生真实交易。

固定问题：对一个已激活、方向和金额已固定的单标的计划，如果前一 UTC 日收益绝对值达到其过去 30 日波动的 1.5 倍，且当日成交额低于自身过去 30 日趋势，按相反方向在下一 UTC 日开盘进入并持有 24 小时，能否在 Binance USDⓈ-M 实际 funding、双边 taker fee、spread/slippage 代理后，于顺序隔离的开发、评价和确认时段保持正收益，并优于不使用成交量条件的简单反转？

否定条件：开发期样本足够时，若基础或压力成本后的组合复合收益非正、30 日块 bootstrap 日均收益下界不大于零、少于 4/6 标的为正，或成交量条件没有改善简单反转，则停止并保留后续时段。盈利回测不证明未来 Alpha；`SUPPORTS_WITHIN_SCOPE` 也只表示固定规则在这些公开数据和成本代理内通过研究门槛。

## 半自动计划适配

候选不是持续自动轮动组合。每个计划固定一个 instrument、LONG 或 SHORT、金额和有效期；策略只在与计划方向一致的信号出现时产生零或一个提议：

- 决策时点：UTC 日线完全收盘后；下一可行动时间为下一 UTC 日开盘。
- LONG：前一日收益 z-score `<= -1.5` 且标准化相对成交量 `<= 0`。
- SHORT：前一日收益 z-score `>= +1.5` 且标准化相对成交量 `<= 0`。
- 市场质量：信号日前 30 日中位 quote volume 至少 500 万 USDT；未知、缺口或无完整 warmup 时不新增风险。
- 仓位：不超过计划固定金额，1x 初始名义，不加仓。
- 退出/保护：进入后 24 小时按下一 UTC 日开盘退出；不自动再入场；研究没有另加事后优化的止损或止盈。

这与当前一次激活只完成一个交易周期、完全平仓后完成且不自动重入的语义一致。它尚不是产品策略；研究通过后仍需框架无关交接和 NautilusTrader 执行资格验证。

## 候选、查重与选择

| 候选 | 未解决差异 | 现实与研究成本 | 决定 |
|---|---|---|---|
| 低相对成交量 + 日级极端反转 | 流动性供给/暂时价格压力；与突破趋势和已否定的无条件 ETH 2h 反转不同 | 单腿、24h、基本公开数据；必须证明成熟标的也有净收益 | **选中** |
| 波动压缩后的突破 | 状态依赖的波动扩张 | 与正式 Donchian 家族近邻，新增决策价值较低 | 淘汰 |
| perpetual premium 极端后的均值回复 | funding 锚定 basis | 需要 spot/index 与精确 basis；与既有 carry 家族重叠且单腿价格风险大 | 暂缓 |
| SOL volume-profile/tape-speed 反转 | 更细粒度的日内流动性结构 | 2026 新工作论文、自由度多、5m volume-at-price 代理和执行敏感度较高 | 暂缓 |
| 已支持 TRX 波动目标多头的计划化改写 | 最快形成风险管理候选 | 是 beta 风险管理而非新 Alpha，且 spot/月度持续配置改成 perpetual 单次周期会改变语义 | 另题，不在本题混合 |

本地 BTC 冲击、BTC-neutral residual reversal、ETH 2h extreme reversal、funding 单腿和多项趋势研究均已扫描。本题不继续它们的币种、阈值或近邻窗口；它检验外部文献给出的“低成交活动时流动性供给收益更强”这一不同状态变量。原论文使用动态大横截面和多场所 USD/USDT 数据，本题是单标的计划可执行的时间序列改写，不声称直接复现原论文。

## 固定对象、规则和试验数

固定 Binance USDⓈ-M perpetual：`ALGOUSDT`、`COMPUSDT`、`THETAUSDT`、`VETUSDT`、`XTZUSDT`、`ZECUSDT`。选择在查看本题历史结果前完成：均有五年以上合约年龄；当前市场名单为 A1–A3 活动层；没有使用当前 24h 收益挑选。它们不是“安全”或永久高流动结论，历史市场质量由 30 日 quote-volume 门和压力成本另行反证。

主配置只有一个：

1. `r_t = close_t / close_(t-1) - 1`。
2. `return_z_t = r_t / std(r_(t-30:t-1))`，波动基线不含当日收益。
3. `volume_shock_t = [log(qv_t) - log(mean(qv_(t-30:t-1)))] / std(log(qv_(t-30:t-1)))`。
4. `return_z <= -1.5` 做多，`>= +1.5` 做空；仅 `volume_shock <= 0` 且过去 30 日中位 quote volume `>= 5,000,000` 时有效。
5. 信号在 t 日收盘后可知；t+1 日 open 进入，t+2 日 open 退出。边界 funding 不假设可获得，只计严格位于进入和退出时间之间的实际结算。

诊断而非选择：同一极端收益但不加 volume filter 的简单反转、同一事件做 momentum、论文报告的 60 日 volume window。总共查看一个主配置、两个简单解释和一个事前文献敏感性；不从中选择赢家，不搜索 z 阈值、持有期、币、方向、止损或成本。

成本按初始计划名义：

- favorable：每边 6 bp taker fee、0 slippage，完整 round trip 约 12 bp；
- base：每边 6 bp fee + 10 bp spread/slippage，约 32 bp；
- stress：每边 6 bp fee + 20 bp spread/slippage，约 52 bp；
- funding：按持仓方向和实际 settled funding 单列；不把 funding 当手续费。

## 数据暴露与顺序门

数据为 Binance 官方 USDⓈ-M 1d Kline 和 funding history，只读公共 REST snapshot；原始页在 Git 外，目录内保存 URL、访问时间、字节数和 SHA-256。暖启动从 2020-11-01 开始；研究 cutoff 为 2025-07-01，刻意不使用本地 BTC 关系监控已经查看的 2025-07-21 以后日线。

| 阶段 | 进入时间 | 本题开始前暴露 | 启封规则 |
|---|---|---|---|
| development | 2021-01-01 至 2023-01-01 | 未作为本地策略/预测输入查看；公开论文只到 2022-03 且不是本题对象/实现 | checkpoint 与代码固定后运行 |
| evaluation | 2023-01-01 至 2025-01-01 | 未查看本题结果 | 仅 development 全部门通过 |
| confirmation | 2025-01-01 至 2025-07-01 | 未进入现有 2025-07-21 起的关系监控 | 仅 evaluation 全部门通过 |

开发门：数据质量通过；至少 120 笔；base/stress 组合复合收益均正；30 日 circular block bootstrap 的 base 日均收益 95% 下界大于零；至少 4/6 标的 base 复合收益为正；主配置 base 日均收益高于无 volume filter 的反转。失败默认不启封 evaluation。

评价门：至少 120 笔；base/stress 复合收益均正；2023、2024 base 均正；bootstrap 下界大于零；至少 4/6 标的为正。失败默认不启封 confirmation。

`SUPPORTS_WITHIN_SCOPE` 还要求 confirmation 至少 30 笔、base/stress 均正、至少 3/6 标的为正、最大回撤不深于 -15%，且 confirmation base 日均收益为正。评价或确认样本足够但 base/stress 非正为 `DOES_NOT_SUPPORT`；经济结果为正但稳健/样本门不足为 `INSUFFICIENT_EVIDENCE`；输入或实现无法可靠判断才是 `CANNOT_DETERMINE`。

## 环境、数据和命令

- Python 3.13.14、VectorBT 1.1.0、pandas 3.0.3、NumPy 2.4.6、SciPy 1.18.0。
- Git 外缓存：`D:/projects/Codex/CodexHome/research-data/halpha/low-relative-volume-daily-reversal/2026-07-22-v1/`。
- VectorBT `Portfolio.from_signals` 将每笔一次性计划作为独立两行/一列组合，验证 long/short、fee 和 slippage；实际 funding 在固定初始名义上单列合并。

预定命令：

```powershell
research\.venv\Scripts\python.exe research/studies/strategy-candidate/2026/low-relative-volume-daily-reversal/study.py checkpoint
research\.venv\Scripts\python.exe research/studies/strategy-candidate/2026/low-relative-volume-daily-reversal/study.py fetch
research\.venv\Scripts\python.exe research/studies/strategy-candidate/2026/low-relative-volume-daily-reversal/study.py inspect
research\.venv\Scripts\python.exe research/studies/strategy-candidate/2026/low-relative-volume-daily-reversal/study.py analyze --stage development
research\.venv\Scripts\python.exe research/studies/strategy-candidate/2026/low-relative-volume-daily-reversal/study.py gate --stage development
```

后续命令只有在顺序门授权后执行。实际尝试、失败与复跑见 `attempts.md`；结论在运行后追加。

## 预先声明的限制

- 1d open 是下一可行动价格代理，不是可保证成交价；没有历史 L1/L2、队列、部分成交、账户 VIP、保证金、ADL、清算或税务。
- 30 日中位 quote volume 只排除明显低活动期，不能证明任意订单规模的容量；个人实际金额未知。
- 原论文研究的是横截面流动性供给，本题是单标的时间序列适配；若失败，不能否定原论文，若成功也不能把论文因果解释直接移植过来。
- 固定六币是当前仍交易的长期合约，存在幸存者偏差；研究不推广到下架币、全市场或未来上市对象。
- 24 小时退出是保护和闭环，不保证止损；若未来产品资格验证要求场内保护单，必须作为新策略版本重新研究，不能事后加到本结果。

## 实际结果与结论

结论：`DOES_NOT_SUPPORT`。

开发段共有 152 笔独立一次性计划（90 long、62 short），399 次持仓内 funding 结算。主配置在 base/stress 成本后的等权活跃计划组合复合收益为 **-23.61% / -35.50%**，最大回撤 **-57.32% / -60.92%**；base 日均收益为 -0.0055%，30 日 circular block bootstrap 95% 区间为 **[-0.1970%, +0.1734%]**。2021 base 为 +17.09%，2022 转为 -34.76%，表明结果不具备基本分期稳定性。

最强支持是每笔 base 中位数 +0.79%、胜率 54.61%，且 ALGO、COMP、THETA、VET、ZEC 五个标的各自 base 复合结果为正。它没有改变门结论：正收益信号高度聚集在同一市场日期，等权活跃计划组合仍亏损并出现深回撤；按开发期盈利币事后挑选会把一次六标的搜索伪装成多个独立策略。

最强反证是低 volume 条件没有提供论文机制预期的增量：主配置 base 日均收益比相同极端收益、不加 volume filter 的简单反转低 **0.1435 个百分点**。无条件反转的 base 组合虽为 +18.76%，压力成本转为 -31.21%、最大回撤 -68.61%、bootstrap 仍跨零，不能作为替代候选。60 日文献敏感性 base/stress 也为 -15.58%/-32.16%；同事件 momentum base 为 -52.30%。

因此开发门的 base、stress、bootstrap 下界和 volume 增量四项失败，2023–2024 evaluation 与 2025H1 confirmation 均未运行、仍保持封存。不交付 `handoff.md`，不形成可供交易核心资格验证的候选，也不修改产品策略、代码、资金或账户。

机器证据为 `development.json`、`development_trades.csv`、`development_gate.json` 和 `results.json`。两次从固定外部缓存重跑得到相同的 152 笔、base 总收益、bootstrap 下界和逐笔 CSV SHA-256 `42fb9245082e095575c10ecca479b3a49be6268ac6677d4a60968e91398a0dc9`；时间戳字段使整个 JSON 文件 hash 不设计为跨运行相同。外部缓存共 48 个原始 REST 页、4,319,771 bytes；六币各 1,703 根连续日线和 5,109 条 funding，均由 manifest 校验。
