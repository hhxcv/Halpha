# 实际尝试

- 2026-07-22：核对 L4、HALPHA-ALP-001/002/003、研究目录契约、父入场研究与持仓期限研究。确认不得继续入场/退出近邻联合调参，研究不得改变产品或自动启用策略。
- 2026-07-22：按 `funding`、`sign`、`crowding`、BTCUSDT 和结论扫描全部既有研究。`btcusdt-next-funding-carry` 已否定单腿下一结算 carry；`multi-asset-funding-sign-hysteresis-carry` 已暴露符号 episode 的集中风险，但没有研究 Donchian 信号过滤。
- 2026-07-22：联网核对 Binance 官方 funding history、He 等的 perpetual/funding 理论与事件研究、Inan 的 funding 可预测性及 Zhang 的 funding 反馈机制。外部结果只支持固定问题和反解释，不替代 Halpha 数据检验。
- 2026-07-22：候选比较后选中一个无数值阈值的方向非不利 funding 过滤器；高时间框架趋势、波动阈值和 quarter-hour 订单流本轮均不运行。
- 2026-07-22：在查看任何新结果前固定 2 个候选、2 个基准、时序、成本、顺序时间门、改善门、尾部门与停止规则。
- 2026-07-22：首个结果前核验 checkpoint、研究代码、父研究和数据清单哈希；静态检查通过且输出目录没有结果文件。
- 2026-07-22：只运行 2021–2023 development。两条未过滤基准与父研究正式默认 LONG/SHORT 行逐字段完全一致；两个 funding 符号候选在 favorable、base、stress 下均为负。
- 2026-07-22：开发门通过数为 0，`evaluation_authorized=false`。按预注册规则停止，未运行或读取 evaluation/confirmation；结论为 `DOES_NOT_SUPPORT`，产品影响为 `NONE`。
