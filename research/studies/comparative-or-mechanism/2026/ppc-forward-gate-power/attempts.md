# Attempts

- 2026-07-22: selected the gate-power question after rejecting unidentified formal
  activation replay and non-directional entropy/efficiency gating.
- 2026-07-22: inspected the retained PPC CSV identity and confirmed 88 trades / 40
  entry-date cohorts. No sealed evaluation or confirmation data was read.
- Commands and deterministic output hashes are appended after execution.
- 2026-07-22 first run: checkpoint/analyze/validate all executed successfully, but
  methodological review found the fixed reference-threshold approximation was not
  equivalent to the candidate's per-sample percentile gate under strong skew. It
  produced 11.484% apparent joint power for a 50 bp effect and 6.172% joint null
  rejection at 26 weeks. The output hashes and correction are preserved in
  `amendment-001.md`; these numbers are invalid for the final decision.
- 2026-07-22 correction frozen: exact nested percentile bootstrap for the unchanged
  26-week primary question; the broad curve remains diagnostic only.
- 2026-07-22 corrected commands: `checkpoint`, `analyze`, and an independent
  deterministic `validate` all passed. Exact 50 bp joint power was 5.92% and null
  joint rejection 1.78%; conclusion `DOES_NOT_SUPPORT` the 26-week horizon claim.
- Final identities: `checkpoint.json`
  `2cabc1c65d44fc1b71c8a63130e9766796adef9c34f72af4bab577f59d72723e`;
  `results.json`
  `e4bb2fadde5e1011ce264bb5de0b119ce4bce98a72eda19a41fe10318792813b`;
  `power_curve.csv`
  `0dfc4f4cf11e3ba286b99f69ca58683890042d66704406da3351f242d4ff1e71`;
  `validation.json`
  `528f8c9760dd845895403478a770e7d1dad0c3b28309ac0ca1f00c29d2fdc05c`.
