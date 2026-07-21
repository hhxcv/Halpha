# 实际尝试与失败记录

## 2026-07-20 预注册

- 父篮子 DOGE base 分解已暴露：2021–2022 +676.33%，2023 +5.39%，2024–2025-08 +18.42%；全部只作背景。
- 新确认 2025-09-01 00:00 至 2026-06-30 16:00 UTC；连续等币数 spot long / perpetual short；完全资本化；16/24/40bp round trip；4% 年化全资本门槛。
- 门与 XRP 单对完全相同：stress 与扣门槛后 >0；2025/2026 均正；回撤 >-5%；funding > |basis|；block-bootstrap 下界 >0；数据 PASS。
- 不依据结果追加 funding 阈值、择时或区间变动。

## 全新数据封存（运行收益前）

- 20 个 checksum 8h 档案、909 条 settled funding、无补档；Git 外 23 文件、175,859 bytes。
- manifest SHA-256 `61b1af25ec78bc94ca1a2b53e2df7a439a58393de119b3cffe3c3cfd8cff1d33`；内容身份 `b8d9781abb23e9be697a4fcc1b2264c2f50c55c7c2c0f4a4844c5ac4b53be4bd`。

## 全新确认与结论

- 数据质量 `PASS`；base/stress +0.5271%/+0.3671%，但 stress 扣 4% 年化门槛后 -2.9498%。
- 2025/2026 分段 +0.4848%/+0.0423%；funding +0.7905%，basis -0.0234%，最大回撤 -0.1288%。
- block-bootstrap 95% 下界 `-0.000126%` 每 8h，略低于零；结论 `INSUFFICIENT_EVIDENCE`，没有去掉资本门或 bootstrap 门。
- Git 外重演 2 文件、7,718 bytes；确认/结果摘要一致。
