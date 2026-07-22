# 结果：DOES_NOT_SUPPORT

传统 `(-1,+3)` BTC 月末/月初效应没有在当前 Binance USD-M、个人半自动计划语义下延续。固定规则为：每月最后一个 UTC 日开盘以全计划资本的 0.5 倍做多 `BTCUSDT-PERP`，次月 4 日 UTC 开盘退出；不使用趋势、波动率、funding 或月份筛选。

## 核心结果

2022–2023 development 共 24 个计划。扣 6 bp/边 taker fee、10 bp/边滑点与实际 funding 后，base 累计收益为 **-7.0143%**；stress（20 bp/边滑点及不利 funding）为 **-9.7364%**。base/stress 最大回撤分别为 **-17.2544% / -19.0383%**，stress 月份只有 **29.17%** 为正；2022 和 2023 base 分别为 **-4.9635% / -2.1579%**。stress 月收益三个月循环块 bootstrap 95% 区间为 **[-1.2081%, +0.3648%]**。

这不是只有交易成本把一个正规律磨掉：零滑点 favorable 累计仍为 **-4.7522%**。用 730 个 open-to-next-open 日收益复现论文 dummy 方法时，96 个 TOM 日平均对数收益为 **-0.06753%**，其余 634 日为 **-0.00367%**；HAC 的 TOM 增量为 **-0.06387%/日**，95% 区间 **[-0.5573%, +0.4296%]**，正向单侧 `p=0.6001`。

固定反解释也不支持主规则：相对相同四天暴露的每月 14–18 日基准，主规则 base 每月平均低 **0.4083%**，配对块区间 **[-1.9889%, +0.9113%]**。两个事前诊断 `TOM3`、`TOM5` 的 base 累计也分别为 **-0.6084% / -11.7503%**。中旬窗口的 +2.0040% base、-0.9259% stress 只是一项固定反解释，未经独立预注册和后续证据，不能事后升级成策略。

## 解释边界

这项结果不否定 Kumar (2022) 与 Kaiser–Stöckl (2022) 在 2021 年以前现货样本中的统计发现；它否定的是把该发现直接移植为 2022–2023 的 UTC、Binance 永续、0.5x、单腿、现实成本/funding 半自动计划。可能差异包括效应衰减、现货与永续参与者不同、24/7 UTC 日界与传统交易日不同，以及早期样本的市场结构不同。当前设计不能在这些解释间建立因果识别。

开发门失败后，2024 evaluation 与 2025–2026H1 confirmation 依预注册保持封存。没有搜索其它月份、日界、窗口、方向、仓位或过滤器；没有 handoff，也没有产品、资金或真实账户影响。该日历家族若无新的独立机制或真正未暴露数据，不应以邻近日期重新开题。

## 数据、身份与重演

- 产品基准：`0bdfeffa616260cebd2d2188ddc8deb9e85c77f4`
- 正式比较身份：`ONE_SHOT_DONCHIAN_ATR_BREAKOUT 1.0.1 / BTCUSDT-PERP`
- Git 外缓存：`D:/projects/Codex/CodexHome/research-data/halpha/btcusdt-perp-turn-of-month-one-shot-long/2026-07-22-v1`
- 数据：1,677 个连续 Binance USD-M UTC 日线、5,029 个 funding 事件及官方 8h mark 补值；质量 `PASS`
- checkpoint：`427ab6c636fa834a3241aff5d93ee3487f58390113b699def9efb3972f3ef745`
- source manifest：`a39de3c8716404c5ba6ec13402cd808d3857bb7dc76e06eb4573036bec991ea7`
- development：`ed07c44f88b40e6e57f692b447edb08f8dc8790756149a2c9d16a722c04b3a9e`
- development gate：`65607a4ce1872ca6a3fd3eeaa84d9ac9b81d065fb82d9c0cdceeb86270fafe2b`
- final results：`96e42cdc5005cd831891e29d59631e214d6cce2517580b965cfeebd86ec0c5ab`
- validation：`613b1f57980199e6b017d340d9ca00a8d2242504e65bb59bf21429ef134ebc73`，状态 `PASS`

完整命令见 `README.md`；重演会重新核对原始响应身份、独立重算经济结果、HAC 结果、门及五个逐计划 CSV。盈利回测从未被视为 Alpha 证明，本次负结果也不外推为所有市场、日界或未来时期的普遍定律。

