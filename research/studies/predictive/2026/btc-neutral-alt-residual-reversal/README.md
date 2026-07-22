# 小时级 BTC-neutral 极端残差的均值回复

## 状态与父问题

- 主要研究类型：`PREDICTIVE`。
- 稳定产品基准：Git `0bdfeffa616260cebd2d2188ddc8deb9e85c77f4`；正式策略 `ONE_SHOT_DONCHIAN_ATR_BREAKOUT 1.0.1 / BTCUSDT-PERP` 只作固定背景。
- 父问题：`../btc-shock-beta-gap-predictability/`。父问题在下一 open 后 15m 只有 +2.08 bp、未击败简单基准且低于成本门，结论 `DOES_NOT_SUPPORT`。
- 本题在任何小时级残差结果计算前固定。复用父问题已校验的 2023-10 至 2024-12 官方 5m 缓存；这批价格历史已经暴露，不能称为未见数据，但本题的 1h 去 beta 极端残差输出尚未查看。

本题只读公开历史与 Git 内研究材料，不读产品数据/数据库/凭据/运行配置，不启动产品运行时，不调用交易所变更端点。结果不授权策略、资金或真实交易。

## 为什么是独立问题

这不是父问题的窗口优化。父问题问“BTC 先冲击、山寨币同 bar 欠反应是否随后跟随”，属于短时信息扩散/延续；本题问“山寨币相对 BTC beta 已经走得过远后是否在 12h 内回归”，属于慢速 idiosyncratic overshoot/流动性供给。

它也不同于既有 `ethusdt-2h-extreme-reversal`：旧题对单一 ETH 的绝对 2h 收益做反转，32 bp 成本已否定；本题固定 15 个成熟永续，先去 BTC beta、按自身历史残差波动标准化、从下一 1h open 观察 BTC-neutral 目标，并把同小时多个币先聚合。

备选包括 cointegration 选对、PCA 多因子 residual、copula、动态 OU 半衰期和本题单 BTC factor。前四项理论更完整，但会引入配对/因子数/窗口/分布/半衰期选择，且近期 crypto 复现显示成本高度敏感或净收益为负。对个人项目，先用单一 BTC factor 和固定阈值证伪更简单的解释；若连它都没有足够毛幅度，不建设复杂 stat-arb。

## 先验与最强允许主张

经典 pairs/stat-arb 把共同因子剥离后的 residual 当作潜在均值回复对象；crypto 研究同时表明高频结果对参数、费用与执行窗口敏感，近期 Binance 永续 copula 策略在 0.08% round-trip 后为负。因此本题必须同时看到时间上可行动的反转、简单基准增量和对双腿成本有意义的毛幅度。

若通过，本题最多支持“固定成熟币、Binance USD-M、固定 1h 定义下的极端 BTC-neutral residual 含有值得继续进行策略候选研究的均值回复信息”。不得称为 cointegration、无风险套利、已实现 Alpha 或长期盈利。

## 固定数据、样本与复用身份

- `BTCUSDT` anchor；山寨币与父问题相同：ETH、BNB、SOL、XRP、DOGE、ADA、LINK、AVAX、LTC、BCH、TRX、DOT、NEAR、SUI、AAVE 的 USDT perpetual。
- Binance 官方月度 5m Kline 先按 UTC 自然小时聚合：open=首个 5m open、close=最后 5m close、quote volume/trade count 求和；每小时必须恰有 12 根。
- development：2024-01-01 至 2025-01-01；2023-10-01 起只用于 90 日暖启动。
- evaluation：2025；confirmation：2026H1。只有本题前一阶段通过才允许借父问题的已校验下载器把新月份写入同一 Git 外共享 cache；各阶段在本题保留自己的 manifest。
- 共享 cache：`D:/projects/Codex/CodexHome/research-data/halpha/btc-shock-beta-gap-predictability/raw/`。不复制大型 ZIP、不建数据库；开发复用 manifest 的 SHA-256 固定在 checkpoint。

## 事前主定义

对山寨币 `i`、已收盘 UTC 小时 `t`：

1. `beta_i,t`：截至 `t-1` 的过去 30 日（720 小时）1h return rolling beta。
2. 形成残差：过去 6 小时 close-to-close `alt_return_6h - beta_i,t * btc_return_6h`。
3. 标准化：形成残差除以截至 `t-1` 的过去 30 日 6h 残差滚动标准差；`abs(z) >= 2.5` 才触发。
4. 同一币触发后 12 小时内不再选新事件，避免重叠目标被当成新证据。
5. 目标：从 `t+1` 的 open 到 `t+12` 的 close 的 `alt_return - beta_i,t * btc_return`。
6. 主响应：`-sign(formation_residual) * future_residual`。同一小时先对所有触发币等权平均，再按 UTC ISO 周 cluster-robust 推断；每个币的探索结果做 BY-FDR。

主配置唯一。固定的一项一变反证共 9 项：beta 7/90 日、形成 1/12h、阈值 z=2/3、目标 4/24h、额外等待 1h。所有结果完整保留，不按最佳配置选择。

简单基准在同一资产事件上使用山寨币原始 6h 收益方向做反转；若去 beta 信号不能击败它，不把普通单币 reversal 重命名为 BTC-neutral Alpha。另有零预测基准。

## 成本、统计门与停止条件

每个 alt 事件隐含 alt 腿和 `abs(beta)` BTC 对冲腿。以既有每腿 round-trip `12/32/52 bp` 代理，事件的 paired cost floor 是 `per_leg * (1 + abs(beta))`；机器结果报告事件平均 favorable/base/stress floor。它仍不包含实时 spread/depth、funding、保证金、清算、不同步成交或税。

development 只有全部满足才启封 2025：

1. 数据质量 `PASS`；至少 200 个独立事件小时、500 个资产事件、两个半年各至少 75 个事件小时；
2. 主平均响应 > 0，ISO 周 cluster 95% CI 下界 > 0；H1/H2 均 > 0；
3. 主平均响应高于同事件 raw-own-return reversal；正/负形成残差不允许一侧显著反向；
4. 主平均响应至少达到**事件平均 favorable paired cost floor**。

只达到 favorable floor 才值得用封存期继续验证；要成为以后策略候选，还必须在独立阶段达到 base paired cost、建模 funding/双腿成交/保证金/强平并转入 NautilusTrader 事件语义验证。若 development 未过，2025–2026 不下载；不改 z、窗口、币种或方向重开近邻问题。

结论只使用四类枚举。统计正但低于 favorable 双腿成本、只在单半年/单方向、额外延迟消失、只由单币驱动或不优于 raw reversal，都支持 `DOES_NOT_SUPPORT` 本项目机会，而不是盈利证据。

## 实际结果

development 对父问题的 240 个 ZIP 逐文件重新核验 SHA-256 后，聚合得到每标的 10,992 个完整 UTC 小时。主配置共有 919 个事件小时、1,249 个资产事件，平均每小时 1.36 个触发币。

| 主结果 | 数值 |
|---|---:|
| 平均 BTC-neutral reversal response | **-10.61 bp** |
| 中位数 / 胜率 | +25.78 bp / 53.86% |
| 95% ISO 周 cluster CI | [-34.80, +13.58] bp |
| 同事件 raw-return reversal | -2.97 bp |
| paired favorable/base/stress 成本代理 | 24.75 / 66.00 / 107.25 bp |

中位数为正但均值为负不是稳定小优势，而是典型的负偏尾部：事件小时 response 的 1%/5% 分位为 -1,437.55/-694.25 bp，最差为 -2,240.44 bp；少数 residual 继续扩张完全吞没多数小回归。最差事件集中在 2024-03 和 2024-11 至 12 月的山寨币单边行情，包括 XRP、TRX、NEAR、DOGE 等，并非单个坏价格即可解释。

| 反证 | 平均 bp | 95% CI bp |
|---|---:|---|
| beta 7d / 90d | -10.01 / -5.65 | 均跨零 |
| formation 1h / 12h | -10.61 / -17.60 | 均不支持 |
| z=2 / z=3 | -16.62 / -8.82 | z=2 CI [-31.66,-1.58]，显著反向 |
| target 4h / 24h | +5.66 / +3.86 | 均跨零且低于 favorable cost |
| 额外等待 1h | -12.01 | [-36.05,+12.04] |

H1 为 +2.51 bp、H2 为 -21.41 bp。异质性显示：正 formation residual（相对赢家）做 reversal 得到 -33.74 bp、CI [-66.21,-1.28]，即它们反而继续跑赢；负 residual（相对输家）做 reversal 为 +33.61 bp、CI [+1.78,+65.43]。这是事前报告的分组，不是事前单边策略；只做输家属于结果驱动改规则，而且 +33.61 bp 仍低于约 66 bp 的 base 双腿成本，故不重开 sign-only 近邻问题。

15 个币在 BY-FDR 后无一显著；NEAR 的 nominal +85.48 bp 也不通过多重比较。主结果不优于更简单 raw reversal，所有开发门中只有样本量通过。

## 结论

`DOES_NOT_SUPPORT`

固定的小时级 BTC-neutral 极端 residual 并不表现为可依赖的双向均值回复；相对赢家的继续扩张、跨阶段不稳和巨大左尾使平均预测为负。即使选取短 4h 目标，毛响应也低于有利双腿成本。2025–2026 不下载、不查看。

这不证明所有 cointegration/PCA/carry-neutral 策略无效，但足以否定“单 BTC beta + 固定 z-score + 无状态双向反转”作为本项目个人小资金候选。进一步复杂 stat-arb 只有在出现独立的结构关系或能事前解释的状态变量时才值得开题，不能用本结果筛 sign、币或止损。

完整数值见 `development.json`，复用身份见 `source_reuse_manifest_development.json`，极端事件审计与复算见 `attempts.md`。研究不改变产品策略、L4、资金或真实账户状态。
