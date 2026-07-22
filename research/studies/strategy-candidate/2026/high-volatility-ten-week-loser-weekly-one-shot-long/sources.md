# 来源、适用性与反证

访问时间 `2026-07-22`。

1. Patrick Kiefer、Michael Nowotny，*Reversal in Cryptocurrency Returns*，SSRN `6703978`，2026-05-03，2026-06-01 修订：https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6703978
   - 原始摘要称 Binance USDT spot 2021–2026 的 8–10 周 loser-minus-winner 反转集中于较高波动、中等规模资产；报告 high-vol 分组、不同分位、skip、inverse-vol、时间子样本和 circular block bootstrap。
   - 全文未能可靠取得，摘要未披露本题所需的精确 volatility 窗口/排序，因此本题不冒充论文复现。RV28/高半区是透明、固定的项目转换；未披露细节保留为未知。
2. Victoria Dobrynskaya，*Cryptocurrency Momentum and Reversal*，JAI 26(1), 65–76 (2023)，DOI `10.3905/jai.2023.1.189`。
   - HSE 记录：https://publications.hse.ru/en/articles/811744977
   - HSE 全文：https://conference.hse.ru/files/download_file_ex?hash=FAE0AB2DC7A67656E89A0B1CB27D8C7D&id=3B5EE9A5-0B18-458A-9458-B4ED0F6C6664
   - 本地公开缓存 SHA-256 `a97eeda242f1ba863ed4006a7f0854d5356cf80d84adda697ae1eeb183d839b6`。约 2,000 币、2014–2020、周频、底/顶 30%、市值加权；中期反转主要来自 loser 长腿，但与当前幸存永续单目标差异很大。
3. Pyo、Jang，*Revisiting the low-volatility anomaly in cryptocurrency markets*，Finance Research Letters 97 (2026)，DOI `10.1016/j.frl.2026.109851`。
   - 出版记录：https://ideas.repec.org/a/eee/finlet/v97y2026ics1544612326003818.html
   - 报告后 2017 低波动币相对高波动币表现更好，是 Q18 的直接反证先验：高波动条件本身可能只是负风险暴露，故必须胜过 low-vol loser、high-vol scheduled 和市场。
4. Halpha Q17 `../ten-week-loser-weekly-one-shot-long/`：无条件 MOM70 loser 在 2022–2023 base/stress 扣门槛 `-0.0504%/-0.1329%` 每周，且未胜过 MOM7/赢家，结论 `DOES_NOT_SUPPORT`。Q18 不能复用其 2022–2023 作“新证据”，也不能失败后继续条件搜索。

数据：Binance 公开 USD-M 1d Kline、官方 monthly fundingRate 与 markPriceKlines archives；https://data.binance.vision/ 与 https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/Introduction 。无凭据、账户、产品数据库或交易端点。

框架：VectorBT `Portfolio.from_orders`（https://vectorbt.dev/api/portfolio/base/#vectorbt.portfolio.base.Portfolio.from_orders）与手工公式双算。未使用 L2、OI/liquidation、新闻、链上、点时市值/退市历史；固定 current-survivor 名单可能高估输家恢复，结论只限当前名单条件转换。
