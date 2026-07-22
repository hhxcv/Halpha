# ETHUSDT monthly one-shot volatility target

This question tests a deliberately small, low-maintenance risk-premium strategy for
Halpha's semi-automatic plan workflow. It does not claim that volatility scaling is
Alpha and it does not modify or invoke the product runtime.

## Question

Can a fixed monthly `ETHUSDT-PERP` long, sized from trailing 60-day realized
volatility to an 8% annual target and capped at 25% of user-selected plan capital,
clear realistic perpetual costs and a 6% annual combined capital/research hurdle
across sequential periods while improving risk versus a fixed 25% monthly long?

## Why this question

- ETH is already in the current demo instrument scope and is liquid enough for a
  small personal account; no universe selection, cross-leg execution, transfer, or
  research-only data is needed at decision time.
- The rule produces one plan per month and maps to the current contract as a target
  **user-entered maximum notional**, not as autonomous allocation inside the core.
- The return source is ETH directional risk premium. Volatility scaling is only a
  risk-control mechanism. A positive backtest would not prove Alpha or guarantee
  long-term profitability.
- Existing ETH paths have been viewed by earlier Halpha work. The exact rule and its
  results are new and sequentially gated, but this is not pristine investigator-blind
  market-time evidence; the limitation remains in every conclusion and handoff.

## Reproduction

Use the repository research environment. Public raw data is stored outside Git at
the cache root recorded in `checkpoint.json` and every page is identified in
`source_manifest.json`.

```powershell
python study.py checkpoint
python study.py fetch
python study.py inspect
python study.py analyze --stage development
python study.py gate --stage development
# Continue only if the preceding gate is PASS.
python study.py analyze --stage evaluation
python study.py gate --stage evaluation
python study.py analyze --stage confirmation
python study.py gate --stage confirmation
python study.py conclude
python study.py validate
```

No command reads product data, credentials, databases, or runtime configuration.

