# 高流动永续周级输家延续：预注册

## 身份、问题和半自动闭环

- 类型：`STRATEGY_CANDIDATE`。
- 身份：`RESEARCH_LIQUID_PERP_WEEKLY_BOTTOM1_SHORT_7D_0P25X_V1`。
- 稳定产品基准：`0bdfeffa616260cebd2d2188ddc8deb9e85c77f4`；正式策略背景 `ONE_SHOT_DONCHIAN_ATR_BREAKOUT 1.0.1 / BTCUSDT-PERP`。
- 固定对象：Binance USD-M `BTCUSDT`、`ETHUSDT`、`BNBUSDT`、`XRPUSDT`、`DOGEUSDT`、`ADAUSDT`。当前名单中均持续交易且属于 anchor 或 A1 活动层；这只是当前和历史活动筛选，不是安全保证。

固定问题：每个 UTC 周一 00:00，在完整前一周日线后，对六币过去 7 日收益排名；选择最差的一个，在下一可行动周一 open 做空，固定持有到下一周一 open，名义不超过计划金额的 0.25 倍。该规则能否在实际 settled funding、双边 taker fee 和 spread/slippage 后，于顺序开发、评价和确认中持续为正，并表现出相对六币等权市场的增量输家延续，而不只是熊市做空 beta？

用户在榜单形成后选择并固定本周 instrument、SHORT、计划金额和有效期；策略只在该 instrument 确为唯一 bottom-1 且输入完整时产生零或一个入场提议。完全退出后完成，不自动重入。并列按 symbol 字母序固定；数据缺口、warmup 不足、排名冲突、过期或场所事实未知均不新增风险。

保护固定为：最大 0.25 倍计划金额、不得加仓、不得重入、最迟 7 日完整退出。本版本没有价格止损；若产品资格验证要求场内价格保护，必须另建版本重新研究。

## 来源、差异和候选选择

本题不同于已经否定的日级极端反转、BTC lead-lag、BTC-neutral residual reversal，也不同于 180 日/月度 TSMOM。外部研究把流动性分层作为机制：小而不活跃币更可能周级反转，大而活跃币更可能 1–2 周延续，且大币动量主要来自 short loser 腿。本题把其动态大横截面缩成当前个人项目可维护的固定六币榜单；这不是原论文复现，固定幸存宇宙和单腿表达都必须重新证伪。

筛选过的少量方向：

| 方向 | 与现有缺口 | 现实/研究成本 | 决定 |
|---|---|---|---|
| 六币前周 bottom-1、空一周 | 文献明确指向高流动币 short loser；一次一腿、一周闭环 | 基础日线/funding，个人小资金可缩放；需防熊市 beta 假象 | **选中** |
| 高成交量日级极端后顺势 24h | 与上一题的低量反转不同 | 阈值与事件稀疏，容易形成结果驱动阈值 | 后置 |
| funding 符号顺势 | 新的拥挤/需求机制 | 方向理论不统一，与既有 funding 家族邻近 | 后置 |
| 周末/星期季节性 | 最简单 | 近期 500 币研究已有强不稳健反证 | 淘汰 |
| 动态全市场周动量 | 更接近论文 | 点时市值、上市退市、容量和下架治理成本过高 | 暂不建设 |

## 数据、时序、成本与搜索披露

- 暖启动 2020-12-20；研究数据截止 `2025-07-01`。development 2021-01-04 至 2023-01-02；evaluation 2023-01-02 至 2025-01-06；confirmation 2025-01-06 至 2025-06-30。只有前一门通过才运行后一阶段。
- 日线信号：周一入场前最后一个完整 UTC 日 close 相对 7 日前 close 的简单收益；六币全部有两个端点才排名。
- 入场/退出：周一 open 至下一周一 open。funding 计 `entry < fundingTime <= exit`；short 的 funding 现金流为 `+quantity * markPrice * rate`。
- favorable：每边 6 bp fee、零 slippage、实际 funding；base：每边 6 bp + 10 bp slippage、实际 funding；stress：每边 6 bp + 20 bp，正 funding 收益只保留 0.5，负 funding 成本放大 1.5。
- 主配置只有 7 日 formation、bottom-1、7 日 hold、0.25 倍 short。预注册诊断为 14 日 formation、bottom-2 等权、六币等权 0.25 倍 short、BTC 0.25 倍 short；不得从诊断选择替代主规则。
- 完整披露每币选择次数、收益、分年、实际/压力 funding、交易成本、周级与日级回撤、4 周 circular-block bootstrap、相对六币等权市场的 gross selection return。

项目此前查看过这些币的其他频率和规则结果，所以不能称市场价格路径完全未见；本题的固定周级横截面排名、逐阶段净结果和相对市场选择效应在 checkpoint 前未查看。顺序门只防止本题内追参，不抹掉跨项目的数据暴露。

## 门槛、否定条件与结论

development/evaluation 各要求：

- 数据质量通过且至少 100 个完整非重叠周计划；
- base 与 stress 复合收益均为正，stress 扣 4% 年化完整资本机会成本后仍为正；
- 两个完整日历年各自 base 为正；
- base 日级最大回撤浅于 -15%；
- bottom-1 的周形成收益显著低于等权市场，随后一周继续相对落后：0.25 倍 short selection return 均值为正，4 周 block-bootstrap 95% 下界大于零；
- 至少 4/6 币被选择 5 次，且没有单币贡献超过正总 PnL 的 50%；
- 主配置 base 总收益高于六币等权 short 基准。

confirmation 要求至少 20 周，base/stress 均正、stress 扣资本门仍正、相对选择收益为正、日级回撤浅于 -10%，且至少 4 个币被选择。确认样本不要求 bootstrap 下界大于零，但必须披露区间。

前门失败就停止，不换币、星期、formation、hold、bottom 数、方向、仓位、成本或 funding 假设。主 base/stress 为负或相对选择效应不正时为 `DOES_NOT_SUPPORT`；原始收益为正但稳健/资本/统计/覆盖门不足为 `INSUFFICIENT_EVIDENCE`；数据或实现不能可靠判断才用 `CANNOT_DETERMINE`。全部门通过才是 `SUPPORTS_WITHIN_SCOPE`，也只表示固定范围内可供产品资格验证，不证明 Alpha、长期或未来必然盈利。
