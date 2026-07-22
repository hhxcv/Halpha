# 结果：永续正溢价日频单腿 USD-M one-shot SHORT

## 结论

`DOES_NOT_SUPPORT`

固定 `premium1>0/top3/daily/0.25x SHORT` 在 2024 development 具有充分样本，但 favorable、base、stress 三种成本下均为负，stress 时间块区间完整位于零下，全部三个局部邻域也为负。2025 evaluation 与 2026H1 confirmation 按顺序门保持未打开；不生成 handoff。

## 主要证据

| 项目 | 实际值 | 判断 |
|---|---:|---|
| 交易 / entry days / targets / categories | 515 / 256 / 25 / 6 | 样本与覆盖门通过 |
| favorable/base/stress 日期扣门均值 | **-0.1133% / -0.1634% / -0.2185%** | 三种均失败 |
| stress 14 日块 bootstrap 95% | **[-0.3859%, -0.0633%]** | 完整位于零下 |
| 2024 base 日期均值 | -0.1634% | 年度门失败 |
| base 胜率 / 中位数 / 5% 分位 | 42.72% / -0.1338% / -2.1096% | 分布不支持 |
| 正目标比例（至少 5 笔） | 33.33% | 低于 50% |
| 正类别（至少 5 笔） | 1/6 | 广度不足 |
| gross price / 实际 funding 逐笔均值 | -0.1673% / +0.0108% | funding 不能抵消价格延续 |
| 缺 mark 排除 | 0/515 | 数据边界通过 |
| VectorBT 最大核对误差 | 7.20e-17 | 实现核对通过 |

## 反证、邻域和机制解释

三个不可择优邻域 `premium3/top3`、`premium5/top3`、`premium1/top5` 的 stress 日期均值分别为 `-0.1919%/-0.1551%/-0.2239%`。失败不是仅由一天窗口或前三名数量造成。

主配置 base `-0.1634%` 也没有胜过 prior-day positive funding `-0.1119%`、5 日 winner SHORT `-0.1132%` 或全体定时 SHORT `-0.1616%`；这些基线本身也都亏损，不能升级为候选。至少 5 笔目标中只有三分之一为正，只有 Infrastructure 类为正；正收益又有 45.27% 集中于单一目标，最差目标路径回撤 -26.98%。不能事后挑选 ENS、DASH 等局部结果形成新策略。

He et al. 的正 funding 附近回落主要是分钟级事件和现货—永续两腿收敛，本题则在下一 UTC 日开盘后承担一整天的单腿方向风险。Chi et al. 发现 basis 因子的 short leg 不显著；Xuan 的 XAUUSDT 结果还提示正 funding 单独可能伴随短周期动量，只有加入 order flow 交互才出现反转。本题的实际结果与这些反证一致：正 funding 现金流存在，但价格继续上涨的平均损失更大。

## 数据、复现与留存

- 数据：25 个目标的 Binance 公开 USD-M 1d OHLCV、8h official premium-index Klines、settled funding 与 mark；无凭据、账户、产品数据库或真实交易。
- 正式期：`[2024-01-01, 2025-01-01)`；此前约 45 日仅用于暖启动。
- Git 外缓存：`D:/projects/Codex/CodexHome/research-data/halpha/category-momentum-gated-one-shot-long/2026-07-22-v1/`；本题 manifest 引用 650 个去重文件、5,637,853 bytes，全部存在并可按官方身份重取。
- 质量：25/25 目标通过；每个目标 412 根日线、1,233 根 8h premium、1,098 条 funding，必要字段缺失与非法值均为 0。
- 环境：Python 3.13.14、VectorBT 1.1.0、pandas 3.0.3、NumPy 2.4.6、SciPy 1.18.0。
- 基准：`0bdfeffa616260cebd2d2188ddc8deb9e85c77f4`；正式策略仅作固定背景：`ONE_SHOT_DONCHIAN_ATR_BREAKOUT 1.0.1 / BTCUSDT-PERP`。

复现命令：

```powershell
& 'research/.venv/Scripts/python.exe' 'research/studies/strategy-candidate/2026/perp-premium-daily-one-shot-short/study.py' checkpoint
& 'research/.venv/Scripts/python.exe' 'research/studies/strategy-candidate/2026/perp-premium-daily-one-shot-short/study.py' fetch --stage development
& 'research/.venv/Scripts/python.exe' 'research/studies/strategy-candidate/2026/perp-premium-daily-one-shot-short/study.py' inspect --stage development
& 'research/.venv/Scripts/python.exe' 'research/studies/strategy-candidate/2026/perp-premium-daily-one-shot-short/study.py' analyze --stage development
& 'research/.venv/Scripts/python.exe' 'research/studies/strategy-candidate/2026/perp-premium-daily-one-shot-short/study.py' gate --stage development
```

七个 trade CSV 的完整重演哈希全部一致，见 `validation.json`。

## 剩余未知

- funding 前后分钟级两腿收敛在个人资金和当前产品能力下是否可行：本题未测试，不能由本题结果外推。
- 加入 OI、order flow 或盘口的条件信号是否能识别反转：用户当前选择基础数据，本题不含这些维度；这不允许事后修改当前规则。
- 2025 以后关系是否变化：开发门已失败，按规则不查看。
- 保证金、强平、ADL、盘中 squeeze 和 00:00 成交顺序：基础数据不能回答；这些未建模风险对单腿 SHORT 通常只会使可执行性更差。

该结论否定这个固定日频单腿转换，不否定永续基差的定价作用或两腿套利，也不证明所有基础数据策略都无效。
