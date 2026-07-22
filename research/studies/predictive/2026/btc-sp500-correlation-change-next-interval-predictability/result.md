# 结果：BTC–S&P 500 相关性变化未通过开发门

## 结论

`DOES_NOT_SUPPORT`

在完全晚于来源论文发表的 `2022-08-01` 至 `2023-10-31` 开发期，冻结的
BTC–S&P 500 DCC 相关性变化没有复现“相关性下降后 BTC 次期上涨”的关系，
也没有形成可承受个人零售成本的单腿策略映射。评估期、确认期和策略转换均已
封存；产品影响为 `NONE`。

## 对问题的回答

- 源近回归的 `delta_rho` 系数为 `+0.032875`，负向单侧 HAC
  `p=0.559472`；控制后系数为 `+0.089889`，`p=0.650272`。两个主系数均与
  预注册负向机制相反，而不是仅仅“显著性不足”。
- 控制回归的前后半系数为 `+0.560533 / -0.534787`，方向翻转。后半段单独
  看似有利，但它是冻结门内的稳定性反证，不能用来改起始日期或重新选模型。
- 校准期冻结预测相对零预测和校准期历史均值的样本外 R2 分别为
  `-1.0672% / -1.2553%`；方向准确率 `54.11%` 不能弥补均方误差恶化。
- 冻结低尾多头减高尾原始收益的均值仅 `+0.041585%`，14 天近似的
  10-observation 循环块 bootstrap 95% 区间为
  `[-1.809520%, +1.578465%]`。低尾多头均值 `+0.054548%`，高尾空头均值
  `-0.012963%`，两端没有同时成立。
- 25% 名义敞口、每次 52 bp 标的往返成本和 4% 年度全计划门槛后，日历日净均值
  `-0.036519%`，区间 `[-0.085071%, +0.004244%]`，端点复合收益
  `-15.6913%`。vectorbt 端点统计的 Sharpe 为 `-1.7210`，最大回撤
  `-21.7790%`；这仍未包括实际 funding，加入它不能修复已经失败的方向和预测门。

因此，本题不支持把论文机制转成 Halpha 半自动策略计划，也不支持长期盈利表述。
它不证明相关性学习机制在所有时期或所有实现中永久不存在；它否定的是本项目事前
固定、时间校正、低维护参数冻结、当前 BTCUSDT 永续映射。

## 数据与方法边界

- 稳定产品基准：`0bdfeffa616260cebd2d2188ddc8deb9e85c77f4`；正式比较背景为
  `ONE_SHOT_DONCHIAN_ATR_BREAKOUT 1.0.1 / BTCUSDT-PERP`，未重估、未修改。
- 公开数据：FRED `SP500` 日收盘；Binance USD-M `BTCUSDT` 官方日线和 15m
  klines。数据根目录：
  `D:/projects/Codex/CodexHome/research-data/halpha/btc-sp500-correlation-change-next-interval-predictability/2026-07-22-v1`。
- 共 104 个边界明确的源对象、8,259,995 bytes；解析出 1,545 条 BTC 日线、
  148,249 条 15m 行和 1,055 个 FRED 交易日。源身份摘要为
  `9d3e1eb25c9286c56d26b02f0ad59dd69fee6ed51adf60254852a7a084788a8d`。
- 709 个校准观测只负责一次性拟合两条 Gaussian GARCH(1,1)、DCC(1,1)、
  回归系数和 20/80% 固定尾部；316 个开发观测全部为校准边界之后的真实
  out-of-time 证据，行动价格覆盖 100%。
- S&P 交易日 `D` 收盘后，再等到 `D+1 00:00 UTC` BTC anchor 完成，
  `00:15 UTC` 才行动；退出在下一个 S&P 交易日对应的 `00:15 UTC`，明确包含
  周末/假日持有长度，避免来源论文承认的 3–4 小时非同步收盘捷径。
- DCC/GARCH 参数在开发期前冻结，不进行滚动调参。这比来源每日重估更严格，
  直接回答个人项目能否用低维护实现保留该效应。

## 质量、失败门与反证

数据质量 `PASS`：两条 GARCH 与 DCC 均收敛且满足预设平稳性；DCC 最小相关
矩阵特征值 `0.4555`；低/高尾 50/44 次，覆盖六个季度。失败的 12 个强制门为：

`source_near_negative_hac`、`controlled_negative_hac`、
`controlled_halves_negative`、`frozen_oos_r2_zero`、
`frozen_oos_r2_historical`、`tail_spread_bootstrap_lower`、
`both_tail_directions_positive`、`net_daily_positive`、
`net_daily_halves_positive`、`net_daily_bootstrap_lower`、
`beats_scheduled_long`、`quarter_concentration`。

最强反证不是单个 p 值，而是主系数反向、前后半翻转、真正样本外误差劣于简单
基准、高尾 short 本身亏损，以及成本后结果明显为负同时出现。

## 复现与身份

命令完整列在 `README.md`。重要内容摘要：

- 最终 checkpoint：`16a4e16b2c13aa1a98adcfa5bcda7956249909b7a8a2993f7932cc889b1ec57d`
- 原始归档覆盖修复前 checkpoint：`708e68bf3d5ed33463d926e1726fd7b3dcc36c921d2ed4b35f996a45a7bbf829`
- source manifest：`0ca504d0b5f20e3d9a48a51092fcdef96f220fbc289759bb4650fc3f98315363`
- data quality：`7f319e7dcd50665e08ebac9f15d015ce84046ecf34c9debc4ae595eaea7d0e0d`
- development analysis：`6c0bac9cd5d9d0d0e9fc3415acf46b998948067224bfd069b7beae53867fe7d4`
- development gate：`68a4e8215cb419bde1d3f5cab8112dc9f7b614bf1f541f84096bf51c15cb221a`
- final results：`66ea2e5f67b24af134ce1117264ffe2654d18c18152cd03acad54beffbb89378`
- independent validation `PASS`：`c1d05c29e9ed9048f8b8d1f6e7e840ef4ca5657ec9a59715083268495fdb0573`

开发 panel 与 event CSV 已保留；原始公开数据在 Git 外按 manifest 可逐字节核验。
验证重新估计模型、复算统计与门槛并确认后段未取数，避免后续重复研究或把后半段
事后升格为新策略。

## 剩余未知

- 来源论文的每日扩展重估、全球股指聚合或条件权重代理在 2022 年后是否仍有预测力
  未知；本题的 family stop 禁止用开发结果继续试这些近邻实现。
- BTC 现货、ETF 流和其他投资者结构变化为何使前半段方向反转，当前基础数据不能
  唯一识别。
- 评估期、确认期和实际 funding 表现刻意未知；开发门失败后打开它们只会增加
  数据窥探，不会提高证据质量。

