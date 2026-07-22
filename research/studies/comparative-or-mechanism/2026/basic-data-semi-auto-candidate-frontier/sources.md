# Source register

As-of 2026-07-22; baseline commit
`0bdfeffa616260cebd2d2188ddc8deb9e85c77f4`.

Internal evidence is enumerated with exact SHA-256 in `study.py` and rechecked by
`validation.json`. It includes the preceding qualification frontier, both latest
question results/gates/validations, the PAXG spot development stop, and the three
closest current single-perpetual candidates.

External method/selection sources:

- Moreira and Muir (2017), DOI `10.1111/jofi.12513`, and Cederburg et al.
  (2020), DOI `10.1016/j.jfineco.2020.04.015`, provide favorable and skeptical
  volatility-management baselines.
- Zhang et al. (2021), DOI `10.1016/j.jbankfin.2021.106246`, and Liu,
  Tsyvinski and Wu (2022), DOI `10.1111/jofi.13119`, motivate but do not prove
  transfer of broad-spot cross-sectional predictors to liquid perpetuals.
- Long et al. (2020), DOI `10.1016/j.frl.2020.101566`, reports positive
  same-weekday cross-sectional seasonality. Caporale and Plastun (2022), DOI
  `10.1016/j.frl.2021.102354`, report that most tested crypto calendar anomalies
  are absent and only a within-month effect is common across their instruments.
- Binance public USD-M `exchangeInfo` provides PAXGUSDT's onboard time. The exact
  public snapshot path and digest are inherited from the ETH study manifest; no
  credentials, product runtime, or product data are involved.
- Kumar (2022), DOI `10.1108/MF-02-2022-0084`, reports a turn-of-month effect in
  BTC in an earlier sample; Kaiser and Stöckl (2022), DOI
  `10.1016/j.frl.2021.102354`, supply the broader skeptical calendar baseline. The
  retained post-publication Halpha test did not support the actionable rule.
- Han (2024), DOI `10.1016/j.frl.2024.106016`, reports nonlinear cross-sectional
  pricing of VIX sensitivity. The retained Halpha study is explicitly an
  operational adaptation because the exact paywalled equation was unavailable;
  it failed its pre-registered development gate.
- Zhang and Li (2023), DOI `10.1002/ijfe.2431`, and Ali, Peng, and Shams (2025),
  SSRN `5527518`, report a crypto illiquidity-return relation; Wei (2018), DOI
  `10.1016/j.econlet.2018.04.003`, reports no illiquidity premium. The retained
  recent-perpetual adaptation failed the combined raw, robustness, distinctness,
  and economic gate despite a positive controlled coefficient.
- Mercik, Zaremba, and Demir (2026), DOI
  `10.1016/j.irfa.2026.105137`, report bid-ask spread as one of the few weekly
  crypto factors with favorable evidence in both halves of their broad spot
  sample. Their CC0 RepOD V1 factor returns (`doi:10.18150/IIVQQE`) were retained
  outside Git and approximately reproduced the value-weighted annualized mean.
  Abdi and Ranaldo (2017), DOI `10.1093/rfs/hhx084`, supplied the preregistered
  two-day-corrected close-high-low estimator. Halpha's fixed mature-perpetual
  transfer had a positive raw development mean but negative rank IC, inconsistent
  halves, intervals crossing zero, a negative monthly-corrected diagnostic and
  concentrated single-leg gains; it does not authorize a strategy conversion.
- Li and Zhu (2026), DOI `10.1016/j.ribaf.2026.103298`, retain residual momentum
  in a cryptocurrency factor model and report an out-of-sample explanatory
  advantage. Blitz, Huij and Martens (2011), DOI
  `10.1016/j.jempfin.2011.01.003`, provide the standardized residual-return
  construction and common-factor-exposure mechanism. Halpha's frozen weekly
  perpetual transfer failed stability, controlled prediction, concentration and
  distinctness gates despite a positive raw mean.
- Zhang and Zhao (2023), DOI `10.1016/j.irfa.2023.102712`, report that higher
  relative signed jump predicts lower next-day cryptocurrency returns in a 2017–2021
  five-minute spot sample. Halpha's explicitly non-numerical 15-minute perpetual
  transfer retained the negative average rank relation but failed the economic tail,
  cost, split-period and coarser-resolution gates; it does not support strategy
  conversion.
- Grobys and Huynh (2022), DOI `10.1016/j.frl.2021.102644`, report that the
  interaction of a positive Bitfinex USDT/USD BNS jump and positive USDT return
  predicts lower next-day BTC returns in 2018-11 through 2021-06. Barndorff-Nielsen
  and Shephard (2006) and CRAN `highfrequency` 1.0.2 supplied the exact jump-test
  basis. Halpha's fully post-source, delayed Binance-perpetual transfer retained the
  negative point estimate but failed significance, split stability, uncertainty,
  cost/hurdle and concentration gates. Bitfinex public candles and Binance's
  checksummed public archive are bound in its manifest; no product or private data
  was used.
- Yae and Tian (2022), DOI `10.1016/j.physa.2022.127379`, and their open 2021
  working paper report that decreases in BTC–equity conditional correlation predict
  higher next-day BTC returns through delayed institutional diversification
  rebalancing. Halpha's fully post-publication transfer corrected the paper's stated
  3–4 hour close mismatch, froze GARCH/DCC parameters before development, and used
  official FRED/Binance public prices. The development coefficient instead had the
  wrong sign, frozen forecast OOS R2 was negative, halves disagreed and the costed
  proxy failed; later stages and nearby DCC/index variants remain sealed.
- Zhang and Makgolo (2026), SSRN `6648082`, report that lagged cross-sectional
  dispersion weakens subsequent cryptocurrency momentum in a dynamic,
  survivorship-aware CoinGecko top-500 universe. Halpha froze a lower-maintenance
  weekly interaction using 25 mature perpetuals, controls for market volatility and
  average correlation, and a one-leg economic proxy. Development failed the state
  count, statistical, economic, yearly and neighbor gates; the recent preprint is
  not treated as independent confirmation of a deployable strategy.
- Lee and Wang (2025), DOI `10.1017/S002210902400022X`, use 15-minute data for
  100 spot cryptocurrencies and report that prior-month realized variance predicts
  lower subsequent-week returns, whereas daily-return volatility is insignificant.
  Halpha used the paper-guided 15-minute/one-month/next-week definition but retained
  a 48-hour semi-automatic activation gap and mature USD-M universe. Rank ordering
  had the published sign, yet controlled increment and one-leg economics failed;
  the difference between the paper's broad small/illiquid spot cross-section and
  Halpha's mature perpetuals remains an explicit applicability boundary, not a
  license to filter risky coins post hoc.
- Lyons and Viswanath-Natraj, *What Keeps Stablecoins Stable?*, NBER Working
  Paper 27136, use blockchain issuance flows and local projections with lagged
  supply, price, hash-rate and address controls. They find no significant Bitcoin
  or Ethereum price response to aggregate USDT issuance and explicitly distinguish
  aggregate supply from wallet-level flows. This is direct counterevidence to a
  low-identification weekly stablecoin-supply timing rule; it does not rule out
  microeconomic flows that would require different, more complex data.
- Cakici, Shahzad, Bedowska-Sojka and Zaremba (2024), DOI
  `10.1016/j.irfa.2024.103244`, compare eight machine-learning approaches on more
  than 500 coins and 40 characteristics. They report limited benefit from model
  complexity, with price, past alpha, illiquidity and momentum carrying most of the
  information, and gains concentrated in small, illiquid, volatile hard-to-trade
  assets. This supports a pre-study rejection for Halpha: those simple families are
  already directly tested, while importing the broad hard-to-trade universe and
  high-turnover portfolio would violate the mature one-leg semi-automatic boundary.
- Hudson and Urquhart, *Technical trading and cryptocurrencies* (2021), DOI
  `10.1007/s10479-019-03357-1`, test 14,919 rules with multiple-testing controls.
  Channel breakouts were among the strongest in-sample families, but the selected
  Bitcoin rules had negative out-of-sample return and risk-adjusted performance.
  This is a useful favorable-and-negative benchmark for the formal Donchian family;
  it does not numerically validate Halpha's much shorter 5-hour channel, one-hour
  hold, perpetual funding or user activation contract.
- Raith, Kinateder and Wagner, *Technical analysis in cryptocurrency markets: Do
  transaction costs and bubbles matter?* (2022), DOI
  `10.1016/j.intfin.2022.101601`, test 69 moving-average and breakout rules at daily
  and one-minute frequency across five major coins. They show that costs, coin and
  bubble regimes materially change rule profitability. This supports requiring a
  frozen activation mechanism and exact costed replay; it does not support inventing
  that missing mechanism from already-observed Halpha trend results.
- Karasinski, *The adaptive market hypothesis and the return predictability in the
  cryptocurrency markets* (2023), DOI `10.18559/ebr.2023.1.4`, applies rolling
  martingale-difference tests to 40 large cryptocurrencies and finds that most are
  unpredictable most of the time. His intraday extension, *The Predictability of
  High-Frequency Returns in the Cryptocurrency Markets and the Adaptive Market
  Hypothesis* (2025), reports the same broad conclusion and that apparent
  inefficiency rises with frequency. These are predictability diagnostics, not a
  pre-specified directional trading rule, and their higher-frequency implication is
  a poor fit for the current low-maintenance plan scope.
- Politis and Romano (1994), DOI `10.1080/01621459.1994.10476870`, provide the
  dependent-data bootstrap basis used by the retained PPC gate. Bailey and López de
  Prado (2014), DOI `10.3905/jpm.2014.40.5.094`, motivate explicit minimum
  track-record analysis under non-normality and selection; Harvey, Liu and Zhu
  (2016), DOI `10.1093/rfs/hhv059`, supply the multiple-testing warning that prevents
  replacing new time evidence with adjacent parameter searches. Halpha's exact
  nested simulation is a local planning calibration, not an external Alpha result.
- CME Group's official 2026-06-01 launch notice documents that near-24/7
  cryptocurrency futures and options trading went live on 2026-05-29. Historical
  CME weekend gaps therefore have a forward mechanism break and were rejected
  before backtesting. Aleti and Mizrach (2021), DOI `10.1002/fut.22163`, place BTC
  cross-market price discovery at microstructure horizons; that family is excluded
  from the current semi-automatic/basic-data scope rather than labeled false.
- Baur et al. (2019), DOI `10.1016/j.frl.2019.04.023`, use more than 15 million
  observations across seven exchanges and report no persistent return pattern
  across years. Caporale and Plastun (2024), DOI
  `10.1016/j.frl.2024.105429`, likewise find no robust cryptocurrency return
  seasonality. These are strong pre-study counterevidence against another fixed
  hour/weekday directional rule. Recent scheduled-FOMC work documents volatility
  and volume jumps rather than a stable return direction, so it does not map to the
  current one-leg directional plan without materially expanding product scope.

Selection caveat: rejecting a research question for low Halpha decision value is not
evidence that its academic effect is false. It records why scarce personal-project
research capacity is not spent there now.
