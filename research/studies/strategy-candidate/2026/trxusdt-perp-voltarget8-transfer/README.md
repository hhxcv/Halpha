# TRXUSDT 8% 波动目标多头的 perpetual 固定迁移

## 问题与选择理由

既有 `trxusdt-voltarget-8pct-long` 已支持一条固定的 Binance Spot 规则：60 日 realized volatility、8% 年化风险目标、每月调整、always long、最大 0.5x。本题只问：不改变任何参数，把执行标的换成 Binance USD-M `TRXUSDT` perpetual 并逐实际 funding 计价后，是否仍在顺序时间段、现实成本和 4% 全资本门下保留产品考虑价值？

- 类型：`STRATEGY_CANDIDATE` 的单工具场所迁移。
- 候选：`TRXUSDT_PERP_VOL60_TARGET8_MONTHLY_LONG_MAX0P5X`。
- 决策价值：若通过，它比两腿候选更接近当前单工具计划模型；这不是降低证据门，也不能事后替换为 6%/10% 诊断。
- 反证：任一阶段门失败即停止，不改 target、lookback、频率、方向、成本或时间段。

## 固定规则

- 每月第一个 UTC 日开盘，使用前一 UTC 日收盘结束的 61 个 close 形成 60 个 log return。
- `realized_vol = std(log_return, ddof=1) * sqrt(365)`。
- 目标权重 `min(0.50, 0.08 / realized_vol)`；始终 long，其余保留现金。
- favorable/base/stress 每单位绝对 turnover 总成本 10/30/60 bp（4 bp taker fee，其余为滑点）；末期按同一成本平仓。
- 逐实际 funding event 与对应 mark price 计入；price-only 同规则只用于解释 funding。
- 诊断邻域固定为 6% 与 10% 目标；50% always-long 是风险基准，均不得替换主候选。
- 年化资本门为全部初始资本 4%。

## 顺序时间门

### Development 2021–2022

- Base/Stress 为正；Stress 扣 4% 年化全资本门后为正。
- Base Sharpe ≥0.45，最大回撤优于 -12% 且浅于 50% always-long。
- 6%/10% 两个邻域 Base 收益为正；active days ≥700；turnover ≤3。
- price PnL 为正，funding 若为拖累不得超过 price PnL 的 50%。

### Evaluation 2023–2024

仅 development 全过后打开：Base/Stress 为正；Stress 扣门为正；两年均正；Sharpe ≥0.75；最大回撤优于 -14% 且浅于 50% always-long；6%/10% Base 为正；turnover ≤4。

### Confirmation 2025–2026H1

仅 evaluation 全过后打开：Base/Stress 为正；Stress 扣门为正；2025 与 2026H1 均正；Sharpe ≥0.50；最大回撤优于 -10% 且浅于 50% always-long；6%/10% Base 非负；active days ≥530；evaluation+confirmation 的 Base/Stress CAGR 均高于 4%。

底层 TRX 现货价格段已在既有研究中暴露，且 2025-04 后 TRX perpetual 的 50% 单腿诊断已在两腿研究中查看。本题的独立增量主要是固定波动目标在完整 perpetual 价差/funding 历史上的顺序迁移；不得把它写成 virgin price holdout。

研究仅读取公开市场数据，产品作用为 `NONE`。
