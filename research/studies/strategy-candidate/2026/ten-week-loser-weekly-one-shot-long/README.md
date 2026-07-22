# Q17：10 周输家的一周 one-shot 做多

## 当前状态

- 研究类型：`STRATEGY_CANDIDATE`
- 稳定产品基准提交：`0bdfeffa616260cebd2d2188ddc8deb9e85c77f4`
- 正式比较策略：`ONE_SHOT_DONCHIAN_ATR_BREAKOUT 1.0.1 / BTCUSDT-PERP`
- 候选身份：`RESEARCH_MOM70_BOTTOM30_WEEKLY_ONE_SHOT_LONG_0P25X_V1`
- 写入边界：仅本目录；公开市场原始数据继续使用 Git 外研究缓存
- 当前结论：尚未运行；不得视为可用策略或 Alpha 证据

## 问题

在固定的 25 个当前 Binance USD-M 永续目标中，若目标在周日完成后的 70 日收益位于当周可交易目标的底部 30%，则下一个周一以计划资金 `0.25x` 做多并持有 7 日，是否能在零售手续费、spread/slippage、真实 funding、4% 全计划资金年化门槛、简单做多基准、参数邻域、横截面广度和顺序时间证据之后仍获支持？

这不是对论文组合的直接复现。论文使用广泛现货横截面和分散组合；本题把“中期输家反转”转换为 Halpha 的固定单目标半自动计划资格判断。研究聚合多个目标/日期只用于估计条件结果；不表示同时开 25 个仓位，也不改变产品当前正式策略。

## 为什么选择它

外部研究给出了直接且可证伪的先验：2014–2020 的同行评审结果认为加密货币从约一个月以后由短期动量转向反转，主要由过去输家推动；2026 年工作论文又在 Binance 2021–2026 样本中报告 8–10 周反转。相较已经失败的 1 周输家/赢家、低量反转、MAX、短 funding/premium 与复杂 CTREND，本题检验的是尚未解决的“中期输家长腿”，而不是重新扫描同一短周期规则。

候选筛选（5 为更适合当前项目；成本列 5 表示研究成本低）：

| 方向 | 决策价值 | 未解决差异 | 可证伪性 | 数据可得 | 小资金/单腿适配 | 研究成本 | 决定 |
|---|---:|---:|---:|---:|---:|---:|---|
| 8–10 周输家一周做多 | 5 | 5 | 5 | 5 | 5 | 5 | 选择；论文先验最直接，规则可冻结 |
| 单腿 funding/basis carry | 4 | 3 | 5 | 5 | 3 | 5 | 暂缓；已见收益压缩，严格 carry 通常需两腿 |
| 日历季节性 | 2 | 3 | 5 | 5 | 5 | 5 | 不选；大样本近期研究缺乏稳健 return seasonality |
| CTREND 再优化 | 3 | 2 | 3 | 5 | 4 | 2 | 不选；已有结果复杂、集中且未稳定胜过简单动量 |
| 新闻、L2、OI/liquidation | 4 | 5 | 4 | 2 | 3 | 1 | 不选；与“基础公开数据、个人可维护、快速验证”约束不符 |

## 数据与边界

- 市场输入仅为 Binance 公开 USD-M 日 OHLCV、官方 funding 事件和对应 mark price；无凭据、无产品数据库、无业务数据。
- 固定目标：`1000XEC AAVE AVAX BCH BNB CRV DASH ENS ETC HBAR KAVA LINK LTC NEAR RUNE SNX SOL TRX UNI VET XLM XMR XRP ZEC ZIL` 的 `USDT` 永续。
- 流动性资格：决策日过去 30 个完成日的 quote volume 中位数至少 1,000 万 USDT；至少 20 个目标可排名。
- 这是当前幸存目标的固定回看，不是 point-in-time 全市场；不含退市损失、新上市资产、容量、真实盘口冲击、延迟或停机。
- 不使用未来数据：周日完整日线收盘后计算，下一周一开盘成交代理；同一时间边界的实际可成交性由 slippage 压力而非理想开盘价保证。

## 顺序证据

1. development：`2022-02-14` 至 `2024-01-01`（entry end-exclusive）。
2. evaluation：`2024-01-01` 至 `2024-12-30`。
3. confirmation：`2025-01-06` 至 `2025-12-29`。

后一期只有前一期门为 `PASS` 才能计算。development 要求 block-bootstrap 下界为正；两个单年留出期分别要求现实压力净值、风险、广度和基准差为正；最终还要求 evaluation+confirmation 合并后的压力净值与市场相对收益 4 周 circular block-bootstrap 95% 下界为正。这样既不靠全样本掩盖失效，也不要求每个约 1 年切片独自取得通常不现实的统计显著性。

## 可重演命令

使用独立研究环境，不修改产品依赖：

```powershell
research/.venv/Scripts/python.exe research/studies/strategy-candidate/2026/ten-week-loser-weekly-one-shot-long/study.py self-test
research/.venv/Scripts/python.exe research/studies/strategy-candidate/2026/ten-week-loser-weekly-one-shot-long/study.py checkpoint
research/.venv/Scripts/python.exe research/studies/strategy-candidate/2026/ten-week-loser-weekly-one-shot-long/study.py prepare --stage development
research/.venv/Scripts/python.exe research/studies/strategy-candidate/2026/ten-week-loser-weekly-one-shot-long/study.py analyze --stage development
research/.venv/Scripts/python.exe research/studies/strategy-candidate/2026/ten-week-loser-weekly-one-shot-long/study.py gate --stage development
```

若门通过，按相同三条 `prepare/analyze/gate` 命令依次替换为 `evaluation`、`confirmation`，最后运行：

```powershell
research/.venv/Scripts/python.exe research/studies/strategy-candidate/2026/ten-week-loser-weekly-one-shot-long/study.py validate
```

## 交付边界

只有三道门全部通过才创建 `handoff.json`，结论才可为 `SUPPORTS_WITHIN_SCOPE`。handoff 只是给未来“交易核心资格验证”任务的框架无关输入，不授权改代码、改 L4、分配资金或真实交易；核心若不能提供冻结横截面快照，或要求新增价格止损，必须另行实现并重新资格验证。
