# 实际尝试与失败记录

- 2026-07-22：审计四项既有 `SUPPORTS_WITHIN_SCOPE`。关联监测不是策略；TRX 8% vol-target 资本门余量仅 0.58%；TRX/PAXG 需要 Spot 双资产；DOGE/XRP/ADA carry 是六腿。均不直接进入当前 Demo。
- 2026-07-22：外部调研后选中 trend × carry。固定上一日实际 funding 净符号、三种文献定义过滤、相同 Donchian/波动/成本、三个顺序时间门和失败即停止；没有查看新候选收益。
- 2026-07-22：复用上一日线 Donchian 研究的数据装载、成交代理和官方缓存；新脚本只实现 carry 条件、门和结果导出，避免维护第二份行情/资金费逻辑。
- 2026-07-22：开发期运行后，`CARRY_BOTH_SIDES` base/stress +4.29%/+3.37%，`CARRY_LONG_SIDE_ONLY` -0.63%/-1.03%，`CARRY_SHORT_SIDE_ONLY` +13.97%/+12.83%。三者均未通过固定开发门；评价和确认未运行。
- 2026-07-22：最接近的 short-side-only 三年 base 均正、Sharpe 0.636、最大回撤 -9.71%，但总 funding PnL -4.00% 略差于纯多空 -3.97%，DSR 0.735 < 0.80。总 funding PnL 会受权益路径和后续 long 名义敞口影响，不能据此否定局部 short carry 过滤；该检查已事前固定，所以不改为事后暴露归一化指标，也不解封评价。
- 2026-07-22：在 Git 外 `D:/projects/Codex/CodexHome/research-data/halpha/btcusdt-daily-donchian-carry-conditioned-replay/` 独立运行开发期；CSV `6cf45b...c0226`、日收益 `27555e...f9c89` 逐字节一致，JSON 去除 `generated_at` 后语义一致。
