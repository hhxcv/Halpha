# 实际尝试与失败记录

## 2026-07-20 预注册

- 锁定三币、等资本、连续持有、全额 pair capital、成本、4% 门槛、年度/单币/回撤/funding 门和顺序启封。
- 2021–2023 数据与旧事件规则已暴露，明确标记规则级留出；2024–2025 core 数据在两门通过前不下载。
- 仅用公开市场数据，不读取产品数据/配置/凭据，不启动运行时或发出交易请求。

## 2026-07-20 开发、评估与确认数据启封

- 开发 base +304.96%，2021/2022 +292.21%/+12.75%，三币均正，funding +305.08%、basis +0.13%、最大回撤 -7.26%；内容摘要 `c5ccbbbda30802fb4c7e4753d821cd2f329e61cb666650553fed07ee8c8d5ca4`，通过开发门。
- 2023 评估 base/stress +5.85%/+5.69%，stress 扣 4% 门槛 +1.69%；三币均正，funding +6.18%、basis -0.09%、最大回撤 -0.15%；内容摘要 `7e5798ea5b0e9d0e29baaa0ee5f1b90ce08ca2fbeab625a15d5825819a5211ec`，通过评估门。
- 两门通过后才获取 2024-01 至 2025-09：126 个 checksum 档案、5,751 条 funding、0 补数；外部缓存 135 文件、1,102,874 bytes。确认 manifest SHA-256 `edfb67ea162e3ec16441d926c0abdc4b53993591ef3b1d4b084ddc80b8d4b96d`，内容身份 `f1cd89b10a72bafb40fd0bc192e3fea41ffc83301a83db5246212845152a8a3a`；尚未运行确认收益时写入 checkpoint。

## 2026-07-20 确认与结论

- 全新确认数据质量 `PASS`；base/stress +14.09%/+13.93%，扣 4% 年化资本门槛后 +7.41%/+7.25%，2024/2025-to-Aug +10.24%/+3.84%。
- 三币确认总收益：DOGE +18.42%、XRP +14.70%、ADA +9.13%；funding +14.24%、basis +0.09%，最大回撤 -0.37%，block-bootstrap 均值下界为正。
- 确认内容摘要 `f599a8c7d04a08d70d243e35f4e53e76151e1edae6c713ecbfaec70eb68823ab`；最终摘要 `3d221747e9e5d3425591120e57bebbe3acfe5fe941c3829fc492010764b0de31`，结论 `SUPPORTS_WITHIN_SCOPE`。
- 没有修改三币、权重、成本、资本门槛、期间或门；结果不授权产品或真实交易。

## 2026-07-20 重演

- 使用两份锁定 manifest，在 Git 外 `D:/projects/Codex/CodexHome/research-data/halpha/mature-alt-continuous-cash-carry-basket-repro/` 顺序重跑三阶段、两门和合并。
- 6 个文件共 22,937 bytes，六个 `content_digest` 全部与研究目录一致；`generated_at` 不参与内容摘要。
