# 实际尝试与失败记录

- 2026-07-22：上一 carry 条件问题开发门失败后，按事前候选顺序转向 Spot 场所适配。固定 `LONG_BALANCED_4`，不搜索新参数。
- 2026-07-22：开发 DSR 明确合并相关六个日线 Donchian、三个 carry 条件和一个 Spot 候选，共十次相关尝试；不会只按单列计算。
- 2026-07-22：Spot 公开 commission 页面不能证明当前账户费率。固定 10 bp taker 加 2/5/10 bp 滑点代理；若历史门通过，Demo 前必须读取当时账户 commission，不能事后以更低费用修饰回测。
- 2026-07-22：78 个官方月档、170,000 bytes 全部 checksum 通过；2020-01-01 至 2026-06-30 共 2,373 个连续 UTC 日、无重复、OHLC 有效，2025+ 微秒时间戳按官方语义归一化。
- 2026-07-22：开发 base/stress +13.56%/+13.25%，stress CAGR 4.24%，Sharpe 0.729、最大回撤 -7.76%、Calmar 0.558；2021/2022/2023 为 +5.27%/-4.99%/+13.55%。除十试验 DSR 0.768 < 0.80 外全部固定门通过，因此评价与确认未运行。
- 2026-07-22：Git 外 `D:/projects/Codex/CodexHome/research-data/halpha/btcusdt-spot-daily-donchian-replay/` 独立运行；开发 CSV `bf5176...fb94c`、日收益 `28553e...f56bdd` 逐字节一致，JSON 去除生成时间后语义一致。
