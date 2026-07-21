# BTC 市场关联与相对强弱研究结果

## 结论

`SUPPORTS_WITHIN_SCOPE`

在固定的当前 Binance Spot USDT 原生加密对象快照中，截至 `2026-07-20T23:59:59.999Z`，存在数量可观、效应幅度明确且跨两个非重叠窗口同号的 BTC 强关联对象。410 个合格对象中 402 个达到样本门槛，385 个对象的单因子 BTC beta 在 HAC 推断并经 Benjamini–Yekutieli 全族 FDR 校正后仍显著，238 个同时满足预先固定的强关联与跨窗口同号规则。

这个结论只支持“BTC 是当前大量币种日收益的重要共同波动基准，并且本研究可以持续、可审计地监测这种关系”。它不支持因果、领先关系、未来收益预测、交易策略、Alpha 或长期盈利主张。

## 问题与方法来源

问题是：当前仍在 Binance Spot 交易的 USDT 原生加密对象中，哪些对象在最近最多 365 个共同日收益上与 BTC 存在统计显著且有实际幅度的共同波动；其 BTC beta、波动倍数、7/30/90 日相对强弱和跨窗口稳定性如何？

本研究没有发明新的相关模型。方法借鉴成熟的市场模型、Pearson/Spearman 相关、滚动窗口、稳健协方差和多重检验控制：

- Liu、Tsyvinski、Wu 的同行评审研究支持加密资产存在共同市场风险结构，并为 365 日特征窗口提供可比背景；本研究的 BTC 单基准不等同于论文的市值加权加密市场因子。
- Koutmos 的同行评审研究表明 BTC 在大型加密资产的收益和波动连通性中居核心、关系随时间变化；本研究只核对方向，不把相关或 beta 冒充 VAR 冲击传导复现。
- 每个对象报告 Pearson、Spearman 和 `r_asset = alpha + beta × r_btc + error`；beta 推断使用 statsmodels 0.14.6 的 HAC/Newey–West Bartlett 协方差、7 lags、小样本修正。
- 数百对象的双侧 p 值统一使用 Benjamini–Yekutieli `q <= 0.05`，避免把逐项 p 值当成全市场发现；强关联还要求 `abs(Pearson) >= 0.50`、Pearson/Spearman 同号、最近 180 与此前非重叠 180 日 Pearson 同号。
- 相对强弱为同一共同日期上的对象累计对数收益减 BTC 累计对数收益，再还原为 7/30/90 日相对收益；它是截止时点状态，不是预测信号。

来源、采用理由和与本研究的差异详见 `sources.md`；启封前规则和结果揭示后的 universe 语义修订详见 `checkpoint.md`。

## 数据

- 产品与策略稳定基准：Git `e2a4cf5372d5ce9984d86edd08c40b72e62026a4`；正式策略仅记录为 `ONE_SHOT_DONCHIAN_ATR_BREAKOUT` `1.0.1`，不参与本问题计算，也未被修改。
- Universe：`research/market-universe/universe.csv`，快照 `2026-07-21T06:42:30Z`。筛选 Binance Spot、当前交易、USDT quote、原生加密/基准对象；BTC 只作参考。结果揭示后的语义审查排除了 36 个被上游默认 taxonomy 错标为原生加密的 bStock，并显式保留 DGB 例外。最终 411 个含 BTC，410 个待分析对象。
- 主价格：Binance 官方公开 `data-api.binance.vision/api/v3/klines` 的 UTC `1d` OHLCV，只接受已闭合 bar、正数价格、唯一 open time，不前向填充，也不跨缺失日期拼接收益。
- 独立核对：Coin Metrics Community `PriceUSD` 日收盘。免费覆盖足以核对 BTC/ETH/DOGE；SOL/SUI 返回 403，明确记为不可用，而不是换用不一致短样本。
- Git 外缓存：`D:/projects/Codex/CodexHome/research-data/halpha/btc-market-relationship-monitor/`。逐 symbol 规范化 CSV.gz 可增量复用；每次在线刷新另存不可覆盖的 source manifest 和源响应快照。
- 最终在线 source manifest：`snapshots/2026-07-21T103633Z/source-manifest.json`，SHA-256 `0c6ca774cf4fb3d300ebebf1b15df50a8790413cdb1fbc4a69429895cbc4eb2d`。

## 主要结果

全体 402 个已分析对象中，400 个 Pearson 为正、2 个为负；385 个显著对象全部为正，没有显著负关联。Pearson 均值 0.517、中位数 0.539、四分位区间 0.428–0.633。BTC beta 中位数 1.231，波动倍数中位数 2.337。说明这个当前样本中共同波动广泛，但典型山寨对象的日波动仍明显高于 BTC。

| 对象 | Pearson | Spearman | BTC beta | R² | 波动倍数 | 7 日相对 | 30 日相对 | 90 日相对 | 最近/此前 180 日相关 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| ETHUSDT | 0.875 | 0.871 | 1.338 | 0.766 | 1.528 | +2.4% | +7.8% | -4.3% | 0.922 / 0.847 |
| SOLUSDT | 0.840 | 0.851 | 1.393 | 0.705 | 1.659 | -0.9% | +4.8% | +5.9% | 0.895 / 0.831 |
| SUIUSDT | 0.793 | 0.811 | 1.609 | 0.629 | 2.029 | +1.2% | +5.5% | -5.8% | 0.808 / 0.830 |
| DOGEUSDT | 0.763 | 0.789 | 1.341 | 0.582 | 1.758 | -4.2% | -15.0% | -11.3% | 0.814 / 0.798 |

WBTCUSDT 的 Pearson 为 0.9997，但这是 wrapped BTC 的机械暴露，不能当作独立市场规律发现。完整 385 个显著对象和 238 个强关联对象分别保存在 `output/significant-associations.csv` 与 `output/strong-associations.csv`，没有只保留排名靠前的对象。

## 独立与外部核对

- ETH：Coin Metrics Pearson 0.8768 对 Binance 0.8755，差 0.0013；beta 1.3466 对 1.3378，差 0.0088，方向一致。
- DOGE：Coin Metrics Pearson 0.7615 对 Binance 0.7629，差 0.0014；beta 1.3556 对 1.3412，差 0.0144，方向一致。
- 结果与既有研究中“加密资产存在广泛共同市场成分、BTC 居核心且关系时变”的方向一致，但模型、价格源、样本和 universe 不同，所以不是对 Liu 等人或 Koutmos 数值结果的直接复现。

## 反证与降级证据

- 17 个已分析对象未通过 BY-FDR，包括 C98、PARTI、ZAMA、GPS、ROBO、ENSO、TNSR、RESOLV、ALPINE、KAT、USDE、JST、OPN、SENT、ESP、BFUSD、XUSD；不能表述为“所有币都显著跟随 BTC”。
- AERO、AIGENSYN、CHIP、GENIUS、GRAM、MEGA、OPG、RE 共 8 个对象只有 3–90 个共同收益，按预先门槛列为样本不足，而不是补齐、放宽或删除。
- XUSD 与 BFUSD 是仅有的负 Pearson 对象，但均不显著。当前 upstream taxonomy 仍把若干稳定型对象默认成原生加密，说明 universe 语义还不是官方完备分类。
- ETH、SOL、SUI、DOGE 的 7/30/90 日相对强弱并不同号，直接反驳“高 BTC 相关自然意味着持续跑赢 BTC”的简单解释。
- 当前名单没有历史重建，存在幸存者偏差；单一 Binance 日收盘不能识别日内领先滞后、跨场所价格发现、操纵、流动性或执行质量。

## 可重演与持续更新

```powershell
# 在线刷新：更新公开数据、产物和不可覆盖 source manifest
research/.venv/Scripts/python.exe research/btc-market-relationship-monitor/monitor.py refresh

# 固定缓存离线重算
research/.venv/Scripts/python.exe research/btc-market-relationship-monitor/monitor.py refresh --offline

# 独立结果/数据质量检查
research/.venv/Scripts/python.exe research/btc-market-relationship-monitor/validate_results.py

# 启动独立本地页面；立即显示持久快照，后台刷新公开数据
research/.venv/Scripts/python.exe research/btc-market-relationship-monitor/monitor.py serve
```

在线与离线运行的统计内容身份 SHA-256 均为 `581d0b3361cdfb4d404b24cd49aef04d2b69da258c6f46930a0133134e9055fb`。完整 CSV 的哈希刻意不同，因为 `fetch_status` 保留本次是在线抓取还是离线缓存重演；`output/validation.json` 同时记录内容身份、产物哈希、独立重算和数据质量检查。

## 仍未知

本研究没有回答这些关系是否可交易、是否领先、在成本后能否预测收益、在退市对象和历史 point-in-time universe 中是否成立，也没有回答 L2、订单流、funding、OI、清算、新闻或链上机制。若下一步目标变为预测或策略，必须另立问题、定义时间因果和 out-of-sample 验证，不能从本结论直接升级。
