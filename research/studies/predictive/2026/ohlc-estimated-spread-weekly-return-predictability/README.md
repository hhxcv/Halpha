# OHLC-estimated spread and next-week perpetual returns

This `PREDICTIVE` study asks whether the low-frequency bid-ask-spread effect
reported in a broad crypto factor zoo survives a narrower, actionable Halpha
setting. It does not create a strategy handoff or modify product code.

## Question

Among 25 fixed, mature Binance USD-M perpetuals, does a high trailing 28-pair
Abdi-Ranaldo close-high-low (`CHL`) spread estimate incrementally predict a higher
next actionable Monday-to-Monday return after controlling for Amihud illiquidity,
volatility, MAX, momentum, market beta, and quote volume? Is the relation stronger
than the two simplest explanations, and is a conservative single-leg proxy large
and stable enough to justify a separate strategy-candidate question?

## Operational timeline

- Saturday 00:00 UTC: calculate the score using only completed daily OHLC pairs.
  The last pair uses Friday's close and Friday's high/low as the `t+1` midrange;
  no Saturday high, low, or close is used.
- Monday 00:00 UTC: earliest modeled entry, after a two-day cooling gap.
- Next Monday 00:00 UTC: target week ends.

The main predictor is the mean of 28 two-day-corrected CHL spread estimates. The
main portfolio diagnostic is an equal-weight high-minus-low quintile return. A
plan-compatible feasibility proxy takes only the highest-volume member of the
high-spread quintile at 25% of plan capital and deducts a 52 bp underlying round
trip plus a 4% annual full-plan hurdle. It remains a diagnostic, not a strategy:
actual funding, executable quotes, and risk paths are not modeled here.

## Why this question

Mercik, Zaremba, and Demir's 2026 crypto factor zoo reports bid-ask spread as an
unusually persistent weekly cross-sectional factor, including a positive result
in both sample halves. The authors publish CC0 weekly factor returns, which this
study binds as an external reference. Abdi and Ranaldo provide a precise estimator
from daily close, high, and low prices, while Brauneis et al. find that daily
high/low/close estimators capture crypto-liquidity time variation better than many
other low-frequency proxies.

The adaptation is deliberately difficult: the source evidence uses a broad spot
universe and diversified factor portfolios, while Halpha has mature perpetuals,
a survivor-fixed universe, single-leg plan semantics, and material costs. The
main test therefore requires incremental evidence after Amihud and volatility,
not merely a positive gross factor spread.

## Reproduction

Run from the repository root with the locked research interpreter:

```powershell
research/.venv/Scripts/python.exe research/studies/predictive/2026/ohlc-estimated-spread-weekly-return-predictability/study.py checkpoint
research/.venv/Scripts/python.exe research/studies/predictive/2026/ohlc-estimated-spread-weekly-return-predictability/study.py bind
research/.venv/Scripts/python.exe research/studies/predictive/2026/ohlc-estimated-spread-weekly-return-predictability/study.py inspect
research/.venv/Scripts/python.exe research/studies/predictive/2026/ohlc-estimated-spread-weekly-return-predictability/study.py analyze --stage development
research/.venv/Scripts/python.exe research/studies/predictive/2026/ohlc-estimated-spread-weekly-return-predictability/study.py gate --stage development
# Later stages remain sealed unless the preceding gate passes.
research/.venv/Scripts/python.exe research/studies/predictive/2026/ohlc-estimated-spread-weekly-return-predictability/study.py conclude
research/.venv/Scripts/python.exe research/studies/predictive/2026/ohlc-estimated-spread-weekly-return-predictability/study.py validate
```

`bind` verifies and references an existing Git-external cache of official public
Binance responses plus the public CC0 reference dataset. It does not copy data or
access product storage. No command uses credentials, a product database, runtime
configuration, or a trading endpoint.
