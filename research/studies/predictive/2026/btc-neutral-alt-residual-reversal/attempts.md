# 尝试与复现

## 2026-07-21：开题

- 在父问题 `DOES_NOT_SUPPORT` 后，拒绝结果驱动的 positive-only、DOGE-only 和近邻阈值优化。
- 联网核对经典 pairs/stat-arb、crypto pairs 和近期 Binance 永续 copula 研究。
- 选择慢速、去 beta、下一 open 的极端 residual reversal；固定 1 个主配置和 9 个一项一变反证。
- development 复用父问题 240 个已校验 ZIP，不重复下载；checkpoint 固定父 manifest hash。
- 在 `study.py` hash 回写 checkpoint 之前，不运行小时级结果。

计划命令：

```powershell
research/.venv/Scripts/python.exe research/studies/predictive/2026/btc-neutral-alt-residual-reversal/study.py self-test
research/.venv/Scripts/python.exe research/studies/predictive/2026/btc-neutral-alt-residual-reversal/study.py verify-plan
research/.venv/Scripts/python.exe research/studies/predictive/2026/btc-neutral-alt-residual-reversal/study.py run --phase development
```

## 2026-07-21：development 复用、结果与尾部审计

1. `verify-plan` 同时通过本题代码、父题代码和父题 manifest hash；240 个共享 ZIP、85,688,452 bytes 再次逐文件与官方 SHA-256/字节数核对，0 新下载。
2. 每标的 131,904 根 5m 聚合成 10,992 个完整 UTC 小时；每小时恰 12 根，16 个标的完全对齐。
3. 主配置：919 事件小时、1,249 资产事件；均值 -10.6107 bp、中位数 +25.7769 bp、95% 周聚类 CI [-34.7969,+13.5754] bp；同事件 raw reversal -2.9680 bp；favorable/base/stress paired floor 24.7507/66.0019/107.2530 bp。
4. 事前 9 个扰动全部保留。z=2 的均值 -16.6188 bp 且 CI 完全低于零；4h/24h 目标虽均值略正，但 CI 跨零且远低于 favorable cost。开发门失败，`release_next_phase=false`、`DOES_NOT_SUPPORT`。
5. 尾部审计：事件均值 1%/5% 分位 -1,437.55/-694.25 bp；最差 `2024-12-03T18:00Z` 为 -2,240.44 bp（TRX -3,449.17、BNB -1,031.71 bp）。另有 2024-03-05/06 与 2024-11/12 的 XRP、NEAR、DOGE、LINK、ADA 持续扩张事件。它们与 H2 山寨币单边行情一致，说明均值被真实路径依赖尾部主导，而非单个 CSV 缺口。
6. 正 formation residual 反转显著为负，负 residual 反转显著为正；不据此创建 sign-only 变体，因为方向由 development 结果选择且 base 成本仍不满足。个币 BY-FDR 无显著结果。
7. 同一命令完整复算，均值、中位数、CI、事件/资产事件数、基准、成本、结论和 release 决策逐值一致。

最终身份：

- 代码 SHA-256：`40234191169a3d8b9a1d5411f885ee2acb3eb4892cd09669e39a2c3a94f502fb`
- `development.json`：`cf3eb584e4addcd5b94e8675bef2a9d3725c6dfd774b82b43fba06ce09a46c83`
- `source_reuse_manifest_development.json`：`452e949107f9d4cc8d0b92d6df6bc2caaf7336472b173c87f5303865d775f663`
- evaluation/confirmation：未下载、未查看。
