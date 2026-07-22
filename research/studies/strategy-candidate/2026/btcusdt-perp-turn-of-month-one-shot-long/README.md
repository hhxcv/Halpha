# BTCUSDT turn-of-month one-shot long

This study asks whether the conventional four-day turn-of-the-month window can
be converted into a low-maintenance Halpha semi-automatic plan. It is research
only: it does not modify or invoke the product runtime and cannot promise future
profitability.

## Question

Does entering a 0.5x `BTCUSDT-PERP` long at the UTC open of the last calendar
day of each month and exiting at the UTC open of day 4 of the next month clear
retail costs, actual/stressed funding, full-plan capital hurdles, a matched
mid-month schedule, local window diagnostics, and sequential evidence?

## Why this question

- Two independent peer-reviewed studies reported a BTC turn-of-month effect,
  while a broad calendar study found that most other crypto calendar effects
  were absent. This supplies an externally fixed direction and window rather
  than a Halpha calendar search.
- One four-day plan per month, one liquid instrument, and public daily/funding
  data fit a personally maintained, small-capital workflow.
- The fixed schedule is independent of trend, momentum, funding/carry, MAX,
  volatility, and BTC-relative cross-sectional families already studied here.
- The external samples end in 2021. Development starts in 2022, so it is a
  direct post-publication test, although Halpha researchers have previously
  seen the same broad BTC market history.

## Reproduction

Run from the repository root with the locked research interpreter:

```powershell
research/.venv/Scripts/python.exe research/studies/strategy-candidate/2026/btcusdt-perp-turn-of-month-one-shot-long/study.py checkpoint
research/.venv/Scripts/python.exe research/studies/strategy-candidate/2026/btcusdt-perp-turn-of-month-one-shot-long/study.py fetch
research/.venv/Scripts/python.exe research/studies/strategy-candidate/2026/btcusdt-perp-turn-of-month-one-shot-long/study.py inspect
research/.venv/Scripts/python.exe research/studies/strategy-candidate/2026/btcusdt-perp-turn-of-month-one-shot-long/study.py analyze --stage development
research/.venv/Scripts/python.exe research/studies/strategy-candidate/2026/btcusdt-perp-turn-of-month-one-shot-long/study.py gate --stage development
# Continue only after PASS.
research/.venv/Scripts/python.exe research/studies/strategy-candidate/2026/btcusdt-perp-turn-of-month-one-shot-long/study.py analyze --stage evaluation
research/.venv/Scripts/python.exe research/studies/strategy-candidate/2026/btcusdt-perp-turn-of-month-one-shot-long/study.py gate --stage evaluation
research/.venv/Scripts/python.exe research/studies/strategy-candidate/2026/btcusdt-perp-turn-of-month-one-shot-long/study.py analyze --stage confirmation
research/.venv/Scripts/python.exe research/studies/strategy-candidate/2026/btcusdt-perp-turn-of-month-one-shot-long/study.py gate --stage confirmation
research/.venv/Scripts/python.exe research/studies/strategy-candidate/2026/btcusdt-perp-turn-of-month-one-shot-long/study.py conclude
research/.venv/Scripts/python.exe research/studies/strategy-candidate/2026/btcusdt-perp-turn-of-month-one-shot-long/study.py validate
```

Public raw responses are stored outside Git at the cache root bound in
`checkpoint.json`; request identity, byte length, and SHA-256 are retained in
`source_manifest.json`. No command reads product data, credentials, databases,
or runtime configuration.
