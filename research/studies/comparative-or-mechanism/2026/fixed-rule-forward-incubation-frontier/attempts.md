# Attempts and decisions

## 2026-07-22 — initial audit

1. Compared the three closest single-perpetual candidates from the qualification
   frontier instead of inventing a new nearby parameter.
2. Selected PPC for active forward incubation because it has simple weekly plan
   semantics, positive but uncertain economics, four-of-five neighbor support, low
   correlation with simple momentum, and an explicit pre-existing forward-evidence
   requirement.
3. Did not activate CTREND incubation: its complex rolling model failed in 19.2% of
   weeks and exceeded the frozen 5% ceiling, while positive PnL was too concentrated.
   More calendar time does not fix a model-maintenance mismatch.
4. Did not activate high-volatility monthly short incubation: three neighboring
   configurations were all negative and the observation cadence would require a
   long wait for weak effective sample size, with asymmetric short squeeze risk.
5. No market outcome after the checkpoints existed at audit time, so no observation
   row was fabricated and no candidate status changed.
