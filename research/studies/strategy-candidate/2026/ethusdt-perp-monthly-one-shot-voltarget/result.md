# Result

Conclusion: **DOES_NOT_SUPPORT**.

The opened 2021–2022 development stage does not support advancing the fixed monthly
ETH volatility-target candidate. Evaluation (2023–2024) and confirmation
(2025–2026-06) remain sealed under the preregistered stop rule.

## Primary 8% target

- 24 complete monthly plans; mean target notional was 8.8681% of full-plan capital.
- Base total return: +2.4291%; annualized return: +1.2072%.
- Base daily maximum drawdown: -13.4933%; zero-risk-free Sharpe: 0.1737.
- Stress return after the 4% annual capital hurdle: -7.9453%.
- Base return after the combined 6% annual capital/research hurdle: -8.8385%.
- Three-month block-bootstrap 95% interval for mean monthly base return:
  [-0.8219%, +0.9747%].
- Calendar years: 2021 +13.2351%; 2022 -9.5430% in the base scenario.

The 6% and 10% diagnostic targets were also below the combined hurdle. They are not
eligible replacements for the primary rule.

## Simple benchmark and falsification

The fixed 25% monthly ETH long returned +17.1137%, had a -28.9939% daily maximum
drawdown, and a 0.4359 Sharpe over the same period. Volatility targeting reduced
drawdown, but it also reduced both absolute return and risk-adjusted efficiency. It
therefore failed the intended economic explanation that scaling exposure down during
high volatility would improve a small account's usable ETH risk-premium harvest.

This is not evidence that ETH has no risk premium, nor that volatility management
never works. It falsifies this fixed 60-day/8%-target/25%-cap/monthly-one-shot rule as
a Halpha candidate under the registered costs and hurdles. The exact rule is not
handoff-ready and no product strategy object was generated.

## Reproduction state

- Checkpoint: `472823c9b055e624222dc755e9af98bcce27ff7b6760fef9983a0ff432894e11`
- Data-quality digest: `795152479c92032de2c70d33d09a7229c4b0f0455b1b221720cf44a652a6026f`
- Primary monthly rows and all scenario results are retained in
  `development_plans.csv` and `development.json`.
- Public raw data remains Git-external at the exact cache root in
  `checkpoint.json`; `source_manifest.json` records every URL, byte count, and
  SHA-256 needed to verify or re-fetch it.

