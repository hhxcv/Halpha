from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
EVIDENCE = {
    "prior_frontier": (
        "research/studies/comparative-or-mechanism/2026/strategy-candidate-qualification-frontier/frontier.json",
        "2f6989ceecd84269783e71b5458fd99574ab82b5697e97cac9a56f20a766e454",
    ),
    "eth_results": (
        "research/studies/strategy-candidate/2026/ethusdt-perp-monthly-one-shot-voltarget/results.json",
        "3d156e60f6d6c37624a2125d8cadb7fbb4decda7a38999a261b0ebf97c892e69",
    ),
    "eth_gate": (
        "research/studies/strategy-candidate/2026/ethusdt-perp-monthly-one-shot-voltarget/development_gate.json",
        "a980b5b1c1a1a2e6162ec558880c63b0b5f0fcb5203afb5419915631218d2704",
    ),
    "eth_validation": (
        "research/studies/strategy-candidate/2026/ethusdt-perp-monthly-one-shot-voltarget/validation.json",
        "4a9bf88399d81c3e464cc3c2f352fc75bb1926ee73299911fe93ed71f9e34a77",
    ),
    "downbeta_results": (
        "research/studies/predictive/2026/btc-downside-beta-monthly-return-predictability/results.json",
        "f75f8c82eeb1e604f935e901b4fb65a1638759a1bb2fc269b155034ddb72bfa5",
    ),
    "downbeta_gate": (
        "research/studies/predictive/2026/btc-downside-beta-monthly-return-predictability/development_gate.json",
        "48210ed8c237033f583e5ae3d53f9b502f8d918dbe50081f944b2a4e9555b88b",
    ),
    "downbeta_validation": (
        "research/studies/predictive/2026/btc-downside-beta-monthly-return-predictability/validation.json",
        "5591bfba0015ed68574743a02be1b8037b2240e1ec802a0feab3d0aec392895a",
    ),
    "tom_results": (
        "research/studies/strategy-candidate/2026/btcusdt-perp-turn-of-month-one-shot-long/results.json",
        "5f87b219d354c9e151e5d207eb414ac815a8aa07aecd936361d12d37ab9c6bab",
    ),
    "tom_gate": (
        "research/studies/strategy-candidate/2026/btcusdt-perp-turn-of-month-one-shot-long/development_gate.json",
        "8a614f6f51a10211b386775ccbdd1ede645317cb39691ab880638ea6a72e3acc",
    ),
    "tom_validation": (
        "research/studies/strategy-candidate/2026/btcusdt-perp-turn-of-month-one-shot-long/validation.json",
        "62df0ea50952f022c9e67ee1dcef5a1d425e7df3040df8b932032dd7e8d8089a",
    ),
    "vix_beta_results": (
        "research/studies/predictive/2026/intermediate-vix-beta-weekly-return-predictability/results.json",
        "72b9dfd798a82338674052b5749694945bae848845aa54217a58b8c69e9c00a0",
    ),
    "vix_beta_gate": (
        "research/studies/predictive/2026/intermediate-vix-beta-weekly-return-predictability/development_gate.json",
        "dfd67995e8692c44021aea06ceec44a860e6d333403b4767eab9a0b346de103a",
    ),
    "vix_beta_validation": (
        "research/studies/predictive/2026/intermediate-vix-beta-weekly-return-predictability/validation.json",
        "ce66e098eb0fee89f78ad81c8d4a6c530817150a6c3625c369a7dee17b4a11af",
    ),
    "amihud_results": (
        "research/studies/predictive/2026/amihud-illiquidity-weekly-return-predictability/results.json",
        "2dc7fdddb670ab63fdc00d51abde211c043c03370161e7b30994281f98185881",
    ),
    "amihud_gate": (
        "research/studies/predictive/2026/amihud-illiquidity-weekly-return-predictability/development_gate.json",
        "e660d8e19675d1cb54ef0a12d813bb251fa014af0cb670b583322df8d7e6dd6c",
    ),
    "amihud_validation": (
        "research/studies/predictive/2026/amihud-illiquidity-weekly-return-predictability/validation.json",
        "51e72f8a6fe842790225970ecff62be653bc51d24d445768b936f15ef0c26c8f",
    ),
    "chl_spread_results": (
        "research/studies/predictive/2026/ohlc-estimated-spread-weekly-return-predictability/results.json",
        "2916499ca1326bd1981eeffc85e5d902a4c3c9d27202971c6c9d7b0cd974b346",
    ),
    "chl_spread_gate": (
        "research/studies/predictive/2026/ohlc-estimated-spread-weekly-return-predictability/development_gate.json",
        "5b6be5fc0eeed67a0ce3a44b4066f117043a444efda45098f3e9365e0ed94a4a",
    ),
    "chl_spread_validation": (
        "research/studies/predictive/2026/ohlc-estimated-spread-weekly-return-predictability/validation.json",
        "d4478bf3d844f1afc4ec1e7c235e3c4ac12c30b9d4c428b243f24670fce8c1dc",
    ),
    "residual_momentum_results": (
        "research/studies/predictive/2026/residual-momentum-weekly-return-predictability/results.json",
        "748c30464311226802ba1c1f2b8f8c1da6924c31419b87c286acf669a44afaae",
    ),
    "residual_momentum_gate": (
        "research/studies/predictive/2026/residual-momentum-weekly-return-predictability/development_gate.json",
        "b3606ecb36cdb002511af0ba7adc67b635faaf34617d3ea836deb5361b3a4791",
    ),
    "residual_momentum_validation": (
        "research/studies/predictive/2026/residual-momentum-weekly-return-predictability/validation.json",
        "ecf9c067e98c3228d5e80d7fc6360edc9e890cd273a710b766c6405952be2ede",
    ),
    "relative_signed_jump_results": (
        "research/studies/predictive/2026/relative-signed-jump-next-day-predictability/results.json",
        "8cb60b1ac25f14eda9215284f15a7f071416e0220e67dd2f896cc074f7218048",
    ),
    "relative_signed_jump_gate": (
        "research/studies/predictive/2026/relative-signed-jump-next-day-predictability/development_gate.json",
        "7909bfbbb30c494307b77f1d1452f00138a026cb0c6d15d3eaf4f98a6b98878f",
    ),
    "relative_signed_jump_validation": (
        "research/studies/predictive/2026/relative-signed-jump-next-day-predictability/validation.json",
        "4f9bd45aa08cc72a4b3068cd23446e71c157cf6aadd035db19ae9311847c5920",
    ),
    "tether_jump_results": (
        "research/studies/predictive/2026/tether-positive-jump-btc-next-day-predictability/results.json",
        "905700430c016be07cdf4b711aae2955a0e4bae025ed31b0f861ab3d05a8868f",
    ),
    "tether_jump_gate": (
        "research/studies/predictive/2026/tether-positive-jump-btc-next-day-predictability/development_gate.json",
        "93bec0aa91f9078b064b12d30ecf783de4d00192d6a83ce5d302de777edbd099",
    ),
    "tether_jump_validation": (
        "research/studies/predictive/2026/tether-positive-jump-btc-next-day-predictability/validation.json",
        "5d078a3f65f5ff6ec72f024b838b5e8d3f327aae7f3383121e95add331062ed5",
    ),
    "btc_sp500_correlation_results": (
        "research/studies/predictive/2026/btc-sp500-correlation-change-next-interval-predictability/results.json",
        "a33a9f72f0302e82c3e3f5ed7f5604547b19ccaa8918cd16fb12ee7a59ecac2a",
    ),
    "btc_sp500_correlation_gate": (
        "research/studies/predictive/2026/btc-sp500-correlation-change-next-interval-predictability/development_gate.json",
        "42db313479be3f8d5f6e4c82c3af84206ed2e2ee3bf2633d6cd30d1ad7c04b88",
    ),
    "btc_sp500_correlation_validation": (
        "research/studies/predictive/2026/btc-sp500-correlation-change-next-interval-predictability/validation.json",
        "2f7442382811c14297314c56fdc6c6576f0c2ea650f861eb0c69efa301001594",
    ),
    "dispersion_results": (
        "research/studies/predictive/2026/cross-sectional-dispersion-momentum-state-predictability/results.json",
        "adcb586d4432d72df02c3deca8f34e4e39759cee3c865396162bd58e432845a3",
    ),
    "dispersion_gate": (
        "research/studies/predictive/2026/cross-sectional-dispersion-momentum-state-predictability/development_gate.json",
        "6aa4091d6a6a033ed4f8f0bf5692d9fed111436dd8e8add451fa55fd5d0b1d45",
    ),
    "dispersion_checkpoint": (
        "research/studies/predictive/2026/cross-sectional-dispersion-momentum-state-predictability/checkpoint.json",
        "e7cbe9a5cf47d739b9e946d501cc248b6456d785e1a0d7efee3e31219dd22604",
    ),
    "intraday_rv_results": (
        "research/studies/predictive/2026/intraday-realized-variance-weekly-return-predictability/results.json",
        "b77042fd93111af37fbc66d0cb1639677cfb9d2851348b62d2464d19894c541e",
    ),
    "intraday_rv_gate": (
        "research/studies/predictive/2026/intraday-realized-variance-weekly-return-predictability/development_gate.json",
        "532f319da78269996f0041f0f71799845d7126b083c4928f44525de0b37b195e",
    ),
    "intraday_rv_validation": (
        "research/studies/predictive/2026/intraday-realized-variance-weekly-return-predictability/validation.json",
        "6a2154f2b6d3aff3489f411326f66f8de31ae8019e2e85cbfbdcb38a8fed08e7",
    ),
    "ppc_power_checkpoint": (
        "research/studies/comparative-or-mechanism/2026/ppc-forward-gate-power/checkpoint.json",
        "2cabc1c65d44fc1b71c8a63130e9766796adef9c34f72af4bab577f59d72723e",
    ),
    "ppc_power_results": (
        "research/studies/comparative-or-mechanism/2026/ppc-forward-gate-power/results.json",
        "e4bb2fadde5e1011ce264bb5de0b119ce4bce98a72eda19a41fe10318792813b",
    ),
    "ppc_power_validation": (
        "research/studies/comparative-or-mechanism/2026/ppc-forward-gate-power/validation.json",
        "528f8c9760dd845895403478a770e7d1dad0c3b28309ac0ca1f00c29d2fdc05c",
    ),
    "paxg_spot_development": (
        "research/studies/legacy/2026/paxgusdt-spot-monthly-tsmom/development.json",
        "c75ba390463e9aeda8c81af4b0e3b3eb40b9c1655c3bac4ff2adf07b401d2090",
    ),
    "paxg_spot_gate": (
        "research/studies/legacy/2026/paxgusdt-spot-monthly-tsmom/development_gate.json",
        "763893892376bd93ce55a648ed3df18a807c35031f0751ffec96e41f82978f3d",
    ),
    "ppc_results": (
        "research/studies/strategy-candidate/2026/price-path-continuity-weekly-winner-long/results.json",
        "823ba93c045d307aeb954832ead508333df8712bf32c7492dc95325dba7e89d0",
    ),
    "ctrend_results": (
        "research/studies/strategy-candidate/2026/ctrend-weekly-top-quintile-one-shot-long/results.json",
        "8d8b0a953f0a4a3a6fec36bf647bc5aeb3a5b7c78d2c4f38f5eb35b8a2b04a6b",
    ),
    "highvol_short_results": (
        "research/studies/strategy-candidate/2026/high-volatility-monthly-one-shot-short/results.json",
        "3f28b3ed2815c8e87c16a911e3500d6e54855bf254b4c81c61f7c3807de10e29",
    ),
}
ETH_MANIFEST = ROOT / "research/studies/strategy-candidate/2026/ethusdt-perp-monthly-one-shot-voltarget/source_manifest.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def canonical(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def write_json(path: Path, value: dict[str, Any]) -> None:
    payload = dict(value)
    payload["content_digest"] = canonical(payload)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_exchange_snapshot() -> tuple[dict[str, Any], dict[str, Any]]:
    manifest = read_json(ETH_MANIFEST)
    item = manifest["exchange_info"]
    path = Path(item["path"])
    if not path.exists() or path.stat().st_size != item["bytes"] or sha256(path) != item["sha256"]:
        raise RuntimeError("public exchangeInfo snapshot identity mismatch")
    exchange = read_json(path)
    symbol = next(row for row in exchange["symbols"] if row["symbol"] == "PAXGUSDT")
    return item, symbol


def command_audit(_args: argparse.Namespace) -> None:
    identities: list[dict[str, Any]] = []
    for name, (relative, expected) in EVIDENCE.items():
        path = ROOT / relative
        actual = sha256(path)
        if actual != expected:
            raise RuntimeError(f"evidence identity mismatch: {name} {actual}")
        identities.append({"name": name, "path": relative, "sha256": actual})
    exchange_item, paxg = load_exchange_snapshot()
    eth = read_json(ROOT / EVIDENCE["eth_results"][0])
    down = read_json(ROOT / EVIDENCE["downbeta_results"][0])
    tom = read_json(ROOT / EVIDENCE["tom_results"][0])
    vix_beta = read_json(ROOT / EVIDENCE["vix_beta_results"][0])
    amihud = read_json(ROOT / EVIDENCE["amihud_results"][0])
    chl_spread = read_json(ROOT / EVIDENCE["chl_spread_results"][0])
    residual_momentum = read_json(ROOT / EVIDENCE["residual_momentum_results"][0])
    relative_signed_jump = read_json(ROOT / EVIDENCE["relative_signed_jump_results"][0])
    tether_jump = read_json(ROOT / EVIDENCE["tether_jump_results"][0])
    btc_sp500_correlation = read_json(ROOT / EVIDENCE["btc_sp500_correlation_results"][0])
    dispersion = read_json(ROOT / EVIDENCE["dispersion_results"][0])
    dispersion_gate = read_json(ROOT / EVIDENCE["dispersion_gate"][0])
    intraday_rv = read_json(ROOT / EVIDENCE["intraday_rv_results"][0])
    intraday_rv_gate = read_json(ROOT / EVIDENCE["intraday_rv_gate"][0])
    ppc_power = read_json(ROOT / EVIDENCE["ppc_power_results"][0])
    frontier = {
        "as_of": "2026-07-22",
        "baseline_commit": "0bdfeffa616260cebd2d2188ddc8deb9e85c77f4",
        "research_kind": "COMPARATIVE_OR_MECHANISM",
        "question": "Do retained basic-data studies now contain multiple one-leg semi-automatic candidates ready for trade-core qualification?",
        "conclusion": "DOES_NOT_SUPPORT",
        "counts": {"current_core_qualification_ready": 0, "minimum_requested": 2, "new_handoff_objects": 0},
        "latest_completed_questions": [
            {
                "id": "RESEARCH_ETHUSDT_PERP_VOL60_TARGET8_CAP25_MONTHLY_ONE_SHOT_V1",
                "kind": "STRATEGY_CANDIDATE", "conclusion": eth["conclusion"],
                "gate": eth["stage_gate_status"], "handoff": eth["handoff_status"],
            },
            {
                "id": "RESEARCH_BTC_DOWN_BETA60_MONTHLY_RETURN_V1",
                "kind": "PREDICTIVE", "conclusion": "DOES_NOT_SUPPORT",
                "development_spread": down["main"]["high_minus_low_return"]["mean"],
                "development_rank_ic": down["main"]["rank_ic"]["mean"], "strategy_conversion": "PROHIBITED_AFTER_GATE_FAIL",
            },
            {
                "id": "RESEARCH_BTCUSDT_PERP_TOM_LAST_TO_DAY4_CAP50_V1",
                "kind": "STRATEGY_CANDIDATE", "conclusion": tom["conclusion"],
                "gate": tom["stage_gate_status"], "handoff": tom["handoff_status"],
            },
            {
                "id": "RESEARCH_INTERMEDIATE_VIX_BETA_36W_NEXT_WEEK_V1",
                "kind": "PREDICTIVE", "conclusion": vix_beta["conclusion"],
                "gate": vix_beta["stage_gate_status"], "strategy_conversion": "PROHIBITED_AFTER_GATE_FAIL",
            },
            {
                "id": "RESEARCH_AMIHUD28_HIGH_NEXT_WEEK_V1",
                "kind": "PREDICTIVE", "conclusion": amihud["conclusion"],
                "gate": amihud["stage_gate_status"], "strategy_conversion": "PROHIBITED_AFTER_GATE_FAIL",
            },
            {
                "id": "RESEARCH_CHL28_HIGH_NEXT_WEEK_V1",
                "kind": "PREDICTIVE", "conclusion": chl_spread["conclusion"],
                "gate": chl_spread["stage_gate_status"],
                "external_broad_spot_benchmark": "APPROXIMATELY_CORROBORATED_BUT_EXCLUDED_FROM_GATE",
                "strategy_conversion": "PROHIBITED_AFTER_GATE_FAIL",
            },
            {
                "id": "RESEARCH_RESIDUAL_MOM14_NEXT_WEEK_V1",
                "kind": "PREDICTIVE", "conclusion": residual_momentum["conclusion"],
                "gate": residual_momentum["stage_gate_status"], "strategy_conversion": "PROHIBITED_AFTER_GATE_FAIL",
            },
            {
                "id": "RESEARCH_RSJ15_LOW_NEXT_DAY_V1",
                "kind": "PREDICTIVE", "conclusion": relative_signed_jump["conclusion"],
                "gate": relative_signed_jump["stage_gate_status"], "strategy_conversion": "PROHIBITED_AFTER_GATE_FAIL",
            },
            {
                "id": "RESEARCH_TETHER_POSITIVE_BNS_JUMP_BTC_NEXT_DAY_V1",
                "kind": "PREDICTIVE", "conclusion": tether_jump["conclusion"],
                "gate": {"development": tether_jump["stage_summaries"]["development"]["gate"]},
                "strategy_conversion": "PROHIBITED_AFTER_GATE_FAIL",
            },
            {
                "id": "RESEARCH_BTC_SP500_DCC_CHANGE_NEXT_INTERVAL_V1",
                "kind": "PREDICTIVE", "conclusion": btc_sp500_correlation["conclusion"],
                "gate": {"development": btc_sp500_correlation["stages"]["development"]["status"]},
                "strategy_conversion": "PROHIBITED_AFTER_GATE_FAIL",
            },
            {
                "id": "RESEARCH_CSSD_MOM20_STATE_NEXT_WEEK_V1",
                "kind": "PREDICTIVE", "conclusion": dispersion["question_result"],
                "gate": {"development": dispersion_gate["status"]},
                "controlled_dispersion_slope": dispersion["regressions"]["controlled"]["coefficients"]["log_dispersion_ratio"],
                "gated_proxy_mean": dispersion["economic_proxy"]["gated_low_dispersion_high_cash_after_cost_hurdle"]["mean"],
                "strategy_conversion": "PROHIBITED_AFTER_GATE_FAIL",
            },
            {
                "id": "RESEARCH_RV15M28_HIGH_NEXT_WEEK_V1",
                "kind": "PREDICTIVE", "conclusion": intraday_rv["conclusion"],
                "gate": {"development": intraday_rv_gate["status"]},
                "development_spread": read_json(ROOT / "research/studies/predictive/2026/intraday-realized-variance-weekly-return-predictability/development.json")["main"]["high_minus_low"]["mean"],
                "strategy_conversion": intraday_rv["strategy_conversion"],
            },
            {
                "id": "RESEARCH_PPC_FORWARD_GATE_POWER_26W_V1",
                "kind": "COMPARATIVE_OR_MECHANISM",
                "conclusion": ppc_power["conclusion"],
                "true_50bp_joint_power_at_26_eligible_weeks": ppc_power["primary_26_weeks"]["joint_power"],
                "null_joint_false_positive": ppc_power["primary_26_weeks"]["null_joint_false_positive"],
                "strategy_conversion": "NOT_APPLICABLE; evidence-horizon calibration only",
            },
        ],
        "basic_data_coverage": [
            {
                "family": "trend, momentum and path shape",
                "status": "DIRECT_NEGATIVE_OR_INSUFFICIENT_PLUS_ONE_FORWARD_INCUBATION",
                "examples": ["raw/risk-adjusted/category momentum", "CTREND", "PPC", "residual momentum", "dispersion-gated momentum"],
            },
            {
                "family": "short/intermediate reversal and price extremes",
                "status": "DIRECT_NEGATIVE_OR_INSUFFICIENT",
                "examples": ["2h extreme reversal", "weekly losers", "MAX", "52-week/high-distance"],
            },
            {
                "family": "volatility and downside risk",
                "status": "DIRECT_NEGATIVE_OR_INSUFFICIENT",
                "examples": ["volatility target", "low/high volatility", "downside beta", "15m realized total variance"],
            },
            {
                "family": "volume, liquidity and kline order-flow proxy",
                "status": "DIRECT_NEGATIVE_OR_INSUFFICIENT",
                "examples": [
                    "relative volume reversal", "Amihud", "OHLC-estimated bid-ask spread",
                    "1m taker imbalance",
                ],
            },
            {
                "family": "intraday signed variation and return asymmetry",
                "status": "DIRECT_NEGATIVE",
                "examples": ["15m relative signed jump", "30m/1h sampling diagnostics"],
            },
            {
                "family": "perpetual premium and funding-conditioned single leg",
                "status": "DIRECT_NEGATIVE; MULTI_LEG_CARRY_IS_SEPARATE_LEGACY_EVIDENCE",
                "examples": ["discount/premium", "premium momentum", "funding carry"],
            },
            {
                "family": "calendar, BTC relationship and external uncertainty",
                "status": "DIRECT_NEGATIVE_OR_INSUFFICIENT",
                "examples": ["turn of month", "BTC lead-lag/residual reversal", "VIX beta", "BTC-SP500 DCC change"],
            },
            {
                "family": "stablecoin price jump spillover to BTC",
                "status": "DIRECT_INSUFFICIENT; LATER_STAGES_SEALED",
                "examples": ["Bitfinex USDT/USD positive BNS jump", "fixed 0.003% USDT-return diagnostic"],
            },
        ],
        "feasibility_screens": [
            {
                "candidate": "PAXGUSDT perpetual monthly trend",
                "decision": "REJECT_BEFORE_STUDY",
                "official_onboard_time_ms": int(paxg["onboardDate"]),
                "official_onboard_time_utc": "2025-03-27T10:30:00+00:00",
                "reason": "insufficient history for sequential development/evaluation/confirmation; related PAXG spot trend already failed development",
                "exchange_snapshot_sha256": exchange_item["sha256"],
            },
            {
                "candidate": "same-weekday cross-sectional seasonality",
                "decision": "DEFER_LOW_DECISION_VALUE",
                "reason": "published daily cadence conflicts with semi-automatic maintenance; later calendar evidence is weak/adaptive",
            },
            {
                "candidate": "medium-horizon taker-flow variants",
                "decision": "REJECT_ADJACENT_SEARCH",
                "reason": "quarter-hour 1m proxy family already rejected; changing aggregation after results is not independent evidence",
            },
            {
                "candidate": "CME weekend-gap convergence",
                "decision": "REJECT_STRUCTURAL_BREAK",
                "reason": "CME cryptocurrency futures moved to near-24/7 trading on 2026-05-29, ending the historical weekend-closure mechanism",
            },
            {
                "candidate": "cross-venue price-discovery lead-lag",
                "decision": "REJECT_SCOPE_MISMATCH",
                "reason": "published information leadership is concentrated at tick/sub-second/seconds horizons and requires order-book data plus automated execution",
            },
            {
                "candidate": "fixed time-of-day or weekday directional seasonality",
                "decision": "REJECT_WEAK_NONPERSISTENT_PRIMARY_EVIDENCE",
                "reason": "multi-exchange and 2024 revisit studies find no persistent or robust return seasonality; turn-of-candle variants are adjacent to the already rejected quarter-hour family",
            },
            {
                "candidate": "scheduled FOMC volatility window",
                "decision": "DEFER_NON_DIRECTIONAL_AND_MULTI_LEG",
                "reason": "current primary evidence supports predictable volatility/volume expansion rather than return direction; monetization would require a separately authorized options or multi-leg volatility scope",
            },
            {
                "candidate": "broad-spot bid-ask-spread factor transferred to one mature perpetual leg",
                "decision": "REJECT_AFTER_PREDICTIVE_GATE_FAIL",
                "reason": "the public diversified factor benchmark was approximately corroborated, but the fixed mature-perpetual development stage failed rank, uncertainty, split-stability, correction-form and concentration gates; later stages and neighboring estimator variants remain sealed",
            },
            {
                "candidate": "cross-sectional dispersion gate for weekly momentum",
                "decision": "REJECT_AFTER_PREDICTIVE_GATE_FAIL",
                "reason": "the recent preprint mechanism was tested without daily multi-asset rebalancing; the controlled slope was insignificant, the gated proxy was negative and did not beat unconditional momentum, so smoothing/threshold/window variants remain sealed",
            },
            {
                "candidate": "15m one-month realized variance high-short",
                "decision": "REJECT_AFTER_PREDICTIVE_GATE_FAIL",
                "reason": "rank IC was negative but the high-minus-low uncertainty crossed zero, the controlled RV coefficient turned positive, the one-leg short proxy lost after cost/hurdle and underperformed the daily-volatility baseline; jump decomposition and small-coin rescue searches remain sealed",
            },
            {
                "candidate": "aggregate stablecoin-supply growth to BTC direction",
                "decision": "REJECT_WEAK_IDENTIFICATION_AND_NEGATIVE_PRIMARY_EVIDENCE",
                "reason": "primary local-projection evidence finds no systematic BTC/ETH price response to aggregate USDT issuance after feedback controls and warns that aggregate supply misses wallet-level flows; supply is endogenous to demand, while the separate Tether-price-jump transfer already failed",
            },
            {
                "candidate": "broad cross-sectional machine-learning forecast",
                "decision": "REJECT_SCOPE_AND_NO_NEW_BASIC_SIGNAL",
                "reason": "peer-reviewed evidence says simple models and price/past-alpha/illiquidity/momentum drive most predictability, while gains concentrate in small illiquid volatile hard-to-trade coins and require broad multi-asset turnover; those signal families are already tested and the implementation conflicts with mature one-leg semi-automatic scope",
            },
            {
                "candidate": "exact formal Donchian/ATR replay with a slow-trend activation policy",
                "decision": "REJECT_UNIDENTIFIED_ACTIVATION_AND_ADJACENT_TREND_SEARCH",
                "reason": "the formal strategy is user-activated and requires direction before observing its 5-hour Donchian/1-minute confirmation window, but no historical activation schedule exists; inventing Monday activation or a slow-trend direction would define a new scheduler and trend rule rather than replay product history. Existing Halpha slow-trend families already failed independent evaluation or confirmation, while peer-reviewed technical-rule evidence reports BTC out-of-sample failure and strong parameter, cost and bubble-regime sensitivity. A costly 1m/15m replay therefore has low incremental decision value unless a separately preregistered activation mechanism is first supported.",
            },
            {
                "candidate": "rolling entropy or adaptive-efficiency gate for momentum/reversal",
                "decision": "REJECT_DIAGNOSTIC_WITHOUT_DIRECTIONAL_MAPPING",
                "reason": "rolling martingale-difference and entropy evidence establishes time-varying predictability, not which low-frequency one-leg direction to take. Peer-reviewed crypto studies find most mature-coin daily and intraday windows unpredictable most of the time and point any remaining inefficiency toward higher frequencies. Choosing momentum versus reversal after seeing the local sign would add an unvalidated meta-rule and reopen two already-rejected families.",
            },
        ],
        "closest_forward_incubation_only": [
            "price-path-continuity-weekly-winner-long",
            "ctrend-weekly-top-quintile-one-shot-long",
            "high-volatility-monthly-one-shot-short",
        ],
        "next_decision": "Accumulate the frozen PPC forward dates without peeking, but treat 26 eligible weeks as the first checkpoint rather than a complete-decision horizon: exact nested calibration gives only 5.92% joint power for a true 50 bp weekly net edge. Residual momentum, intraday RSJ, Tether-jump spillover, BTC-SP500 correlation learning, OHLC-estimated spread, dispersion-gated momentum and 15m realized variance all failed frozen development gates. The realized-variance test preserved a negative rank IC but lost its sign after controls and produced a negative one-leg short proxy versus a simpler daily-volatility baseline; do not rescue it with jump decomposition, small-coin filtering or new windows. The recent dispersion mechanism likewise produced a negative gated proxy and no significant controlled increment. Aggregate stablecoin issuance has weak causal identification and direct primary counterevidence; broad ML mostly recombines already-tested basic signals and extracts gains from small hard-to-trade coins. An exact formal-strategy replay is not identified without inventing a new activation policy, and entropy/efficiency measures do not supply a low-frequency trade direction. Stop opening adjacent basic-data historical questions. Resume only on genuinely new primary mechanism/data or changed product scope.",
        "product_effects": "NONE",
        "evidence_identities": identities,
        "study_py_sha256": sha256(Path(__file__)),
    }
    write_json(HERE / "frontier.json", frontier)
    output = read_json(HERE / "frontier.json")
    validation = {
        "status": "PASS",
        "frontier_content_digest_valid": output["content_digest"] == canonical({key: value for key, value in output.items() if key != "content_digest"}),
        "evidence_files_checked": len(identities),
        "public_exchange_snapshot_checked": True,
        "current_core_qualification_ready": output["counts"]["current_core_qualification_ready"],
    }
    if not validation["frontier_content_digest_valid"]:
        raise RuntimeError("frontier digest invalid")
    write_json(HERE / "validation.json", validation)
    print(json.dumps({"conclusion": output["conclusion"], "ready": 0, "evidence": len(identities), "validation": "PASS"}))


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Audit the basic-data semi-automatic candidate frontier")
    sub = root.add_subparsers(dest="command", required=True)
    sub.add_parser("audit").set_defaults(func=command_audit)
    return root


if __name__ == "__main__":
    args = parser().parse_args(); args.func(args)
