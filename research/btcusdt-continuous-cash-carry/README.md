# BTCUSDT 连续 fully-funded cash-and-carry

- 基准提交：`de6b3052f28fe547730e89e58186d4ab397884b1`。
- 候选：`RESEARCH_BTCUSDT_CONTINUOUS_CASH_CARRY_FULLY_FUNDED`。
- 最终结论：`INSUFFICIENT_EVIDENCE`。开发与评估门通过；确认期绝对收益为正，但未覆盖预注册 4% 年化资本门槛。

问题是：不预测 funding、不中途切换，持续持有等 BTC 数量的 spot long / USD-M perpetual short，能否在两腿成本、basis、实际 funding 和 4% 资本机会成本后稳定为正。完整规则、门、数据身份、来源和限制见 `checkpoint.json` 与 `sources.md`。

## 可重演命令

```powershell
$cache = 'D:/projects/Codex/CodexHome/research-data/halpha/binance-positive-funding-cash-carry'
$manifest = 'research/binance-positive-funding-cash-carry/source_manifest_btc_evaluation.json'
python research/btcusdt-continuous-cash-carry/study.py analyze --cache-dir $cache --source-manifest $manifest --phase development --output research/btcusdt-continuous-cash-carry/development.json
python research/btcusdt-continuous-cash-carry/study.py qualify-development --input research/btcusdt-continuous-cash-carry/development.json --output research/btcusdt-continuous-cash-carry/development_gate.json
```

后一阶段必须传入前一门控文件且其中 `holdout_authorized=true`。缓存留在 Git 外，研究目录记录 manifest 内容身份、SHA-256、文件数、字节数和官方重取来源。

## 结果、反证与限制

- 开发 base +28.54%，扣 4% 年化资本门槛后 +20.54%；2021/2022 均正。评估 base +32.03%，扣门槛后 +24.02%；2023/2024 均正。
- 2025-01 至 2025-08 确认 base/stress +1.73%/+1.57%，但扣资本门槛后 -0.93%/-1.09%，直接未过支持门；funding +1.96%、basis +0.006%、最大回撤 -0.13%。
- 最强支持是三个阶段 raw 均正、funding 主导、basis 很小且区间均值 bootstrap 下界为正；最强反证是后期经济收益压缩到低于资本机会成本。
- 同 bar 现货最低与永续最高的保守机械组合在开发/评估达 -22.42%/-34.78%；两极值不一定同时发生，不能当实际路径，但明确表明 8h bar 无法验证腿风险、保证金或清算安全。
- Git 外重演目录包含 6 个文件、20,865 bytes；三阶段、两门和最终结果的 `content_digest` 全部一致。
