# 实际尝试与失败记录

## 2026-07-20 预注册

- 在下载本题分段数据前锁定三币、180/60 日、风险预算、gross/cap、月频、成本、funding 时间顺序、两个诊断窗口、基准与三阶段门。
- 原始大文件只放 Git 外；每次门通过后才下载下一阶段并在分析前记录 manifest 身份。
- 不使用产品数据、数据库、配置或凭据，不启动产品/交易运行时，不发出交易请求。

## 2026-07-20 开发数据边界

- 首次只取至 2022-12（102 档、9,324 funding、0 补数），在运行收益前发现阶段退出 `2023-01-01 00:00` 的预注册 `(前一日开盘, 当日开盘]` funding 端点会被 API end-exclusive 排除。
- 改为只读边界缓冲至 2023-01，不延长分析期；最终开发 manifest 105 档、9,603 funding、0 补数，外部缓存 117 文件、1,709,161 bytes。
- 首次结果前 manifest SHA-256 `0d1d0d6c08549a909a0b4f761f8e7f29fca75488f35c0a325a2b49e0399f79c7`，内容身份 `2823f1e8c4bb36990472db98a462511109576fc8053bb843bcff1e00512feb87`。规则、期间和门未改变。

## 2026-07-20 开发结果与停止

- 数据质量 `PASS`。180 日 base/stress +33.49%/+32.97%，2021/2022 +30.32%/+2.43%，120/240 日 +35.06%/+60.58%；turnover 2.776，平均 gross 18.78%。
- 最大回撤 -21.80%，唯一决定性失败是超过 -20% 门；最差日内 adverse 实为 -11.63%（一次 PowerShell 临时投影显示 null，直接核对原 JSON 后纠正，数据文件没有缺失）。
- funding -7.88%、价格 PnL +41.93%；连续 0.5x 多头 +75.00%、回撤 -45.46%。开发内容摘要 `8a6b21434aa330df9364f59f711ef7f73acc0504c5438e6a7b8b84b215a7f0dc`。
- `FAILED_DEVELOPMENT_GATE_STOP`；不下载评估和确认数据，不事后降低风险预算、gross、回撤门或改窗口。结论 `INSUFFICIENT_EVIDENCE`。

## 2026-07-20 重演

- 从锁定 manifest 在 Git 外 `D:/projects/Codex/CodexHome/research-data/halpha/core-perp-volscaled-tsmom-repro/` 重跑开发与开发门。
- 2 个文件共 17,126 bytes；两个 `content_digest` 均与研究目录一致。
