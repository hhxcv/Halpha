# 一周高点距离底部五分位单腿 SHORT

本目录研究一个框架无关候选：在固定的 25 个当前长期、较高活动 Binance USD-M 永续中，以完整前一周周日收盘相对最近七个完整日最高盘中价的对数距离 `HMOM7 = ln(close / max(high))` 排名；用户固定目标只有位于底部五分位时，才提出一次 `0.5x SHORT / 7d` 计划。

问题来自 Fičura 的流动币 high-momentum 研究。该论文在 2017-06 至 2022-12 的大且流动币中报告 `HMOM1W` Q5-Q1 下一周收益差 `2.68%`、Newey-West t 值 `4.93`，并指出可利用性主要依赖做空 Q1。Halpha 不复制其全市场、市值加权现货组合；本题只检验当前幸存永续、固定目标、单腿、实际 funding 和个人零售成本转换。

规则、候选筛选、顺序门和否定条件见 `preregistration.md`；来源与适用差异见 `sources.md`；所有命令、失败和修正见 `attempts.md`。大型公开输入复用既有 Git 外缓存，原始论文另存于：

`D:/projects/Codex/CodexHome/research-data/halpha/_sources/impact-size-volume-crypto-momentum-reversal-ffa-2023.pdf`

本目录不修改核心交易、L4、配置、产品数据库、凭据、资金或真实账户，也不调用任何交易端点。

