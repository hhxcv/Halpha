# 可重演命令

以下命令从仓库根目录在 PowerShell 中执行。开发与评估是已披露的校准证据；只有确认阶段是全新留出证据。命令只使用公开现货日线数据，不接触产品运行时或账户。

```powershell
$q = 'research/trxusdt-voltarget-8pct-long'
$developmentCache = 'D:/projects/Codex/CodexHome/research-data/halpha/trxusdt-spot-monthly-tsmom'
$evaluationCache = 'D:/projects/Codex/CodexHome/research-data/halpha/trxusdt-voltarget-monthly-tsmom'
$confirmationCache = 'D:/projects/Codex/CodexHome/research-data/halpha/trxusdt-voltarget-8pct-long'
$developmentManifest = 'research/trxusdt-spot-monthly-tsmom/source_manifest_development.json'
$evaluationManifest = 'research/trxusdt-voltarget-monthly-tsmom/source_manifest_evaluation.json'

python "$q/study.py" analyze --cache-dir $developmentCache --manifest $developmentManifest --phase development --output "$q/development.json"
python "$q/study.py" analyze --cache-dir $evaluationCache --manifest $evaluationManifest --phase evaluation --output "$q/evaluation.json"
python "$q/study.py" qualify-calibration --development "$q/development.json" --evaluation "$q/evaluation.json" --output "$q/calibration_gate.json"
python "$q/study.py" analyze --cache-dir $confirmationCache --manifest "$q/source_manifest_confirmation.json" --phase confirmation --authorization "$q/calibration_gate.json" --output "$q/confirmation.json"
python "$q/study.py" conclude --development "$q/development.json" --evaluation "$q/evaluation.json" --calibration-gate "$q/calibration_gate.json" --confirmation "$q/confirmation.json" --output "$q/results.json"
```

若 Git 外确认缓存丢失，按下列命令从 Binance 官方公开归档重新获取，并在分析前核对 `checkpoint.json` 中的 manifest SHA-256、内容身份、文件数与字节数：

```powershell
python "$q/study.py" fetch --cache-dir $confirmationCache --start-month 2024-04 --end-month 2026-06 --manifest "$q/source_manifest_confirmation.json"
```

已完成的独立重演在 Git 外生成五个输出文件。比较时忽略 `generated_at`，开发、评估、校准门、确认和最终结果的 `content_digest` 必须全部与本目录一致；清单见 `attempts.md`。
