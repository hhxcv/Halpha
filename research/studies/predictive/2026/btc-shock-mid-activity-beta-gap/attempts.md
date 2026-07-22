# 尝试与复现

## 2026-07-21：开题

- 父题成熟币 lead-lag 和小时级 residual reversal 均已固定为 `DOES_NOT_SUPPORT`。
- 按市场快照的可审计规则选择 12 个中等活动、长历史、当前窄 spread、非官方 meme 的原生币；未用本题价格或结果筛选。
- 复用父题锁定分析函数和 Binance downloader，避免复制/漂移核心计算；wrapper 固定父代码 hash，并把 12 个 symbol 注入相同口径。
- 本题会把 BTC 与 12 个币共 13×15=195 个官方月文件写入独立 manifest；已有 BTC cache 只复用并重新校验。

计划命令：

```powershell
research/.venv/Scripts/python.exe research/studies/predictive/2026/btc-shock-mid-activity-beta-gap/study.py self-test
research/.venv/Scripts/python.exe research/studies/predictive/2026/btc-shock-mid-activity-beta-gap/study.py verify-plan
research/.venv/Scripts/python.exe research/studies/predictive/2026/btc-shock-mid-activity-beta-gap/study.py prepare --phase development --workers 4
research/.venv/Scripts/python.exe research/studies/predictive/2026/btc-shock-mid-activity-beta-gap/study.py run --phase development
```

## 2026-07-21：development

1. 195 个文件全部通过官方 checksum，共 64,503,862 ZIP bytes；BTC 15 个复用 verified cache，12 币 180 个首次下载，0 failures。
2. 13 个标的各 131,904 根 5m bar，完整网格、正价格、无重复并跨标的对齐。
3. 主配置：1,470 事件、+2.4094 bp、CI [-0.3933,+5.2120]、p=0.0920；BTC/own-sign 基准 +2.3607/+2.6831 bp。
4. 预测门因 CI 下界、own-sign 增量失败；经济门因 2.41 < 12 bp 失败；结论 `DOES_NOT_SUPPORT`，不启封后续。
5. 5m 目标的 +1.9776 bp 虽 nominal 显著，但 own-sign 为 +2.0393 bp、远低成本；额外一根 bar 后 +0.2492 bp。12 币 BY-FDR 无显著结果，未筛个币。
6. 同一命令复算，主均值、CI、事件数、两个基准、release 和结论逐值一致。

最终身份：

- 代码 SHA-256：`6690b380465717696c790baa3bfda89876c99bd432c92002470eafd992676709`
- `development.json`：`4553b4ee1ddd6dd0a0d2020589a003ec2fb0c2c9e5f76ad40f4d1596ee974ae4`
- `source_manifest_development.json`：`15c5509240d118b7db10bd43f7a1655507c89ab0b47c5cd87392f715537d5528`
- evaluation/confirmation：未下载、未查看。
