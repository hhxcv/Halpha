# 实际尝试

- 2026-07-22：扫描 `research/studies/**` 的 BTCUSDT、Donchian、trend、持仓期和 `max_hold_bars_15m`。确认父问题已否定 1 小时下的全部入场近邻；历史 96×15m 代理也为负，但 2/4/8 小时未被同一固定规则成组运行。
- 2026-07-22：核对当前正式默认参数、父问题代码/完整开发矩阵、历史 96×15m 评价产物及各自 SHA-256；不读取任何新持仓期结果。
- 2026-07-22：联网核对近期 crypto Donchian、日内趋势与多个预测期限的原始论文/预印本，并据此保持问题为“少量持仓期限”，不引入动态选币、trailing stop、波动 sizing 或第二套产品策略。
- 2026-07-22：在查看结果前锁定 6 个新候选、两个已暴露边界基准、固定入场/止损/止盈、三种成本、顺序时期、选择门与停止规则。
- 2026-07-22：研究脚本通过 `py_compile`、Ruff 和 CLI 装载检查；首次结果前封存 SHA-256 `0a2a7d8c324622f58ce4aa40ae9af73aa24cb52397352ebe06d1fd84ba36ab9c`。
- 2026-07-22：完整运行 development 10 行（6 个新候选 + 4 个已暴露基准）；6 个新候选在 favorable、base、stress 均无正均值，选择门返回 0，`evaluation_authorized=false`，因此未读取 evaluation 或 confirmation。
- 2026-07-22：逐字段核对同一 runner 的 1 小时 LONG/SHORT 基准与父研究正式默认行，共 62 个数值零差异；研究脚本 SHA-256 保持封存值。
- 2026-07-22：在 Git 外独立目录重放 development 与选择门；`development.csv` SHA-256 完全一致，去除生成时间后 `development.json`、`selection.json` 语义完全一致，仍为 0 个通过者且 evaluation 未授权。
