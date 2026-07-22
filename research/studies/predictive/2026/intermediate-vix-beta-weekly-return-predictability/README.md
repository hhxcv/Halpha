# Intermediate VIX-beta weekly return predictability

This predictive study tests a post-publication, operational adaptation of Han
(2024). It does not create a strategy handoff or modify the product runtime.

## Question

Among 25 mature Binance USD-M perpetuals, does intermediate residual sensitivity
to weekly Cboe VIX innovations predict the next actionable Monday-to-Monday return
better than low/high sensitivity, after market beta and plain price/volume controls,
at a magnitude worth a separate costed strategy study?

## Operational timeline

- Friday U.S. close: the latest Cboe VIX close becomes observable.
- Saturday 00:00 UTC: weekly crypto returns and the VIX innovation are complete;
  estimate 36-week market-controlled VIX betas and freeze the cross-section.
- Monday 00:00 UTC: earliest modeled entry, leaving a full weekend gap.
- Next Monday 00:00 UTC: target return ends.

The main comparison is the equal-weight middle quintile minus the equal-weight
average of both extreme quintiles. A single-leg feasibility proxy selects only the
highest trailing-volume member of the middle quintile; it is not a strategy.

## Reproduction

Run from the repository root with the locked research interpreter:

```powershell
research/.venv/Scripts/python.exe research/studies/predictive/2026/intermediate-vix-beta-weekly-return-predictability/study.py checkpoint
research/.venv/Scripts/python.exe research/studies/predictive/2026/intermediate-vix-beta-weekly-return-predictability/study.py fetch
research/.venv/Scripts/python.exe research/studies/predictive/2026/intermediate-vix-beta-weekly-return-predictability/study.py inspect
research/.venv/Scripts/python.exe research/studies/predictive/2026/intermediate-vix-beta-weekly-return-predictability/study.py analyze --stage development
research/.venv/Scripts/python.exe research/studies/predictive/2026/intermediate-vix-beta-weekly-return-predictability/study.py gate --stage development
# Later stages remain sealed until the preceding stage passes.
research/.venv/Scripts/python.exe research/studies/predictive/2026/intermediate-vix-beta-weekly-return-predictability/study.py conclude
research/.venv/Scripts/python.exe research/studies/predictive/2026/intermediate-vix-beta-weekly-return-predictability/study.py validate
```

Raw public responses are content-addressed outside Git at the cache root recorded
in `checkpoint.json`. No command reads product data, credentials, databases, or
runtime configuration.

