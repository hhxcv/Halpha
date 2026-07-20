# 先行调研与适用性

访问日期均为 2026-07-20；下列来源在运行本题收益结果前记录。

| 来源 | 层级 | 本题使用 | 适用差异与反证 |
|---|---|---|---|
| Moskowitz, Ooi & Pedersen (2012), [Time Series Momentum](https://doi.org/10.1016/j.jfineco.2011.11.003) | 同行评审原始论文 | 自身过去收益方向在 1–12 个月可能延续，是 60/90/180 日方向规则的成熟先验 | 原论文是 58 个传统期货的分散组合，不证明单一 BTC、永续资金费率后或小样本有效 |
| Han, Kang & Ryu (2023/2026 revision), [Momentum in the Cryptocurrency Market: A Comprehensive Analysis under Realistic Assumptions](https://doi.org/10.2139/ssrn.4675565) | 原始工作论文 | 指出 crypto 时间序列动量证据强于横截面动量，并要求把日内波动、清算和厚尾纳入现实检查 | 工作论文仍在修订；统计正收益可能在清算后变成负利润，直接构成本题的否定风险 |
| Grobys et al. (2025), [Cryptocurrency momentum has (not) its moments](https://doi.org/10.1007/s11408-025-00474-9) | 同行评审原始论文 | 空头腿会因单币暴涨出现严重尾部风险；支持采用单一最成熟币、0.25× 硬上限和 adverse 检查 | 研究对象主要是横截面组合与周频，不直接验证 BTC 时间序列规则；波动管理不能消除厚尾 |
| Wesselink (2018), [Time-series Momentum in the Cryptocurrency Market](https://thesis.eur.nl/pub/44390/) | 可核查学位论文，反证 | 其 long-short 组合未得到显著正收益，防止把传统期货先验当作 crypto 结论 | 非同行评审、早期样本、日频多币组合，仅作反证线索 |
| Binance Academy, [What Are Funding Rates in Crypto Markets?](https://academy.binance.com/en/articles/what-are-funding-rates-in-crypto-markets) | 交易场所官方教育资料 | 正 funding 为多头向空头付款，负 funding 反向；标准间隔 8 小时，2025 年开始可动态改变 | Academy 不是合约规范；因此按实际结算记录计费，并把确认期截到动态制度生效前 |
| Binance public data archives, [data.binance.vision](https://data.binance.vision/) | 交易场所公开数据源 | 锁定的现货/USD-M 永续 8 小时 OHLC ZIP 与官方 CHECKSUM | K 线 open/close 不是可执行订单簿；没有深度、延迟、清算价格或账户费率 |
| Binance USD-M API, [Funding Rate History](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Get-Funding-Rate-History) | 交易场所官方 API 文档 | 公开 `NONE` 市场数据，锁定 fundingTime/fundingRate 快照 | 回测用永续 K 线 open 近似结算名义价值，未重建 mark price，保守成本不能消除该差异 |

## 候选筛选

本轮少量候选为：（1）BTC 永续双向多周期趋势；（2）BTC/ETH 相对强弱 market-neutral；（3）极端负 funding 的反向修复。选择（1），因为它直接回答此前 long/cash 在 2025 失败时“空头状态能否盈利”的未解决差异，单币、月频、公开数据、最高 0.25×，验证和个人维护成本最低。相对强弱仍需两条腿、相关性和双重 funding；极端 funding 事件更少、确认周期更长，当前决策价值较低。

本题不是 Alpha 证明。即使通过，也只支持已锁定区间与摩擦假设下的研究候选；不授权产品策略、L4、资金或真实账户动作。
