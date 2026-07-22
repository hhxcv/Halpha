# 实际尝试

- 2026-07-22：扫描当前 L4、`research/studies/**`、4 个 one-shot 新问题和历史 BTC 趋势问题。确认当前 15 分钟固定退出近邻均不支持，日线中线跟踪组合是机制不同的新问题。
- 2026-07-22：核对 Git 外现有 2021-01 至 2026-06 BTCUSDT 1m 与 funding 缓存；底层时期已暴露。确认 Binance 官方 USD-M 日线月档案从 2020-01 可用，funding API 从 2019-09 可取。
- 2026-07-22：在查看任何本问题结果前完成公开论文、原始 Turtle 规则、时间序列动量、交易成本、选择偏差和 Binance 官方数据语义核查。
- 2026-07-22：在查看任何本问题结果前锁定 6 个候选、信号、退出、执行延迟、规模、成本、时期、顺序门、排序和禁止事项；论文高风险规模仅作诊断。
- 2026-07-22：下载并逐档核验 2020-01 至 2026-06 共 78 个 Binance USD-M BTCUSDT 1d 月档案与 7,457 条 funding；首次质量加载只检查时间轴和输入身份，没有计算候选收益。
- 2026-07-22：首次质量加载发现 4,198 条旧 funding 记录缺 `markPrice`。在任何候选结果前补入 78 个官方 8h mark-price 月档案；回填 4,173 条，官方 mark 时间轴六处缺口对应的 25 条保守使用同 UTC 日永续开盘价。日线 2,373 条连续、无重复、OHLC 合法。
- 2026-07-22：研究实现通过 `py_compile` 与 Ruff；在首次候选结果前封存 `study.py` SHA-256 `ea598414629c930370e7de3eff08fcb5002f9543d9719a7b635c67b0434e5019` 和 manifest SHA-256 `2e0de6c4396e48c00fc64b87dee7dedf509be8cc0ea56f0fc970f89218eb3e3d`。
- 2026-07-22：合成路径检查通过：平价无成本为零、成本只减收益、正 funding 对多头为负且对空头为正、上涨序列形成 Donchian 多头。
- 2026-07-22：首次运行 development，一次保存全部 6 候选、三成本情景、单周期分量和每日 base 回报。六个候选 base/stress 均为正；固定开发选择门返回 0 个通过者，`evaluation_authorized=false`。
- 2026-07-22：最接近的 `LONG_BALANCED_4` base +8.38%、stress +8.08%、Sharpe 0.473、最大回撤 -8.46%，但相对持续多头的 Sharpe 优势极薄，DSR 0.750 未达 0.80；未放宽门，也未选择事后最优 60 日分量。
- 2026-07-22：在 Git 外独立目录重演；`development.csv` 与 `development_daily_returns.csv` SHA-256 逐字节一致，去除生成时间和派生 source hash 后 development/selection 语义一致。
- 2026-07-22：非选择审计显示 0%/20%/50% 换仓容忍带下 `LONG_BALANCED_4` base 为 +8.46%/+8.38%/+9.98%；零成本保留 funding 为 +9.21%，base 成本移除 funding 为 +13.44%。这些诊断不改变固定候选、排序或门。
- 2026-07-22：开发期 24 个 funding mark fallback 改用日收盘价后总收益只增加 `2.665e-7`；结论不依赖 fallback。最终为 `INSUFFICIENT_EVIDENCE`，未读取 evaluation/confirmation，产品与 Demo 状态不变。
