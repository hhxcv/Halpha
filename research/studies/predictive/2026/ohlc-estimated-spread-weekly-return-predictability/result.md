# Result

Conclusion: `INSUFFICIENT_EVIDENCE`.

Predictive relationship only; no strategy qualification or long-term profitability claim.

## Opened evidence

### development

- Gate: `FAIL`; weeks: 52; median rankable: 24.0.
- CHL high-minus-low mean: 0.008694; 95% block CI: [-0.014817, 0.034821].
- Mean increment versus Amihud: 0.006241; versus volatility: 0.000116.
- Controlled CHL slope: 0.003911; one-sided HAC p: 0.1883.
- Single-leg full-plan proxy after cost and hurdle: 0.003108; 95% block CI: [-0.006400, 0.014719].
- Failed checks: spread_bootstrap_lower_positive, spread_positive_fraction_at_least_55pct, rank_ic_positive, rank_ic_one_sided_hac_p_lt_10pct, controlled_slope_one_sided_hac_p_lt_10pct, proxy_bootstrap_lower_positive, spread_both_halves_positive, proxy_both_halves_positive, monthly_corrected_28p_spread_nonnegative, proxy_contribution_not_concentrated.

## External benchmark check

The official CC0 value-weighted bid-ask factor series has 325 usable weekly observations, an arithmetic annualized mean of 1.0844, and positive means in both halves. This approximately matches the published broad-spot result but is excluded from Halpha gates.

## Scope and decision

Do not convert this predictor into a strategy; preserve the family stop.

No product strategy, L4 fact, capital state, account state, or real trading action changed.
