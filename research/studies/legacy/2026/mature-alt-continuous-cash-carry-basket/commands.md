# 可重演命令

以下命令从仓库根目录在 PowerShell 中执行。它们只读取锁定的公开数据缓存，并把结果写回本研究目录；不会读取产品数据库、凭据或运行配置，也不会启动产品运行时。

```powershell
$q = 'research/studies/legacy/2026/mature-alt-continuous-cash-carry-basket'
$historicalCache = 'D:/projects/Codex/CodexHome/research-data/halpha/multi-asset-persistent-funding-carry'
$confirmationCache = 'D:/projects/Codex/CodexHome/research-data/halpha/mature-alt-continuous-cash-carry-basket'
$historicalManifest = 'research/studies/legacy/2026/multi-asset-persistent-funding-carry/source_manifest_development_backfilled.json'

python "$q/study.py" analyze --cache-dir $historicalCache --manifest $historicalManifest --phase development --output "$q/development.json"
python "$q/study.py" qualify-development --input "$q/development.json" --output "$q/development_gate.json"
python "$q/study.py" analyze --cache-dir $historicalCache --manifest $historicalManifest --phase evaluation --authorization "$q/development_gate.json" --output "$q/evaluation.json"
python "$q/study.py" qualify-evaluation --input "$q/evaluation.json" --output "$q/evaluation_gate.json"
python "$q/study.py" analyze --cache-dir $confirmationCache --manifest "$q/source_manifest_confirmation.json" --phase confirmation --authorization "$q/evaluation_gate.json" --output "$q/confirmation.json"
python "$q/study.py" combine --development "$q/development.json" --evaluation "$q/evaluation.json" --evaluation-gate "$q/evaluation_gate.json" --confirmation "$q/confirmation.json" --output "$q/results.json"
```

若 Git 外确认缓存丢失，可从 Binance 官方公开归档和公开 REST 数据重新获取；下载身份须与 `checkpoint.json` 和 `source_manifest_confirmation.json` 核对后才能分析：

```powershell
python research/studies/legacy/2026/multi-asset-persistent-funding-carry/study.py fetch --cache-dir $confirmationCache --universe core --start-month 2024-01 --end-month 2025-09 --manifest "$q/source_manifest_confirmation.json"
```

已完成的独立重演使用 `D:/projects/Codex/CodexHome/research-data/halpha/mature-alt-continuous-cash-carry-basket-repro/` 存放六个输出文件。比较时忽略 `generated_at`，六个 `content_digest` 必须与本目录一致；记录见 `attempts.md`。
