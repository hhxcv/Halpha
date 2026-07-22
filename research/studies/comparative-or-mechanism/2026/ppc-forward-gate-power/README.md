# PPC forward-gate power calibration

This comparative/method study asks whether the frozen minimum of 26 eligible
forward weeks can reliably identify a realistic positive net edge for
`RESEARCH_PPC14_TOP_TERCILE_MOM14_TOP_TERCILE_WEEKLY_LONG_0P25X_V1`.

It does **not** reopen the candidate's sealed 2025+ market data, change its signal,
select a target, or qualify a strategy. It uses the already retained 40 development
entry-date cohorts only as an empirical dependence and tail-shape calibration. The
simulated effect is imposed prospectively and is not estimated from the selected
development mean.

The fixed primary estimand is the probability that a future sequence passes both:

1. the lower endpoint implied by the candidate's two-sided 95% four-week circular
   block-bootstrap mean interval is above zero; and
2. both chronological half-sample means are above zero.

Primary true net edge: 50 bp per eligible week after stress cost, actual/stressed
funding treatment and the 4% full-plan capital hurdle. Diagnostics use 25, 75 and
100 bp, block lengths 1 and 8, and 26 through 520 eligible weeks. Eighty-percent
joint power is the planning threshold; it is not a profitability or Alpha threshold.

Run from the repository root:

```powershell
research/.venv/Scripts/python.exe research/studies/comparative-or-mechanism/2026/ppc-forward-gate-power/study.py checkpoint
research/.venv/Scripts/python.exe research/studies/comparative-or-mechanism/2026/ppc-forward-gate-power/study.py analyze
research/.venv/Scripts/python.exe research/studies/comparative-or-mechanism/2026/ppc-forward-gate-power/study.py validate
```

See `preregistration.md` for the frozen design, `sources.md` for method provenance,
`attempts.md` for actual commands, `results.json` and `result.md` for conclusions,
and `validation.json` for deterministic recomputation evidence.

## Result

Conclusion: `DOES_NOT_SUPPORT` the claim that 26 eligible weeks is a
decision-capable evidence horizon. Under the exact nested gate, a true 50 bp weekly
net effect passed only 5.92% of 5,000 possible 26-week samples; even a 100 bp effect
passed only 17.34%. The zero-effect joint rejection rate was 1.78%, so the failure is
low power rather than a permissive gate.

The January 2027 date remains the earliest **first checkpoint**, not a promise of a
complete negative decision. A positive exact gate would still be informative; a
non-pass would usually remain inconclusive. No longer horizon is recommended from
the non-equivalent reference-threshold diagnostic.
