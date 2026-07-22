# Result

## Conclusion

`INSUFFICIENT_EVIDENCE`

The development gate failed. Evaluation and confirmation remain sealed; no
strategy conversion, handoff, product change, or long-term profitability claim is
permitted.

## Answer

Recent mature Binance perpetuals do not provide sufficiently stable or distinct
support for the pre-registered claim that high 28-day Amihud illiquidity predicts
higher next-week returns:

- the high-minus-low quintile spread averaged +0.2452% per target week, but its
  four-week block-bootstrap 95% interval was [-1.3478%, +2.0347%];
- only 48.08% of weekly spreads were positive and the first chronological half
  averaged -0.1883%;
- mean rank IC was -0.05441, opposite the claimed direction (one-sided HAC
  p=0.9365);
- the controlled Amihud slope was positive and significant, but Amihud's median
  absolute weekly rank correlation with log quote volume was 0.9579;
- the 14- and 56-day diagnostic spreads were both negative on average;
- the one-leg feasibility proxy averaged +0.3465% of full-plan capital per week
  after the frozen cost and hurdle, but its 95% interval crossed zero.

The positive controlled slope is retained as an important attempt, not promoted as
a discovery. With a negative raw rank IC, wrong-sign neighboring windows, and
near-mechanical dependence on volume, it can plausibly be a multicollinearity or
suppression artifact. The frozen gate correctly requires the raw, controlled,
economic, and distinctness evidence to agree.

## Evidence boundary and retained data

- Baseline commit:
  `0bdfeffa616260cebd2d2188ddc8deb9e85c77f4`.
- Predictor: `RESEARCH_AMIHUD28_HIGH_NEXT_WEEK_V1`.
- Fixed universe: 25 mature current-survivor Binance USD-M perpetuals.
- Raw data: official public daily klines and exchange metadata already held outside
  Git; 51 files / 6,713,938 bytes were verified and referenced, not copied.
- Each symbol: 1,663 consecutive bars from 2022-01-01 through 2026-07-21, with no
  missing dates, duplicate dates, invalid OHLC, or nonpositive quote volume.
- Development: 52 Saturday decisions from 2023-03-04 through 2024-02-24; Monday
  entry proxy and next-Monday target.
- Checkpoint digest:
  `50ee173a8e60d483e5dbc54dfd1a7658d9b73f8b7cea80b2bee7a81addc9ee77`.
- Source-reuse binding digest:
  `45aac73154794b268f210e9112c339c4037ac9157b119b9ed643c0b6070b5980`.

The source studies use broad, dynamic spot universes and mostly monthly sorts.
This result is an operational weekly perpetual adaptation, not a numerical
replication and not a rejection of every liquidity premium. The fixed current
survivor list understates listing and delisting risk and narrows liquidity
dispersion; quote volume also cannot replace point-in-time market capitalization.

## Costs and omissions

The proxy selects the highest trailing-volume member inside the high-illiquidity
quintile, allocates 25% of plan capital, deducts a 52 bp underlying round trip, and
deducts a 4% annual full-plan hurdle. It omits actual settled funding, historical
bid/ask, depth, impact, queue, partial fills, margin, liquidation, ADL, fee tier,
manual delay, and tax. Those omissions prevent strategy qualification even if the
predictive gate had passed.

## Counterevidence and stop rule

Nine mandatory checks failed: spread interval, positive-week fraction, IC sign and
significance, proxy interval, spread halves, both diagnostic windows, and score
distinctness. The family stop forbids reversing the sort, changing formation,
choosing favorable symbols or regimes, moving entry/exit, or turning volume and
volatility diagnostics into new candidates under this result.

## Reproduction and validation

Use the commands in `README.md`. The complete primary and diagnostic symbol panels,
weekly summaries, and selected-proxy rows are retained as nine CSV files with
hashes in `development.json`.

Validation is `PASS`: the calculation was recomputed from the bound raw source,
the gate points to the exact development result, and every CSV byte identity
matches. Validation digest:
`001250bdefa4a60f1caa9c0e8a4cb082505de3dde7034c8b3f556d02e317e00e`.

## Remaining unknowns

- Evaluation and confirmation outcomes are deliberately unknown.
- A point-in-time broad universe with market capitalization could distinguish size
  and liquidity more cleanly, but would be a materially different research design.
- Actual funding and execution costs for any concrete one-leg rule were not tested.
- The controlled positive coefficient may reflect a real conditional relation, but
  current evidence cannot separate that from multicollinearity or search exposure
  well enough to authorize further strategy work.
