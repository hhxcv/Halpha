# Attempts

## 2026-07-22 — source and data-cost screen

- Confirmed the 2023 peer-reviewed cryptocurrency paper's formula, negative expected
  sign, 5-minute sampling, daily sort, 2017-01 through 2021-06 sample and controls
  from the open conference manuscript and publisher record.
- Confirmed from Binance's official public-data repository that USD-M 15-minute
  monthly kline archives and companion checksum files are available.
- A read-only HEAD request for `SOLUSDT-15m-2023-01.zip` returned HTTP 200 and
  `124,608` bytes. Development is therefore expected to remain well below the
  project's resource ceiling even across 25 symbols and 17 months.
- Chose 15-minute primary sampling because it matches the project's existing bar
  semantics and reduces long-term storage/maintenance. The difference from 5-minute
  evidence is explicit and cannot be silently upgraded after results.

## 2026-07-22 — frozen development replay

Commands, in order:

```powershell
research/.venv/Scripts/python.exe research/studies/predictive/2026/relative-signed-jump-next-day-predictability/study.py checkpoint
research/.venv/Scripts/python.exe research/studies/predictive/2026/relative-signed-jump-next-day-predictability/study.py fetch --stage development
research/.venv/Scripts/python.exe research/studies/predictive/2026/relative-signed-jump-next-day-predictability/study.py inspect --stage development
research/.venv/Scripts/python.exe research/studies/predictive/2026/relative-signed-jump-next-day-predictability/study.py analyze --stage development
research/.venv/Scripts/python.exe research/studies/predictive/2026/relative-signed-jump-next-day-predictability/study.py gate --stage development
research/.venv/Scripts/python.exe research/studies/predictive/2026/relative-signed-jump-next-day-predictability/study.py conclude
research/.venv/Scripts/python.exe research/studies/predictive/2026/relative-signed-jump-next-day-predictability/study.py validate
```

- Downloaded and verified 425 official monthly archives and companion checksums:
  50,798,433 compressed bytes in the Git-external cache. The fetch took 97.3 seconds.
- Data quality passed. Complete signal-and-target coverage ranged from 98.92% to
  100% by symbol; no duplicate timestamps, invalid positive-price rows or invalid
  OHLC ranges were retained. Inspection took 50.5 seconds.
- The analysis command's shell wait timed out after 124 seconds, but its single child
  process remained healthy and was not duplicated. It completed normally after about
  19 minutes 46 seconds and wrote all 12 declared CSVs plus `development.json`.
- Development had 457 eligible days and 11,042 panel rows. The primary low-minus-high
  spread was `-0.0235%` per day and the conservative one-leg proxy was `-0.2403%`
  of full-plan capital per day. The frozen gate failed 11 checks.
- Evaluation and confirmation were not fetched or inspected. No five-minute rescue,
  reversed signal, alternative delay, tail, universe, target or cost search was run.
- Validation independently rebuilt all three resolutions from the bound public bytes
  in 1,176.7 seconds. All 19 checks, including 12 CSV identities and recomputed
  development economics, passed.
