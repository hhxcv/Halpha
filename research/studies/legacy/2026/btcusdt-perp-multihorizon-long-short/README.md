# BTCUSDT 永续多周期双向趋势研究

## 状态

- 稳定基准：`de6b3052f28fe547730e89e58186d4ab397884b1`。
- 正式策略固定背景：`ONE_SHOT_DONCHIAN_ATR_BREAKOUT 1.0.0` on `BTCUSDT-PERP`；未运行不可比的激活重放。
- 候选：`RESEARCH_BTCUSDT_PERP_MULTIHORIZON_LONG_SHORT_MAX_0P25X`。
- 最终结论：`INSUFFICIENT_EVIDENCE`。开发门通过，但评估期 stress -0.13%、2023 -12.05%，且相对简单连续 0.25x 多头没有足够经济余量；确认期未解封。

问题、规则、否定条件、来源和数据身份已分别锁定在 `checkpoint.json`、`sources.md`。本目录只使用公开 Binance 市场数据；外部缓存不进入 Git，精确身份与重取来源均已记录。原始 funding 时间戳只允许在距最近 8 小时边界不超过 1 秒且无冲突时规范化，实际观察最大偏移 47ms。

## 可重演命令

在仓库根目录使用 Python 标准库运行，缓存路径可替换为包含相同 SHA-256 文件的副本：

```powershell
$cache = 'D:/projects/Codex/CodexHome/research-data/halpha/binance-positive-funding-cash-carry'
$manifest = 'research/studies/legacy/2026/binance-positive-funding-cash-carry/source_manifest_btc_evaluation.json'
python research/studies/legacy/2026/btcusdt-perp-multihorizon-long-short/study.py analyze --cache-dir $cache --source-manifest $manifest --phase development --output research/studies/legacy/2026/btcusdt-perp-multihorizon-long-short/development.json
python research/studies/legacy/2026/btcusdt-perp-multihorizon-long-short/study.py qualify-development --input research/studies/legacy/2026/btcusdt-perp-multihorizon-long-short/development.json --output research/studies/legacy/2026/btcusdt-perp-multihorizon-long-short/development_gate.json
```

仅当前一门的 JSON 中 `holdout_authorized=true` 时，才可把该文件作为 `--authorization` 运行下一阶段。大型原始数据不复制；锁定 manifest、官方 URL、逐文件 SHA-256、总文件数和字节数使其可核验与重取。

## 核心限制

单一交易场所、单一 BTC、规则级留出、确认期仅 8 个月；K 线无法重建盘口成交、延迟、mark price、清算阶梯、保证金模式或个人账户费率。0.25× 上限降低而不消除空头尾部和交易所风险；盈利回测不等于 Alpha 证明，也不授权产品或真实交易。

## 结果与反证

- 开发期 base/stress +7.40%/+7.13%，最大回撤 -13.07%；60/90/180 日分别 -0.61%/+15.69%/+4.48%，通过开发门。
- 评估期 base +0.33%、stress -0.13%，2023/2024 分别 -12.05%/+14.67%，最大回撤 -16.20%；funding 对初始资本贡献 -3.51%。连续 0.25x 多头同期 +54.92%。
- 最强支持只是早期资本保护及 2/3 窗口微正；最强反证是 stress、年度一致性和简单基准同时失败。未调窗口、权重、成本或门槛，确认期保持未打开。
- 从锁定 manifest 在 Git 外重跑的开发/门控/评估/门控四个内容摘要全部一致；重演目录 4 个文件、48,657 bytes。
