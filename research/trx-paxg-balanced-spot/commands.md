# 可重演命令

以下命令从仓库根目录在 PowerShell 中执行。三段数据严格按“上一阶段通过后才释放下一阶段”的顺序处理；只使用 Binance 官方公开现货日线归档。

```powershell
$q = 'research/trx-paxg-balanced-spot'
$cache = 'D:/projects/Codex/CodexHome/research-data/halpha/trx-paxg-balanced-spot'

python "$q/study.py" analyze --cache-dir $cache --manifest "$q/source_manifest_development.json" --phase development --output "$q/development.json"
python "$q/study.py" qualify-development --development "$q/development.json" --output "$q/development_gate.json"
python "$q/study.py" analyze --cache-dir $cache --manifest "$q/source_manifest_evaluation.json" --phase evaluation --authorization "$q/development_gate.json" --output "$q/evaluation.json"
python "$q/study.py" qualify-evaluation --evaluation "$q/evaluation.json" --output "$q/evaluation_gate.json"
python "$q/study.py" analyze --cache-dir $cache --manifest "$q/source_manifest_confirmation.json" --phase confirmation --authorization "$q/evaluation_gate.json" --output "$q/confirmation.json"
python "$q/study.py" combine --development "$q/development.json" --evaluation "$q/evaluation.json" --evaluation-gate "$q/evaluation_gate.json" --confirmation "$q/confirmation.json" --output "$q/results.json"
```

若 Git 外缓存丢失，三段分别重新获取。每一段下载后均须先核对 `checkpoint.json` 中对应的 manifest SHA-256、内容身份、文件数和字节数，再运行该段分析：

```powershell
python "$q/study.py" fetch --cache-dir $cache --start-month 2021-01 --end-month 2022-12 --manifest "$q/source_manifest_development.json"
python "$q/study.py" fetch --cache-dir $cache --start-month 2023-01 --end-month 2024-12 --manifest "$q/source_manifest_evaluation.json"
python "$q/study.py" fetch --cache-dir $cache --start-month 2025-01 --end-month 2026-06 --manifest "$q/source_manifest_confirmation.json"
```

已完成的独立重演在 Git 外生成六个输出文件。比较时忽略 `generated_at`，三阶段、两道门和最终结果的 `content_digest` 必须全部与本目录一致；清单见 `attempts.md`。
