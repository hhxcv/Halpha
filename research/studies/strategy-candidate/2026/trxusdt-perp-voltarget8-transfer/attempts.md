# 实际尝试与失败记录

- 2026-07-22：选择固定迁移既有 8% 目标，而不是根据 perpetual 结果扫描新的风险目标。
- 2026-07-22：6%/10% 只作邻域反证；50% always-long 与 price-only 只作诊断，任何结果都不能替换主候选。
- 2026-07-22：2025-04 后 TRX perpetual 单腿历史已在 TRX/PAXG 场所迁移中暴露；本研究如实把新增证据限定为完整历史上的固定波动缩放和逐段场所迁移。
- 2026-07-22：Binance funding REST 在当前网络返回 403；在查看收益前改用同一官方源的月度 fundingRate 压缩包和 checksum，变更记录见 `checkpoint-amendment.json`。
- 2026-07-22：官方月度日线包缺少 2022-02-26～28 与 2022-04-01～02；只以对应官方逐日包补齐并校验 checksum，变更记录见 `checkpoint-amendment-data-gaps.json`。
- 2026-07-22：月度 8h mark-price 包另有 7 个历史整日缺口，以官方逐日包补齐；2026-06-29 的逐日包也不可取得，保留缺口并让当日 3 笔 funding 使用已有官方日开盘 mark。该回退只占 7,076 笔 funding 的 0.042%，且在计算收益前固定，见两份 mark amendment。
- 2026-07-22：Development 2021～2022 的 8% 主候选 Base 总收益 +8.18%、Sharpe 0.439、最大回撤 -9.53%；Stress 总收益 +7.85%，扣 4% 年化全资本门后为 -0.29%。因此未通过 `base_sharpe_at_least_0p45` 与 `stress_after_4pct_hurdle_positive`，不授权打开 Evaluation 或 Confirmation。
- 2026-07-22：price-only Base Sharpe 0.481，而计入真实 funding 后降至 0.439；funding 拖累约为 price PnL 的 9.88%。未缩放 50% 多头虽有 +57.32% Base 总收益，但最大回撤 -44.85%，不是可替换候选。
- 2026-07-22：在 Git 外目录独立重放。`development.csv` 与逐日收益 CSV 逐字节一致；两个 JSON 除生成时间及派生来源哈希外语义一致。重放仍失败于同两项门禁。
