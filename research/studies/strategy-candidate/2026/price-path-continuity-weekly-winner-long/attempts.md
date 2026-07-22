# 实际尝试与失败

- 2026-07-22：先查重现有 19 个新流程策略问题及 32 个 legacy 问题；普通 momentum、风险调整 momentum、MAX、低波、premium/funding 单腿和中期反转邻域已有失败或证据不足，未重复近邻阈值。
- 2026-07-22：联网取得并完整核对 Kim 2026 PPC 论文 30 页版本。普通 HTTP/REST 下载被 Cloudflare 403 阻止；使用真实浏览器完成只读页面访问后取得 SSRN 签名 PDF，存入 Git 外源目录并记录 356,354 bytes、SHA-256 `61eed44eb1a6fe3904eecf3ec6b80a587cdcd0b960b75fe1fd56422313f2bb69`。
- 2026-07-22：用文本提取与页面渲染双重核对公式页、组合排序表、形成/持有期稳健表和替代连续性定义；未根据搜索摘要猜测公式。
- 2026-07-22：发现论文显著性主要在 `winner-minus-loser` 与交互项，连续赢家自身 alpha 不显著；因此放弃裸空/多腿表达，冻结“PPC 是否改善单目标 MOM14 多头”的更强否证问题。
- 2026-07-22：checkpoint `d1173deb1f62dca2e90a37a9031d0232c524e29263d0190ae87a652911cbabce` 后，self-test 通过：连续上涨/下跌 PPC 均为 1，单次正跳跃且多数小跌的路径 PPC 为 -0.980952；VectorBT/手工误差 `1.734723475976807e-17`；funding stress 方向通过。
- 2026-07-22：首次只运行 development `prepare`，尚未计算任何收益。所有源完整性检查通过，但 2024-11-04 只有 19 个目标通过资格门。实现错误地把冻结规则的“该周全局 NO_ACTION”升级为整阶段数据失败，而 `build_panel` 已按相同规则跳过该周。记录 `amendment-001.json`，只修正 source-quality 分支和审计字段，不改变目标、公式、阈值、时序、成本、阶段或任何收益规则。
- 2026-07-22：development 首次 `analyze` 已计算各变体交易文件，但在写入汇总前因 `scheduled_long` 诊断的隔周 cooldown `NO_ACTION` 报错；没有生成 `development.json` 或 gate。记录 `amendment-002.json`：只允许该非门控诊断把明确的基准 NO_ACTION 周记为现金 0，并记录填充数量；MOM14 与无冷却 market 基准仍要求严格同日期覆盖，主交易、收益、成本和门均不变。
- 2026-07-22：amendment 链通过后重跑 development。数据质量 PASS；51 个 panel 周，2024-11-04 全局 NO_ACTION；主规则 109 个计划机会、21 个 cooldown skip、88 笔、40 个入场周、24 个目标，mark/funding 排除 0。
- 2026-07-22：base/stress 扣门日期均值 +0.5997%/+0.5057%，但 stress 95% `[-0.9884%, +2.6665%]`；H1/H2 -0.6768%/+2.0107%。base 相对 MOM14 +0.2623%，95% `[-0.4079%, +1.1145%]`；gross 相对市场 +0.4718%，95% `[-0.4375%, +1.7110%]`。
- 2026-07-22：只有 2/6 类别为正、至少两笔目标的正比例 40%；XLM/HBAR 分别占正贡献 35.43%/28.32%。development gate FAIL，结论 `INSUFFICIENT_EVIDENCE`；2025 evaluation 未打开，handoff 未生成。
- 2026-07-22：development 完整重演后证据 digest 再次为 `92c5cb161412af9d74002b757e46425c609b3de7109f510deaa081426a74c985`，数值、失败门和 9 个 trade CSV 哈希一致。`validate` PASS：8 个 JSON digest、9 个 CSV、仅 development 打开、结论 `INSUFFICIENT_EVIDENCE`。

## 可重演命令

```powershell
$python = 'research\.venv\Scripts\python.exe'
& $python research/studies/strategy-candidate/2026/price-path-continuity-weekly-winner-long/study.py self-test
& $python research/studies/strategy-candidate/2026/price-path-continuity-weekly-winner-long/study.py checkpoint
& $python research/studies/strategy-candidate/2026/price-path-continuity-weekly-winner-long/study.py prepare --stage development
& $python research/studies/strategy-candidate/2026/price-path-continuity-weekly-winner-long/study.py analyze --stage development
& $python research/studies/strategy-candidate/2026/price-path-continuity-weekly-winner-long/study.py gate --stage development
& $python research/studies/strategy-candidate/2026/price-path-continuity-weekly-winner-long/study.py validate
```

不要运行 `prepare/analyze --stage evaluation`：development gate 为 FAIL，代码会拒绝打开。

后续实际命令、阶段门、任何实现修正和结果追加于此，不覆盖失败。
