# Residual momentum and next-week perpetual returns

This directory tests one predictive question only. It does not qualify a strategy,
create a product handoff, change the formal strategy, or authorize trading.

## Question

Among the same 25 mature Binance USD-M perpetuals used by the current basic-data
research frontier, does high 14-day residual momentum predict higher next-week
returns after removing a leave-one-out crypto-market factor, and does it add value
beyond ordinary 14-day momentum in a conservative one-leg feasibility proxy?

The operational score is the mean of the most recent 14 daily open-to-open returns
minus their estimated common-market component, divided by residual volatility. The
market beta is estimated over 84 complete days; the fitted intercept is not included
in the score, following the distinction made by Blitz, Huij and Martens. A two-day
signal-to-entry gap separates the Saturday decision from the Monday open.

## Why this question was selected

The selection screen considered five directions:

1. **Residual momentum — selected.** A 2026 peer-reviewed cryptocurrency factor
   study retains residual momentum in a three-factor model and reports better
   out-of-sample anomaly explanation. It uses only basic market data, maps to a
   weekly one-leg plan, and can be rejected against ordinary momentum.
2. **Dollar/macro timing — rejected for now.** Low independent sample count and a
   weak instrument-level mapping make it lower decision value after the VIX-beta
   failure.
3. **Crypto market breadth — rejected for now.** Direct crypto evidence is not yet
   mature and the idea overlaps existing market-state/dispersion work.
4. **Token dilution or network growth — deferred.** These require a new point-in-time
   supply/on-chain dataset and do not meet the current basic-data boundary.
5. **Exact Donchian/ATR transfer to more instruments — deferred.** It requires a
   costly 1m/15m execution-semantic replay and tests instrument portability, not a
   second return mechanism.

This is an operational transfer test, not a numerical replication. The source papers
use broad spot universes, market capitalization and/or long-short portfolios. Halpha
uses a fixed survivor universe of liquid perpetuals, one-leg feasibility, actual
future product qualification gates, and conservative retail costs. Those differences
are retained as limitations even if the prediction passes.

## Reproduction

Run from the repository root with the isolated research environment:

```powershell
research/.venv/Scripts/python.exe research/studies/predictive/2026/residual-momentum-weekly-return-predictability/study.py checkpoint
research/.venv/Scripts/python.exe research/studies/predictive/2026/residual-momentum-weekly-return-predictability/study.py bind
research/.venv/Scripts/python.exe research/studies/predictive/2026/residual-momentum-weekly-return-predictability/study.py inspect
research/.venv/Scripts/python.exe research/studies/predictive/2026/residual-momentum-weekly-return-predictability/study.py analyze --stage development
research/.venv/Scripts/python.exe research/studies/predictive/2026/residual-momentum-weekly-return-predictability/study.py gate --stage development
research/.venv/Scripts/python.exe research/studies/predictive/2026/residual-momentum-weekly-return-predictability/study.py conclude
research/.venv/Scripts/python.exe research/studies/predictive/2026/residual-momentum-weekly-return-predictability/study.py validate
```

Evaluation and confirmation remain sealed unless the immediately preceding gate is
`PASS`. Large public inputs remain in the existing content-addressed Git-external
cache; this directory binds their exact identities without copying them.

