# 预注册：持续 UP–UP 状态下的周赢家 LONG

记录于 2026-07-22，任何本题收益输出之前。

## 基准、用途与最强主张

- 稳定产品基准：Git `0bdfeffa616260cebd2d2188ddc8deb9e85c77f4`。
- 正式策略背景：`ONE_SHOT_DONCHIAN_ATR_BREAKOUT 1.0.1 / BTCUSDT-PERP`；只作固定背景，不在研究侧复制产品策略。
- 主要研究类型：`STRATEGY_CANDIDATE`。
- 决策用途：判断一个只需基础日线、周频、单腿、低名义的状态依赖 momentum 规则，是否值得列为未来前向验证对象；本题不能授权产品实现、资金或交易。
- 最强允许主张：固定六个幸存高活动永续、固定时间与成本代理下，该规则是否具有足够历史经济证据继续前向验证。盈利历史不证明 Alpha 或长期盈利。

## 候选与选择理由

| 候选 | 未解决差异 | 数据/复杂度 | 取舍 |
|---|---|---|---|
| 持续 UP–UP + 周赢家单腿 LONG | 已有无条件/类别 momentum 失败，但未检验文献给出的持续上涨状态 | 日线、funding、周频、单腿 | **选中**；最贴合半自动 one-shot，能快速证伪 |
| 截面 dispersion 缩放日频 momentum | 2026 论文提出高 dispersion 预示 breakdown | 需要动态市值/成交活动 universe、每日多资产权重、论文为最高 2x 多腿组合 | 暂缓；产品与个人维护错配更大 |
| 15 分钟边界 order-flow | 新论文、公开 1m/逐笔 | 本项目 1m 代理已 `DOES_NOT_SUPPORT`，精确 10 秒成本和复杂度过高 | 淘汰，避免重复 |
| Amihud/低流动性溢价 | 与既有趋势不同 | 收益可能集中低质量对象，违背优先高流动/可维护边界 | 淘汰 |
| tokenized gold/equity 趋势 | 分散 crypto beta | 历史过短，且底层 beta 不是 Alpha | 暂缓 |

## 固定对象与数据

- Binance USD-M perpetual：`BTCUSDT`、`ETHUSDT`、`BNBUSDT`、`XRPUSDT`、`DOGEUSDT`、`ADAUSDT`。
- 六币来自既有研究开题时固定的 anchor/A1 当前高活动幸存对象；不是历史 point-in-time 全市场，也不是安全保证。
- 只用 Binance 公开 USD-M REST 已保存的 1d Kline、settled funding 和 8h mark-price Kline。时区 UTC，日线 open time 表示自然日开始。
- 复用父题 `liquid-perp-weekly-loser-continuation` 的 `source_manifest.json` 和 Git 外缓存；checkpoint 保存父 manifest SHA-256、逐文件总数/字节数和本题重取身份。任何文件身份不一致即停止。
- 覆盖：`[2020-12-20, 2025-07-01)`；development 从 2021-02-15 开始，使 6 周状态邻域连同上一状态和底层周收益也有完整暖启动。

## 固定信号与行动时间

每个 UTC 周一 `00:00` open 为唯一入场候选时点。令该时点前一完整日（日线索引为周日）的 close 为决策截止点：

1. 对六币各计算过去七个完整 UTC 日的 close-to-close return；六币等权平均为该周市场收益。
2. 当前四周市场状态是截至当前决策点的四个周市场收益复合值；上一状态是整体向前移一周的四周复合值。两者都 `>0` 才是 `UP–UP`。窗口重叠三周，这是状态转换论文口径的基础数据适配，不冒充其 value-weighted 全市场复现。
3. 在六币中按上一周 return 降序、symbol 升序破同值，选择唯一 winner；winner 自身 return 必须 `>0`。
4. 在下一个周一 open 以初始计划资本 `0.25x` LONG；七天后的周一 open 全部退出。相邻周若同币再次入选，也按新的 one-shot 计划完整退出再入场并支付双边成本。
5. 任何必需 bar、funding mark、状态暖启动或数值无效时不交易；不补零、不插值、不换币。

该规则每周最多一腿、无 short、无同时多腿执行、无加仓、止损、止盈或日内重选。计划金额由用户以后决定；`0.25x` 只表示研究中的计划资本名义，不是资金授权。

## 固定成本与统计

- favorable/base/stress 每边：`6/16/26 bp`，即 6 bp taker fee 加 `0/10/20 bp` spread/slippage 代理。
- LONG 实际 funding：正 funding 为支付、负 funding 为收益；stress 将支付乘 `1.5`、收益只保留 `0.5`。
- 4% 年化门按完整计划资本与阶段实际日数扣除，不因仅用 `0.25x` 而缩小。
- 同周只有一笔；四周循环块 bootstrap 5,000 次，保留周依赖。按年份、symbol、正贡献集中和日级持有路径检查稳健性。
- VectorBT `Portfolio.from_orders` 只核对显式两笔订单的费用/滑点；funding 和状态逻辑为本题最小补充，另用手算逐笔核对。

## 固定基准、诊断与搜索披露

主配置只有一个：`state=UP-UP(4w), formation=7d, top1 positive, hold=7d, 0.25x LONG`。

六个不可择优诊断：

1. 相同 UP–UP 周等权六币 LONG（普通市场 beta）；
2. 相同 UP–UP 周 BTC-only LONG；
3. 无状态过滤的 positive top1 weekly LONG；
4. 只要求当前四周 UP 的 positive top1 LONG；
5. winner formation 14 日，其余不变；
6. 状态窗口 3 周与 6 周两个邻域。

总计 1 个主配置、7 个诊断输出（最后一项含两个固定邻域），都保存，不按最好结果改主规则。不会搜索币、窗口、top 数、持有期、名义、成本、状态阈值、止损或指标。

## 时间阶段与已暴露边界

| 阶段 | 区间 | 启封规则 | 证据限制 |
|---|---|---|---|
| development | `[2021-02-15, 2023-01-02)` | checkpoint、代码、source reuse identity 固定后 | 底层市场路径已被父题查看；不是未暴露市场证据 |
| evaluation | `[2023-01-02, 2025-01-06)` | development 全部门通过 | 精确规则输出未查看，但底层路径已暴露 |
| confirmation | `[2025-01-06, 2025-06-30)` | evaluation 全部门通过 | 同上，且仅约半年 |

阶段独立从 1.0 初始资本开始。development 失败默认停止，后段不运行。即使三段全过，因为没有真正未暴露市场区间，结论仍至多 `INSUFFICIENT_EVIDENCE`；需要 checkpoint 后自然形成、至少覆盖 26 个 eligible 周且跨两个市场状态的新前向区间，才可能升级。

## 固定门与否定条件

development/evaluation 必须全部满足：

- 数据质量 PASS、VectorBT/手算最大差异 `<=1e-10`；
- 至少 30 个 eligible 周，development/evaluation 中每个有入场的历年各至少 8 个；至少四个 symbol 各入选两次；最大正贡献 symbol 不超过全部正贡献 50%；
- base、stress 复合收益和 stress 扣 4% 年化门后收益都 `>0`；每个有入场的历年 base 都 `>0`；base 日级最大回撤 `>-15%`；
- stress 周收益四周块 bootstrap 95% 下界 `>0`；
- 相对同状态六币等权 gross excess 均值及其 bootstrap 下界都 `>0`，且 base 总收益高于同状态六币等权和 BTC-only；
- formation14、state3、state6 三个邻域中至少两个 stress 总收益 `>0`。

confirmation 若获准打开，至少要求 8 个 eligible 周、base/stress 与扣门收益 `>0`、base 回撤 `>-10%`、gross excess `>0`、至少两个邻域非负。由于已暴露边界，这仍不是支持结论。

任一主要收益为负，结论为 `DOES_NOT_SUPPORT`；收益为正但统计、基准、稳健性、风险、样本或独立性不足，结论为 `INSUFFICIENT_EVIDENCE`。不能因某年、某币或某邻域漂亮而改规则。

## 未建模与失效条件

当前幸存者偏差、等权六币市场代理、历史盘口/队列/部分成交、保证金/强平/ADL、人工计划激活延迟、账户 fee tier、税和场所故障未被完整重放。日线不能确定周内跳跃和真实执行顺序。状态反转、winner crash、funding 激增、盈利集中、简单市场 beta 同样优越或新时间证据不持续，均是失效条件。
