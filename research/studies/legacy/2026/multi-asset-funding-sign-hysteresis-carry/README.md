# 多资产 funding 符号滞后 cash-and-carry 研究

## 状态与继承

- 稳定基准 `de6b3052f28fe547730e89e58186d4ab397884b1`；正式策略 `ONE_SHOT_DONCHIAN_ATR_BREAKOUT 1.0.0`。
- 候选 `RESEARCH_MULTI_ASSET_FUNDING_SIGN_HYSTERESIS_CARRY`；若支持，只计一个 carry 家族候选。
- 最终结论：`INSUFFICIENT_EVIDENCE`。开发累计盈利但 episode 中位数、胜率和回撤同时失败，后两段保持封存。
- 继承：3 bp、两次持续的 DOGE/XRP/ADA 开发规则 base +69.06%、回撤 -1.77%，但只有 5 episodes 且单一 DOGE episode 占大部收益，结论 `INSUFFICIENT_EVIDENCE`；后续区间未启封。
- 新题不用幅度阈值：某币连续两次 settled funding >0 后入场；持有到连续两次 ≤0 后退出并计两次 funding。一次只做一币 long spot / short 等名义 perp，两单位全额资本。

## 先行调研与选择

访问日 2026-07-20。[He 等](https://arxiv.org/abs/2212.06888) 给出含摩擦 perpetual 无套利边界并显示偏离会衰减；[Gornall 等](https://ssrn.com/abstract=5036933) 强调受限资本与 basis 风险；[Inan 2025](https://ssrn.com/abstract=5576424) 提供下一期 funding 方向可预测但稳定性时变的样本外证据；[Binance Funding History](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Get-Funding-Rate-History) 是 settled rate 官方来源。

候选中：把 3 bp 改成 1 bp 是连续数值追参，淘汰；每个结算点切换成本过高，淘汰；跨所增加库存与故障，淘汰；纯符号 + 对称两事件 hysteresis 不依赖已知幅度收益，直接检验“延长 episode 是否覆盖两腿成本”，选中。

## 固定规则与门槛

- 开发/评价 DOGE、XRP、ADA；跨标的确认 LTC、LINK。阶段与父研究相同：2021–2023、2024–2025、LTC/LINK 2021–2025。
- 入场仅用当前和前次已结算 rate；若多币合格选当前 rate 最高者。持有中不切换；连续第二个非正 rate 计入后退出；期末强退。
- episode 内两腿数量固定；basis 与 funding 按实际 spot/perp 8h open 计算并除以两单位资本。
- 单次进入或退出的两腿合计有利/base/stress 16/24/40 bp；不搜索符号次数、币、退出或成本。
- 开发门：对齐完整；base/stress 正；≥10 episodes、≥100 active 8h；episode 中位数正、胜率≥50%、最大非复合回撤>-10%。
- 评价门：base/stress 正；≥5 episodes、≥50 active；中位数非负、胜率≥50%、回撤>-10%。
- 支持门：LTC/LINK base/stress 正；≥10 episodes、≥100 active；两币均被选、中位数非负、胜率≥50%、回撤>-10%。评价或确认 base 负为 `DOES_NOT_SUPPORT`，其他失败为 `INSUFFICIENT_EVIDENCE`。

| 数据 | 状态 | 启封 |
|---|---|---|
| DOGE/XRP/ADA 2021–2023 | 已运行；样本充足但分布/回撤门失败 | checkpoint 后复用修复后 manifest |
| DOGE/XRP/ADA 2024–2025 | 未下载 | 开发门通过 |
| LTC/LINK 2021–2025 | 未下载 | 评价门通过 |

开发复用父研究外部缓存；holdout 缓存 `D:/projects/Codex/CodexHome/research-data/halpha/multi-asset-funding-sign-hysteresis-carry/`。未覆盖两腿同步成交、部分成交、保证金/ADL、划转、USDT 机会成本、税务与场所故障。盈利回测不证明无风险套利或 Alpha，结果不授权产品/资金/交易。

## 实际结果与反证

- 数据/价格对齐完整。84 episodes、3,131 active 8h；DOGE/XRP/ADA 分别入选 36/28/20 次，解决了父研究的样本数量与资产覆盖问题。
- favorable/base/stress 非复合累计收益 +47.70%/+40.98%/+27.54%；funding +63.25%、basis -2.11%、base cost -20.16%。
- episode 中位数 -0.219%，胜率仅 13.10%，最大非复合回撤 -11.94%。2021 +49.23%、2022 -8.19%、2023 -0.06%，总收益高度依赖早期少数长 episode。
- 最强支持是成本压力下累计仍正；最强反证是典型 episode 亏损、胜率远低于 50% 且回撤越界。它不能列为可用策略，也不能用 2021 总收益掩盖 2022–2023 失效。
- 开发/selection 内容摘要 `e0448f9f73f690736ef7519aae8c9daf3b4a61a58e78c7546223c432a1af8b5d` / `4e7d6165f8d98ca40ec36cdc3187947267486f71934d1cde1c1f266451ad00b6`；数据 manifest 沿用父研究 `1587d2f2505177db808e915a5a83dd1b4d35991e6f9588cf4dd95adcdb438609`。
