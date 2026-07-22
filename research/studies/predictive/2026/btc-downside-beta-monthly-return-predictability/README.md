# BTC downside beta and next-month mature-perpetual returns

This predictive question tests whether the earlier cryptocurrency downside-risk
premium transfers to a fixed, liquid Binance USD-M survivor universe in a form that
could later justify a simple one-leg monthly plan. It is not yet a strategy study.

## Question

Among 25 mature liquid perpetuals, does trailing 60-day beta measured only on
negative BTC days positively predict next-month return after total beta, total
volatility, momentum, MAX, and volume controls, with incremental information beyond
simply selecting high-beta or high-volatility instruments?

## Reproduction

Use `research/.venv/Scripts/python.exe`. Existing content-addressed public altcoin
data are reused. BTC daily public pages are stored outside Git and identified by the
stage source manifest.

```powershell
research/.venv/Scripts/python.exe study.py checkpoint
research/.venv/Scripts/python.exe study.py self-test
research/.venv/Scripts/python.exe study.py fetch --stage development
research/.venv/Scripts/python.exe study.py prepare --stage development
research/.venv/Scripts/python.exe study.py analyze --stage development
research/.venv/Scripts/python.exe study.py gate --stage development
research/.venv/Scripts/python.exe study.py validate
```

Later stages may be fetched and opened only after the preceding gate passes.

