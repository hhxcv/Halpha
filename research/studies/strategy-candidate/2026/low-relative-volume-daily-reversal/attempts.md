# 实际尝试

## 2026-07-22 选题前

- 只读核对基准 `0bdfeffa616260cebd2d2188ddc8deb9e85c77f4`、正式策略 `ONE_SHOT_DONCHIAN_ATR_BREAKOUT 1.0.1`、TRADEPLAN 单次激活语义、研究目录和 33 项历史问题。
- 关闭 BTC 冲击/残差/lead-lag 近邻继续调参；已有新一轮四项预测结果均不支持策略升级。
- 联网检查同行评审的低 volume reversal、crypto return/volume 样本外研究、perpetual basis/funding 原始研究、Binance 官方市场数据和 VectorBT 文档。
- 在查看本题历史结果前固定六个长期合约、一个主配置、一个 60 日文献敏感性、成本、时序和顺序门。

后续命令、返回、门结果、任何代码修复与复跑在实际发生后追加；不把失败下载或运行静默覆盖。

## 2026-07-22 首次取数失败

- 命令：`research\.venv\Scripts\python.exe research/studies/strategy-candidate/2026/low-relative-volume-daily-reversal/study.py fetch`
- 结果：约 50.5 秒后在 `ALGOUSDT` funding 分页的 HTTPS response read 阶段 `TimeoutError`；尚未生成 `source_manifest.json`，没有执行完整性检查或任何收益计算。
- 留存：成功返回的原始页仍在固定 Git 外缓存，重跑时必须逐字节相同才复用，不能静默覆盖。
- 允许修复：把单次 45 秒请求改为最多 4 次、90 秒读取超时和有限退避。经济规则、阶段、资产、数据 cutoff、成本和门槛不变；原 checkpoint 及其初始代码 hash 保留为时间锚，修复后的代码 hash 会进入最终结果。

## 2026-07-22 成功取数与完整性

- 修复后同一 `fetch` 命令成功；每币 2 个 Kline 页、6 个 funding 页，`source_manifest.json` SHA-256 `57f63438fef28c70fe4c7ed9f345b700e0c70058e3f9cf1798c71054107c82b3`。
- Git 外缓存共 48 文件、4,319,771 bytes，位于 `D:/projects/Codex/CodexHome/research-data/halpha/low-relative-volume-daily-reversal/2026-07-22-v1/`。
- `inspect`：六币各 1,703 根 1d bar、5,109 条 funding；日线缺口、重复后的缺失、非正 OHLC 和无效 range 均为 0，结论 `PASS`。

## 2026-07-22 development、门和停止

- `analyze --stage development`：主配置 152 笔；同时完整保存无 volume filter 反转、同事件 momentum 和 60 日 volume window 三项事前诊断。
- `gate --stage development`：样本数和至少 4/6 标的为正通过；base 总收益、stress 总收益、bootstrap 下界和 volume 增量失败，状态 `FAIL`。
- `combine`：`DOES_NOT_SUPPORT`。未运行 evaluation/confirmation；没有用盈利标的、60 日窗口或无条件反转替换主配置。
- 重要结果：主配置 base/stress -23.61%/-35.50%，base 最大回撤 -57.32%，base 日均 bootstrap 95% `[-0.1970%, +0.1734%]`；2021/2022 base +17.09%/-34.76%；主配置相对无 volume filter 的 base 日均增量 -0.1435pp。

## 2026-07-22 重演

- 从现有固定缓存再次顺序执行 `analyze --stage development`、`gate --stage development`、`combine`。
- 152 笔、base 总收益、bootstrap 下界逐值一致；`development_trades.csv` 两次 SHA-256 均为 `42fb9245082e095575c10ecca479b3a49be6268ac6677d4a60968e91398a0dc9`。
- 输出 JSON 含实际生成时间，因此完整文件 hash 会变化；结论、门和确定性结果未变化。
