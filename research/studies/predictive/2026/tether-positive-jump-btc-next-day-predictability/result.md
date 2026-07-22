# Result

**Conclusion: `INSUFFICIENT_EVIDENCE`**

Do positive BNS jumps in Bitfinex USDT/USD predict negative next-24-hour Binance BTCUSDT perpetual returns after a 15-minute action delay?

## development

- Gate: `FAIL`; eligible days: 546; positive BNS events: 74.
- Controlled interaction coefficient: -13.298989918318696; one-sided HAC p: 0.18723621927024897.
- Gross event-short mean: 0.002833792282431779; 95% block-bootstrap lower: -0.006500937381083529.
- Full-plan feasibility mean per day: -0.0001897627458120298; bootstrap lower: -0.0004787956977546287.
- Failed checks: controlled_one_sided_hac, controlled_halves_negative, gross_event_short_halves, gross_event_short_bootstrap_lower, daily_plan_feasibility_positive, daily_plan_feasibility_halves, daily_plan_feasibility_bootstrap_lower, quarter_concentration, fixed_threshold_one_sided_hac.

## Decision boundary

This is a predictive result, not a deployable strategy. No core code, strategy identity, L4 fact, capital or account state changes. Even a positive conclusion would require a new strategy-candidate study with actual funding, vectorbt execution replay and a framework-neutral handoff before core qualification.

The study cannot prove causality, future alpha or long-term profitability. The principal remaining method limits are hourly stablecoin tick discreteness, 24-return BNS finite-sample behavior, one signal venue, one target venue and omitted private/order-book information.
