# 来源与外部启发

- [Binance USD-M Exchange Information](https://fapi.binance.com/fapi/v1/exchangeInfo)：确认 `TRXUSDT`、`PAXGUSDT` 当前均为 `TRADING` 的 `PERPETUAL` 合约；PAXGUSDT `onboardDate=1743071400000`（2025-03-27 14:30 UTC）。研究缓存只保留两个合约的响应字段和 checksum。
- [Binance USD-M Funding Rate History](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Get-Funding-Rate-History)：实际 funding 事件来源；不得用固定费率替代。
- [Binance Public Data](https://data.binance.vision/)：官方月度 USD-M 日线与 8h mark-price K 线归档；每个 zip 在 manifest 中固定 URL、字节数与 SHA-256。
- [Binance Academy: Funding Rates](https://academy.binance.com/en/articles/what-are-funding-rates-in-crypto-markets)：funding 用于使 perpetual 价格贴近现货，持有多头可能支付也可能收取；这正是现货结论不能直接移植到 perpetual 的机制差异。
- 内部先验：`research/studies/legacy/2026/trx-paxg-balanced-spot/results.json`。该固定 25/25 月度现货配置已通过开发、评价和新鲜确认；本题不重新选择其标的或参数。

未采用新的外部“高收益策略参数”。本题的价值是验证一个已有强证据、低复杂度组合能否穿过当前交易场所的真实摩擦。
