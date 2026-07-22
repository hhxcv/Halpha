# Amihud illiquidity and next-week perpetual returns

This `PREDICTIVE` study asks whether a simple, published liquidity characteristic
has enough post-sample incremental information to justify a later costed strategy
question. It does not create a strategy handoff or modify product code.

## Question

Among 25 fixed, mature Binance USD-M perpetuals, does a high trailing Amihud
illiquidity ratio predict a higher next actionable Monday-to-Monday return than a
low ratio after controlling for volatility, MAX, momentum, market beta, and quote
volume? Is the magnitude large and stable enough for a separate one-leg strategy
candidate study?

## Operational timeline

- Saturday 00:00 UTC: the preceding 28 daily bars are complete; calculate and
  freeze the cross-sectional ranking.
- Monday 00:00 UTC: earliest modeled entry, after a two-day cooling gap.
- Next Monday 00:00 UTC: target week ends.

The main predictor is the 28-day mean of absolute open-to-open daily return divided
by same-bar USDT quote volume. The main spread is equal-weight high-minus-low
quintile return. A feasibility proxy takes only the highest-volume member of the
high-illiquidity quintile at 25% of plan capital and deducts a 52 bp underlying
round trip plus a 4% annual full-plan hurdle. It is not a strategy because actual
funding and executable spreads are not modeled.

## Why this question

Published crypto evidence is directly conflicted: Zhang and Li report a priced
cross-sectional liquidity risk relation; Ali, Peng, and Shams report an
illiquidity factor; Wei reports no crypto illiquidity premium. That conflict is
more useful for Halpha than another nearby momentum parameter because it creates a
clear falsification test on recent, mature perpetuals.

This is distinct from the retained low-relative-volume daily reversal study. That
study conditioned one-day extreme reversal on an abnormal volume shock. This
study ranks a 28-day price-impact proxy and tests next-week cross-sectional return,
while requiring incremental evidence after both volatility and volume controls.

## Reproduction

Run from the repository root with the locked research interpreter:

```powershell
research/.venv/Scripts/python.exe research/studies/predictive/2026/amihud-illiquidity-weekly-return-predictability/study.py checkpoint
research/.venv/Scripts/python.exe research/studies/predictive/2026/amihud-illiquidity-weekly-return-predictability/study.py bind
research/.venv/Scripts/python.exe research/studies/predictive/2026/amihud-illiquidity-weekly-return-predictability/study.py inspect
research/.venv/Scripts/python.exe research/studies/predictive/2026/amihud-illiquidity-weekly-return-predictability/study.py analyze --stage development
research/.venv/Scripts/python.exe research/studies/predictive/2026/amihud-illiquidity-weekly-return-predictability/study.py gate --stage development
# Later stages remain sealed unless the preceding gate passes.
research/.venv/Scripts/python.exe research/studies/predictive/2026/amihud-illiquidity-weekly-return-predictability/study.py conclude
research/.venv/Scripts/python.exe research/studies/predictive/2026/amihud-illiquidity-weekly-return-predictability/study.py validate
```

`bind` verifies and references an existing Git-external cache of official public
Binance responses; it does not copy data or access product storage. No command
uses credentials, a product database, runtime configuration, or a trading endpoint.
