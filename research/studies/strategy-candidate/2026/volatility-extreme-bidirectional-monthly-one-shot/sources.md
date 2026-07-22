# 先行调研与数据边界

检索时间：2026-07-22。优先使用同行评审论文、作者/机构公开全文、Binance 官方数据与已有可重演研究；摘要不能支持未披露的方法细节。

## 原始研究

1. Kaya & Mostowf, *Low-volatility strategies for highly liquid cryptocurrencies*, Finance Research Letters 46 (2022), DOI `10.1016/j.frl.2021.102422`：<https://digitalcollection.zhaw.ch/server/api/core/bitstreams/5c4ee9d5-59bd-44fc-9934-d7a996d0ed96/content>。35 个高流动币，按历史波动排序构造等权低波 LONG 与相应高波 SHORT，测试 1/3/6/12 月形成和持有、现实交易成本；低波集中组合特别是更长窗口/持有有正证据，但高波 SHORT 并非普遍有效。适用：支持把相对波动排序作为独立机制并严格拆腿。差异：本题是 USD-M、RV90、月频单目标 one-shot、实际 funding、当前固定幸存者名单，不复制其 spot 组合或 stop-loss。公开全文保存在 Git 外 `_sources/low-volatility-strategies-liquid-cryptocurrencies-kaya-mostowf.pdf`，467,632 bytes，SHA-256 `f0dc7ab0def876c5b86962e3f382f35a977d91fecb184381f5f42d896d665dfd`。
2. Pyo & Jang, *Revisiting the low-volatility anomaly in cryptocurrency markets*, Finance Research Letters 97 (2026), DOI `10.1016/j.frl.2026.109851`：<https://ideas.repec.org/a/eee/finlet/v97y2026ics1544612326003818.html>。官方索引摘要称 post-2017 低实现波动系统性胜过高波动，且跨形成/持有窗口、市场控制、极端 BTC 阶段和固定早期上市 cohort 稳健。全文受限，因此只把“low-minus-high 是应检验对象”作为先验，不声称复制其精确参数或统计表。
3. Long et al., *Seasonality in the Cross-Section of Cryptocurrency Returns*, Finance Research Letters 35 (2020), DOI `10.1016/j.frl.2020.101566`：<https://repository.up.ac.za/server/api/core/bitstreams/43ef1895-818c-44bb-9c3c-848aa9f670f5/content>。151 币、20 周同星期收益、日频 quintile long-short 的成熟备选。公开全文保存在 Git 外 `_sources/seasonality-cross-section-crypto-long-et-al-2020.pdf`，747,337 bytes，SHA-256 `1ddbdf7ef7329079a734e907a30f4b2d78a683afad6334823f76c78b75ae37fa`。未选择原因是日频换手和多目标组合与当前半自动/零售成本不匹配。
4. Mueller, *Revisiting seasonality in cryptocurrencies*, Finance Research Letters 64 (2024), DOI `10.1016/j.frl.2024.105429`：<https://www.sciencedirect.com/science/article/pii/S1544612324004598>。约 500 币没有稳健普通日历收益异常，构成日历方向的反证；它不直接否定 Long et al. 的横截面同星期排序。
5. Kim, *Price Path Continuity and the Cross-Section of Cryptocurrency Returns* (SSRN, 2026), DOI `10.2139/ssrn.6871159`：<https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6871159>。14 日价格路径连续性是另一周频候选，但为近期工作论文、缺少独立复现，并与已有持续上涨状态研究相邻，因此不优先。

## 项目先验与已知暴露

- `../perp-low-volatility-monthly-one-shot-long/`：2022–2023 VOL90/bottom3 LONG 为正但未胜过 scheduled LONG、年度不一致、统计区间跨零，结论 `INSUFFICIENT_EVIDENCE`。
- `../high-volatility-monthly-one-shot-short/`：2024 VOL90/top3 SHORT 绝对结果为正但统计区间和邻域失败，结论 `INSUFFICIENT_EVIDENCE`。
- 因此 2024 双向结果可由相邻输出部分推断，只能作为选择回放；支持结论必须来自之后固定规则的顺序证据。

## 市场数据

- 2024/2025 复用已有 Binance 官方公开 USD-M 1d kline、settled funding、8h/必要时 1m mark 的冻结 manifest 和 SHA-256 身份，不复制大型文件。
- confirmation 只有 evaluation PASS 后才从 <https://data.binance.vision/> 和 Binance USD-M 公共 REST 获取，放在 Git 外：`D:/projects/Codex/CodexHome/research-data/halpha/volatility-extreme-bidirectional/2026-07-22-v1/`。
- 不使用产品数据库、凭据、运行配置、账户、订单或业务数据；不启动产品运行时。
- 日线和成本代理不能观测历史盘口、排队、部分成交、保证金、强平/ADL、月内 squeeze、人工计划延迟或场所故障。这些未知只降低结论，不能有利填补。
