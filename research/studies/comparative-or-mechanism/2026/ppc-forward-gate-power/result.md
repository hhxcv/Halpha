# Result: 26 PPC forward weeks are not a decision-capable horizon

Conclusion: `DOES_NOT_SUPPORT`.

The claim tested was narrow: can 26 eligible, genuinely forward PPC weeks reliably
identify a true 50 bp weekly net edge after the candidate's stress cost, funding
treatment and full-plan capital hurdle? The answer is no under the retained
development noise shape and exact existing percentile-bootstrap gate.

## Exact primary result

| Quantity | Result |
|---|---:|
| Outer possible 26-week samples | 5,000 |
| Inner four-week circular bootstrap draws per sample | 5,000 |
| Zero-effect joint false positive | 1.78% |
| 50 bp mean-gate power | 6.14% |
| 50 bp joint power | **5.92%** |
| 50 bp joint-power Wilson 95% | [5.30%, 6.61%] |
| 100 bp joint power | 17.34% |

The joint gate requires both the exact percentile lower endpoint above zero and both
chronological half means above zero. The half rule removes little additional power;
the dominant problem is a weekly distribution with 4.87% standard deviation, 2.68
skew and 9.82 excess kurtosis. One retained date returned +22.20% after stress and
hurdle, while the minimum was -5.00%. Twenty-six observations cannot reliably
separate a 0.50% mean shift from that tail variation.

## Interpretation

- `2027-01-25` is only the earliest first 26-week checkpoint, assuming every
  scheduled week is eligible. It is not a date by which PPC can be promised either
  qualified or disproved.
- A positive exact gate at that checkpoint would be relatively rare under the null
  and remains useful evidence. A failure to cross the lower bound would have very
  weak ability to distinguish no edge from a real 50 bp edge, so it should normally
  remain `INSUFFICIENT_EVIDENCE`, subject to any hard negative risk/cost evidence.
- The 26–520 reference-threshold curve from the first implementation is retained as
  a non-equivalent diagnostic only. It cannot establish a new minimum horizon; the
  method correction and original output hashes are in `amendment-001.md`.
- This power result does not improve PPC's Alpha evidence, does not open its sealed
  evaluation/confirmation periods, and does not justify a different signal,
  instrument, effect size or cost assumption.

## Strongest counterevidence and remaining unknowns

The strongest counterargument is that the 40 development dates are themselves short,
selected and regime-specific. Future tails could be milder, making this estimate too
pessimistic, or worse, making it optimistic. Circular repetition beyond 40 dates
cannot model structural breaks. Exact power for longer horizons was not computed, so
no claim such as “five years is enough” is allowed.

The practical implication is not to lower the gate. It is that weekly time-only
validation of a noisy single-leg effect is intrinsically slow. Faster reliable
evidence would require a genuinely different design with more independent units or a
larger stable effect, not repeated parameter searches on the same market history.

No product, capital, account, runtime or exchange-changing effect occurred.
