# 结果：永续正溢价延续日频 USD-M one-shot LONG

## 结论

`DOES_NOT_SUPPORT`

2024 发现期产生的 `premium1>0/top3/daily/0.25x LONG` 方向没有在未触碰的 2025 evaluation 延续。充分样本下 favorable、base、stress 都为负，stress 时间块区间完整位于零下；三个邻域和全部基线比较也失败。2026H1 confirmation 按顺序门保持未打开；不生成 handoff。

## 主要证据

| 项目 | 实际值 | 判断 |
|---|---:|---|
| 交易 / entry days / targets / categories | 273 / 196 / 22 / 6 | 样本与覆盖门通过 |
| favorable/base/stress 日期扣门均值 | **-0.1160% / -0.1659% / -0.2216%** | 三种均失败 |
| stress 14 日块 bootstrap 95% | **[-0.3252%, -0.1214%]** | 完整位于零下 |
| 2025 base 日期均值 | -0.1659% | 未触碰年度失败 |
| 正目标（至少 5 笔） | 3/9 = 33.33% | 低于 50% |
| 正类别（至少 5 笔） | 0/6 | 全部类别为负 |
| gross price / 实际 funding 逐笔均值 | -0.0252% / -0.0038% | 价格腿先失败，funding 再恶化 |
| 缺 mark 排除 | 0/273 | 数据边界通过 |
| VectorBT 最大核对误差 | 7.98e-17 | 实现核对通过 |

## 发现期失效与反证

第 10 题在 2024 的同一选择规则下，SHORT gross price 均值为 `-0.1673%`，数学上使 LONG 价格腿为正，因此本题把 2024 明确标为自适应发现期。未触碰 2025 中，LONG gross price 均值却变成 `-0.0252%`。这不是成本边缘误差，而是预测方向本身跨年翻转；它直接否定“正 premium 稳定代表下一日需求延续”。

三个不可择优邻域 `premium3/top3`、`premium5/top3`、`premium1/top5` 的 stress 日期均值为 `-0.1496%/-0.1619%/-0.2254%`，不能用平滑窗口或 top5 挽救。主配置 base `-0.1659%` 还弱于 positive funding LONG `-0.1192%`、5 日 winner LONG `-0.1028%` 与全体定时 LONG `-0.0982%`；这些基线也全为负，不能升级成候选。

只有 AVAX、LINK、RUNE 在至少 5 笔的目标中为正，但这是 2025 结果后的局部观察；六个聚合类别全负，正贡献又有 34.51% 集中于单一目标。事后只选三个币、加牛熊状态或改变窗口都会形成新搜索，不能写回本题。

Xuan 的 XAUUSDT 分钟级正 funding 延续并不泛化到本题的加密横截面日持有，而且该论文自己报告成本后不盈利。Cao 等证明 basis/price-volume 是重要系统因子，但摘要不提供本规则方向。结果说明“因子重要”与“固定单腿计划可盈利”是两个不同命题。

## 数据、复现与留存

- 数据：25 个目标的 Binance 公开 USD-M 1d OHLCV、8h official premium-index Klines、settled funding 与 mark；无凭据、账户、产品数据库或真实交易。
- 资格期：`[2025-01-01, 2026-01-01)`；此前约 45 日仅用于暖启动。2024 不进入 gate。
- Git 外缓存：`D:/projects/Codex/CodexHome/research-data/halpha/category-momentum-gated-one-shot-long/2026-07-22-v1/`；本题 manifest 引用 652 个去重文件、6,946,877 bytes，全部存在并可按官方身份重取。
- 质量：25/25 目标通过；每目标 411 根日线、1,230 根 8h premium、1,095–1,999 条实际 funding，mark 缺失为 0。
- 环境：Python 3.13.14、VectorBT 1.1.0、pandas 3.0.3、NumPy 2.4.6、SciPy 1.18.0。
- 基准：`0bdfeffa616260cebd2d2188ddc8deb9e85c77f4`；正式策略仅作固定背景：`ONE_SHOT_DONCHIAN_ATR_BREAKOUT 1.0.1 / BTCUSDT-PERP`。

复现命令：

```powershell
& 'research/.venv/Scripts/python.exe' 'research/studies/strategy-candidate/2026/perp-premium-momentum-daily-one-shot-long/study.py' checkpoint
& 'research/.venv/Scripts/python.exe' 'research/studies/strategy-candidate/2026/perp-premium-momentum-daily-one-shot-long/study.py' fetch --stage evaluation
& 'research/.venv/Scripts/python.exe' 'research/studies/strategy-candidate/2026/perp-premium-momentum-daily-one-shot-long/study.py' inspect --stage evaluation
& 'research/.venv/Scripts/python.exe' 'research/studies/strategy-candidate/2026/perp-premium-momentum-daily-one-shot-long/study.py' analyze --stage evaluation
& 'research/.venv/Scripts/python.exe' 'research/studies/strategy-candidate/2026/perp-premium-momentum-daily-one-shot-long/study.py' gate --stage evaluation
```

七个 trade CSV 的完整重演哈希全部一致，见 `validation.json`。

## 剩余未知

- 正 premium 延续是否只在可事先识别的特定市场状态存在：当前证据提示状态依赖，但没有未触碰数据授权选择状态；需另题、另来源和新 holdout。
- OI/order flow 是否能区分延续与拥挤反转：用户当前数据边界不包含，不能猜测。
- 2026H1 是否再次翻转：evaluation 已失败，按预注册不查看。
- 分钟级反应是否存在：不适合当前日频半自动优先级，且原始研究提示成本后无利润。

该结论否定从 2024 反向发现直接推广出的固定 LONG，不否定 funding/basis 的解释价值，也不证明所有基础数据策略都无效。
