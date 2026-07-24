"""Independent, no-lookahead replication of published BTC MVRV Z-score timing."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import vectorbt as vbt


ENTRY_THRESHOLD = -0.2
EXIT_THRESHOLDS = (5.0, 6.0, 7.0)
PHASES = {
    "development": ("2013-12-07", "2022-01-01"),
    "confirmation": ("2022-01-01", "2026-07-01"),
}
CYCLES = {
    "cycle_2015_2017": {
        "phase": "development",
        "bottom_window": ("2014-12-01", "2015-03-01"),
        "peak_window": ("2017-11-01", "2018-02-01"),
    },
    "cycle_2018_2021": {
        "phase": "development",
        "bottom_window": ("2018-11-01", "2019-03-01"),
        "peak_window": ("2021-10-01", "2022-01-01"),
    },
    "cycle_2022_2025": {
        "phase": "confirmation",
        "bottom_window": ("2022-10-01", "2023-02-01"),
        "peak_window": ("2025-09-01", "2025-12-01"),
    },
}
COSTS = {"base": 0.0025, "stress": 0.0050}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load(cache_root: Path, manifest_path: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw_path = cache_root / manifest["cache_relative_path"]
    if _sha256(raw_path) != manifest["raw_sha256"]:
        raise ValueError("RAW_SHA256_MISMATCH")
    rows = json.loads(raw_path.read_text(encoding="utf-8"))["data"]
    normalized = [
        {
            "time": row["time"],
            "PriceUSD": row["PriceUSD"],
            "CapMVRVCur": row["CapMVRVCur"],
            "CapMrktCurUSD": row["CapMrktCurUSD"],
        }
        for row in rows
    ]
    identity = hashlib.sha256(
        json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    if identity != manifest["content_identity"]:
        raise ValueError("CONTENT_IDENTITY_MISMATCH")
    frame = pd.DataFrame(normalized)
    frame["time"] = pd.to_datetime(frame["time"], utc=True)
    frame["price"] = pd.to_numeric(frame["PriceUSD"], errors="raise")
    frame["mvrv"] = pd.to_numeric(frame["CapMVRVCur"], errors="raise")
    frame["market_cap"] = pd.to_numeric(frame["CapMrktCurUSD"], errors="raise")
    frame = frame[["time", "price", "mvrv", "market_cap"]].sort_values("time")
    frame = frame.set_index("time")
    if frame.index.duplicated().any():
        raise ValueError("DUPLICATE_DATES")
    if not (frame.index.to_series().diff().dropna() == pd.Timedelta(days=1)).all():
        raise ValueError("NON_CONTINUOUS_DAILY")
    if not np.isfinite(frame.to_numpy()).all() or not (frame > 0).all().all():
        raise ValueError("INVALID_NUMERIC_DATA")
    realized_cap = frame["market_cap"] / frame["mvrv"]
    expanding_std = frame["market_cap"].expanding(min_periods=365).std(ddof=1)
    frame["mvrv_z_expanding"] = (frame["market_cap"] - realized_cap) / expanding_std
    full_std = float(frame["market_cap"].std(ddof=1))
    frame["mvrv_z_full_sample_diagnostic"] = (
        frame["market_cap"] - realized_cap
    ) / full_std
    return frame, manifest


def _events(z_score: pd.Series, exit_threshold: float) -> tuple[pd.Series, pd.Series]:
    raw_entry = (z_score < ENTRY_THRESHOLD) & (z_score.shift(1) >= ENTRY_THRESHOLD)
    raw_exit = (z_score >= exit_threshold) & (z_score.shift(1) < exit_threshold)
    candidate_entries = raw_entry.shift(1, fill_value=False).astype(bool)
    candidate_exits = raw_exit.shift(1, fill_value=False).astype(bool)
    entries = pd.Series(False, index=z_score.index)
    exits = pd.Series(False, index=z_score.index)
    invested = False
    for date, wants_entry, wants_exit in zip(
        z_score.index, candidate_entries, candidate_exits, strict=True
    ):
        if not invested and wants_entry:
            entries.loc[date] = True
            invested = True
        elif invested and wants_exit:
            exits.loc[date] = True
            invested = False
    return entries, exits


def _portfolio(
    price: pd.Series, entries: pd.Series, exits: pd.Series, cost: float
) -> Any:
    return vbt.Portfolio.from_signals(
        price,
        entries=entries,
        exits=exits,
        fees=cost,
        init_cash=1.0,
        freq="1D",
    )


def _buy_hold(price: pd.Series, cost: float) -> Any:
    entries = pd.Series(False, index=price.index)
    entries.iloc[0] = True
    exits = pd.Series(False, index=price.index)
    return _portfolio(price, entries, exits, cost)


def _metrics(returns: pd.Series) -> dict[str, Any]:
    if returns.empty:
        raise ValueError("EMPTY_RETURNS")
    total = float((1.0 + returns).prod() - 1.0)
    years = len(returns) / 365.25
    cagr = float((1.0 + total) ** (1.0 / years) - 1.0) if total > -1.0 else -1.0
    volatility = float(returns.std(ddof=1) * np.sqrt(365.0))
    sharpe = float(returns.mean() / returns.std(ddof=1) * np.sqrt(365.0))
    wealth = (1.0 + returns).cumprod()
    drawdown = wealth / wealth.cummax() - 1.0
    annual = (1.0 + returns).groupby(returns.index.year).prod() - 1.0
    return {
        "days": len(returns),
        "total_return": total,
        "cagr": cagr,
        "annualized_volatility": volatility,
        "sharpe": sharpe,
        "max_drawdown": float(drawdown.min()),
        "annual_returns": {str(int(year)): float(value) for year, value in annual.items()},
    }


def _state(entries: pd.Series, exits: pd.Series) -> pd.Series:
    values = np.zeros(len(entries), dtype=np.float64)
    current = 0.0
    for index, (entry, exit_) in enumerate(zip(entries, exits, strict=True)):
        if entry:
            current = 1.0
        elif exit_:
            current = 0.0
        values[index] = current
    return pd.Series(values, index=entries.index)


def _endpoints(frame: pd.DataFrame, definition: dict[str, Any]) -> dict[str, Any]:
    bottom_start, bottom_end = map(pd.Timestamp, definition["bottom_window"])
    peak_start, peak_end = map(pd.Timestamp, definition["peak_window"])
    bottom_start = bottom_start.tz_localize("UTC")
    bottom_end = bottom_end.tz_localize("UTC")
    peak_start = peak_start.tz_localize("UTC")
    peak_end = peak_end.tz_localize("UTC")
    bottom = frame.loc[bottom_start:bottom_end - pd.Timedelta(days=1), "price"].idxmin()
    peak = frame.loc[peak_start:peak_end - pd.Timedelta(days=1), "price"].idxmax()
    return {
        "bottom_date": bottom.strftime("%Y-%m-%d"),
        "bottom_price": float(frame.loc[bottom, "price"]),
        "peak_date": peak.strftime("%Y-%m-%d"),
        "peak_price": float(frame.loc[peak, "price"]),
    }


def _nearest_signed_days(events: pd.Series, target: str) -> int | None:
    event_dates = events.index[events]
    if len(event_dates) == 0:
        return None
    target_date = pd.Timestamp(target, tz="UTC")
    differences = pd.Series(
        [(date - target_date).days for date in event_dates], index=event_dates
    )
    nearest_date = differences.abs().idxmin()
    return int(differences.loc[nearest_date])


def _strict_bull_result(
    candidate_returns: pd.Series,
    frame: pd.DataFrame,
    endpoints: dict[str, Any],
    cost: float,
) -> dict[str, float]:
    bottom = pd.Timestamp(endpoints["bottom_date"], tz="UTC")
    peak = pd.Timestamp(endpoints["peak_date"], tz="UTC")
    start = bottom + pd.Timedelta(days=1)
    candidate = candidate_returns[
        (candidate_returns.index > start) & (candidate_returns.index <= peak)
    ]
    if candidate.empty:
        raise ValueError("EMPTY_BULL_SEGMENT")
    action_price = float(frame.loc[start, "price"])
    peak_price = float(frame.loc[peak, "price"])
    buy_hold = (1.0 - cost) * peak_price / action_price - 1.0
    return {
        "candidate_total_return": float((1.0 + candidate).prod() - 1.0),
        "perfect_next_day_buy_hold_return": float(buy_hold),
    }


def _analyze_variant(
    frame: pd.DataFrame,
    phase_start: pd.Timestamp,
    phase_end: pd.Timestamp,
    threshold: float,
    cycle_names: list[str],
) -> tuple[dict[str, Any], dict[str, pd.Series]]:
    entries, exits = _events(frame["mvrv_z_expanding"], threshold)
    state = _state(entries, exits)
    variant: dict[str, Any] = {
        "entry_dates": [date.strftime("%Y-%m-%d") for date in entries.index[entries]],
        "exit_dates": [date.strftime("%Y-%m-%d") for date in exits.index[exits]],
        "position_at_cutoff": float(state.loc[:phase_end - pd.Timedelta(days=1)].iloc[-1]),
        "scenarios": {},
        "cycles": {},
    }
    return_series: dict[str, pd.Series] = {}
    for scenario, cost in COSTS.items():
        portfolio = _portfolio(frame["price"], entries, exits, cost)
        returns = portfolio.returns()
        phase_returns = returns[(returns.index >= phase_start) & (returns.index < phase_end)]
        variant["scenarios"][scenario] = _metrics(phase_returns)
        return_series[scenario] = phase_returns
        for name in cycle_names:
            endpoints = _endpoints(frame, CYCLES[name])
            cycle = variant["cycles"].setdefault(name, {"endpoints": endpoints})
            cycle[scenario] = _strict_bull_result(returns, frame, endpoints, cost)
    for name in cycle_names:
        endpoints = variant["cycles"][name]["endpoints"]
        variant["cycles"][name]["entry_lag_from_bottom_days"] = _nearest_signed_days(
            entries, endpoints["bottom_date"]
        )
        variant["cycles"][name]["exit_lag_from_peak_days"] = _nearest_signed_days(
            exits, endpoints["peak_date"]
        )
    return variant, return_series


def _development_checks(payload: dict[str, Any]) -> dict[str, bool]:
    benchmark = payload["benchmark"]["base"]
    variants = payload["variants"]
    performance_passes = 0
    timing_passes = 0
    for threshold in ("5", "6", "7"):
        variant = variants[threshold]
        base = variant["scenarios"]["base"]
        if (
            base["total_return"] > benchmark["total_return"]
            and base["max_drawdown"] > benchmark["max_drawdown"]
        ):
            performance_passes += 1
        timing_ok = True
        for cycle in ("cycle_2015_2017", "cycle_2018_2021"):
            entry = variant["cycles"][cycle]["entry_lag_from_bottom_days"]
            exit_ = variant["cycles"][cycle]["exit_lag_from_peak_days"]
            timing_ok = timing_ok and entry is not None and abs(entry) <= 180
            timing_ok = timing_ok and exit_ is not None and abs(exit_) <= 180
        if timing_ok:
            timing_passes += 1
    directions = [
        variants[str(threshold)]["scenarios"]["base"]["total_return"]
        > benchmark["total_return"]
        for threshold in (5, 6, 7)
    ]
    return {
        "at_least_two_variants_beat_same_start_buy_hold_and_drawdown": performance_passes
        >= 2,
        "all_variants_enter_both_bottoms_within_180d": all(
            variants[str(threshold)]["cycles"][cycle]["entry_lag_from_bottom_days"]
            is not None
            and abs(
                variants[str(threshold)]["cycles"][cycle][
                    "entry_lag_from_bottom_days"
                ]
            )
            <= 180
            for threshold in (5, 6, 7)
            for cycle in ("cycle_2015_2017", "cycle_2018_2021")
        ),
        "at_least_two_variants_exit_both_peaks_within_180d": timing_passes >= 2,
        "threshold_direction_consistent": len(set(directions)) == 1,
    }


def analyze(args: argparse.Namespace) -> None:
    if args.phase == "confirmation":
        if not args.authorization:
            raise ValueError("AUTHORIZATION_REQUIRED")
        authorization = json.loads(Path(args.authorization).read_text(encoding="utf-8"))
        if not authorization.get("confirmation_authorized"):
            raise ValueError("CONFIRMATION_NOT_AUTHORIZED")
    manifest_path = Path(args.source_manifest).resolve()
    frame, manifest = _load(Path(args.cache_root).resolve(), manifest_path)
    phase_start = pd.Timestamp(PHASES[args.phase][0], tz="UTC")
    phase_end = pd.Timestamp(PHASES[args.phase][1], tz="UTC")
    if args.phase == "development":
        analysis_frame = frame[frame.index < phase_end].copy()
    else:
        analysis_frame = frame.copy()
    cycle_names = [
        name for name, definition in CYCLES.items() if definition["phase"] == args.phase
    ]
    variants: dict[str, Any] = {}
    base_returns: dict[str, pd.Series] = {}
    for threshold in EXIT_THRESHOLDS:
        result, returns = _analyze_variant(
            analysis_frame, phase_start, phase_end, threshold, cycle_names
        )
        variants[str(int(threshold))] = result
        base_returns[f"MVRV_Z_EXIT_{int(threshold)}"] = returns["base"]
    benchmark: dict[str, Any] = {}
    benchmark_returns: pd.Series | None = None
    for scenario, cost in COSTS.items():
        portfolio = _buy_hold(analysis_frame.loc[phase_start:, "price"], cost)
        returns = portfolio.returns()
        returns = returns[(returns.index >= phase_start) & (returns.index < phase_end)]
        benchmark[scenario] = _metrics(returns)
        if scenario == "base":
            benchmark_returns = returns
    if benchmark_returns is None:
        raise RuntimeError("BENCHMARK_RETURNS_MISSING")
    base_returns["BUY_HOLD_SAME_START"] = benchmark_returns
    valid_z = analysis_frame["mvrv_z_expanding"].dropna()
    payload: dict[str, Any] = {
        "schema_version": 1,
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "phase": args.phase,
        "period": list(PHASES[args.phase]),
        "question": "Does published MVRV Z-score cycle timing survive an independent no-lookahead definition and fair same-start benchmark?",
        "framework_versions": {
            "vectorbt": vbt.__version__,
            "pandas": pd.__version__,
            "numpy": np.__version__,
        },
        "method_identity": {
            "study_sha256": _sha256(Path(__file__).resolve()),
            "source_manifest_sha256": _sha256(manifest_path),
            "source_content_identity": manifest["content_identity"],
        },
        "data_quality": {
            "rows": len(frame),
            "first_time": frame.index[0].isoformat(),
            "last_time": frame.index[-1].isoformat(),
            "continuous_daily": True,
            "valid_expanding_z_observations": len(valid_z),
        },
        "definition": {
            "entry_threshold": ENTRY_THRESHOLD,
            "exit_thresholds": list(EXIT_THRESHOLDS),
            "z_score": "(market cap - market cap / MVRV) / expanding std(market cap), min 365 days",
            "action_time": "next daily PriceUSD observation",
            "costs_per_order": COSTS,
        },
        "benchmark": benchmark,
        "variants": variants,
        "z_diagnostics": {
            "phase_min_expanding": float(valid_z.loc[phase_start:phase_end].min()),
            "phase_max_expanding": float(valid_z.loc[phase_start:phase_end].max()),
            "cutoff_expanding": float(valid_z.iloc[-1]),
            "cutoff_full_sample_lookahead_diagnostic": float(
                analysis_frame["mvrv_z_full_sample_diagnostic"].iloc[-1]
            ),
            "cutoff_mvrv": float(analysis_frame["mvrv"].iloc[-1]),
        },
        "product_effects": "NONE",
    }
    if args.phase == "development":
        payload["development_checks"] = _development_checks(payload)
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / f"{args.phase}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    pd.concat(base_returns, axis=1).to_csv(
        output_dir / f"{args.phase}_daily_returns.csv", index_label="date"
    )
    print(
        json.dumps(
            {
                "phase": args.phase,
                "benchmark": benchmark["base"],
                "variant_base_returns": {
                    key: value["scenarios"]["base"]["total_return"]
                    for key, value in variants.items()
                },
            },
            ensure_ascii=False,
        )
    )


def qualify_development(args: argparse.Namespace) -> None:
    source = Path(args.input).resolve()
    payload = json.loads(source.read_text(encoding="utf-8"))
    if payload.get("phase") != "development":
        raise ValueError("NOT_DEVELOPMENT")
    checks = payload["development_checks"]
    result = {
        "schema_version": 1,
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "source_sha256": _sha256(source),
        "checks": checks,
        "failed_checks": [name for name, value in checks.items() if not value],
        "confirmation_authorized": all(checks.values()),
    }
    Path(args.output).write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False))


def qualify_confirmation(args: argparse.Namespace) -> None:
    source = Path(args.input).resolve()
    payload = json.loads(source.read_text(encoding="utf-8"))
    if payload.get("phase") != "confirmation":
        raise ValueError("NOT_CONFIRMATION")
    benchmark = payload["benchmark"]["base"]
    variants = payload["variants"]
    performance_passes = sum(
        variants[str(threshold)]["scenarios"]["base"]["total_return"]
        > benchmark["total_return"]
        for threshold in (5, 6, 7)
    )
    timing_passes = 0
    strict_bull_beats = 0
    for threshold in (5, 6, 7):
        cycle = variants[str(threshold)]["cycles"]["cycle_2022_2025"]
        entry = cycle["entry_lag_from_bottom_days"]
        exit_ = cycle["exit_lag_from_peak_days"]
        if entry is not None and abs(entry) <= 180 and exit_ is not None and abs(exit_) <= 180:
            timing_passes += 1
        if (
            cycle["base"]["candidate_total_return"]
            > cycle["base"]["perfect_next_day_buy_hold_return"]
        ):
            strict_bull_beats += 1
    checks = {
        "at_least_two_variants_beat_same_start_buy_hold": performance_passes >= 2,
        "at_least_two_variants_time_2022_bottom_and_2025_peak_within_180d": timing_passes
        >= 2,
        "strict_bull_result_reported_without_relabeling": True,
    }
    passed = all(checks.values())
    result = {
        "schema_version": 1,
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "source_sha256": _sha256(source),
        "checks": checks,
        "strict_bull_variants_beating_perfect_buy_hold": strict_bull_beats,
        "passed": passed,
        "conclusion": "SUPPORTS_WITHIN_SCOPE" if passed else "DOES_NOT_SUPPORT",
        "product_effects": "NONE",
    }
    Path(args.output).write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(required=True)
    analyze_parser = subparsers.add_parser("analyze")
    analyze_parser.add_argument("--phase", choices=tuple(PHASES), required=True)
    analyze_parser.add_argument("--cache-root", required=True)
    analyze_parser.add_argument("--source-manifest", required=True)
    analyze_parser.add_argument("--output-dir", required=True)
    analyze_parser.add_argument("--authorization")
    analyze_parser.set_defaults(func=analyze)

    development_parser = subparsers.add_parser("qualify-development")
    development_parser.add_argument("--input", required=True)
    development_parser.add_argument("--output", required=True)
    development_parser.set_defaults(func=qualify_development)

    confirmation_parser = subparsers.add_parser("qualify-confirmation")
    confirmation_parser.add_argument("--input", required=True)
    confirmation_parser.add_argument("--output", required=True)
    confirmation_parser.set_defaults(func=qualify_confirmation)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
