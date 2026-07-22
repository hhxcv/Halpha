# 审计执行记录

## 2026-07-21：范围固定

- 本审计在三项新 predictive 问题完成后进行，明确是事后综合，不伪装成预注册预测。
- 固定当前 L4、BTC 描述研究、5 项历史策略研究、3 项新结果和 2 个官方数据 manifest 的 hash。
- 审计只回答“当前约束下是否有新 BTC-correlation 候选”，不把不同机制的 carry 支持据为相关性 Alpha，也不宣称穷尽所有市场数据或未来制度。

计划命令：

```powershell
research/.venv/Scripts/python.exe research/studies/comparative-or-mechanism/2026/btc-correlation-opportunity-frontier/audit.py
```

## 2026-07-21：实际审计

- 12 个固定输入（当前 L4、描述关系、5 个历史策略结果、3 个新 predictive 结果、2 个源 manifest）全部通过 SHA-256。
- 当前正式策略身份解析为 `ONE_SHOT_DONCHIAN_ATR_BREAKOUT 1.0.1`。
- 两个 manifest 合并去重后为 420 个官方月 ZIP、144,160,250 bytes。
- 三项新 predictive 结论均为 `DOES_NOT_SUPPORT` 且 `release_next_phase=false`；carry 的 `SUPPORTS_WITHIN_SCOPE` 被明确保留为独立 funding 机制。
- 审计结论 `DOES_NOT_SUPPORT`；`new_btc_correlation_strategy_candidate=false`、`current_scope_substantially_covered=true`。
- 完整复跑生成相同字节：`audit.json` SHA-256 `c3a903658fd40cc3b58342f3a98eef336fed6cf7bb929c4f88ed72a398ea0640`。

## 2026-07-23：产品基线漂移复验

- 在基于最新 `main` 准备集成时，旧审计因直接读取工作树中的 L4 而报告 SHA-256 不一致；研究证据本身没有变化。
- 根因是执行实现没有落实 checkpoint 已声明的 `baseline_commit`，会错误依赖产品后续提交，违反稳定研究基线约束。
- 审计改为通过 Git 对象读取基准提交中的 L4，并同时记录当前工作树 L4 的 hash 与是否匹配；产品漂移不再改变历史结论，基准对象缺失或基准内容不匹配仍会失败。
- 随后发现关系监控结果文件的 hash 已因其 checkpoint 明确记录的“代币化证券 taxonomy 修订”而变化。先独立运行 `validate_results.py`，402 个已分析对象、385 个显著对象、238 个强关联对象、四个重点币复算和跨源核对均通过，再将当前结果 hash 重新封存；这不是按收益或相关数值调参，结论和分析身份 `581d0b3361cdfb4d404b24cd49aef04d2b69da258c6f46930a0133134e9055fb` 均未改变。
- 修订后审计通过，仍为 `DOES_NOT_SUPPORT`；420 个去重官方月 ZIP、144,160,250 bytes。新 `audit.json` SHA-256 为 `b3d6d416138432eefc43cd52626e4d59630148a91dbf0860c695a0b487093b78`，审计代码 SHA-256 为 `37eb47968e97c3e8ebeefe8ee81a3508bfca69124daec72a4cafde184dd297f2`。
