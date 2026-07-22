# TRXUSDT 永续月度一次性 8% 波动目标

## 状态与结论

研究类型为 `STRATEGY_CANDIDATE`，研究身份为 `RESEARCH_TRXUSDT_PERP_VOL60_TARGET8_MONTHLY_ONE_SHOT_V1`。结论为 `INSUFFICIENT_EVIDENCE`；开发门失败，评价和确认没有启封，不生成产品交接。

本题不是寻找新的 TRX 规则，而是检查已经有全新现货确认的 60 日/8%/最大 0.5 倍波动目标，改为当前产品使用的 Binance USD-M 永续、每月一次激活必须完整平仓后，实际 funding 和重复 round trip 是否会耗尽其很薄的资本门后余量。父现货路径已经暴露，所以即使通过，也只支持可移植性，不增加独立价格时间证据，更不承诺长期盈利。

写入仅在 `research/**`；不读取产品数据库、凭据、账户或运行配置，不启动产品运行时，不调用交易所变更端点。稳定产品基准为 `0bdfeffa616260cebd2d2188ddc8deb9e85c77f4`，正式策略背景为 `ONE_SHOT_DONCHIAN_ATR_BREAKOUT 1.0.1 / BTCUSDT-PERP`。

## 预定命令

```powershell
research\.venv\Scripts\python.exe research/studies/strategy-candidate/2026/trxusdt-perp-monthly-one-shot-voltarget/study.py checkpoint
research\.venv\Scripts\python.exe research/studies/strategy-candidate/2026/trxusdt-perp-monthly-one-shot-voltarget/study.py fetch
research\.venv\Scripts\python.exe research/studies/strategy-candidate/2026/trxusdt-perp-monthly-one-shot-voltarget/study.py inspect
research\.venv\Scripts\python.exe research/studies/strategy-candidate/2026/trxusdt-perp-monthly-one-shot-voltarget/study.py analyze --stage development
research\.venv\Scripts\python.exe research/studies/strategy-candidate/2026/trxusdt-perp-monthly-one-shot-voltarget/study.py gate --stage development
```

评价与确认命令只有在前一门通过后执行。Git 外原始缓存固定为 `D:/projects/Codex/CodexHome/research-data/halpha/trxusdt-perp-monthly-one-shot-voltarget/2026-07-22-v1/`。

目录保留 checkpoint、原始来源 manifest、数据质量、开发期完整目标/成本矩阵、逐月计划、门、结果、实际尝试和复现校验。数据质量修复和未启封阶段见 `attempts.md`，详细数字与反证见 `result.md`/`results.json`。

开发段主配置 base +7.63%、最大回撤 -9.89%，但 stress 扣 4% 年化资本门后为 -3.85%，因此没有达到预注册门槛。这个结果说明风险缩放仍有效，却没有足够余量证明永续 funding 与每月强制闭环后的长期经济价值。
