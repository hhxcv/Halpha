# 结果：两分钟 taker-flow 方向过滤不支持继续

结论：`DOES_NOT_SUPPORT`。

## 最强证据

- 开发期 2021-01-01 至 2024-01-01 共核验 37 个 Binance USD-M 月档案、70,193,234 bytes、1,576,861 根 1m K 线和 3,286 个 funding 事件。
- 1,576,620 根 K 线具有有效 taker-flow，241 根无效、16 根净方向为零；29,084 个原始突破触发的 flow 均已知，没有因缺失字段偏向性删去触发。
- LONG 对齐过滤保留 9,192/15,401 个原始触发，实际 base 交易 1,763 笔，平均 -0.329638%；同方向未过滤基准为 -0.324678%，过滤反而差 0.496 bps/笔。
- SHORT 对齐过滤保留 8,448/13,683 个原始触发，实际 base 交易 1,684 笔，平均 -0.372200%；同方向未过滤基准为 -0.368648%，过滤反而差 0.355 bps/笔。
- favorable、base、stress 与 2021、2022、2023 年度均没有正均值。LONG/SHORT stress 分别为 -0.448498%/-0.507714%。

## 最强反证与限制

最强反解释不是成本过高：即使 favorable 成本情景，两项过滤候选仍分别为 -0.159682% 和 -0.185998%。这说明当前代理在进入成本前就缺乏足够毛边际，降低手续费假设不能把结论转为正向。

本题只测试两根确认 1m K 线合计 `2 × taker_buy_base_volume - total_base_volume` 的符号，不测试完整订单簿 OFI、阈值强度、时钟相位、OI、basis 或波动状态。底层时间区间曾被父研究查看，结论只约束这项固定过滤在当前代理中的开发期表现，不能推广为“订单流在 BTCUSDT 永远无效”。

## 门与后续区间

固定开发门没有任何方向通过：

- `gate_pass_count=0`
- `evaluation_authorized=false`
- `stop_reason=NO_TAKER_FLOW_DIRECTION_PASSED_DEVELOPMENT_GATE`

因此 2024–2025 evaluation 和 2026H1 confirmation 未运行、未暴露。本研究不生成产品交接，不修改正式策略，不支持继续搜索同一近邻过滤或立即重复开单。

## 可重演性

保存结果：

- `development.csv`：`6da9891eeb82b2dc656326c5c1f59208923f8569c3ec5fc39b427cf6c1d99322`
- `development.json`：`38cb1a7a66759df852d5943c976caa14bd9b9c6c8f1b4692678b5782dfd1aca9`
- `selection.json`：`673baca073867e020e0020dbb5aac9507cac8c80c9297cf7e7cdb7695d9db3a5`

2026-07-22 使用 `attempts.md` 中的固定命令输出到独立临时目录，重演 CSV 哈希与保存结果完全一致，选择门语义一致。
