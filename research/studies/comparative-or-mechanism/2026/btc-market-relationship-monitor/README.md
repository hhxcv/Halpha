# BTC 市场关联与相对强弱监测

研究问题：在固定的当前 Binance Spot USDT 原生加密对象名单中，哪些对象在最近 365 个已闭合 UTC 日收益上与 BTC 存在统计显著且有实际幅度的共同波动；这些对象的 BTC beta、波动倍数、7/30/90 日相对强弱和跨窗口稳定性如何？

本目录把已有成熟方法做成可持续更新、可扩展到当前更多币种的独立研究监测。它不是新统计方法，不预测未来收益，不证明因果或 Alpha，也不进入交易核心。当前结论在首次完整运行后写入 `result.md`，且只能使用研究流程允许的四类结论之一。

## 边界

- 研究类型：`COMPARATIVE_OR_MECHANISM`，最强主张仅为观察样本外仍需谨慎推广的关联与稳定性描述。
- 产品基准提交：`e2a4cf5372d5ce9984d86edd08c40b72e62026a4`。
- 正式策略基准：`ONE_SHOT_DONCHIAN_ATR_BREAKOUT` `1.0.1`；本问题不比较或修改该策略。
- 对象名单：`research/market-universe/universe.csv` 中快照时间为 `2026-07-21T06:42:30Z`、`market=BINANCE_SPOT`、`currently_trading=True`、`quote_asset=USDT`、`economic_exposure` 为 `CRYPTO_NATIVE` 或作为基准的 `CRYPTO_ANCHOR`。排除 BTC 自身、稳定/法币相对、代币化商品和 TradFi 衍生暴露。结果揭示后的语义审计另发现 36 个 bStock 因 Spot 缺 taxonomy 被上游默认成原生加密；当前固定快照以“默认来源、无 crypto subtype、base 以 B 结尾”的保守合取规则排除，显式保留已核对的原生加密 DGB 例外，并在输出 universe identity 保存精确名单。未来 universe 变化必须重新审核，不能把后缀规则当成永久 taxonomy。
- 行情：Binance 官方公开 Spot `1d` kline；只使用已闭合 UTC bar。跨源核对尝试对 BTC、ETH、SOL、SUI、DOGE 使用 Coin Metrics Community `PriceUSD` 日收盘；免费覆盖缺失的对象明确列为不可用，不替代主数据。
- 不读取产品数据、数据库、凭据或运行配置；不启动产品运行时；不调用任何交易所变更端点。
- 当前名单不是历史 point-in-time universe，因此结论只适用于当前仍在名单内且达到样本门槛的对象，保留幸存者偏差限制。

## 固定方法

完整启封前规则见 `checkpoint.md`。核心口径为：

1. 对齐每个对象与 BTC 的已闭合 UTC 日收盘，计算对数收益。
2. 主窗口取每对最多 365 个共同收益观测，最少 120 个；另报告最近 180 日、前一非重叠 180 日和 90 日滚动 Pearson 相关。
3. 报告 Pearson、Spearman、单因子 OLS `r_asset = alpha + beta * r_btc + error`、R-squared、残差波动和对象/BTC 波动倍数。
4. OLS beta 的推断使用 statsmodels HAC/Newey-West（Bartlett，7 lags，小样本修正）；所有对象的 beta 双侧 p 值统一用 Benjamini-Yekutieli 以 `q <= 0.05` 控制依赖检验的 FDR。
5. “统计显著”只表示 BY-FDR 通过；“强关联”另外要求 `abs(Pearson) >= 0.50`、Pearson 与 Spearman 同号，且最近/前一 180 日 Pearson 同号。效应阈值固定在看结果前，不把显著性等同于重要性。
6. 相对强弱是 7/30/90 日对象累计对数收益减 BTC 累计对数收益；它是截至 cutoff 的状态量，不是预测信号。

## 运行

研究虚拟环境和依赖锁位于 `research/.venv` 与 `research/requirements.txt`。默认缓存和持续刷新的最新页面状态都位于 Git 外：

`D:/projects/Codex/CodexHome/research-data/halpha/btc-market-relationship-monitor/`

其中固定 cutoff 的审核证据保存在本目录 `evidence/`；刷新默认写入 Git 外 `live/`，不会覆盖固定证据或持续制造工作树改动。页面优先读取 `live/`，尚无最新状态时回退到 `evidence/`。

一次刷新并生成 Git 外最新结果：

```powershell
research/.venv/Scripts/python.exe research/studies/comparative-or-mechanism/2026/btc-market-relationship-monitor/monitor.py refresh
```

启动独立只读页面（默认仅绑定 `127.0.0.1:8766`，避开当前核心本地端口；立即显示上次已验证快照并在后台刷新，以后每 15 分钟检查；日线指标只在新 UTC 日线闭合后变化）：

```powershell
research/.venv/Scripts/python.exe research/studies/comparative-or-mechanism/2026/btc-market-relationship-monitor/monitor.py serve --port 8766
```

该页面属于独立研究边界，由研究环境自行启停，不随 `start product` 启动，交易内核也不引用或控制它。服务绑定成功后会主动向通用外部服务登记目录写入 PID 和监听信息；仓库根目录的 `halpha-control status` 交叉核验后显示 `external:btc-market-relationship-monitor-8766` 和 `External Registration`，但不取得启停权。前台运行时用 `Ctrl+C` 停止，登记会随正常退出删除；`halpha-control stop all` 不会停止它。

离线重算已缓存数据：

```powershell
research/.venv/Scripts/python.exe research/studies/comparative-or-mechanism/2026/btc-market-relationship-monitor/monitor.py refresh --offline
```

测试：

```powershell
research/.venv/Scripts/python.exe -m unittest discover -s research/studies/comparative-or-mechanism/2026/btc-market-relationship-monitor/tests -v
research/.venv/Scripts/python.exe research/studies/comparative-or-mechanism/2026/btc-market-relationship-monitor/validate_results.py
```

上述验证默认只读，不改写固定证据。只有明确固定新的研究 cutoff 并完成审核时，才使用 `validate_results.py --write-report` 更新 `evidence/validation.json`。

## 产物

- Git 内：问题、检查点、来源、代码、测试、结果与限制，以及固定 cutoff 的 `evidence/` 规范化结果、摘要、验证 JSON 和桌面/窄屏截图。
- Git 外：`live/` 最新页面状态、逐 symbol 原始/规范化 kline 缓存、Coin Metrics 核对数据和每次不可覆盖的 source manifest；可用 manifest、SHA-256 和命令重取。
- 页面只读取本问题的 Git 外最新状态或固定证据回退；刷新失败时保留上次成功快照并明确显示陈旧/失败对象，不静默缩小宇宙。
