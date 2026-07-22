# 预注册：15 分钟边界 1m 成交失衡与 12h 收益

## 身份、问题和产品映射

- 类型：`STRATEGY_CANDIDATE`；身份：`RESEARCH_QH_1M_TAKER_IMBALANCE_12H_0P25X_V1`。
- 稳定基准：`0bdfeffa616260cebd2d2188ddc8deb9e85c77f4`；正式策略比较背景 `ONE_SHOT_DONCHIAN_ATR_BREAKOUT 1.0.1 / BTCUSDT-PERP`。
- 固定对象：Binance USD-M `BTCUSDT`、`ETHUSDT`、`SOLUSDT`、`XRPUSDT`、`DOGEUSDT`、`ADAUSDT`。它们与问题来源论文一致，且适合个人小资金；固定当前幸存合约仍有幸存者偏差。

固定问题：对一个已由用户固定 instrument、LONG/SHORT、计划金额和有效期的半自动计划，若策略只在每日 UTC `00:15`、`12:15` 的完整 1m bar 结束后检查一次成交失衡，在信号进入过去 60 个同类边界观测的上/下四分位且方向匹配计划时，于下一分钟 open 提议一次入场、持有 12h、最多使用计划金额 25% 并完整退出，那么它能否在论文结束后的全新时间、实际 settled funding、双边 taker fee 与 spread/slippage 压力后持续为正，并优于伪边界和简单价格动量解释？

策略不自动替用户决定 instrument、direction 或金额。未知/零成交量、warmup 不足、缺 bar、数据冲突、错过 entry、过期或已有持仓均不新增风险。一次激活最多一个 entry 和一个完整 exit，不加仓、不重入。研究未加事后止损；最大 12h 持有和 0.25 倍名义是固定保护。

## 信号、时序与可行组合

1. 对 1m Kline 的 `quote_volume` 和 `taker_buy_quote_volume`，定义 `OI = 2*taker_buy_quote_volume/quote_volume - 1`；只在 quote volume 为正时有效。
2. 只使用严格早于当前信号 bar 的最近 60 个相同计划时隙观测计算 25%/75% 分位；`OI >= q75` 为 LONG，`OI <= q25` 为 SHORT，中间不行动。并列包含在信号内。
3. 信号 bar 为 `00:15:00–00:15:59` 或 `12:15:00–12:15:59` UTC；决策在 bar 完整结束后，主入场代理为 `00:16/12:16` open；退出为恰好 12h 后 open。
4. 下一时隙恰好等于上一持仓退出后的首个计划时隙，因此每币不重叠。跨六币组合按六个等权资金 sleeve 计算，每个 sleeve 的最大名义为其资本的 25%，总组合最大同步名义仍为 25%；无信号部分为零收益现金。
5. funding 只计 `entry < fundingTime <= exit`。LONG 支付正 funding、SHORT 收取正 funding；使用官方 mark price。压力下 funding 收益只保留 0.5、成本放大 1.5。

论文使用 10 秒逐笔 `aggTrades`；本题只用 1m Kline 中的 taker-buy volume，是面向个人维护与核心交付的代理。2025-01 单月 BTC/ETH aggTrades 压缩文件分别约 692/731 MB，完整六币 20 个月会达到数十 GB；1m 方案约两个数量级更小。这个资源选择在看结果前固定，失败只能否定 1m 代理。

## 样本、成本和搜索披露

- 数据暖启动：2024-10-01；开发 `2024-11-01 <= signal < 2025-07-01`；评价 `2025-07-01 <= signal < 2026-01-01`；确认 `2026-01-01 <= signal < 2026-07-01`。下一阶段只有前一门全通过才打开。
- 原论文样本结束于 2024-10-31，因此三段均为相对论文的时间外证据。项目此前查看过这些币的其他频率和规则；不能称价格路径完全未暴露，但本题确切 1m OI 规则、成本结果和阶段输出在 checkpoint 前未查看。
- favorable：每边 6 bp fee、零 slippage；base：每边 6 bp fee + 10 bp slippage；stress：每边 6 bp fee + 20 bp slippage。三者均计实际 funding，stress 再施加 funding 不利乘数。
- 主配置只有 1m OI、60 个观测分位、`00:15/12:15`、下一分钟 entry、12h hold、0.25 倍。
- 预注册诊断：额外延迟 5 分钟；把边界平移到 `00:22/12:22` 的伪边界；在主 OI 极端发生时改用过去 6h 价格方向。它们只作反证，不得替代主规则。
- 不搜索币、分钟、分位、窗口、持有期、方向、仓位、费用或 funding 假设。失败后不得以只选赢家币、只选某月或改阈值救回。

## 门槛、反证和结论

development/evaluation 各要求：数据质量通过、VectorBT 与独立手算最大误差不高于 `1e-12`、至少 500/350 笔主交易；favorable/base/stress 复合收益均为正；stress 扣 4% 年化完整资本机会成本后仍为正；8 日 circular block-bootstrap 的主 gross 时隙均值 95% 下界大于零；主 base 相对伪边界和相对 6h 动量的匹配时隙差值均值为正且 bootstrap 下界大于零；额外延迟 5 分钟的 stress 仍为正；至少 4/6 币 base 为正；正收益月份过半；组合 drawdown 与单计划 1m 内最大不利变动都浅于 -15%；单币不贡献超过正总 PnL 的 50%。

confirmation 至少 300 笔，base/stress 和扣资本门后 stress 为正，主 gross 与两个增量方向为正、延迟版本 stress 为正、至少 4/6 币为正、正月份过半、drawdown 与单计划不利变动浅于 -12%；短确认段不要求 bootstrap 下界大于零，但完整披露。

任何前门失败立即停止，不打开下一时段。主 favorable/base/stress 为负或 gross predictive mean 不正时为 `DOES_NOT_SUPPORT`；原始净收益为正但统计、增量、覆盖或稳健门不足为 `INSUFFICIENT_EVIDENCE`；数据/实现无法可靠判断才为 `CANNOT_DETERMINE`。只有三门全过才是 `SUPPORTS_WITHIN_SCOPE`，也只表示固定 1m 代理可供 NautilusTrader 产品资格验证；不证明 Alpha、长期或未来必然盈利，不改变产品、资金或真实账户。
