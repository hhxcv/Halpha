"""Fixed venue transfer of the supported TRX/PAXG 25/25 monthly spot allocation."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
import pandas as pd
import vectorbt as vbt


STUDY_DIR = Path(__file__).resolve().parent
PAIR_PATH = STUDY_DIR.parent / "btc-eth-perp-relative-momentum" / "study.py"
SPOT_RESULTS_PATH = (
    STUDY_DIR.parent.parent.parent
    / "legacy"
    / "2026"
    / "trx-paxg-balanced-spot"
    / "results.json"
)
PERIOD = ("2025-04-01T00:00:00Z", "2026-07-01T00:00:00Z")
SYMBOLS = ("TRXUSDT", "PAXGUSDT")
LEG_WEIGHT = 0.25
MAXIMUM_GROSS = 0.50
ANNUAL_CAPITAL_HURDLE = 0.04
SCENARIOS = {
    "favorable": {"fee": 0.0004, "slippage": 0.0006},
    "base": {"fee": 0.0004, "slippage": 0.0026},
    "stress": {"fee": 0.0004, "slippage": 0.0056},
}


def _load_pair_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "halpha_trx_paxg_pair_base", PAIR_PATH
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("PAIR_STUDY_IMPORT_UNAVAILABLE")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


PAIR = _load_pair_module()
BASE = PAIR.BASE


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _utc_ms(value: str) -> int:
    return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1000)


def _verify_contract_snapshot(
    cache_root: Path, manifest_path: Path, symbol: str
) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    snapshot = manifest["exchange_info_snapshot"]
    path = cache_root / snapshot["cache_relative_path"]
    if _sha256(path) != snapshot["sha256"]:
        raise ValueError(f"EXCHANGE_INFO_SHA256_MISMATCH:{symbol}")
    record = json.loads(path.read_text(encoding="utf-8"))
    if (
        record.get("symbol") != symbol
        or record.get("status") != "TRADING"
        or record.get("contractType") != "PERPETUAL"
    ):
        raise ValueError(f"CONTRACT_SNAPSHOT_INVALID:{symbol}")
    return {
        "symbol": symbol,
        "status": record["status"],
        "contract_type": record["contractType"],
        "onboard_date": int(record["onboardDate"]),
        "sha256": snapshot["sha256"],
    }


def _slice_market(market: Any, indices: np.ndarray) -> Any:
    return BASE.MarketData(
        open_time=market.open_time[indices],
        open=market.open[indices],
        high=market.high[indices],
        low=market.low[indices],
        close=market.close[indices],
        funding_boundary_value=market.funding_boundary_value[indices],
        funding_intraday_value=market.funding_intraday_value[indices],
        manifest_identity=market.manifest_identity,
        quality=market.quality,
    )


def _load_pair(args: argparse.Namespace) -> tuple[Any, Any, dict[str, Any]]:
    trx_root = Path(args.trx_cache_root).resolve()
    paxg_root = Path(args.paxg_cache_root).resolve()
    trx_manifest = Path(args.trx_manifest).resolve()
    paxg_manifest = Path(args.paxg_manifest).resolve()
    contracts = {
        "TRXUSDT": _verify_contract_snapshot(trx_root, trx_manifest, "TRXUSDT"),
        "PAXGUSDT": _verify_contract_snapshot(paxg_root, paxg_manifest, "PAXGUSDT"),
    }
    trx = BASE._load_market_data(trx_root, trx_manifest)
    paxg = BASE._load_market_data(paxg_root, paxg_manifest)
    common, trx_indices, paxg_indices = np.intersect1d(
        trx.open_time, paxg.open_time, assume_unique=True, return_indices=True
    )
    if len(common) < 2 or np.any(np.diff(common) != 86_400_000):
        raise ValueError("TRX_PAXG_COMMON_TIMELINE_NOT_CONTINUOUS")
    return _slice_market(trx, trx_indices), _slice_market(paxg, paxg_indices), contracts


def _simulate(
    trx: Any,
    paxg: Any,
    target_weights: tuple[float, float],
    *,
    fee_rate: float,
    slippage_rate: float,
    include_funding: bool,
) -> tuple[dict[str, Any], np.ndarray, pd.DatetimeIndex]:
    start_ms, end_ms = map(_utc_ms, PERIOD)
    start = int(np.searchsorted(trx.open_time, start_ms, side="left"))
    end = int(np.searchsorted(trx.open_time, end_ms, side="left"))
    if start < 1 or end <= start:
        raise ValueError("PERIOD_OUTSIDE_DATA")
    equity = 1.0
    quantities = [0.0, 0.0]
    prior_close = [float(trx.close[start - 1]), float(paxg.close[start - 1])]
    returns: list[float] = []
    dates: list[pd.Timestamp] = []
    turnover = trade_events = active_days = 0
    maximum_gross = maximum_absolute_net = 0.0
    price_pnl = {symbol: 0.0 for symbol in SYMBOLS}
    funding_pnl = {symbol: 0.0 for symbol in SYMBOLS}
    fee_cost = slippage_cost = 0.0
    total_cost = fee_rate + slippage_rate
    markets = (trx, paxg)
    for index in range(start, end):
        initial = equity
        date = pd.Timestamp(int(trx.open_time[index]), unit="ms", tz="UTC")
        opens = [float(market.open[index]) for market in markets]
        closes = [float(market.close[index]) for market in markets]
        for leg, (market, symbol) in enumerate(zip(markets, SYMBOLS, strict=True)):
            gap = quantities[leg] * (opens[leg] - prior_close[leg])
            funding = (
                -quantities[leg] * float(market.funding_boundary_value[index])
                if include_funding
                else 0.0
            )
            equity += gap + funding
            price_pnl[symbol] += gap
            funding_pnl[symbol] += funding
        if date.day == 1:
            current = tuple(quantities[leg] * opens[leg] for leg in range(2))
            desired, cost = PAIR._targets_after_cost(
                equity, current, target_weights, (True, True), total_cost
            )
            changes = [
                abs(after - before)
                for after, before in zip(desired, current, strict=True)
            ]
            turnover += sum(changes) / equity
            trade_events += sum(change > 1e-12 for change in changes)
            if total_cost > 0:
                fee_cost += cost * fee_rate / total_cost
                slippage_cost += cost * slippage_rate / total_cost
            equity -= cost
            quantities = [desired[leg] / opens[leg] for leg in range(2)]
        for leg, (market, symbol) in enumerate(zip(markets, SYMBOLS, strict=True)):
            price = quantities[leg] * (closes[leg] - opens[leg])
            funding = (
                -quantities[leg] * float(market.funding_intraday_value[index])
                if include_funding
                else 0.0
            )
            equity += price + funding
            price_pnl[symbol] += price
            funding_pnl[symbol] += funding
        if equity <= 0:
            raise ValueError("NON_POSITIVE_EQUITY")
        notionals = [quantities[leg] * closes[leg] / equity for leg in range(2)]
        maximum_gross = max(maximum_gross, sum(abs(value) for value in notionals))
        maximum_absolute_net = max(maximum_absolute_net, abs(sum(notionals)))
        if any(quantity != 0 for quantity in quantities):
            active_days += 1
        returns.append(equity / initial - 1.0)
        dates.append(date)
        prior_close = closes
    terminal_notional = sum(abs(quantities[leg] * prior_close[leg]) for leg in range(2))
    terminal_cost = terminal_notional * total_cost
    before = equity
    equity -= terminal_cost
    turnover += terminal_notional / before
    trade_events += sum(quantity != 0 for quantity in quantities)
    if total_cost > 0:
        fee_cost += terminal_cost * fee_rate / total_cost
        slippage_cost += terminal_cost * slippage_rate / total_cost
    returns[-1] = (1.0 + returns[-1]) * (equity / before) - 1.0
    date_index = pd.DatetimeIndex(dates)
    return (
        PAIR._statistics(
            date_index,
            np.asarray(returns, dtype=np.float64),
            turnover=turnover,
            trade_events=trade_events,
            active_days=active_days,
            maximum_gross=maximum_gross,
            maximum_absolute_net=maximum_absolute_net,
            price_pnl=price_pnl,
            funding_pnl=funding_pnl,
            fee_cost=fee_cost,
            slippage_cost=slippage_cost,
        ),
        np.asarray(returns, dtype=np.float64),
        date_index,
    )


def analyze(args: argparse.Namespace) -> None:
    trx, paxg, contracts = _load_pair(args)
    candidate: dict[str, Any] = {}
    benchmarks: dict[str, dict[str, Any]] = {
        "price_only_same_contracts": {},
        "trx_half_long": {},
        "paxg_half_long": {},
    }
    base_returns: np.ndarray | None = None
    base_dates: pd.DatetimeIndex | None = None
    for scenario, costs in SCENARIOS.items():
        candidate[scenario], returns, dates = _simulate(
            trx,
            paxg,
            (LEG_WEIGHT, LEG_WEIGHT),
            fee_rate=costs["fee"],
            slippage_rate=costs["slippage"],
            include_funding=True,
        )
        if scenario == "base":
            base_returns, base_dates = returns, dates
        benchmarks["price_only_same_contracts"][scenario], _, _ = _simulate(
            trx,
            paxg,
            (LEG_WEIGHT, LEG_WEIGHT),
            fee_rate=costs["fee"],
            slippage_rate=costs["slippage"],
            include_funding=False,
        )
        benchmarks["trx_half_long"][scenario], _, _ = _simulate(
            trx,
            paxg,
            (MAXIMUM_GROSS, 0.0),
            fee_rate=costs["fee"],
            slippage_rate=costs["slippage"],
            include_funding=True,
        )
        benchmarks["paxg_half_long"][scenario], _, _ = _simulate(
            trx,
            paxg,
            (0.0, MAXIMUM_GROSS),
            fee_rate=costs["fee"],
            slippage_rate=costs["slippage"],
            include_funding=True,
        )
    if base_returns is None or base_dates is None:
        raise AssertionError("BASE_RETURNS_MISSING")
    spot_results = json.loads(SPOT_RESULTS_PATH.read_text(encoding="utf-8"))
    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "phase": "venue_transfer_confirmation",
        "period": list(PERIOD),
        "framework_versions": {
            "vectorbt": vbt.__version__,
            "pandas": pd.__version__,
            "numpy": np.__version__,
        },
        "method_identity": {
            "study_sha256": _sha256(Path(__file__).resolve()),
            "pair_base_sha256": _sha256(PAIR_PATH),
            "spot_results_sha256": _sha256(SPOT_RESULTS_PATH),
            "spot_conclusion": spot_results["conclusion"],
            "trx_data_identity": trx.manifest_identity,
            "paxg_data_identity": paxg.manifest_identity,
        },
        "contract_snapshots": contracts,
        "data_quality": {
            "TRXUSDT": trx.quality,
            "PAXGUSDT": paxg.quality,
            "aligned_bars": int(len(trx.open_time)),
            "aligned_first_open_time": datetime.fromtimestamp(
                trx.open_time[0] / 1000, tz=UTC
            ).isoformat(),
            "aligned_last_open_time": datetime.fromtimestamp(
                trx.open_time[-1] / 1000, tz=UTC
            ).isoformat(),
        },
        "rules": {
            "symbols": list(SYMBOLS),
            "target_weights": {"TRXUSDT": LEG_WEIGHT, "PAXGUSDT": LEG_WEIGHT},
            "maximum_gross": MAXIMUM_GROSS,
            "rebalance": "first UTC daily open monthly",
            "annual_capital_hurdle": ANNUAL_CAPITAL_HURDLE,
        },
        "costs_per_unit_turnover": SCENARIOS,
        "candidate": {
            "candidate_id": "TRX_PAXG_USDM_MONTHLY_25PCT_EACH",
            "scenarios": candidate,
        },
        "benchmarks": benchmarks,
        "product_effects": "NONE",
    }
    output = Path(args.output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    (output / "transfer.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    rows: list[dict[str, Any]] = []
    for scenario, metrics in candidate.items():
        row: dict[str, Any] = {
            "candidate_id": "TRX_PAXG_USDM_MONTHLY_25PCT_EACH",
            "scenario": scenario,
        }
        for key, value in metrics.items():
            if key == "annual_returns":
                for year, annual_return in value.items():
                    row[f"return_{year}"] = annual_return
            elif not isinstance(value, (dict, list)):
                row[key] = value
        rows.append(row)
    pd.DataFrame(rows).to_csv(output / "transfer.csv", index=False)
    pd.DataFrame(
        {"TRX_PAXG_USDM_MONTHLY_25PCT_EACH": base_returns}, index=base_dates
    ).to_csv(output / "transfer_daily_returns.csv", index_label="date")
    print(
        json.dumps(
            {"phase": "venue_transfer_confirmation", "candidate": candidate["base"]}
        )
    )


def _hurdle(total_return: float, days: int) -> float:
    return (1.0 + total_return) / (
        (1.0 + ANNUAL_CAPITAL_HURDLE) ** (days / 365.25)
    ) - 1.0


def select_transfer(args: argparse.Namespace) -> None:
    source = Path(args.input)
    payload = json.loads(source.read_text(encoding="utf-8"))
    candidate = payload["candidate"]["scenarios"]
    base, stress = candidate["base"], candidate["stress"]
    trx = payload["benchmarks"]["trx_half_long"]["base"]
    paxg = payload["benchmarks"]["paxg_half_long"]["base"]
    price_pnl = sum(base["price_pnl_on_initial_equity"].values())
    funding_pnl = sum(base["funding_pnl_on_initial_equity"].values())
    funding_drag_fraction = (
        max(0.0, -funding_pnl) / price_pnl if price_pnl > 0 else None
    )
    checks = {
        "spot_support_inherited": payload["method_identity"]["spot_conclusion"]
        == "SUPPORTS_WITHIN_SCOPE",
        "contracts_were_trading_perpetual": all(
            item["status"] == "TRADING" and item["contract_type"] == "PERPETUAL"
            for item in payload["contract_snapshots"].values()
        ),
        "base_total_positive": base["total_return"] > 0,
        "stress_total_positive": stress["total_return"] > 0,
        "stress_after_4pct_hurdle_positive": _hurdle(
            stress["total_return"], stress["days"]
        )
        > 0,
        "both_calendar_segments_stress_positive": all(
            stress["annual_returns"].get(year, -1.0) > 0 for year in ("2025", "2026")
        ),
        "base_sharpe_at_least_0p75": base["sharpe"] >= 0.75,
        "base_calmar_at_least_1": base["calmar"] >= 1.0,
        "drawdown_above_minus_10pct": base["max_drawdown"] > -0.10,
        "drawdown_shallower_than_both_single_legs": base["max_drawdown"]
        > max(trx["max_drawdown"], paxg["max_drawdown"]),
        "calmar_exceeds_both_single_legs": base["calmar"]
        > max(trx["calmar"], paxg["calmar"]),
        "funding_drag_at_most_half_price_pnl": funding_drag_fraction is not None
        and funding_drag_fraction <= 0.50,
        "active_days_at_least_450": base["active_days"] >= 450,
        "turnover_at_most_2p5": base["turnover"] <= 2.5,
    }
    failed = [name for name, passed in checks.items() if not passed]
    result = {
        "schema_version": 1,
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "phase": "venue_transfer_gate",
        "source_sha256": _sha256(source),
        "candidate_id": payload["candidate"]["candidate_id"],
        "stress_return_after_4pct_annual_hurdle": _hurdle(
            stress["total_return"], stress["days"]
        ),
        "base_price_pnl_on_initial_equity": price_pnl,
        "base_funding_pnl_on_initial_equity": funding_pnl,
        "base_funding_drag_fraction_of_price_pnl": funding_drag_fraction,
        "checks": checks,
        "failed_checks": failed,
        "research_supports_demo_candidate": not failed,
        "conclusion": "SUPPORTS_VENUE_TRANSFER" if not failed else "DOES_NOT_SUPPORT",
    }
    Path(args.output).write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(required=True)
    analyze_parser = commands.add_parser("analyze")
    analyze_parser.add_argument("--trx-cache-root", required=True)
    analyze_parser.add_argument("--trx-manifest", required=True)
    analyze_parser.add_argument("--paxg-cache-root", required=True)
    analyze_parser.add_argument("--paxg-manifest", required=True)
    analyze_parser.add_argument("--output-dir", required=True)
    analyze_parser.set_defaults(func=analyze)
    select_parser = commands.add_parser("select-transfer")
    select_parser.add_argument("--input", required=True)
    select_parser.add_argument("--output", required=True)
    select_parser.set_defaults(func=select_transfer)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
