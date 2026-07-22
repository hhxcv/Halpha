# Result — relative signed jump and next-day perpetual returns

## Conclusion

`DOES_NOT_SUPPORT`

The fixed 15-minute operational transfer failed development. It must not open the
evaluation or confirmation periods, become a strategy candidate, or be described as
evidence of long-term profitability.

## Development evidence

- Period: 457 eligible UTC decisions in `[2022-03-26, 2023-07-01)`; 11,042
  symbol-days; median 24 rankable instruments (range 21–25).
- Primary low-RSJ minus high-RSJ return: `-0.0235%` per day.
- Seven-day circular block-bootstrap 95% interval: `[-0.2222%, +0.1765%]`.
- Positive-spread days: `50.98%`.
- First half / second half: `-0.1057% / +0.0583%` per day.
- Mean daily RSJ rank IC: `-0.02882`; one-sided HAC p `0.00354`.
- Controlled RSJ slope: `-0.00095`; one-sided HAC p `0.03610`.
- Simple prior-day reversal spread: `+0.0401%`; RSJ minus reversal:
  `-0.0636%` per day.
- Conservative one-leg proxy after 52 bp underlying round-trip stress cost, 25%
  plan notional and 4% annual full-plan hurdle: `-0.2403%` per day; block interval
  `[-0.3490%, -0.1390%]`.
- Proxy first half / second half: `-0.3743% / -0.1069%`; only 5 of 20 selected
  symbols had a positive mean.
- Diagnostic 30-minute / one-hour spreads: `-0.1034% / -0.1805%` per day.
- Maximum median absolute RSJ/control correlation was `0.6923`, with prior-day
  return the closest control; the frozen distinctness ceiling passed.

## Interpretation and counterevidence

The negative and statistically significant rank IC and controlled coefficient are
consistent with the source paper's average ordering relation. They are not enough for
Halpha: the preregistered extreme-tail portfolio has the wrong economic sign, loses
to simple prior-day reversal, is unstable across halves, and becomes clearly negative
under the conservative one-leg feasibility proxy. Coarser sampling does not rescue
the relation.

This result does not refute the paper's five-minute spot-universe evidence. Halpha
tested official 15-minute USD-M perpetual klines, a fixed survivor universe, a later
market period, a 15-minute action delay and a retail one-leg feasibility proxy. Those
differences bound the conclusion. Funding and exact fills were intentionally deferred;
because the pre-funding economic screen already fails, adding them cannot qualify this
candidate.

## Gate and family stop

Failed checks covered:

- primary mean, bootstrap lower bound, positive-day fraction and both-half stability;
- superiority to the simple reversal spread;
- proxy mean, bootstrap lower bound, both-half stability and positive-symbol breadth;
- nonnegative 30-minute and one-hour diagnostics.

The negative/significant rank IC and controlled coefficient, selection breadth,
contribution concentration, proxy advantage over the even worse reversal one-leg
proxy, and score/control distinctness checks passed. All checks were required.

Do not inspect later stages, reverse the trade, or change the delay, day boundary,
tail, universe, controls, target, cost, notional or sampling interval under this
question. A future five-minute study would require an independently valuable project
reason rather than serving as a rescue attempt.

## Data and reproduction identities

- Baseline commit: `0bdfeffa616260cebd2d2188ddc8deb9e85c77f4`
- Formal comparison strategy: `ONE_SHOT_DONCHIAN_ATR_BREAKOUT 1.0.1 / BTCUSDT-PERP`
- Input: 425 official Binance USD-M 15-minute archive files, 50,798,433 compressed
  bytes, stored Git-external under the path recorded in the source manifest; daily
  controls reuse the bound official daily cache.
- Checkpoint content digest: `0f3ea9c0a177a565d15e69a0cfac725fefe9683ab1190a6c56e765597c485491`
- Development source manifest: `ca419060bd58d89a86c8b652446008e005952dbf4b178daebc34dd56105aa4ff`
- Data quality: `3bdbd6794fff18ca3b554cce7a72384b5961a107a703fc625c0818dd7fa9b4bf`
- Development: `33885b717fdd441bfa3d7e7ff0da0fb36107fedd74828294524b7d0f0a40dba2`
- Development gate: `fe417996538487022a31b0b84dfe1070df021dd5c1a35b9170b9474e9e71fde0`
- Results: `4bf5a38877ea6eac4bb5696cab14ffb7bd63e8a15f3e39e7cb808daf12289ffd`
- Validation: `8cdb11dca2cbf17dbf7b8798b418ebf9372c0f8684174a8e8101adad8c2ce72e`
- Validation status: `PASS`; development economics were independently recomputed,
  all 425 cache identities were verified, and all 12 retained CSV identities matched.

Product, capital and real-account effects: `NONE`.
