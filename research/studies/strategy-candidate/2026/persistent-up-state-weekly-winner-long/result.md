# 结果：UP–UP 状态有市场 beta，但周赢家没有增量资格证据

## 结论

`INSUFFICIENT_EVIDENCE`

在六个 Binance USD-M 高活动幸存永续、2021-02-15 至 2023-01-02 的已暴露 development 市场路径中，固定 `UP–UP(4w) / positive top1 weekly winner / 0.25x LONG / hold7d` 在 favorable/base/stress 下复合收益为 `+9.10%/+7.41%/+2.13%`。但是 stress 扣 4% 年化全资本门后为 `-5.13%`，stress 周均四周块 bootstrap 95% 区间跨零，base 日级最大回撤为 `-26.69%`，2022 为 `-8.33%`。

更关键的是，赢家选择没有提供增量：在相同 31 个可交易周，相对同状态六币等权市场的 gross excess 平均为 `-0.2720%/周`，95% 区间 `[-1.9147%, +1.4683%]`；同状态六币等权 base/stress 总收益反而达到 `+16.45%/+10.67%`。因此观察到的绝对正收益更符合“持续上涨状态下的普通广义市场 beta”，而不是周赢家 Alpha。

development gate 失败，evaluation 与 confirmation 没有打开，产品 handoff 没有生成。结论不是 `SUPPORTS_WITHIN_SCOPE`，也不支持任何资金或真实交易动作。

## 固定方法与数据

- 产品基准：Git `0bdfeffa616260cebd2d2188ddc8deb9e85c77f4`；正式策略 `ONE_SHOT_DONCHIAN_ATR_BREAKOUT 1.0.1 / BTCUSDT-PERP` 只作背景。
- 六币：BTC、ETH、BNB、XRP、DOGE、ADA 的 Binance USD-M perpetual。
- 每周一 open 前，用六币等权周收益构造当前和上一四周复合市场状态；两者均正且上一周唯一 winner 自身收益正，才以计划资本 0.25x LONG 一周。
- 使用实际 settled funding；favorable/base/stress 每边成本 6/16/26 bp。正 funding 为 LONG 支付；stress 放大支付、削减收益。
- 只有一个主配置；7 个非选择性诊断全部保存。四周循环块 bootstrap 5,000 次；VectorBT 明确订单与独立手算逐笔核对。
- 复用父题 66 个 Binance 公开缓存文件、7,669,925 bytes；父 manifest SHA-256 `23566d464f3b57eca11288160d8331610862210e20ec0b04c08306ee21e33fe0`，逐文件 bytes/SHA-256 再核验，data quality `PASS`。

## 主要证据

| 证据 | 结果 | 判定 |
|---|---:|---|
| eligible 周 / 交易 / funding events | 31 / 31 / 650 | 样本最低数刚通过 |
| favorable / base / stress 复合 | +9.10% / +7.41% / +2.13% | 绝对收益为正 |
| favorable / base / stress 扣 4% 门 | +1.35% / -0.22% / -5.13% | base/stress 资本门失败 |
| stress 周均 bootstrap 95% | [-1.2641%, +1.7991%] | 不能排除负均值 |
| 2021 / 2022 base | +17.17% / **-8.33%** | 状态外推不稳定 |
| base / stress 日级最大回撤 | -26.69% / -28.66% | 超过 -15% 门 |
| gross excess vs 同状态六币市场 | **-0.2720%/周** | winner 排名没有增量 |
| excess bootstrap 95% | [-1.9147%, +1.4683%] | 增量不确定且点估计为负 |
| 同状态六币市场 base / stress | +16.45% / +10.67% | 更简单解释明显更强 |
| 最大正贡献 symbol | BNB，占正贡献 96.08% | 严重集中 |
| VectorBT/手算最大差异 | 6.42e-17 | 实现核对通过 |

逐笔算术拆分显示：毛价格收益 `+21.95%`，base 价格与显式成本后 `+19.43%`，实际 funding 合计 `-6.33%`；stress funding 合计 `-9.97%`。成本和 funding 显著削弱结果，但不是唯一否定原因，因为毛层面的 winner-vs-market 增量已经为负。

base 单笔胜率仅 `45.16%`，中位数 `-0.2483%`，最差/最好单笔约 `-10.73%/+27.82%`。正复合收益依赖少数右尾，且 BNB 的算术正贡献约 `+43.50%`，BTC/ETH/DOGE/ADA 均为负。

## 诊断与反证

| 固定诊断 | base | stress | 解释 |
|---|---:|---:|---|
| 同状态六币等权 LONG | +16.45% | +10.67% | 普通市场 beta 优于 winner |
| 同状态 BTC-only LONG | -22.23% | -25.29% | 广义 alt beta，不是 BTC 单腿即可替代 |
| 无状态 positive winner | +6.05% | -2.33% | UP–UP 过滤改善 stress，但未形成增量 Alpha |
| 只要求当前 UP | +15.42% | +9.14% | 更简单状态条件反而更强；仅为已暴露诊断，不能改主规则 |
| formation 14 日 | -1.12% | -6.02% | 形成期不稳 |
| state 3 周 | +6.36% | +1.33% | 一个邻域勉强正 |
| state 6 周 | +1.06% | -3.62% | 另一个邻域转负 |

三个事前邻域只有 state3 在 stress 下非负；盈利集中、2022 反向和回撤都说明这不是稳定平台。`up_only` 更好是结果揭示后的诊断，不能反选成新候选；若将来有独立的外部机制与真正新数据，才可另题固定。

## 实际失败与修正

- 第一次 analyze 在任何结果生成前因状态邻域暖启动不足报 `KeyError`；只把 development 起点顺延到 2021-02-15，保持规则和数据不变，旧检查点与 traceback 已保留。
- 首次成功结果后发现汇总器把 0 入场的 2023 加入历年门；只移除空年份并完整重跑。修复前后所有交易和经济指标不变，仍有九项实质门失败。
- 状态论文 DOI 的开题记录有一位误写，已按 ScienceDirect/RePEc 更正为 `10.1016/j.frl.2025.108356`；不影响方法或结果。
- 最终重复 analyze/gate：8 个 trade CSV SHA-256 全部稳定，FAIL 项完全一致。

## 限制与剩余未知

- 底层 2021–2025H1 市场路径此前已被父研究查看；本题阶段只是精确规则输出的顺序打开，不是真正未暴露市场证据。
- 六个当前幸存对象不是历史 point-in-time universe；等权六币状态不是原论文的 value-weighted 全市场状态。
- 本题把原论文多资产 long-short momentum 转成当前 one-shot 单腿 LONG；负结果不能否定论文组合，也不能证明所有状态 momentum 无效。
- 日线和成本带未重放真实 bid/ask、队列、部分成交、保证金、强平/ADL、人工激活延迟、账户费率与税。
- evaluation/confirmation 按门未运行；不得根据已暴露的 `up_only`、BNB 或某个邻域继续调参。

要改变判断，需要一个事前独立机制而不是本结果挑出的子规则，并在 checkpoint 后自然形成的真正新时间区间中通过同样的资本门、市场基准、bootstrap、回撤、邻域和集中度门。当前没有可交给交易核心资格验证的策略。

