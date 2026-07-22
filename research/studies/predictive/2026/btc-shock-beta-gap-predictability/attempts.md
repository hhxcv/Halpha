# 实际尝试与失败留存

## 2026-07-21：开题与预注册

1. 读取当前 L2/L3/L4、研究 skill、研究总目录、市场对象快照和相关历史问题。
2. 查重确认：已有日频 BTC 关系展示只描述共同波动；已有 ETH 2h reversal、alt momentum、BTC/ETH momentum 和永续 TSMOM 的失败不能回答“BTC 冲击后去 beta 欠反应是否仍有下一 open 预测性”。
3. 联网查看同行评审论文、工作稿与 Binance 官方归档说明，形成 6 类候选；按个人小资金、短反馈、可证伪、数据可得、执行现实和与旧题差异，选择本题。
4. 从 `research/market-universe/universe.csv` 固定 2026-07-21 当前仍交易的 1 个 anchor + 15 个成熟/高活动永续；没有读取本题 5m 结果来筛币。
5. 固定主配置、7 个邻域反证、时间阶段、事件级推断、FDR、成本参照和 holdout 停止门。

在 `study.py` 完成并把 SHA-256 写回 `checkpoint.json` 前，不允许执行下载。任何结果启封后的经济逻辑变更必须新开问题，不能覆盖本记录。

## 2026-07-21：development 首次下载失败（无结果启封）

- 计划 240 个官方月文件；238 个通过官方 SHA-256，共 84,957,353 bytes。
- `BNBUSDT-5m-2024-09.zip` 和 `SUIUSDT-5m-2024-05.zip` 分别发生 HTTP `IncompleteRead`，没有进入分析或查看任何 beta-gap 结果。
- 原始失败完整保存在 `source_manifest_development.json`。该错误属于 checkpoint 允许的 download retry 范围；代码只把 `http.client.IncompleteRead` 加入既有三次重试，不改对象、时期、信号、目标、反证、成本或门。
- 修订前代码 SHA-256：`53e868f1cb08e9fbab93da1b2c09a521b0e0944fac218c4275420f970392f898`。修订后 hash 将在再次下载前写入 checkpoint。

## 待执行命令

```powershell
research/.venv/Scripts/python.exe research/studies/predictive/2026/btc-shock-beta-gap-predictability/study.py verify-plan
research/.venv/Scripts/python.exe research/studies/predictive/2026/btc-shock-beta-gap-predictability/study.py prepare --phase development
research/.venv/Scripts/python.exe research/studies/predictive/2026/btc-shock-beta-gap-predictability/study.py run --phase development
```

evaluation/confirmation 命令只有前一阶段门通过才执行；是否执行及实际输出将在这里追加，不能把计划写成已完成。

## 2026-07-21：development 下载、分析与复算

1. 第二次 `prepare` 复用 238 个已校验缓存，仅重新下载先前中断的 2 个文件；最终 240/240、85,688,452 ZIP bytes、0 failures。每个文件的 URL、官方/实得 SHA-256、字节数与缓存身份在 `source_manifest_development.json`。
2. 16 个标的各 131,904 根 5m bar，覆盖 2023-10-01 至 2024-12-31 23:55 UTC；完整网格、正价格、无重复、跨标的对齐均通过。
3. 主配置结果：1,562 个事件、+2.0756 bp、95% UTC 日 cluster CI [+0.0167, +4.1346] bp、p=0.0482；BTC/own-sign 基准分别 +2.3390/+2.3734 bp。
4. 预测门因未击败两个简单基准而失败；经济门因 +2.08 bp < 12 bp 而失败；结论 `DOES_NOT_SUPPORT`、`release_next_phase=false`。
5. 重新执行同一 `run --phase development`，主均值、CI、事件数、两个基准、结论和 release 决策逐值完全一致。最终 `development.json` SHA-256 为 `dfb3eec79b8503df7bdfa99ae6e9aab77aa0cded46cdc1e8386165bda86c8785`；最终 manifest SHA-256 为 `847588d0721c162374b794bc6720dced970c94095bebc1c0d9c965bc59737b81`。
6. 没有执行 evaluation/confirmation 下载；没有搜索 positive-only、DOGE-only、新阈值、新窗口或资产子集。

实际执行命令：

```powershell
research/.venv/Scripts/python.exe research/studies/predictive/2026/btc-shock-beta-gap-predictability/study.py self-test
research/.venv/Scripts/python.exe research/studies/predictive/2026/btc-shock-beta-gap-predictability/study.py verify-plan
research/.venv/Scripts/python.exe research/studies/predictive/2026/btc-shock-beta-gap-predictability/study.py prepare --phase development --workers 4
research/.venv/Scripts/python.exe research/studies/predictive/2026/btc-shock-beta-gap-predictability/study.py run --phase development
```
