# Attempts and decision log

## 2026-07-22 — direction survey

- Reviewed the existing basic-data and strategy-candidate frontier. No candidate is
  currently core-qualification-ready; PPC14+MOM14 remains only in forward incubation.
- Screened stablecoin issuance, severe depeg reversal and intraday Tether jump spillover.
- Rejected issuance growth because competing primary evidence and demand endogeneity
  weaken decision value relative to the extra on-chain normalization work.
- Deferred severe depeg rebound because genuinely new severe events are too rare for a
  quick independent confirmation.
- Selected positive Tether jump spillover because it is source-grounded, post-source
  falsifiable, single-leg, public-data-only and operationally compatible with a daily
  semi-automatic plan.

## 2026-07-22 — method verification

- Read the 2006 BNS primary paper, the current CRAN `highfrequency` 1.0.2 manual and
  source for `BNSjumpTest`, bipower variance and tripower quarticity.
- Resolved the exact linear statistic and constants instead of inferring them from the
  application paper’s abbreviated equation.
- Recorded the 24-return finite-sample/tick-size limitation and fixed an independent
  formula self-test before outcome analysis.

## 2026-07-22 — availability probes (not outcome analysis)

- Confirmed through Bitfinex’s public pair configuration that `USTUSD` is listed.
- Requested one historical day beginning 2021-07-01 and one recent day beginning
  2026-07-21 from `trade:1h:tUSTUSD`; both returned the expected public OHLCV schema.
- Confirmed Binance’s official USD-M archive documents 15-minute BTCUSDT klines and
  adjacent SHA-256 checksum files.
- No BTC target-return summary was computed or inspected before preregistration.

## Frozen next action

Create the checkpoint, run the formula self-test, then fetch and inspect development
only. Later stages remain sealed unless every preceding gate passes.

## 2026-07-22 — development result and mechanical validation repair

- Original frozen checkpoint: `e5dafcbb14d0903307bb26fce0e6f7d46c6391464289476cb8bbc803216c45b7`;
  original `study.py` SHA-256:
  `cdd63470ac6b5ce95bbebcb16a2dd821ff3e3eef6f214b680cf8916e79d8c55f`.
- Original source manifest digest:
  `ca21d711ed8bd10a429b98a8162beebcf08baddad41e1d7d1b5f7ddb4602f55a`;
  development analysis digest:
  `b48421763dad4e981e96d64581cf7e534daf7c1d4175bdb25d4504a073a4e20f`;
  development gate digest:
  `9b13ec30fb456babb46fc1ed293c99ade7f870429a3399b68e9b58544bfaa0b5`;
  original aggregate-result digest:
  `44ee66881985364f3c0f0a3a3a8b34e32f4c16db41f79bfd480fcbc67f464eec`.
- Development failed nine frozen checks. Evaluation and confirmation stayed sealed.
- The first independent validation recomputed statistics and gates but failed the two
  CSV byte checks: logical CSV hashes were frozen from LF text, while Windows
  `Path.write_text` persisted CRLF. This was an evidence-I/O defect only.
- Mechanical repair: validate CSVs after Python universal-newline decoding and add a
  one-off manifest-rebind command that verifies every original source byte before
  binding the unchanged inputs to the repaired code checkpoint. No signal, sample,
  outcome, regression, bootstrap, cost, gate or conclusion rule changed.
- The original checkpoint is retained in `checkpoint_pre_validation_io_fix.json`.

