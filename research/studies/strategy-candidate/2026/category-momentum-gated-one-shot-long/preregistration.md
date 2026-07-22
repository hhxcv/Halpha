# 类别动量门控单腿 one-shot LONG：预注册

## 固定研究身份与用途

- 研究身份：`RESEARCH_CATEGORY_MOMENTUM_GATED_ONE_SHOT_LONG_7D_0P5X_V1`
- 研究类型：`STRATEGY_CANDIDATE`
- 产品基准提交：`0bdfeffa616260cebd2d2188ddc8deb9e85c77f4`
- 固定正式策略：`ONE_SHOT_DONCHIAN_ATR_BREAKOUT` `1.0.1`，`BTCUSDT-PERP`
- 当前产品用途：半自动 one-shot 计划由用户固定账户、工具、`LONG` 方向和交易金额；候选只能决定是否入场、固定持有与退出，不选择工具、不改变金额、不直接发单。
- 研究只产生候选证据，不修改产品代码、L4、资金或真实账户状态。

## 当前缺口、候选与选择

现有 Halpha 已研究自身趋势、横截面 top-2 momentum、周频输家延续、短周期反转、BTC lead-lag、funding 单腿和 cash-and-carry。它们没有直接回答：同类别中其他大额成交、长历史永续的共同趋势，能否在用户已经固定一个币后改善该币的入场时机。

| 候选 | 未解决差异 | 可证伪性与成本 | 取舍 |
|---|---|---|---|
| 类别动量门控固定单币 LONG | 多标的只形成信号，实际只做用户固定的一腿；类别信号排除目标自身 | 公开日线和 funding；7 日持有；与自身动量、固定 long、成本和留出直接比较 | **选中** |
| funding 与趋势同向/反向交互 | 单腿、数据简单 | 与已经失败的下一 funding 单腿和多个趋势家族相邻，外部证据主要解释 basis/carry，缺少该拼接的独立支持 | 淘汰 |
| 类别 top/bottom 多腿组合 | 最接近论文原策略 | 由策略选类别和币、同时多腿，违反当前工具与方向由用户固定的计划语义 | 淘汰 |
| tokenized TradFi 时段传导 | 新对象、可能有独立价格发现 | 当前合约历史太短，闭市、锚定和标的身份差异使长期资格无法快速验证 | 暂缓 |

本题与已有 momentum 家族共享“收益延续”背景，只计一个类别共同成分候选，不把窗口扰动或每个币重复计数。若类别信号不优于自身动量或无条件 long，不得以换类别、换币或近邻参数重开同义题。

## 外部方法怎样影响本题

1. Luo（爱丁堡大学博士论文，2025 入库；样本至 2024-07）使用 CoinMarketCap 类别、市值和 Binance 永续日线，形成大量价值加权类别组合，报告类别动量解释相当部分单币动量；短周期主要由 buy-side 和大额/流动币驱动。它支持检验“类别共同成分”，但原策略是 30 类、top-5/bottom-5、多腿且机构成本，不能移植收益。
2. Moskowitz 与 Grinblatt（1999）给出股票行业动量的原始基准，要求与个体动量区分。股票行业、月度窗口和交易制度不等同于 crypto。
3. Liu、Tsyvinski 与 Wu（2022）表明 crypto market、size、momentum 是重要共同解释，要求本题把自身动量和无条件市场 beta 作为更简单解释，而不是把正收益都称为类别 Alpha。
4. Binance 官方 USD-M Kline 与 Funding History 是价格、quote volume 和实际 settled funding 来源。当前 `exchangeInfo` 分类只证明访问时点标签；不能倒推出历史类别不变。
5. VectorBT `1.1.0` 用于每笔固定订单的成本与成交方向重演；实际 funding 作为明确补充现金流。VectorBT 不代表产品成交、保证金或 NautilusTrader 语义。

完整链接、访问时间、适用性和差异见 `sources.md`。

## 固定对象与分类边界

- 分类冻结自 `research/market-universe/universe.csv`，SHA-256 `1f24adfb64b7a52a170b730ee7517916b2da8ab45785779dee6be991762186cc`，快照时间 `2026-07-21T06:42:30Z`。
- 只使用当前仍交易、USDT quote、USD-M perpetual、`CRYPTO_NATIVE`、官方 `classification_subtypes`、且 `onboard_date_utc < 2022-01-01` 的对象。
- 固定七类：`AI`、`DeFi`、`Infrastructure`、`Layer-1`、`Layer-2`、`Payment`、`PoW`；各类至少五个固定成员。精确 74 个成员写入 `checkpoint.json`。
- 可实际成为用户固定工具的目标进一步冻结为快照时 `A1/A2 PROVISIONAL 24H`、单次 top-of-book 相对 spread 不高于 5 bp、且 development settled-funding 官方月归档完整的 25 个长历史对象；精确名单写入 `checkpoint.json`。`ICPUSDT` 因 2022-01 至 2022-08 funding 月归档缺失只保留为类别 peer，不作为目标。这个门只用于当前候选发现，不能证明长期流动性，历史分析仍要求目标 30 日成交额门。
- 这是“当前仍可用固定名单”的适配研究，不是历史 point-in-time 全市场。已经退市的对象和历史分类修订未覆盖，构成幸存者偏差；正结果也不能推广为全部 Binance 类别效应。

## 固定策略规则

全部时间为 UTC 日线。对用户已固定的目标工具与 `LONG` 方向：

1. 决策日 `t` 收盘后，仅使用 `t` 及以前完整数据。
2. 目标必须有完整 30 日 quote volume，且过去 30 日 quote volume 中位数不低于 `10,000,000 USDT/day`。
3. 类别成员必须有完整 30 日 quote volume、完整形成期价格，且 30 日 quote volume 中位数不低于 `1,000,000 USDT/day`。
4. 对每个类别按 `t` 时点已知的 30 日成交额中位数降序选择最多五个成员，等权计算形成期 close-to-close 收益。计算目标所属类别时排除目标并用下一成员补足；至少四个同类 peer。其他类别至少五个成员。
5. 至少五个类别可计算；目标类别得分为正且排在前二时产生入场信号。
6. `t+1` UTC 日 open 以 `0.5x` 计划资本初始名义做多，`t+8` UTC 日 open 退出，持有七天。决策与入场间显式错开一根 bar。
7. 一项产品计划只闭合一次。历史研究为取得样本，把每次退出后的下一完整日视为一个新的、假设已由用户重新激活的独立计划机会；不声称这是产品真实历史，也不允许同日退出后重新入场。
8. 入场、持有或退出输入缺失、不连续、无效，或分类/成交额门不足时不行动；不前向填充价格或信号。
9. funding 只计严格满足 `entry_time < funding_time < exit_time` 的官方 monthly `fundingRate` 归档事件；边界结算不假设能被获取。归档没有逐事件 markPrice，因此使用同月官方 8h `markPriceKlines` 在 funding 时点最近（容差 1 分钟）的 open 作为结算名义代理；缺失时不计算，不用目标成交价或前向填充替代。

主规则固定为 `formation=7d, hold=7d, top_categories=2`。不从开发结果选择主参数。下列只作事前稳健性诊断，全部保存：

- `formation_14d`：14 日形成、7 日持有、前二；
- `hold_3d`：7 日形成、3 日持有、前二；
- `top_1`：7 日形成、7 日持有、第一名；
- `own_momentum`：目标自身 7 日收益为正，其他规则相同；
- `scheduled_long`：只过目标成交额门，不使用类别或自身动量。

总搜索披露：一个可选择主配置；三个不可选择的类别参数邻域；两个更简单基准。没有看结果后的人工变体。

## 成本、funding 与风险

- 初始名义为计划资本 `0.5x`，不借助高杠杆。
- favorable：每边 taker fee `6 bp`、spread/slippage `0 bp`；round trip 名义成本约 `12 bp`。
- base：每边 taker fee `6 bp`、spread/slippage `10 bp`；round trip 名义成本约 `32 bp`。
- stress：每边 taker fee `6 bp`、spread/slippage `20 bp`；正 funding 支出乘 `1.5`，负 funding 收益只保留 `0.5`。
- 每笔另以完整计划资本扣 `4%` 年化机会成本，按实际持有天数折算。
- 未覆盖历史 bid/ask、深度、队列、部分成交、精确账户手续费、保证金、强平/ADL、税务、系统故障与用户重新激活延迟。日线不解析 bar 内路径；固定 open 入出不使用同 bar 高低价止损。

## 时间隔离

| 阶段 | 信号/入场范围 | 角色 | 当前状态 |
|---|---|---|---|
| development | `2022-01-01` 至 `2024-01-01`（exit 可在 end 边界） | 只判断固定规则是否值得启封 | 未下载、未查看 |
| evaluation | `2024-01-01` 至 `2025-01-01` | 固定规则样本外评价；与原论文样本期重叠，不能算论文外确认 | 封存 |
| confirmation | `2025-01-01` 至 `2026-07-01` | 论文样本结束后的时间确认 | 封存 |

每阶段只取本阶段及 45 日暖启动。日线来自公开 REST；目标的 settled funding 与 8h mark proxy 来自官方 monthly archive 及相邻 `.CHECKSUM`。只有前一阶段所有门通过才允许下载下一阶段；失败后不打开后段寻找有利结果。

## 主要统计单位与门槛

每个目标按时间形成互不重叠的 one-shot 交易序列。主推断不把同时出现的多币交易当独立样本：先按 entry date 对合格交易等权形成“日期 cohort 平均”，再对该序列做 28 日 circular block bootstrap。它估计固定名单中一个事前未按结果挑选的合格计划的平均机会，不代表同时持有多腿的产品组合。

开发门全部满足才进入评价：

- 数据质量和 VectorBT/手工收益核对通过；主规则至少 300 笔、至少 20 个目标、至少 4 个目标类别；
- base 与 stress 的每笔平均净收益扣 4% 年化持有期机会成本后均为正；
- stress-hurdle 日期 cohort 块 bootstrap 95% 下界大于零；
- 2022、2023 的 base-hurdle 均值分别为正；
- 至少 50% 被交易目标和至少 4 个目标类别的 base-hurdle 均值为正；
- 主规则 base-hurdle 均值高于 `own_momentum` 与 `scheduled_long`；
- 三个参数邻域至少两个的 stress-hurdle 均值为正；
- 单一目标贡献不超过主规则全部正 PnL 的 20%；目标序列最大回撤中位数高于 `-20%`，最差高于 `-40%`。

评价门沿用经济、bootstrap、年度、广度、基准和集中度要求；至少 150 笔、15 个目标、4 个类别。确认门至少 150 笔、15 个目标、4 个类别；2025 与 2026H1 base-hurdle 分别为正，stress-hurdle 与 bootstrap 下界为正，评价+确认的日期 cohort 算术均值为正，且集中度和回撤不过界。

结论规则：

- 任一阶段 base 或 stress 的扣门槛均值不正，且样本/数据门满足：`DOES_NOT_SUPPORT`；
- 经济均值为正但稳健性、广度、集中度、分类/幸存者边界或样本门不足：`INSUFFICIENT_EVIDENCE`；
- 全部顺序门通过仍只能是固定分类、固定名单、公开 bar/funding 和代理成本内的 `SUPPORTS_WITHIN_SCOPE`；

## 2026-07-22 数据取得修正附录（任何收益分析前）

首次 development 数据质量检查发现：官方 8h markPriceKlines 在 2022-10-02、2023-02-24 缺整日，且 SOL 在 2022-11-09 至 2022-11-18 曾出现非 8 小时 funding 时点。因此，原第 55 行“仅用 8h mark open、缺失即不计算”会让全部目标或 SOL 无法通过质量门，但尚未产生任何收益结果。

修正规则固定为：先用原 8h 官方标记价；仅对实际无法在 1 分钟内匹配的 `目标 × 月`，下载同一 Binance public-data、同一 markPriceKlines 的 1m 月归档及 `.CHECKSUM`，再以 funding 时点最近 1 分钟内的 open 补足。仍不前向填充、不使用成交价、不把缺失 funding 当零；补充归档月份由 funding 时点和 8h 覆盖确定，不由收益决定。代码、附录和来源变化后必须重建 checkpoint、manifest 和质量结果；所有旧摘要保留在 `attempts.md`。

1m 归档仍缺整日，且官方 Funding Rate REST 对同一事件返回空 `markPrice`。在仍未计算任何收益时追加最终缺失规则：单目标缺失标记价事件占全部 funding 不得超过 `0.5%`；任何持仓窗只要跨过一条缺失事件，整笔交易从收益样本排除，但仍占用其原计划持仓与重启间隔；排除数和比例必须进入主结果及所有基准/邻域，主策略排除比例不得超过候选信号的 `2%`。不插值、不按零、不用合约成交价替代。这个处理牺牲样本而不猜测资金费名义；缺失集中于全市场异常日期、可能非随机，仍是结论限制。
- 输入身份或实现无法可靠判断才是 `CANNOT_DETERMINE`。

盈利回测不证明 Alpha，更不证明长期必然盈利。正结论也必须先由项目所有者明确选择，另开产品任务用框架无关轨迹和 NautilusTrader 验证。
