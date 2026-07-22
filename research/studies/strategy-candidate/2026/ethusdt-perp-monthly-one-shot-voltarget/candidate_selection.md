# Candidate selection

Selection date: 2026-07-22 UTC. Baseline commit:
`0bdfeffa616260cebd2d2188ddc8deb9e85c77f4`.

| Candidate | Decision value | Unresolved difference | Falsifiability | Data / operating cost | Selection |
|---|---|---|---|---|---|
| ETH monthly capped volatility-target long | Direct one-leg monthly plan; tests whether simple beta harvesting survives plan semantics | Existing ETH SMA study did not test fixed external volatility scaling, forced monthly round trips, or fixed-quarter benchmark | High: fixed rule, sequential gates, absolute and relative thresholds | Public daily/funding data; one manual plan monthly | Selected |
| Turn-of-month long | Very easy to operate | Literature and crypto evidence conflict; many plausible windows create search degrees of freedom | Moderate unless a single window is externally fixed | Public OHLCV; low operating cost | Rejected for now |
| Abnormal-turnover reversal | Potential short-horizon predictability | Peer-reviewed evidence reports disappearance after assets become shortable; Binance perps are directly shortable | High | Daily volume sufficient, but daily plans | Rejected for low transfer expectation |
| Ten-week reversal / high-vol loser | Simple long plan | Already tested by Halpha and the registered family stop forbids further direction/window/subgroup search | Already falsified in current scope | Public OHLCV | Rejected; do not repeat |
| Liquidity-shock risk management | Published crypto motivation | Requires extra liquidity construction and more decisions; not minimal relative to current question | High but materially more complex | Public trade/order data may be available; higher research cost | Deferred |

The selected rule is not chosen for novelty or a known favorable output. The 8%
target reuses the pre-existing personal-risk convention from the TRX volatility-target
study; the 25% cap is fixed before access to this rule's returns to keep full-plan
drawdown relevant to a small owner-maintained account.

