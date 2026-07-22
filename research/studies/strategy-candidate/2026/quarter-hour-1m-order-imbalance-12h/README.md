# 15 分钟边界 1m 成交失衡与 12h 收益

状态：开发阶段已停止，结论 `DOES_NOT_SUPPORT`。研究身份 `RESEARCH_QH_1M_TAKER_IMBALANCE_12H_0P25X_V1`。

本题检验一个面向半自动一次性计划的低复杂度代理：在 UTC `00:15` 或 `12:15` 的完整 1 分钟 bar 结束后，以 Kline 官方字段中的 taker-buy quote volume 构造主动买卖失衡；只有它进入本币过去 30 日同类边界的上/下四分位时，才在下一分钟 open 顺失衡方向进入，持有 12 小时后完整退出，最多使用计划金额 25%，不自动再入。

它只使用 Binance 公开 1m OHLCV/taker-buy volume、funding 和 mark price，不使用 L2、新闻、舆情、OI、liquidation、产品数据库、账户、凭据或运行配置。精确论文信号使用边界后前 10 秒逐笔成交；本题有意研究更便宜、更容易长期维护和交付的 1 分钟代理。代理失败不能否定原论文的 10 秒规律。

开发期 2024-11 至 2025-06 共 1,464 笔。gross 复合收益已为 -1.02%，favorable/base/stress 净收益为 -8.03%/-18.60%/-28.21%；六币和八个月 base 全部为负，额外延迟 5 分钟也没有救回。开发门失败后没有打开 evaluation/confirmation，没有生成交接包。

全库事后查重发现更早的 `research/studies/predictive/2026/quarter-hour-kline-order-flow-predictability/` 已用四个论文外资产否定同类 1m 代理。选题时未把该未跟踪目录纳入候选表，是明确流程缺陷。本题只增加论文六币、2024-11 后时间、实际成本/funding 和唯一仓位时间轴的依赖性确认，不计为独立机制发现或第四份独立市场证据。

稳定产品基准 `0bdfeffa616260cebd2d2188ddc8deb9e85c77f4`，正式策略背景 `ONE_SHOT_DONCHIAN_ATR_BREAKOUT 1.0.1 / BTCUSDT-PERP`。只写 `research/**`，不修改或启动产品。

重演入口：

```powershell
research\.venv\Scripts\python.exe research/studies/strategy-candidate/2026/quarter-hour-1m-order-imbalance-12h/study.py checkpoint
research\.venv\Scripts\python.exe research/studies/strategy-candidate/2026/quarter-hour-1m-order-imbalance-12h/study.py fetch
research\.venv\Scripts\python.exe research/studies/strategy-candidate/2026/quarter-hour-1m-order-imbalance-12h/study.py inspect
research\.venv\Scripts\python.exe research/studies/strategy-candidate/2026/quarter-hour-1m-order-imbalance-12h/study.py analyze --stage development
research\.venv\Scripts\python.exe research/studies/strategy-candidate/2026/quarter-hour-1m-order-imbalance-12h/study.py gate --stage development
```

Git 外缓存：`D:/projects/Codex/CodexHome/research-data/halpha/quarter-hour-1m-order-imbalance-12h/2026-07-22-v1/`。问题、反证、样本隔离和门槛见 `preregistration.md`。
