# CTREND 周频顶部五分位单腿 LONG

本目录研究一个框架无关的策略候选：按论文 CTREND 思路，用 28 个仅由日线 OHLCV 构造的技术指标、52 周滚动横截面回归和 elastic net 组合预测；用户固定的 Binance USD-M 永续只有在其周度预测位于事前固定流动名单顶部五分位时，才提出一次 `0.5x LONG / 7d` 计划。

它不是正式策略，也不修改交易核心。论文的多币 long-short 组合结果不能直接代表这里的单目标 one-shot 转换；本题必须另外面对真实 funding、零售成本、全计划资本门槛、简单动量/均线/市场基准、模型稳定性和顺序时间门。

主要文件：

- `preregistration.md`：候选筛选、固定问题、配置、门槛与否定条件。
- `sources.md`：先行外部研究、官方数据与框架资料。
- `study.py`：可重演的数据身份、特征、滚动训练、回测、门控和验证代码。
- `attempts.md`：所有重要尝试、失败和修改记录。
- `checkpoint.json`：任何 CTREND 收益输出之前的冻结身份。
- `source_reuse_manifest.json`：复用上游公开 Binance 文件的逐文件身份。
- `source_supplement_manifest.json`：Git 外早期日线补充数据的 URL、字节和 SHA-256。
- `data_quality_development.json`、`development.json`、`development_gate.json`：顺序开发证据。
- `results.json`、`result.md`、`validation.json`：最终结论、反证和复现检查。

外部大数据仅放在 `D:/projects/Codex/CodexHome/research-data/halpha/ctrend-weekly-top-quintile-one-shot-long/2026-07-22-v1/`，不进入 Git；manifest 保留可重取身份。
