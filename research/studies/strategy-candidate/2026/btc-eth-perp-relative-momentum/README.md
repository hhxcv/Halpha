# BTC/ETH 永续相对动量

## 问题与用途

用 90 日 ETH/BTC 比率趋势决定下一月的相对方向，始终对较强者 long 25%、较弱者 short 25%，能否在两腿实际 funding、现实成本和顺序时间门后，以最多两腿、总 gross 0.5 的方式产生稳定、低共同 crypto beta 的收益，并适合当前 BTC/ETH USD-M Demo 验证？

- 类型：`STRATEGY_CANDIDATE`。
- 候选：每月首个 UTC 日开盘，使用前一日 close 相对 90 日前 close 的 ETH/BTC 比率变化；比率上升则 long ETH/short BTC，下降则 long BTC/short ETH。
- 每腿目标绝对权重 0.25；月内信号固定，但当实际权重偏离目标超过 20% 时再平衡，避免固定数量在单边行情中扩大风险。
- 机制：从共同 crypto 方向中提取 BTC 与 ETH 的相对趋势；不是静态协整或均值回归。
- 反证：任一顺序门失败；不根据结果改 lookback、方向、gross、调仓频率或成本。

## 固定设计

- Binance USD-M BTCUSDT 与 ETHUSDT perpetual，UTC `1d`，下一日开盘行动。
- 90 日相对动量，月度更新；无空仓状态；总目标 gross 0.5、目标净敞口 0。
- favorable/base/stress 每单位绝对 turnover 为 4 bp taker fee 加 2/10/15 bp 滑点；逐实际 funding 事件和 mark price 计入两腿。
- 基准：静态 long BTC/short ETH、静态 long ETH/short BTC，以及 BTC/ETH 各 25% long 的共同 beta 诊断。
- 开发选择偏差按 13 个相关尝试处理：此前 12 个日线/8h 趋势与迁移尝试加本候选。

## 顺序门

- development 2021–2023：base/stress 正；stress CAGR >4%；Sharpe ≥0.75；13-trial DSR ≥0.80；回撤 >-15%；至少两年正且最差年度 ≥-5%；active days ≥1,000；turnover ≤25；Sharpe 与 Calmar 均超过两个静态相对方向。
- evaluation 2024–2025：仅开发通过后；base/stress 正；stress CAGR >4%；两年均正；Sharpe ≥0.75；回撤 >-15%；active days ≥650；turnover ≤20；Sharpe 与 Calmar 均超过两个静态相对方向。
- confirmation 2026H1：仅评价通过后；base/stress 非负；回撤 >-8%；active days ≥150；评价+确认 base/stress CAGR >4%。

BTC/ETH 历史已被其他规则查看，本题不声称 virgin data；证据来自未运行过的固定两腿机制、13-trial 校正与顺序门。

研究复用此前 checksum 已验证的 Git 外 BTC/ETH 日线、mark-price 与 funding 快照，不调用产品或交易端点。
