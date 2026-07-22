# Result — residual momentum and next-week perpetual returns

## Conclusion

`INSUFFICIENT_EVIDENCE`

The fixed 14-day residual-momentum question did not pass development. The positive
mean is not stable enough to justify opening evaluation, converting the predictor to
a strategy, or claiming long-term profitability.

## Development evidence

- Period: 52 Saturday decisions from 2023-03-04 through 2024-02-24.
- Panel: 1,214 symbol-weeks; median 24 rankable instruments.
- RMOM14 high-minus-low mean: `+1.8096%` per week.
- Four-week circular block-bootstrap 95% interval: `[-0.7774%, +4.5644%]`.
- Positive weeks: `50.00%`.
- First half / second half: `-0.2557% / +3.8749%`.
- Mean weekly rank IC: `-0.03215`; one-sided HAC p `0.78185`.
- Controlled RMOM slope: `-0.00237`; one-sided HAC p `0.62416`.
- Ordinary MOM14 high-minus-low baseline: `+1.2247%`; RMOM minus ordinary
  momentum: `+0.5850%`.
- Median absolute tail beta spread: RMOM `0.1519` versus ordinary momentum
  `0.2618`, consistent with lower common-market exposure but insufficient to rescue
  the failed prediction.
- Conservative one-leg feasibility proxy mean: `+0.6189%` of full-plan capital per
  week; block interval `[-0.3283%, +1.6884%]`.
- Proxy first half / second half: `-0.6146% / +1.8523%`.
- Ten symbols were selected; 70% had a positive mean, but SOL contributed `68.31%`
  of all positive proxy P&L and was selected 21 of 52 weeks.
- Diagnostic RMOM7 / RMOM28 spreads: `+0.8755% / +0.6198%`.
- Maximum median absolute score/control correlation: `0.9103`, just above the
  frozen distinctness ceiling; ordinary momentum is therefore not cleanly separated.

## Why the positive mean is not enough

The aggregate mean is driven by a small number of large later-period winner weeks:
the five largest weekly spreads include two SOL weeks above 28%. Cross-sectional
rank ordering is negative on average, the controlled coefficient is negative, and
the first half loses. This pattern is compatible with a concentrated favorable path,
not a stable incremental predictor. The lower market-beta spread supports the
mechanical effect of residualization, but not economic predictability.

Funding was intentionally not modeled in this predictive screen. Because uncertainty
already crosses zero before funding, adding exact funding cannot turn this failed gate
into qualifying evidence. The 52 bp cost proxy may reject but cannot establish
execution profitability.

## Gate and family stop

Failed checks:

- spread bootstrap lower bound, positive-week fraction and both-half stability;
- positive/significant rank IC and controlled slope;
- proxy bootstrap lower bound and both-half stability;
- proxy contribution concentration;
- score/control distinctness.

The ordinary-momentum superiority and lower common-market exposure checks passed,
but all checks were required. Evaluation and confirmation remain sealed. Do not
reverse direction, promote SOL, change the residual/beta window, alter the universe,
tail, gap, cost or hurdle, or inspect later stages under this question.

## Reproduction identities

- Baseline commit: `0bdfeffa616260cebd2d2188ddc8deb9e85c77f4`
- Checkpoint: `37ccd36d92b0321a45f4fc40051f6ac5feb554e87ae0b2e1517bde39a031ce20`
- Source reuse binding: `488ff37ea9de42cfa8b0a2c58f1a6f3def19bbfd0dc96169ca0a40c617f4ea2e`
- Data quality: `a844176c654810f3620b37f944098beaed87e0332d2913899784cd9a11ac983f`
- Development: `cedc2f5d99d45c3b9597f21e4ea330e626fbd145b1d533efa761c6f1a54f9bf2`
- Development gate: `033a8baa44c8991e19517d7405129bde20348695e9be0c2c2c31b3d6ef2717eb`
- Results: `dd99dce413d37c1bda6d392da782de93ce346e8857d34c2ae96aaff24c6bfd1a`
- Validation: `b90e13805ff48f32d2e49d5b352128ef044e2c4d6093ad974936fb6ee51e3cbb`
- Validation status: `PASS`; development economics were independently recomputed
  from the bound public bytes and all nine retained CSV identities matched.

Product, capital and real-account effects: `NONE`.

