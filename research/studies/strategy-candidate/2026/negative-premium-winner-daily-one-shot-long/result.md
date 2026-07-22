# 结果：负溢价赢家日频 USD-M one-shot LONG

## 结论

`DOES_NOT_SUPPORT`

固定 `winner5 top3 AND premium1<0 / daily / 0.25x LONG` 在 2022–2023 有充分样本，也显示相对单因子的弱增量，但 base/stress 在零售成本与资金门槛后为负，stress 时间块区间跨零，两个年份符号不同，广度和邻域均失败。2024–2026 按顺序门保持未打开；不生成 handoff。

## 主要证据

| 项目 | 实际值 | 判断 |
|---|---:|---|
| 交易 / entry days / targets / categories | 971 / 522 / 25 / 6 | 样本充分 |
| favorable/base/stress 日期扣门均值 | **+0.0210% / -0.0291% / -0.0850%** | 现实成本门失败 |
| stress 14 日块 bootstrap 95% | **[-0.1950%, +0.0263%]** | 下界为负 |
| 2022 / 2023 base 日期均值 | -0.0695% / +0.0203% | 跨年符号翻转 |
| 正目标（至少 5 笔） | 44% | 低于一半 |
| 正类别（至少 5 笔） | 2/6 | 广度不足 |
| gross price / 实际 funding 逐笔均值 | +0.0520% / +0.0047% | 有弱增量，但不足覆盖摩擦 |
| 缺 mark 排除 | 3/974 = 0.31% | 数据边界通过 |
| VectorBT 最大核对误差 | 8.50e-17 | 实现核对通过 |

## 增量为何仍不是 alpha

主配置 base `-0.0291%` 确实优于普通 winner5 `-0.0354%`、单独 premium bottom3 `-0.0723%` 和定时 LONG `-0.0854%`。这说明“价格已经上涨而 premium 仍负”比任一单因子更有信息，但三个基线全部亏损；相对改善不能替代正的绝对净收益。

三个不可择优邻域 winner3/top3、winner10/top3、winner5/top5 的 stress 日期均值为 `-0.0894%/-0.1597%/-0.1006%`，全部为负。主配置只在 2023 为正，目标正比例 44%、正类别仅 2 个，最大正目标贡献 28.33%。因此不能通过改变窗口、扩大 top5 或事后挑币挽救。

经济量级也解释了失败：0.25x 仓位的价格与 funding 合计逐笔约 `+0.0567%`，favorable 尚能留下小幅正值；base 双边 fee+spread/slippage 和 4% 年化资金门后变成负值，stress 更差。除非有独立、可验证且长期可获得的显著更低真实成交成本，否则该机制不适合个人半自动计划。

## 数据、复现与留存

- 数据：25 目标 Binance 公开 USD-M 1d OHLCV、8h official premium、settled funding 与 mark；无凭据、账户、产品数据库或真实交易。
- 正式期：`[2022-01-01, 2024-01-01)`；前约 45 日只作暖启动。
- Git 外缓存：`D:/projects/Codex/CodexHome/research-data/halpha/category-momentum-gated-one-shot-long/2026-07-22-v1/`；manifest 引用 1,332 个去重文件、56,588,780 bytes，全部存在。
- 质量：25/25 通过；143 个历史 funding mark 缺失事件未越界，主配置只排除 3 笔。
- 环境：Python 3.13.14、VectorBT 1.1.0、pandas 3.0.3、NumPy 2.4.6、SciPy 1.18.0。
- 基准：`0bdfeffa616260cebd2d2188ddc8deb9e85c77f4`；正式策略背景 `ONE_SHOT_DONCHIAN_ATR_BREAKOUT 1.0.1 / BTCUSDT-PERP`。

复现命令：

```powershell
& 'research/.venv/Scripts/python.exe' 'research/studies/strategy-candidate/2026/negative-premium-winner-daily-one-shot-long/study.py' checkpoint
& 'research/.venv/Scripts/python.exe' 'research/studies/strategy-candidate/2026/negative-premium-winner-daily-one-shot-long/study.py' fetch --stage development
& 'research/.venv/Scripts/python.exe' 'research/studies/strategy-candidate/2026/negative-premium-winner-daily-one-shot-long/study.py' inspect --stage development
& 'research/.venv/Scripts/python.exe' 'research/studies/strategy-candidate/2026/negative-premium-winner-daily-one-shot-long/study.py' analyze --stage development
& 'research/.venv/Scripts/python.exe' 'research/studies/strategy-candidate/2026/negative-premium-winner-daily-one-shot-long/study.py' gate --stage development
```

七个 trade CSV 重演哈希稳定，见 `validation.json`。

## 剩余未知

- maker 或更低真实成本是否足以保留增量：favorable 仅小幅为正，且 stress 区间/跨年/广度仍失败，所以不能只改费率重开。
- OI/order flow 是否能提升条件精度：当前数据边界不含，需独立来源和新问题。
- 2024–2026 是否改善：开发门失败，按规则不查看。
- 盘中路径、清算和手工延迟：未建模，通常只会进一步降低可执行性。

该结论否定精确 conjunction 的策略资格，但保留“负 premium 可对 winner 提供弱信息增量”作为后续查重参考。
