# Attempts

## 2026-07-22 — direction screen and source review

- Reviewed the retained basic-data frontier and the direct failures in raw momentum,
  risk-adjusted momentum, BTC lead-lag/residual reversal, calendar, VIX beta,
  volatility, premium/funding-flow proxies and daily Amihud liquidity.
- Selected residual momentum because a 2026 peer-reviewed cryptocurrency paper
  retains it in an out-of-sample factor model and because it is falsifiable against
  ordinary MOM14 and common-factor exposure without adding a new data service.
- The ScienceDirect page and author/SSRN record were accessible; the SSRN PDF fetch
  returned HTTP 403 in the current environment. The publisher section snippets,
  bibliographic record and open publisher-version Blitz paper were sufficient to
  freeze an explicitly non-numerical operational transfer. No missing method detail
  was guessed as a claimed replication.
- Reused the exact public Binance cache bound by the prior VIX-beta study. No product
  data, database, credential, runtime or trading endpoint was used.

## 2026-07-22 — frozen development replay

Commands, in order:

```powershell
research/.venv/Scripts/python.exe research/studies/predictive/2026/residual-momentum-weekly-return-predictability/study.py checkpoint
research/.venv/Scripts/python.exe research/studies/predictive/2026/residual-momentum-weekly-return-predictability/study.py bind
research/.venv/Scripts/python.exe research/studies/predictive/2026/residual-momentum-weekly-return-predictability/study.py inspect
research/.venv/Scripts/python.exe research/studies/predictive/2026/residual-momentum-weekly-return-predictability/study.py analyze --stage development
research/.venv/Scripts/python.exe research/studies/predictive/2026/residual-momentum-weekly-return-predictability/study.py gate --stage development
research/.venv/Scripts/python.exe research/studies/predictive/2026/residual-momentum-weekly-return-predictability/study.py conclude
research/.venv/Scripts/python.exe research/studies/predictive/2026/residual-momentum-weekly-return-predictability/study.py validate
```

- Checkpoint, source binding and data quality passed. The binding verified 51 files,
  6,713,938 bytes, without copying the raw cache.
- Development produced a positive `+1.8096%` weekly high-minus-low mean and a
  `+0.6189%` full-plan one-leg proxy mean, but the gate failed 11 checks.
- The primary spread was positive in only 50% of weeks, its block interval crossed
  zero, the first half was negative, rank IC and controlled slope were negative,
  proxy uncertainty crossed zero, and positive proxy P&L was concentrated in SOL.
- Evaluation and confirmation were not run. No failed command was hidden and no
  post-result rule change was made.

