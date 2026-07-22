# Attempts and failures

## 2026-07-22 — selection and registration

1. Compared three externally motivated basic-data directions: return-distribution
   skewness, nonlinear VIX beta, and BTC turn-of-month timing.
2. Rejected a new long-horizon skewness question because the already frozen
   `LOW_SKEW52` diagnostic produced a negative 2022–2023 mean; intraday
   realized-skewness papers require 5-minute data and next-day turnover and overlap
   the failed MAX/lottery family.
3. Deferred VIX beta because it adds a macro series and dynamic universe ranking.
   It remains independent and was not tested or discarded.
4. Selected conventional `(-1,+3)` BTC TOM because two independent peer-reviewed
   studies fix the BTC-specific sign, one skeptical broad study says most other
   calendar effects are absent, and the rule maps to one low-frequency one-leg plan.
5. Before viewing any current TOM return, froze target, UTC schedule, 0.5x notional,
   three cost scenarios, actual/stressed funding, capital/research hurdles, matched
   mid-month comparator, two non-selectable neighboring windows, HAC method,
   sequential stages, gates, and stopping rule.

## 2026-07-22 — implementation and synthetic verification

1. The default system Python lacked `statsmodels`; no package was installed and no
   dependency file was changed. The commands use the repository's isolated
   `research/.venv`, which already contains VectorBT 1.1.0 and statsmodels 0.14.6.
2. Reused the frozen TRX monthly research engine only for public Binance pagination,
   mark-price reconciliation, funding settlement, VectorBT/manual cash-flow
   reconciliation, daily equity, and deterministic block bootstrap. The TOM
   schedule, comparators, HAC replication, gates, and conclusion logic are local.
3. Before opening market results, a synthetic schedule test confirmed that January
   2022 maps to primary `2022-01-31 00:00 -> 2022-02-04 00:00`, TOM3 to day 3,
   TOM5 from January 30, mid-month from January 14 to 18, and month-long from
   January 1 to February 1.

## 2026-07-22 — public data and development result

1. Public fetch retained two daily-kline pages, five 8-hour mark-kline pages, seven
   funding pages, and one current exchange-information snapshot. Manifest digest:
   `a39de3c8716404c5ba6ec13402cd808d3857bb7dc76e06eb4573036bec991ea7`.
2. Data quality `PASS`: 1,677 consecutive UTC daily bars and 5,029 funding events,
   no missing/duplicate/invalid daily bars, and no missing funding mark after 2,098
   missing response marks were reconciled to official 8-hour mark bars within 32 ms.
3. Opened only 2022–2023 development. The 24 primary plans returned -4.7522%
   favorable, -7.0143% base, and -9.7364% stress. Base/stress maximum drawdown was
   -17.2544%/-19.0383%; only 29.17% of stress months were positive.
4. Both calendar years were negative after base costs: 2022 -4.9635% and 2023
   -2.1579%. Stress monthly block-bootstrap 95% interval was
   `[-1.2081%, +0.3648%]`.
5. The mechanism replication also reversed: 96 TOM daily log returns averaged
   -0.06753%, versus -0.00367% on 634 non-TOM days. The HAC TOM-minus-other
   coefficient was -0.06387% per day, 95% interval `[-0.5573%, +0.4296%]`, and
   one-sided positive p-value 0.6001.
6. Primary base underperformed the matched day-14-to-18 schedule by 0.4083% per
   month on average; paired block interval `[-1.9889%, +0.9113%]`. TOM3 and TOM5
   base totals were also negative (-0.6084% and -11.7503%). The mid-month result
   was merely a comparator (+2.0040% base, -0.9259% stress) and is not promoted.
7. Development gate failed 13 economic/robustness checks. Evaluation and
   confirmation remain sealed; no date, leverage, month subset, weekday, trend,
   cost, or window repair was attempted. Conclusion: `DOES_NOT_SUPPORT`.
8. Deterministic validation recomputed all development economics, re-bound the
   gate to result digest, and checked all five plan CSV identities: `PASS`.

