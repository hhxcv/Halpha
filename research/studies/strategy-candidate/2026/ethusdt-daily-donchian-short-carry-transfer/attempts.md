# 实际尝试与失败记录

- 2026-07-22：BTC carry 条件中只有 short-side-only 同时三年正并改善风险，但预注册 DSR 与总 funding PnL 门失败；BTC 评价保持未读。ETH transfer 固定该规则，不重搜三种过滤。
- 2026-07-22：总 funding PnL 会受权益路径和后续名义敞口影响，因此本题不声称“收取 carry”，也不以事后替换的 funding 指标作支持门；它检验的是完整净收益与风险的跨 instrument 可迁移性。
- 2026-07-22：开发选择偏差按 11 个相关尝试处理；不会只对 ETH 单候选计算 DSR。
- 2026-07-22：冻结身份校验全部一致后只运行 development。候选 base/stress 为 +16.67%/+15.57%，但 11-trial DSR 仅 0.752；Sharpe 0.732、Calmar 0.747 均低于更简单的 ETH 纯 long-only（0.818、0.997），因此未解封 evaluation。
- 2026-07-22：没有降低 DSR、删除基准超越门或按 ETH 结果重选过滤规则。Git 外独立重放的开发 CSV 与每日收益逐字节一致，JSON 去除生成时间与派生 source hash 后语义一致。
