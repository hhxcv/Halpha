# Sources and applicability

Accessed 2026-07-22.

- Politis and Romano (1994), *The Stationary Bootstrap*, DOI
  `10.1080/01621459.1994.10476870`, establishes block resampling for weakly dependent
  stationary observations. This study keeps Halpha's already frozen fixed circular
  four-week block rather than switching the candidate to a new estimator. Blocks 1
  and 8 expose dependence sensitivity.
- Bailey and López de Prado (2014), *The Deflated Sharpe Ratio*, DOI
  `10.3905/jpm.2014.40.5.094`, explains why sample length, non-normality and strategy
  selection affect performance claims and motivates explicit minimum track-record
  analysis. This study does not apply DSR numerically because the PPC decision gate
  is a costed mean/bootstrap gate, not a selected Sharpe-ratio claim.
- Harvey, Liu and Zhu (2016), *... and the Cross-Section of Expected Returns*, DOI
  `10.1093/rfs/hhv059`, documents the multiple-testing problem in return research.
  It supports preserving the strategy-family stop and using new forward dates rather
  than searching neighboring PPC parameters. This single-rule forward power study
  does not claim to erase the upstream selection history.
- The exact candidate definitions, costs, retained input and failed development
  evidence are local research artifacts under
  `research/studies/strategy-candidate/2026/price-path-continuity-weekly-winner-long/`.
  Their hashes are bound by `checkpoint.json`; no product data or runtime is read.

Applicability boundary: the empirical 40-date residual distribution is short,
selected and dominated by one historical regime. Block resampling preserves only
patterns present in that series. Structural breaks, worse future tails, changing
funding/spread, missing eligible weeks and execution errors can make actual power
lower. Therefore the output is a planning calibration, not external validation.

