# Amendment 001: exact percentile-gate simulation

Frozen after the first deterministic run and before the corrected simulation.

The first implementation used an independent centered reference distribution to
translate the percentile interval into a fixed critical mean. With the retained PPC
series' strong right skew and excess kurtosis, that shortcut is not equivalent to
recomputing the candidate's percentile bootstrap inside each possible forward
sample. The symptom was a 6.172% joint null rejection estimate at 26 weeks despite
the intended 2.5% lower-tail interpretation.

The invalid-for-decision attempt is retained by identity:

- `results.json`: SHA-256
  `87a39e1dc1f58a861f8e4ad01db0b6c452b5691ff3011431159825715784727c`;
- `power_curve.csv`: SHA-256
  `c0151ed96ce7e37d769f277c4eb1dd5b0b3e1d5783c1ce83a450a3e02ed69810`;
- `validation.json`: SHA-256
  `528f8c9760dd845895403478a770e7d1dad0c3b28309ac0ca1f00c29d2fdc05c`.

Correction fixed before rerun:

- preserve the original primary question, 26 eligible weeks, four-week circular
  blocks, 0/25/50/75/100 bp effects, half-sample rule and decision thresholds;
- draw 5,000 possible centered 26-week forward samples;
- inside each sample, run 5,000 four-week circular bootstrap resamples and apply the
  exact lower 2.5th-percentile-above-zero gate;
- use bootstrap seed `20260722` for the inner gate, matching the candidate, and the
  preregistered study seed for outer samples;
- report the earlier 26–520 reference-threshold curve only as a non-equivalent
  planning diagnostic. It cannot determine a recommended horizon.

This is a method correction, not a favorable-result selection. The corrected result
may strengthen or weaken the same preregistered conclusion. Exact power beyond 26
weeks is deliberately not claimed because nested computation over every horizon was
not preregistered and is unnecessary to answer the primary decision.

