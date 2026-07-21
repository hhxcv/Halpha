# 实际尝试与失败记录

## 2026-07-20 预注册

- 规则：连续等 SOL 数量 long spot / short USD-M perpetual；阶段内不再平衡；完全资本化；每阶段各一次进入/退出。
- development 2023；evaluation 2024；confirmation 2025–2026-06。只有上一阶段门通过才获取下一阶段。
- 每阶段门：数据 PASS；stress 与扣 4% 年化门后 >0；每个年份切片 >0；回撤 >-5%；funding > |basis|；8h block-bootstrap 95% 下界 >0。最终三阶段非复合和亦需 >0。
- 不构造阈值、择时、动态币池或杠杆；失败即停止。

## 开发数据封存（运行收益前）

- 2023 年 24 个 checksum spot/futures 档案、1,095 条 funding、无补档；Git 外 27 文件、202,530 bytes。
- manifest SHA-256 `f522f3f6db446286bf0146b31296a9cd3bc7f289d0982f1f9afc49995ccfcdb4`；内容身份 `86ec4935f4641bf24270da2d32f411ae80ddc8c31d370d685c4fe4bf14d935ec`。

## 开发门与评估数据封存

- 开发 base/stress +12.03%/+11.87%，stress 扣资本门后 +7.87%；funding +12.71%、basis -0.45%、最大回撤 -3.18%、bootstrap 下界为正；通过开发门。
- 随后才获取 2024：24 个档案、1,098 条 funding、无补档。评估 manifest SHA-256 `82ab0da166fce0618264edc6804d50de2bfea36cc6ac36e5cde9b88767fef5c4`；内容身份 `9ba91137fecbd579795aa0fbd1ebabc8d3fd57838d5c70e684e89502912c57ae`。

## 评估门与确认数据封存

- 评估 base/stress +10.48%/+10.32%，stress 扣资本门后 +6.31%；funding +10.63%、basis +0.09%、最大回撤 -0.16%、bootstrap 下界为正；通过评估门。
- 随后才获取 2025-01 至 2026-06：36 个档案、1,638 条 funding、无补档。确认 manifest SHA-256 `c24ecef875f9394d2aa944de687a0ec3c9be9fc62b2e8ae3794f493e5c85ca44`；内容身份 `252b0a42cef24ce8a31bef5b6fb695158d5eabe03e16eed4e721ded1c165ac36`。

## 确认、否定与重演

- 确认 base/stress -0.3758%/-0.5358%，stress 扣资本门后 -6.5158%；2025 +0.0866%、2026 -0.4624%。
- funding -0.1226%、basis -0.0132%、最大回撤 -0.9376%；bootstrap 95% 跨零。尽管三阶段非复合和 +22.13%，最终新阶段失败，结论 `DOES_NOT_SUPPORT`。
- Git 外重演 6 文件、18,846 bytes；三阶段、两门与最终结果的 6 个内容摘要全部一致。
