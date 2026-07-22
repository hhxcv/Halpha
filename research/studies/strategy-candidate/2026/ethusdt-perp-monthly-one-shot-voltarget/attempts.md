# Attempts and failures

## 2026-07-22 — registration

- Reused the already validated TRX perpetual research engine for Binance pagination,
  funding settlement, VectorBT/manual reconciliation, and daily equity accounting.
- Chose an independent external cache so raw responses remain content-addressed and
  reusable without copying generated data into Git.
- No strategy output had been calculated when the preregistration was frozen.

## 2026-07-22 — public data and development

- Retrieved two daily-kline pages, five 8-hour mark-price-kline pages, seven
  funding pages, and one current exchange-information snapshot from public Binance
  USD-M endpoints. The manifest digest is
  `183d5f6e449fd8475cb0466cfe73b0ddfd0c63962bcc2f02655c141ff9632b7c`.
- Data quality passed: 2,100 consecutive daily bars, 6,298 funding observations,
  no missing OHLC days, no invalid ranges, and no missing funding mark price after
  official 8-hour mark-kline reconciliation.
- Opened only the registered 2021–2022 development stage. The 8% primary rule failed
  the stress-after-4%-hurdle, base-after-6%-combined-hurdle, and Sharpe-versus-fixed-
  quarter gates. Evaluation and confirmation were not opened.
- No parameter, entry date, cap, instrument, or trend-filter repair was attempted.

