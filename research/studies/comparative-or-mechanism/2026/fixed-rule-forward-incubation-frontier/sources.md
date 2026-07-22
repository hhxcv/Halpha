# Sources and evidence identities

As-of 2026-07-22; stable product baseline
`0bdfeffa616260cebd2d2188ddc8deb9e85c77f4` and formal background
`ONE_SHOT_DONCHIAN_ATR_BREAKOUT 1.0.1 / BTCUSDT-PERP`.

This decision uses retained Halpha evidence, checked byte-for-byte by `audit.py`:

- `price-path-continuity-weekly-winner-long`: checkpoint, development gate, and
  result. Its checkpoint explicitly caps any historical support at
  `INSUFFICIENT_EVIDENCE` until at least 26 eligible frozen-rule weeks accrue after
  the checkpoint.
- `ctrend-weekly-top-quintile-one-shot-long`: checkpoint and result. Development
  had positive mean economics but failed minimum entry dates, model reliability,
  uncertainty, and contribution concentration.
- `high-volatility-monthly-one-shot-short`: checkpoint and result. The main exact
  slice was positive, while all three pre-registered neighboring configurations
  were negative and the bootstrap interval crossed zero.

External methods and data sources remain owned by each candidate's `sources.md` and
source manifest. This audit does not duplicate or reinterpret those claims.

Forward-data policy:

- decisions strictly after each frozen checkpoint only;
- official public Binance market/funding responses, stored outside Git and bound by
  URL, retrieval time, byte size, and SHA-256;
- full derived decisions/trades and aggregate evidence retained in Git;
- no product business data or account observations;
- no early peeking, rolling rule adjustment, symbol pruning, or favorable-regime
  exclusions;
- no scheduler or generic research platform; a candidate-specific replay is opened
  only at the maturity boundary.
