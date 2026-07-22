# Relative signed jump and next-day perpetual returns

This predictive study asks whether a high-frequency price-asymmetry result from the
academic cryptocurrency literature transfers to Halpha's liquid perpetual universe.
It does not create a strategy, handoff, product change or trading authorization.

## Question

Among 25 mature Binance USD-M perpetuals, does a low daily relative signed jump
(`RSJ = (RV+ - RV-) / RV`) computed from closed 15-minute bars predict a higher
next-24-hour return than a high RSJ, after a 15-minute action delay and controls for
one-day reversal, realized volatility, momentum, beta, MAX and volume?

The source paper uses 5-minute vendor tick data, a broad spot universe and daily
long-short portfolios. Halpha deliberately tests a lower-complexity operational
transfer: official 15-minute perpetual klines, a fixed survivor universe, a one-leg
feasibility proxy and conservative retail costs. This is not a numerical replication.

## Why selected

The current daily-data frontier has direct negative or insufficient evidence across
momentum/path, reversal/extremes, volatility/downside risk, liquidity/volume,
premium/funding, calendar, BTC relationships and external uncertainty. RSJ is
different: it measures whether squared positive or negative intraday moves dominate
within a day, rather than using daily direction or total volatility alone.

The direction passed a cost/value screen because:

- a peer-reviewed cryptocurrency study reports a strong negative RSJ–next-day return
  relation after reversal, volatility, salience and factor controls;
- 2022 onward is later than the source sample ending 2021-06, though the broad market
  path has been exposed in other Halpha work;
- official Binance monthly 15-minute archives are small, checksummed and reusable;
- a decision at 00:00 UTC and entry at 00:15 UTC corresponds to 08:00/08:15 China
  time, making manual activation possible if a later strategy question qualifies;
- 30-minute and one-hour resolutions can be derived from the same files, so sampling
  robustness does not require more data.

Five-minute data is not fetched. If 15-minute operational transfer fails, this study
stops; failure does not refute the source's 5-minute finding. If all predictive stages
pass, a separate strategy-candidate study must add actual funding and vectorbt replay.

## Reproduction

```powershell
research/.venv/Scripts/python.exe research/studies/predictive/2026/relative-signed-jump-next-day-predictability/study.py checkpoint
research/.venv/Scripts/python.exe research/studies/predictive/2026/relative-signed-jump-next-day-predictability/study.py fetch --stage development
research/.venv/Scripts/python.exe research/studies/predictive/2026/relative-signed-jump-next-day-predictability/study.py inspect --stage development
research/.venv/Scripts/python.exe research/studies/predictive/2026/relative-signed-jump-next-day-predictability/study.py analyze --stage development
research/.venv/Scripts/python.exe research/studies/predictive/2026/relative-signed-jump-next-day-predictability/study.py gate --stage development
research/.venv/Scripts/python.exe research/studies/predictive/2026/relative-signed-jump-next-day-predictability/study.py conclude
research/.venv/Scripts/python.exe research/studies/predictive/2026/relative-signed-jump-next-day-predictability/study.py validate
```

Large zip inputs live outside Git under the path recorded in each stage manifest.
Evaluation and confirmation remain sealed until the immediately preceding gate passes.

