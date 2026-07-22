# 结果：高波动月频单腿 USD-M one-shot SHORT

## 结论

`INSUFFICIENT_EVIDENCE`

固定的 `VOL90/top3/monthly/0.25x SHORT` 在 2024 development 呈现正的成本后绝对收益，但统计下界与参数邻域稳健性均未达预注册门槛。顺序门因此关闭 2025 evaluation 和 2026H1 confirmation；没有生成框架无关 handoff，更没有修改或授权核心交易。

## 开发期证据

| 项目 | 实际值 | 门槛/解释 |
|---|---:|---|
| 交易 / entry months / targets / categories | 24 / 12 / 10 / 6 | 通过 15 / 8 / 6 / 3 最低量 |
| favorable/base/stress 日期扣门均值 | +0.8199% / +0.7709% / +0.5440% | 三者均为正 |
| stress 三月块 bootstrap 95% | **[-0.8139%, +2.3318%]** | 下界未大于 0，失败 |
| base 交易胜率 / 中位数 / 5% 分位 | 66.67% / +3.2190% / -6.0376% | 描述性，不替代时间聚合 |
| gross price / 实际 funding 逐笔均值 | +1.9129% / +0.3172% | SHORT 的正 funding 是收益；两者不可拆开择优 |
| 正目标比例（至少两笔） | 50.00% | 刚好通过 |
| 正类别（至少三笔） | 3 | 刚好通过 |
| 最大正目标贡献 | 34.95% | 低于 40% |
| 目标回撤中位 / 最差 | -3.40% / -14.27% | 通过 -15% / -30% 门 |
| missing-mark 排除 | 0/24 | 通过 |
| VectorBT 最大核对误差 | 5.55e-17 | 通过 1e-10 |

日期等权均值低于逐笔均值，是因为每月实际入选笔数不等；预注册以 entry month 为推断单位，不能用更好看的逐笔均值替代。

## 反证与简单解释

三个不可择优邻域在 stress 下全部为负：VOL60/top3 `-0.1727%`、VOL120/top3 `-2.0760%`、VOL90/top5 `-2.5344%`。主规格因此只在精确的 90 日、前三名切片上为正，缺少局部稳定平台，这是比单一正回测更有力的反证。

主规格确实优于三个预注册简单对照：LOWVOL90-SHORT `-4.1468%`、LOSER90-SHORT `-4.6436%`、SCHEDULED_SHORT `-2.8000%`（均为 base 日期扣门均值）。这说明 2024 结果不是“所有币普遍做空”即可解释，但仍不能排除小样本时序偶然和精确规格择时；bootstrap 跨零正体现了该不确定性。

目标层面，NEAR 的正收益和 ENS/RUNE 等共同贡献，最大正目标贡献未超限；但 HBAR 三笔均值 `-4.0141%`，且 24 笔不足以证明跨目标长期持续。日线模型也看不到月内 squeeze、保证金路径、盘口深度、排队与部分成交，这对 SHORT 尤其重要。

## 数据与复现

- 数据：Binance 公开 USD-M 1d klines、settled funding、8h/必要时 1m mark；无凭据、账户或产品数据库。
- 时期：暖启动自 2023-08-19；正式 development 为 `[2024-01-01, 2025-01-01)`。
- Git 外缓存：`D:/projects/Codex/CodexHome/research-data/halpha/category-momentum-gated-one-shot-long/2026-07-22-v1/`。
- 本题清单引用 1,274 个去重文件、6,077,841 bytes；每个档案保留官方 checksum/内容哈希，日线页保留 URL 与 SHA-256，可重复获取。
- 环境：Python 3.13.14、VectorBT 1.1.0、pandas 3.0.3、NumPy 2.4.6、SciPy 1.18.0。
- 基准提交：`0bdfeffa616260cebd2d2188ddc8deb9e85c77f4`；正式策略身份仅作背景：`ONE_SHOT_DONCHIAN_ATR_BREAKOUT 1.0.1 / BTCUSDT-PERP`。

复现命令（仓库根目录）：

```powershell
& 'research/.venv/Scripts/python.exe' 'research/studies/strategy-candidate/2026/high-volatility-monthly-one-shot-short/study.py' checkpoint
& 'research/.venv/Scripts/python.exe' 'research/studies/strategy-candidate/2026/high-volatility-monthly-one-shot-short/study.py' fetch --stage development
& 'research/.venv/Scripts/python.exe' 'research/studies/strategy-candidate/2026/high-volatility-monthly-one-shot-short/study.py' inspect --stage development
& 'research/.venv/Scripts/python.exe' 'research/studies/strategy-candidate/2026/high-volatility-monthly-one-shot-short/study.py' analyze --stage development
& 'research/.venv/Scripts/python.exe' 'research/studies/strategy-candidate/2026/high-volatility-monthly-one-shot-short/study.py' gate --stage development
```

重跑 `analyze` 后，主表与六个诊断 trade CSV 的 SHA-256 均完全一致。JSON 中含生成时间，因此以 `validation.json` 中的 trade CSV 哈希验证确定性。

## 尚未回答

- 该现象能否在 2025 和 2026H1 延续：顺序门失败，按规则不得打开。
- 90 日恰好前三名是否存在经济机制，还是 2024 的偶然切片：当前反证更偏向后者。
- 真实月内 squeeze 和人工计划延迟是否会进一步恶化结果：基础数据无法判定。
- 更广、point-in-time 的历史上市/退市总体是否一致：当前名单是 2026 幸存目标，不能推断。

因此，本题有值得保留的弱正发现，却没有达到“可供交易核心资格验证”的标准，更不构成长期盈利证明。
