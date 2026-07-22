# Preregistration: power of the frozen PPC forward gate

Frozen before any power-curve simulation was run on 2026-07-22.

## Identity and decision

- Baseline commit: `0bdfeffa616260cebd2d2188ddc8deb9e85c77f4`.
- Research kind: `COMPARATIVE_OR_MECHANISM`.
- Candidate under observation:
  `RESEARCH_PPC14_TOP_TERCILE_MOM14_TOP_TERCILE_WEEKLY_LONG_0P25X_V1`.
- Product effect: none. No product code, strategy registry, L4, account, capital or
  exchange-changing endpoint is in scope.
- Decision: whether 26 eligible forward weeks is merely a first checkpoint or has
  at least 80% probability of detecting a realistic 50 bp weekly net edge under the
  frozen core evidence gate.

## Candidate questions considered

| Question | Unresolved project difference | Decision |
|---|---|---|
| Power and false-positive behavior of the 26-week PPC gate | Directly determines whether the only active incubation horizon can support a reliable decision | **Selected** |
| Exact formal Donchian/ATR replay | Historical activation time and direction are unidentified; inventing them creates a new trend strategy | Rejected before study |
| Entropy/adaptive-efficiency momentum/reversal switch | Efficiency diagnostics do not pre-specify direction and would reopen failed families | Rejected before study |

The selected question is not chosen for favorable performance. It can falsify the
current evidence horizon without changing the trading rule and costs little because
all inputs are already retained research evidence.

## Frozen input

- `development_main_trades.csv`, SHA-256
  `8c3b0ce004fba8bf788c0b28a0b70d63475ffd2c1e3cfc1c6fc06a6930adbf3e`.
- Expected: 88 trades, 40 distinct entry dates.
- For each entry date, equal-weight `stress_net_return` across eligible symbols and
  subtract `0.04 * 7 / 365` from full plan capital. This is exactly the existing PPC
  stress-after-hurdle date unit.
- The 40-date series is centered before simulation. Its observed positive mean is
  not carried into the null or alternative.

This input is selected-development evidence and cannot validate PPC. It is used only
as a conservative empirical distribution of weekly noise, dependence, skew and
outliers. Circular reuse beyond 40 dates assumes local stationarity and is explicitly
a limitation.

## Frozen simulation

- Circular fixed-block resampling; primary block length 4 eligible weeks.
- Diagnostics: block lengths 1 and 8. They cannot replace the primary result.
- Independent calibration and evaluation Monte Carlo streams, each 25,000 draws.
- Deterministic seed `2026072201` with configuration-specific derived streams.
- Eligible-week sample sizes:
  `26, 52, 78, 104, 156, 208, 260, 312, 416, 520`.
- Imposed weekly net effects after all cost/hurdle terms:
  `0, 0.0025, 0.0050, 0.0075, 0.0100`.
- For each block length and sample size, calibrate the rejection threshold as the
  negative 2.5th percentile of independent centered bootstrap sample means. This
  matches the meaning of a two-sided 95% percentile interval lower endpoint above
  zero without a computationally wasteful nested bootstrap.
- Report mean-gate power and joint power. Joint power additionally requires both
  chronological half means to be positive.
- Report Wilson 95% Monte Carlo intervals for every probability.

The primary effect is 50 bp because it is an economically material weekly net edge
for a 0.25x one-leg plan and is close to, but deliberately not estimated from, the
already disclosed PPC development point estimate. The other effects show how the
required horizon changes; none may be selected after the result.

## Decision rules

- `SUPPORTS_WITHIN_SCOPE`: at 26 eligible weeks, primary block-4 joint power is at
  least 80% and null joint false-positive probability is at most 5%.
- `DOES_NOT_SUPPORT`: 26-week primary joint power is below 50%, or null joint false
  positive exceeds 5%.
- Otherwise `INSUFFICIENT_EVIDENCE`.
- The planning horizon is the first frozen sample size whose primary 50 bp joint
  power reaches 80%. If none through 520 weeks, report `>520`; do not interpolate or
  choose a more favorable block/effect diagnostic.

This result may lengthen or stage the forward observation plan. It cannot shorten
the existing 26-week minimum, change the candidate, or qualify it. Even 80% power
does not prove long-term profitability; it only means the gate has a reasonable
chance to recognize the imposed effect under this noise model.

Implementation note: the original reference-threshold approximation was found not
to be gate-equivalent under the exposed skewed sample. `amendment-001.md` freezes
the exact nested 26-week correction and preserves the invalid attempt by hash. The
amendment supersedes only the computational shortcut and long-horizon planning
claim; all economic effects and primary decision thresholds remain unchanged.
