# BTC–S&P 500 correlation-change next-interval predictability

This predictive study tests a public-price, post-publication transfer of Yae and
Tian's sequential-learning mechanism. It does not create a strategy handoff or
modify the product runtime.

## Question

After a U.S. trading day is complete, does a decrease in the recursively filtered
BTC–S&P 500 conditional correlation predict a higher BTCUSDT perpetual return over
the next U.S.-trading-day interval, after a 15-minute action delay, strongly enough
to justify a separately frozen one-leg strategy-candidate study?

## Operational timeline

- The S&P 500 cash close for U.S. trading date `D` is observable at 20:00 or
  21:00 UTC.
- The Binance BTC UTC anchor for `D` is the `D+1 00:00 UTC` daily open. Waiting
  until `00:15 UTC` removes the 3–4 hour non-synchronous-close shortcut explicitly
  acknowledged in the source paper.
- A hypothetical plan acts at the `D+1 00:15 UTC` 15-minute open and closes at
  `00:15 UTC` following the next S&P 500 trading date. Friday and holiday signals
  therefore have longer, explicitly measured holding intervals.

The primary object is a predictive relationship. A fixed-tail, 25%-notional
long/short calculation is only a conservative feasibility screen; passing it would
still require a separate funding-aware strategy study.

## Reproduction

Run from the repository root with the locked research interpreter:

```powershell
research/.venv/Scripts/python.exe research/studies/predictive/2026/btc-sp500-correlation-change-next-interval-predictability/study.py checkpoint
research/.venv/Scripts/python.exe research/studies/predictive/2026/btc-sp500-correlation-change-next-interval-predictability/study.py fetch --stage development
research/.venv/Scripts/python.exe research/studies/predictive/2026/btc-sp500-correlation-change-next-interval-predictability/study.py inspect --stage development
research/.venv/Scripts/python.exe research/studies/predictive/2026/btc-sp500-correlation-change-next-interval-predictability/study.py analyze --stage development
research/.venv/Scripts/python.exe research/studies/predictive/2026/btc-sp500-correlation-change-next-interval-predictability/study.py gate --stage development
# Later stages remain sealed until the preceding stage passes.
research/.venv/Scripts/python.exe research/studies/predictive/2026/btc-sp500-correlation-change-next-interval-predictability/study.py conclude
research/.venv/Scripts/python.exe research/studies/predictive/2026/btc-sp500-correlation-change-next-interval-predictability/study.py validate
```

Raw FRED and checksummed Binance public files are content-addressed outside Git at
the cache root recorded in `checkpoint.json`. No command reads product data,
credentials, databases, or runtime configuration. The econometric layer uses
NumPy/SciPy/statsmodels; vectorbt 1.1.0 supplies framework-level return statistics
for the fixed feasibility series. The small DCC recursion is study-specific rather
than a new shared research framework.

