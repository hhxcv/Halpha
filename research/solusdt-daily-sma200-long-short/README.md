# SOLUSDT 日线 SMA200 0.5x 双向趋势候选研究

## 状态与边界

- 稳定产品基准提交：`de6b3052f28fe547730e89e58186d4ab397884b1`
- 固定正式策略：`ONE_SHOT_DONCHIAN_ATR_BREAKOUT` `1.0.0`
- 候选身份：`RESEARCH_SOLUSDT_DAILY_SMA200_LONG_SHORT_0P5X`
- 标的：Binance USDⓈ-M `SOLUSDT` 线性永续，UTC 日线，0.5x 初始资本名义。
- cutoff：`2026-07-01T00:00:00Z`。
- 用途：判断一个单标的、低换手、能在下行状态持有 short 的趋势候选是否有范围内支持；不是产品策略、资金决定、收益保证或真实交易许可。

只使用公开数据与独立研究代码；不读取产品数据库、业务数据、秘密或运行配置，不启动产品运行时，不调用交易所变更端点。大文件在 Git 外，研究目录保存可重取身份和全部小型证据。

## 去重、候选与选择

ETH SMA200 long/cash 在 2024–2025 总体正且显著减小回撤，但 2025 为负、2026H1 全现金，结论为 `INSUFFICIENT_EVIDENCE`。本问题只计作同一趋势家族的后续候选，不把两者重复算作两个独立 Alpha。它事先改变的是稳定用途：固定 0.5x 双向而非 long/cash，并使用完全未查看的 SOL 数据检验牛熊适配和 short 风险。

| 候选 | 决策价值 | 复杂度/风险 | 取舍 |
|---|---|---|---|
| SOL 日线 SMA200 0.5x long/short | 单标的、低换手；熊市不必长期现金；全新数据 | short 有 squeeze、清算和 funding 风险 | **选中**；用 0.5x、日内 adverse 检查约束 |
| SOL 1x long/short | 收益更高 | 账户级 short liquidation 风险明显更高 | 淘汰，不搜索杠杆 |
| 12 月收益符号 | 原始 TSMOM 常见 | 与 SMA200 同义选择 | 不并行搜索 |
| 多周期 Donchian | 文献证据较强 | 与正式策略重复且参数更多 | 淘汰 |

## 先行调研（访问日 2026-07-20）

1. Moskowitz、Ooi、Pedersen, [Time Series Momentum](https://doi.org/10.1016/j.jfineco.2011.11.003)（JFE, 2012）：在多类液态期货上报告 1–12 月趋势持续并使用 long/short。它给出机制先验，但分散组合不能替代单一 SOL 证据。
2. Han、Kang、Ryu, [Momentum in the Cryptocurrency Market: A Comprehensive Analysis under Realistic Assumptions](https://doi.org/10.2139/ssrn.4675565)（2024，2026 修订）：crypto time-series momentum 强于 cross-sectional，但厚尾、日内价格和清算会令表面均值失真。它直接促使本研究用 0.5x、日内 high/low adverse、分年、回撤和成本门。
3. Zarattini、Pagani、Barbon, [Catching Crypto Trends](https://doi.org/10.2139/ssrn.5209907)（2025）：survivorship-bias-free crypto 趋势研究报告净费用后证据并强调波动率 sizing 与换手控制。当前问题固定单标的/单周期以降低个人维护复杂度，不能移植其组合结果。
4. Meb Faber, [A Quantitative Approach to Tactical Asset Allocation](https://ssrn.com/abstract=962461)（2007/2013）：提供 10 个月均线作为低自由度风险过滤先例；其 long/cash 设计不是本研究 short 证据。
5. [Binance Public Data](https://github.com/binance/binance-public-data) 与 [USDⓈ-M Funding History](https://developers.binance.com/en/docs/derivatives/usds-margined-futures/market-data/rest-api/Get-Funding-Rate-History)：官方日线与 funding 输入、checksum 和修订边界。

## 固定问题、规则和否定条件

问题：以前一 UTC 日 close 相对当日已知 SMA200 的位置决定下一日 `+0.5x long` 或 `-0.5x short`，能否在实际 funding、每单位换手 16 bp base 成本和日内 adverse 风险下，于 2021–2023 开发、2024–2025 独立评价及 2026H1 确认都保持正复合收益？

- SMA：包含信号日 close 的最近 200 日简单均线；不足 200 日不持仓。
- 执行：下一日 open 调整到 `+0.5` 或 `-0.5`；连续同方向不重复收费；日 close 计收益。
- funding：按当日实际 rate 总和和 0.5x 方向计入；精确 mark 未知，按初始名义代理。
- 换手成本：有利/base/stress 为每 1.0 绝对名义变化 6/16/26 bp；long↔short 的 1.0 turnover 已含平旧开新。
- 不搜索 SMA、杠杆、缓冲、止损、持有期或成本。
- 风险检查：用日 high/low 相对当前趋势 episode 入场价计算最差资本 adverse；若 <= -50%，不能形成支持结论，即使日线 close 回测为正。
- 基准：0.5x 持续 long SOL 永续，计 funding 与首尾成本；现金为零。正式 Donchian/ATR 的标的和激活日程不可比，不运行第二实现。

开发门：base 复合收益为正，2021–2023 三年均正，30 日 block bootstrap 日均下界大于零，最大回撤小于 0.5x 持续 long，且最差 episode adverse 大于 -50%。单一规则，无参数选择；失败即停止并保留 2024–2026。

`SUPPORTS_WITHIN_SCOPE` 还要求：2024–2025 总收益和两年分别为正、bootstrap 下界为正、回撤小于持续 long、adverse > -50%；2026H1 总收益为正且 adverse > -50%。评价总收益为负则 `DOES_NOT_SUPPORT`，其余为 `INSUFFICIENT_EVIDENCE`。

## 数据与启封

SOLUSDT 的 spot、perp、funding 或收益此前均未在 `research/**` 使用。本研究只取 perpetual 日线和 funding。

| 区间 | 用途 | 状态 | 启封 |
|---|---|---|---|
| 2021-01-01 至 2024-01-01 | development | 已运行；数据质量修复后仍未过门 | checkpoint 和代码固定后 |
| 2024-01-01 至 2026-01-01 | evaluation | **未查看、未下载** | 开发门失败，保持封存 |
| 2026-01-01 至 2026-07-01 | confirmation | **未查看、未下载** | 开发门失败，保持封存 |

只允许修复下载、checksum、解析、数据质量或不改变经济规则的实现错误。盈利回测不证明 Alpha；主要反证是 short squeeze/adverse、funding、非平稳或成本使任一独立阶段失效。

## 环境、缓存与限制

Python 3.11.9、pandas 2.3.3、numpy 2.4.6；外部缓存：`D:/projects/Codex/CodexHome/research-data/halpha/solusdt-daily-sma200-long-short/`。不修改产品依赖。

日线无法证明 bar 内止损或清算顺序，0.5x 也不保证账户永不清算；保证金模式、maintenance margin、ADL、盘口、部分成交、最小名义、USDT 现金收益和税务未建模。若结果为正，仍须在产品考虑任务重新验证场所规则和实时执行。

## 实际结果

官方 checksum 验证通过的月归档缺 5 根日线：2022-02-26、27、28 与 2022-04-01、02。Binance 官方仓库说明 USD-M 归档 Kline 来自 `/fapi/v1/klines`、归档可能因问题后续更新；公开 issue #297 也记录 2022-04-01 至 02 的多币种（含 SOL）期货 Kline 缺失。修复只从同一官方只读端点补齐缺失 open time，不覆盖任何归档行；补数 JSON 的 SHA-256 为 `6ce36c95cfa8138f3e70a7ccd047da029fdb20e4dd86fe3f8fcd13826451ef0b`，新 manifest identity 为 `a99c312ad205dcf217dec7200e9b134b2a83ed33909cd8f93ac3a8108a4e563a`。

| 开发集指标（base） | 数据质量修复后结果 |
|---|---:|
| 日数 / gaps | 1,095 / 0，`PASS` |
| 复合收益 | +166.84% |
| 2021 / 2022 / 2023 | +137.06% / +38.48% / **-18.72%** |
| 30 日 block-bootstrap 日均 95% CI | **[-0.0526%, +0.3289%]** |
| 最大回撤 | -71.88%（0.5x 持续 long：-73.06%） |
| 最差 episode adverse / turnover | -9.72% / 19.0 |
| favorable / stress 总收益 | +171.96% / +161.81% |

开发门同时被 2023 负收益和 bootstrap 下界小于零否定；高总收益主要由早期 SOL 牛熊趋势贡献，不能覆盖年份不稳健与极深回撤。按预注册停止，不使用 2024–2026 来补救或改规则。

## 结论

`DOES_NOT_SUPPORT`

在固定问题范围内，不支持把 SOLUSDT 日线 SMA200 0.5x 双向规则列为“可用、已有支持”的候选策略。它保留为一个有盈利潜力但开发证据失败的反例：成本敏感性较低、趋势年有效，却没有稳定到足以启封独立区间。盈利回测不构成 Alpha 证明，本研究不改变产品策略、L4、资金或真实账户状态。

可重演命令、首次缺数失败、数据完整性修复、复跑与缓存身份见 `attempts.md`；机器结果见 `development_backfilled.json`、`selection_backfilled.json` 与 `results.json`。
