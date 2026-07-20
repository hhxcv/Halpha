# 实际尝试与失败记录

## 2026-07-20 预注册

- 明确记录父题开发已暴露；固定 3%/币、0.10 cap、0.30 gross，其他规则和门完全继承。
- 先用锁定父题 manifest 做校准门；未下载的 2023–2024 与 2025–2026 才承担顺序验证。
- 不使用产品数据/运行时/凭据，不产生交易动作；大型数据留 Git 外。

## 2026-07-20 首次校准门控修复

- 首次 PnL 正常写出：base +19.94%、最大回撤 -14.55%；随后门控抛出 `KeyError`，未生成授权文件、未下载评估数据。
- 根因是复用父题门控时读取 `worst_daily_intraday...`，实际输出键为 `worst_daily_intrabar...`。父题因回撤条件先为假而短路，未受该潜在缺陷影响。
- 只在本包装层读取正确键，并同步修正最终支持门；P​​nL、规则、期间、成本和阈值不变。首次开发内容文件不覆盖，门控将对同一摘要重试。

## 2026-07-20 校准通过与评估启封

- 校准 base/stress +19.94%/+19.66%，2021/2022 +18.01%/+1.64%，最大回撤 -14.55%、adverse -7.98%，120/180/240 日均正，内容摘要 `fb1000c7230372107e1d912e39f4c8dc116bf31be06f5acd2f9bd6d0973cf5b9`；通过校准门但不算独立证据。
- 门通过后才下载 2022-03 至 2025-01 评估源：105 档、9,612 funding、0 补数，外部缓存 111 文件、977,762 bytes。
- 分析前 manifest SHA-256 `aada0e7d643c8d73bc62579a2cb23255b823c8cdeec3f5a39261b5e8f0dd669d`，内容身份 `a735d9f10c585232ca49b9c1b3aab7704700096a60dad1882c9c8d656abc4838`。

## 2026-07-20 独立评估与停止

- 数据质量 `PASS`；base +0.18%、stress -0.25%，2023/2024 -5.74%/+6.28%，回撤 -10.27%、adverse -3.50%、turnover 3.084。
- 120/180/240 日 +2.26%/+0.18%/+8.19%，但 primary stress 和逐年门失败；funding -0.97%、价格 PnL +1.64%，连续 long +51.69%。
- 评估内容摘要 `4639265995fef4c28db3448cece82451e27b0ad48ae827152c9714763a3b3462`，门为 `FAILED_EVALUATION_GATE_STOP`。确认数据未下载，结论 `INSUFFICIENT_EVIDENCE`。

## 2026-07-20 重演与版本差异

- Git 外 `D:/projects/Codex/CodexHome/research-data/halpha/core-perp-conservative-volscaled-tsmom-repro/` 重跑四文件，共 34,428 bytes。评估与评估门内容摘要完全一致。
- 首次开发文件记录修复前 wrapper SHA，当前代码重跑的外层摘要因此不同，但 primary `returns_digest`、`rebalance_digest` 均一致。保留首次文件，并新增当前代码的 `development_revised.json` / `development_gate_revised.json`，摘要 `cb8a2eb...34f8` / `36089c...081b`，与外部重演一致。
