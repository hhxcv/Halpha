# 结果：永续折价日频单腿 USD-M one-shot LONG

## 结论

`DOES_NOT_SUPPORT`

固定 `premium1<0/bottom3/daily/0.25x LONG` 在 2022–2023 development 具有充分样本却在 favorable、base、stress 三种成本下均为负，且两个日历年、全部六类和三个局部邻域都没有给出支持。2024 evaluation 与 2025–2026H1 confirmation 按顺序门保持未打开；不生成 handoff。

## 主要证据

| 项目 | 实际值 | 判断 |
|---|---:|---|
| 交易 / entry days / targets / categories | 1,662 / 710 / 25 / 6 | 样本与覆盖充分 |
| favorable/base/stress 日期扣门均值 | **-0.0223% / -0.0723% / -0.1291%** | 三种均失败 |
| stress 14 日块 bootstrap 95% | **[-0.2055%, -0.0542%]** | 完整位于零下 |
| 2022 / 2023 base 日期均值 | -0.1111% / -0.0320% | 两年均负 |
| base 胜率 / 中位数 / 5% 分位 | 46.21% / -0.0859% / -2.0708% | 分布不支持 |
| 正目标比例（至少 10 笔） | 20%（5/25） | 低于 50% |
| 正类别（至少 10 笔） | 0/6 | 全部类别为负 |
| gross price / 实际 funding 逐笔均值 | -0.0089% / +0.0093% | 几乎抵消，不能覆盖摩擦 |
| 缺 mark 排除 | 5/1,667 = 0.30% | 数据边界通过 |
| VectorBT 最大核对误差 | 8.93e-17 | 实现核对通过 |

## 反证与文献差异

三个不可择优邻域同样为负：premium3、premium5、premium1/bottom5 的 stress 日期均值分别为 `-0.1282%/-0.1432%/-0.1132%`。因此失败不是恰好选错一天窗口或前三名数量。

主配置 base `-0.0723%` 仅胜过全体 `SCHEDULED_LONG` 的 `-0.0854%`，却弱于 prior-day negative funding 的 `-0.0512%` 和 5 日 momentum 的 `-0.0354%`；后两者也均亏损，不能升级为候选。

Chi et al. 使用 OKEx 当季期货和现货定义的 basis，样本止于 2021，约 5 bp 成本，且其因子组合并不等于 Binance 永续 premium 的负值条件。He et al. 的高 Sharpe 主要来自现货—永续两腿收敛。本题只有永续多头，承担完整市场方向风险；结果显示 funding 收益虽略为正，但价格腿略负，两者合计不足以覆盖当前 6 bp fee 与零售 spread/slippage。故不能把“基差机制存在”解释成“单腿有 alpha”。

## 数据、修复与复现

- 数据：25 个目标的 Binance 公开 USD-M 1d OHLCV、8h official premium-index Klines、settled funding、8h/必要时 1m mark；无凭据、账户或产品数据库。
- 正式期：`[2022-01-01, 2024-01-01)`；暖启动要求前 30 日。
- Git 外缓存：`D:/projects/Codex/CodexHome/research-data/halpha/category-momentum-gated-one-shot-long/2026-07-22-v1/`；本题清单引用 2,589 个去重文件、56,706,660 bytes。
- 质量：25/25 目标通过；54,825 个 funding rows；143 个历史 funding mark 缺失均低于单目标 0.5% 上限，只有 5 个实际入选交易被严格排除。
- 环境：Python 3.13.14、VectorBT 1.1.0、pandas 3.0.3、NumPy 2.4.6、SciPy 1.18.0。
- 基准：`0bdfeffa616260cebd2d2188ddc8deb9e85c77f4`；正式策略仅作比较背景：`ONE_SHOT_DONCHIAN_ATR_BREAKOUT 1.0.1 / BTCUSDT-PERP`。

checkpoint 后有三项透明 amendment：001 修复 ENS 上市前数据被误判为必需；002 只复用进程内矩阵并避免计算会被丢弃的月频 bootstrap；003 让 checkpoint 重跑校验 amendment 链。三者都锁定前后代码哈希、声明未查看的输出且不改变经济方法。首次 analyze 超时没有生成结果 JSON；完整重跑和确定性复跑才形成结论。

复现命令：

```powershell
& 'research/.venv/Scripts/python.exe' 'research/studies/strategy-candidate/2026/perp-discount-daily-one-shot-long/study.py' checkpoint
& 'research/.venv/Scripts/python.exe' 'research/studies/strategy-candidate/2026/perp-discount-daily-one-shot-long/study.py' fetch --stage development
& 'research/.venv/Scripts/python.exe' 'research/studies/strategy-candidate/2026/perp-discount-daily-one-shot-long/study.py' inspect --stage development
& 'research/.venv/Scripts/python.exe' 'research/studies/strategy-candidate/2026/perp-discount-daily-one-shot-long/study.py' analyze --stage development
& 'research/.venv/Scripts/python.exe' 'research/studies/strategy-candidate/2026/perp-discount-daily-one-shot-long/study.py' gate --stage development
```

七个 trade CSV 的复跑哈希全部一致，详见 `validation.json`。

## 剩余未知

- 两腿 cash-and-carry 在个人资金和当前成本下是否可行：本题未测试，且当前核心契约不能直接交付。
- 2024 以后 premium 关系是否变化：前门失败，按规则不查看。
- 更低真实 maker 成本是否改变符号：favorable 已为负，不能用未验证费率挽救。
- 盘口和 00:00 结算/成交顺序：基础数据不能回答，但不太可能逆转完整为负的 stress 区间。

该结论否定这个固定单腿转换，不否定基差的定价作用或两腿套利；更不构成“基础数据无法发现 alpha”的证明。
