# 实际尝试

- 2026-07-22：完成现有研究去重、外部调研、固定问题、两个方向候选、成本、顺序时间门和停止条件；尚未查看本规则结果。
- 2026-07-22：在固定 `study.py` SHA-256 `cc8fac83d6cbe107a50550f74b571e4963481d8ae2f3a48d542be0cac3d63f7e` 后运行开发期：

  ```powershell
  research/.venv/Scripts/python.exe study.py analyze --phase development --cache-root D:/projects/Codex/CodexHome/research-data/halpha/btcusdt-next-funding-carry --manifest ../../../legacy/2026/btcusdt-next-funding-carry/source_manifest.json --output-dir .
  research/.venv/Scripts/python.exe study.py select-development --input development.csv --output selection.json
  ```

  四行完整矩阵均为负；LONG/SHORT 方向过滤的 base 均值分别为 -0.329638%/-0.372200%，比同方向未过滤基准分别差 0.496/0.355 bps。门结果为 `gate_pass_count=0`、`evaluation_authorized=false`，按预定规则停止，未运行 evaluation 或 confirmation。
- 2026-07-22：把同一固定命令重演到独立临时输出目录。重演 `development.csv` SHA-256 为 `6da9891eeb82b2dc656326c5c1f59208923f8569c3ec5fc39b427cf6c1d99322`，与保存结果完全一致；重演选择门仍为 0 项通过和 `NO_TAKER_FLOW_DIRECTION_PASSED_DEVELOPMENT_GATE`。JSON 的生成时间允许变化，经济结果和门语义未变化。
- 允许修复仅限路径、解析、字段完整性、内容身份或明显不改变经济规则的实现错误；任何过滤、阈值、时间或成本变化必须保留旧结果并作为新问题处理。

最终结论：`DOES_NOT_SUPPORT`。未追加结果驱动参数，未启封后续区间，也未形成产品交接材料。
