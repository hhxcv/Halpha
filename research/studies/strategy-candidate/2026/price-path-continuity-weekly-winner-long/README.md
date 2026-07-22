# 价格路径连续性周频赢家多头候选

本目录研究一个与 Halpha 半自动一次性计划契约一致的固定候选：用户先固定一个受支持目标、`LONG` 方向和交易金额；策略只在该目标同时属于 14 日收益顶部三分位和 14 日 Rank-Weighted Price Path Continuity（PPC）顶部三分位时，于下一可行动周一提出一次 `0.25x LONG / 7d` 依据，否则 `NO_ACTION`。

问题不是“PPC 论文是否显著”，而是论文的横截面关系压缩为单目标、单腿、多头、零售成本永续计划后，能否仍优于更简单的 14 日赢家和市场多头解释。论文的主要可交易统计来自 winner-minus-loser，多头连续赢家自身并不显著，因此本题把这一点当作强反证，而不是盈利先验。

- 产品稳定基准：Git `0bdfeffa616260cebd2d2188ddc8deb9e85c77f4`。
- 正式策略背景：`ONE_SHOT_DONCHIAN_ATR_BREAKOUT 1.0.1 / BTCUSDT-PERP`；只作固定比较背景。
- 研究身份：`RESEARCH_PPC14_TOP_TERCILE_MOM14_TOP_TERCILE_WEEKLY_LONG_0P25X_V1`。
- 研究类型：`STRATEGY_CANDIDATE`。
- 数据：固定 25 个当前较高活动 Binance USD-M 永续目标，公开 1d OHLCV、settled funding 与官方 mark-price 数据；不读取产品数据或凭据。
- 大型公开缓存沿用父问题记录的 Git 外身份；原始论文 PDF 也保存在 Git 外并记录 SHA-256。
- 2024 development 与 2025 evaluation 均已被外部论文或本项目其他问题暴露为底层市场时期；顺序门能防止本题按结果调参，但不能把它们冒充论文发表后的全新市场证据。即使两段都通过，当前结论上限仍为 `INSUFFICIENT_EVIDENCE`，需要冻结规则后的新前向区间再决定是否生成产品交接。

候选筛选、公式、时序、门槛和否定条件见 `preregistration.md`；来源适用性见 `sources.md`；实际命令和失败见 `attempts.md`；证据与限制见 `result.md`。

