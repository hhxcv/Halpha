# Fixed-rule forward-incubation frontier

Question: after the historical gates failed, which positive-but-insufficient rules
still justify collecting genuinely new forward evidence without changing the rule,
and when can the next decision be made?

Conclusion: `INSUFFICIENT_EVIDENCE`.

Only the fixed `PPC14 + MOM14` weekly one-shot long remains a proportionate active
incubation item. Its own checkpoint already requires at least 26 eligible weeks
after 2026-07-22 before any handoff question. The first eligible entry is
2026-07-27; the 26th entry exits on 2027-01-25. No qualification decision should be
made before that date, and missing/no-action weeks can push the date later.

Power calibration changes the meaning of that date. Using the exact existing
four-week percentile-bootstrap gate and the retained heavy-tailed PPC development
noise, a true 50 bp weekly net edge passes the 26-week joint gate in only 5.92% of
simulated samples; even a 100 bp edge passes in 17.34%. The null rejection rate is
1.78%. Therefore 2027-01-25 is the earliest **first checkpoint**, not a promised
complete decision date. A full positive gate remains useful evidence, but a non-pass
will usually remain inconclusive. The power study did not establish a later exact
horizon and does not authorize lowering the gate.

CTREND and the monthly high-volatility short stay retained as research references,
but are not active forward-incubation priorities. CTREND's 19.2% model-failure rate
and concentration are maintenance/definition failures, not merely missing time.
The high-volatility short is positive only at one exact lookback/rank slice while
all three frozen neighboring configurations are negative; waiting a year for a
small monthly sample is low decision value for a personal project.

This directory is deliberately an audit record, not a data platform, scheduler, or
live monitor. When the PPC maturity boundary is reached, a new read-only research
question must fetch/bind official public market and funding data, replay the exact
frozen rule, and evaluate it without incorporating the earlier development sample
into rule choice.

Run:

```powershell
research/.venv/Scripts/python.exe research/studies/comparative-or-mechanism/2026/fixed-rule-forward-incubation-frontier/audit.py audit
```

The command checks exact retained evidence identities and regenerates the small
JSON audit. It never reads product data, credentials, databases, runtime
configuration, or exchange-changing endpoints.
