# 核验日志

## 2026-07-22

1. 读取当前 L4，确认当前 venue/instrument/正式策略边界与第二正式策略排除项；记录文件 SHA-256。
2. 读取冻结 legacy catalog 和 `research/README.md` 的方法审计；确认 3 个支持项并非 3 个独立 Alpha。
3. 逐项读取 3 个支持候选 README/results；读取 TRX 永续转换和当前最接近的 CTREND、PPC、高波动 short 结果。
4. 递归扫描 `research/studies/**/handoff*.json`，结果为 0。
5. 把最新 RMOM 预测门的否定证据纳入前沿；未把预测研究当作策略。
6. 使用 `Get-FileHash -Algorithm SHA256` 记录所有关键证据身份；没有重跑或改写任何历史研究。
7. `frontier.json` 解析 PASS；实际 handoff 文件数 0；frontier SHA-256 `2f6989ceecd84269783e71b5458fd99574ab82b5697e97cac9a56f20a766e454`。

复核命令：

```powershell
Get-ChildItem research/studies -Recurse -File -Filter 'handoff*.json'
rg -n 'SUPPORTS_WITHIN_SCOPE|INSUFFICIENT_EVIDENCE|DOES_NOT_SUPPORT' research/studies -g 'result.md' -g 'README.md'
Get-FileHash -Algorithm SHA256 docs/L4/HALPHA-PLAN-001-current-plan.yaml
Get-FileHash -Algorithm SHA256 research/catalog-2026-07-21.json
Get-Content research/studies/comparative-or-mechanism/2026/strategy-candidate-qualification-frontier/frontier.json -Raw | ConvertFrom-Json | Out-Null
```
