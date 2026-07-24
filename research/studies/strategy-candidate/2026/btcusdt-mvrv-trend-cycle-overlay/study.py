"""Audit a fixed MVRV-bottom and slow-trend-exit BTC cycle overlay."""

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
MACRO_STUDY_PATH = STUDY_DIR.parent / "btcusdt-macro-cycle-trend-overlay" / "study.py"
MVRV_STUDY_PATH = (
    STUDY_DIR.parent.parent.parent
    / "comparative-or-mechanism"
    / "2026"
    / "btc-mvrv-cycle-timing-replication"
    / "study.py"
)
CANDIDATE = "BTC_MVRV_BOTTOM_TREND_EXIT_ENSEMBLE_1P25"
DIAGNOSTICS = (
    "BTC_MVRV_BOTTOM_TREND_EXIT_ENSEMBLE_1P0",
    "BTC_MVRV_BOTTOM_HOLD_1P25",
    "BTC_SMA200_BINARY_1P25",
)
BENCHMARK = "BTC_BUY_HOLD_1P0"
PERIODS = {
    "development": ("2014-01-01T00:00:00Z", "2022-01-01T00:00:00Z"),
    "confirmation": ("2022-01-01T00:00:00Z", "2026-07-01T00:00:00Z"),
    "full": ("2014-01-01T00:00:00Z", "2026-07-01T00:00:00Z"),
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
SCENARIOS = {
    "favorable": {"cost": 0.0010, "annual_financing": 0.00},
    "base": {"cost": 0.0025, "annual_financing": 0.05},
    "stress": {"cost": 0.0050, "annual_financing": 0.10},
}
EXIT_THRESHOLDS = (5.0, 6.0, 7.0)
ENTRY_THRESHOLD = -0.2


def _load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"MODULE_IMPORT_UNAVAILABLE:{name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


MACRO = _load_module("halpha_mvrv_trend_macro_base", MACRO_STUDY_PATH)
MVRV = _load_module("halpha_mvrv_trend_replication_base", MVRV_STUDY_PATH)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_frame(cache_root: Path, manifest_path: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    indexed, manifest = MVRV._load(cache_root, manifest_path)
    frame = indexed.reset_index()
    if frame.columns[0] != "time":
        frame = frame.rename(columns={frame.columns[0]: "time"})
    return frame, manifest


def _cycle_weights(frame: pd.DataFrame) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    z_score = frame["mvrv_z_expanding"]
    price = frame["price"]
    sma200 = price.rolling(200, min_periods=200).mean()
    bottom_cross = (z_score < ENTRY_THRESHOLD) & (z_score.shift(1) >= ENTRY_THRESHOLD)
    sleeve_states: list[np.ndarray] = []
    top_cross_dates: dict[str, list[str]] = {}
    for threshold in EXIT_THRESHOLDS:
        top_cross = (z_score >= threshold) & (z_score.shift(1) < threshold)
        started = False
        armed = False
        state = np.zeros(len(frame), dtype=np.float64)
        for index in range(len(frame)):
            if bool(bottom_cross.iloc[index]):
                started = True
                armed = False
            if started and bool(top_cross.iloc[index]):
                armed = True
            if started and (not armed or bool(price.iloc[index] > sma200.iloc[index])):
                state[index] = 1.0
        sleeve_states.append(state)
        top_cross_dates[str(int(threshold))] = [
            date.strftime("%Y-%m-%d")
            for date in frame.loc[top_cross, "time"]
        ]
    combined = np.mean(np.column_stack(sleeve_states), axis=1)
    bottom_hold = np.zeros(len(frame), dtype=np.float64)
    if bottom_cross.any():
        bottom_hold[int(np.flatnonzero(bottom_cross.to_numpy())[0]) :] = 1.25
    sma_weight = (1.25 * (price > sma200).astype(float)).to_numpy(dtype=np.float64)
    weights = {
        CANDIDATE: 1.25 * combined,
        DIAGNOSTICS[0]: combined,
        DIAGNOSTICS[1]: bottom_hold,
        DIAGNOSTICS[2]: sma_weight,
        BENCHMARK: np.ones(len(frame), dtype=np.float64),
    }
    events = {
        "mvrv_bottom_cross_dates": [
            date.strftime("%Y-%m-%d")
            for date in frame.loc[bottom_cross, "time"]
        ],
        "mvrv_top_cross_dates": top_cross_dates,
        "sma200_valid_from": frame.loc[sma200.notna(), "time"].iloc[0].strftime("%Y-%m-%d"),
    }
    return weights, events


def _run_variants(
    frame: pd.DataFrame,
    manifest_identity: str,
    weights: dict[str, np.ndarray],
    period: tuple[str, str],
) -> tuple[dict[str, Any], dict[str, np.ndarray], pd.DatetimeIndex]:
    results: dict[str, Any] = {}
    base_returns: dict[str, np.ndarray] = {}
    dates: pd.DatetimeIndex | None = None
    for scenario, assumptions in SCENARIOS.items():
        data = MACRO._coin_metrics_market(
            frame, manifest_identity, assumptions["annual_financing"]
        )
        scenario_results: dict[str, Any] = {}
        for name in (CANDIDATE, *DIAGNOSTICS):
            simulation = MACRO._simulate(
                data,
                weights[name],
                period,
                assumptions["cost"],
                0.0,
            )
            scenario_results[name] = simulation.metrics
            if scenario == "base":
                base_returns[name] = simulation.returns
                dates = simulation.dates
        benchmark = MACRO._simulate(
            MACRO._zero_funding(data),
            weights[BENCHMARK],
            period,
            assumptions["cost"],
            0.0,
        )
        scenario_results[BENCHMARK] = benchmark.metrics
        if scenario == "base":
            base_returns[BENCHMARK] = benchmark.returns
            dates = benchmark.dates
        results[scenario] = scenario_results
    if dates is None:
        raise RuntimeError("RETURN_DATES_MISSING")
    return results, base_returns, dates


def _cycle_results(
    frame: pd.DataFrame,
    manifest_identity: str,
    weights: dict[str, np.ndarray],
    names: list[str],
) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for name in names:
        endpoints = MACRO._cycle_endpoints(frame, CYCLES[name])
        period = MACRO._cycle_period(endpoints)
        results, _, _ = _run_variants(frame, manifest_identity, weights, period)
        output[name] = {"endpoints": endpoints, "period": period, "results": results}
    return output


def _nearest_action_lag(event_dates: list[str], target: str) -> int | None:
    if not event_dates:
        return None
    target_date = pd.Timestamp(target, tz="UTC")
    lags = [
        int((pd.Timestamp(date, tz="UTC") + pd.Timedelta(days=1) - target_date).days)
        for date in event_dates
    ]
    return min(lags, key=abs)


def _transition_diagnostics(
    frame: pd.DataFrame,
    candidate_weight: np.ndarray,
    event_dates: list[str],
    endpoints: dict[str, Any],
) -> dict[str, Any]:
    index = pd.DatetimeIndex(frame["time"])
    target = pd.Series(candidate_weight, index=index)
    actual = target.shift(1, fill_value=0.0)
    bottom = pd.Timestamp(endpoints["bottom_date"], tz="UTC")
    peak = pd.Timestamp(endpoints["peak_date"], tz="UTC")
    post_peak = actual[actual.index > peak]
    exits = post_peak[post_peak <= 0.25]
    return {
        "mvrv_bottom_action_lag_days": _nearest_action_lag(event_dates, endpoints["bottom_date"]),
        "actual_weight_at_bottom": float(actual.loc[bottom]),
        "actual_weight_at_peak": float(actual.loc[peak]),
        "first_post_peak_weight_at_most_0p25_lag_days": (
            int((exits.index[0] - peak).days) if not exits.empty else None
        ),
    }


def _bear_result(
    frame: pd.DataFrame,
    manifest_identity: str,
    weights: dict[str, np.ndarray],
    peak_date: str,
    bottom_date: str,
) -> dict[str, Any]:
    start = pd.Timestamp(peak_date, tz="UTC") + pd.Timedelta(days=1)
    end = pd.Timestamp(bottom_date, tz="UTC") + pd.Timedelta(days=1)
    period = (start.isoformat(), end.isoformat())
    results, _, _ = _run_variants(frame, manifest_identity, weights, period)
    return {"period": period, "results": results}


def _dsr(base_returns: dict[str, np.ndarray], dates: pd.DatetimeIndex) -> dict[str, float]:
    names = [CANDIDATE, *DIAGNOSTICS]
    returns = pd.DataFrame({name: base_returns[name] for name in names}, index=dates)
    return {
        str(trials): float(
            returns.vbt.returns.deflated_sharpe_ratio(nb_trials=trials)[CANDIDATE]
        )
        for trials in (4, 30, 60)
    }


def _strictly_dominated(candidate: dict[str, Any], diagnostics: list[dict[str, Any]]) -> bool:
    return any(MACRO._strictly_dominates(item, candidate) for item in diagnostics)


def _development_checks(payload: dict[str, Any]) -> dict[str, bool]:
    period = payload["period_results"]
    cycles = payload["cycles"]
    cycle_wins = []
    for cycle_name in ("cycle_2015_2017", "cycle_2018_2021"):
        result = cycles[cycle_name]["results"]
        cycle_wins.extend(
            result[scenario][CANDIDATE]["total_return"]
            > result[scenario][BENCHMARK]["total_return"]
            for scenario in ("base", "stress")
        )
    base_candidate = period["base"][CANDIDATE]
    base_benchmark = period["base"][BENCHMARK]
    stress_candidate = period["stress"][CANDIDATE]
    stress_benchmark = period["stress"][BENCHMARK]
    transitions = payload["transition_diagnostics"]
    bear = payload["bear_segments"]["peak_2017_to_bottom_2018"]["results"]
    return {
        "both_development_bull_legs_beat_buy_hold_base_and_stress": all(cycle_wins),
        "development_base_beats_buy_hold": base_candidate["total_return"]
        > base_benchmark["total_return"],
        "development_stress_beats_buy_hold": stress_candidate["total_return"]
        > stress_benchmark["total_return"],
        "development_drawdown_shallower_than_buy_hold": base_candidate["max_drawdown"]
        > base_benchmark["max_drawdown"],
        "complete_bear_leg_beats_buy_hold": bear["base"][CANDIDATE]["total_return"]
        > bear["base"][BENCHMARK]["total_return"],
        "both_bottom_actions_within_90d_and_peak_weight_at_least_1x": all(
            abs(transitions[name]["mvrv_bottom_action_lag_days"]) <= 90
            and transitions[name]["actual_weight_at_peak"] >= 1.0
            for name in ("cycle_2015_2017", "cycle_2018_2021")
        ),
        "both_post_peak_exits_within_180d": all(
            transitions[name]["first_post_peak_weight_at_most_0p25_lag_days"]
            is not None
            and transitions[name]["first_post_peak_weight_at_most_0p25_lag_days"] <= 180
            for name in ("cycle_2015_2017", "cycle_2018_2021")
        ),
        "not_strictly_dominated_by_any_diagnostic": not _strictly_dominated(
            base_candidate, [period["base"][name] for name in DIAGNOSTICS]
        ),
        "thirty_trial_dsr_at_least_0p80": payload["selection_bias"][
            "deflated_sharpe_probability"
        ]["30"]
        >= 0.80,
        "bootstrap_probability_beats_buy_hold_at_least_0p80": payload[
            "paired_block_bootstrap"
        ]["probability_candidate_beats_buy_hold"]
        >= 0.80,
    }


def _binance_bridge(
    frame: pd.DataFrame,
    weights: dict[str, np.ndarray],
    cache_root: Path,
    manifest_path: Path,
    endpoints: dict[str, Any],
) -> dict[str, Any]:
    data = MACRO.BASE._load_market_data(cache_root, manifest_path)
    source_index = pd.DatetimeIndex(frame["time"])
    target_index = pd.to_datetime(data.open_time, unit="ms", utc=True)
    aligned: dict[str, np.ndarray] = {}
    for name in (CANDIDATE, BENCHMARK):
        selected = pd.Series(weights[name], index=source_index).reindex(target_index)
        if selected.isna().any():
            raise ValueError(f"BINANCE_SIGNAL_ALIGNMENT_GAP:{name}")
        aligned[name] = selected.to_numpy(dtype=np.float64)
    periods = {
        "cycle_2022_2025": MACRO._cycle_period(endpoints),
        "confirmation_2022_2026": PERIODS["confirmation"],
    }
    output: dict[str, Any] = {}
    for period_name, period in periods.items():
        output[period_name] = {}
        for scenario, assumptions in MACRO.BINANCE_SCENARIOS.items():
            candidate = MACRO._simulate(
                data,
                aligned[CANDIDATE],
                period,
                assumptions["fee"],
                assumptions["slippage"],
            )
            benchmark = MACRO._simulate(
                MACRO._zero_funding(data),
                aligned[BENCHMARK],
                period,
                assumptions["fee"],
                assumptions["slippage"],
            )
            output[period_name][scenario] = {
                "candidate": candidate.metrics,
                "spot_buy_hold_proxy": benchmark.metrics,
            }
    output["data_quality"] = data.quality
    output["data_identity"] = data.manifest_identity
    output["manifest_sha256"] = _sha256(manifest_path)
    return output


def analyze(args: argparse.Namespace) -> None:
    if args.phase == "confirmation":
        if not args.authorization:
            raise ValueError("CONFIRMATION_AUTHORIZATION_REQUIRED")
        authorization = json.loads(Path(args.authorization).read_text(encoding="utf-8"))
        if not authorization.get("confirmation_authorized"):
            raise ValueError("CONFIRMATION_NOT_AUTHORIZED")
    manifest_path = Path(args.source_manifest).resolve()
    frame, manifest = _load_frame(Path(args.cache_root).resolve(), manifest_path)
    weights, events = _cycle_weights(frame)
    period_results, base_returns, dates = _run_variants(
        frame, manifest["content_identity"], weights, PERIODS[args.phase]
    )
    cycle_names = [
        name for name, definition in CYCLES.items() if definition["phase"] == args.phase
    ]
    cycles = _cycle_results(
        frame, manifest["content_identity"], weights, cycle_names
    )
    transitions = {
        name: _transition_diagnostics(
            frame,
            weights[CANDIDATE],
            events["mvrv_bottom_cross_dates"],
            cycles[name]["endpoints"],
        )
        for name in cycle_names
    }
    bear_segments: dict[str, Any] = {}
    if args.phase == "development":
        bear_segments["peak_2017_to_bottom_2018"] = _bear_result(
            frame,
            manifest["content_identity"],
            weights,
            cycles["cycle_2015_2017"]["endpoints"]["peak_date"],
            cycles["cycle_2018_2021"]["endpoints"]["bottom_date"],
        )
    else:
        peak = cycles["cycle_2022_2025"]["endpoints"]["peak_date"]
        start = pd.Timestamp(peak, tz="UTC") + pd.Timedelta(days=1)
        period = (start.isoformat(), PERIODS["confirmation"][1])
        result, _, _ = _run_variants(
            frame, manifest["content_identity"], weights, period
        )
        bear_segments["peak_2025_to_cutoff"] = {"period": period, "results": result}
    payload: dict[str, Any] = {
        "schema_version": 1,
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "phase": args.phase,
        "period": list(PERIODS[args.phase]),
        "candidate_id": CANDIDATE,
        "framework_versions": {
            "vectorbt": vbt.__version__,
            "pandas": pd.__version__,
            "numpy": np.__version__,
        },
        "method_identity": {
            "study_sha256": _sha256(Path(__file__).resolve()),
            "macro_base_sha256": _sha256(MACRO_STUDY_PATH),
            "mvrv_base_sha256": _sha256(MVRV_STUDY_PATH),
            "source_manifest_sha256": _sha256(manifest_path),
            "source_content_identity": manifest["content_identity"],
        },
        "data_quality": {
            "rows": len(frame),
            "first_time": frame["time"].iloc[0].isoformat(),
            "last_time": frame["time"].iloc[-1].isoformat(),
            "continuous_daily": True,
        },
        "rules": {
            "mvrv_entry": "expanding Z crosses below -0.2",
            "top_warning_sleeves": [5.0, 6.0, 7.0],
            "post_warning_trend": "long only while PriceUSD > SMA200",
            "maximum_weight": 1.25,
            "action_time": "next daily observation",
            "rebalance_relative_tolerance": 0.20,
        },
        "events": events,
        "scenarios": SCENARIOS,
        "period_results": period_results,
        "cycles": cycles,
        "transition_diagnostics": transitions,
        "bear_segments": bear_segments,
        "product_effects": "NONE",
    }
    if args.phase == "development":
        payload["selection_bias"] = {
            "deflated_sharpe_probability": _dsr(base_returns, dates),
            "interpretation": "4 is the fixed local comparison; 30 and 60 include prior related BTC rule exposure.",
        }
        payload["paired_block_bootstrap"] = MACRO._bootstrap_excess(
            base_returns[CANDIDATE], base_returns[BENCHMARK]
        )
        payload["development_checks"] = _development_checks(payload)
    else:
        if not args.binance_cache_root or not args.binance_manifest:
            raise ValueError("BINANCE_BRIDGE_INPUTS_REQUIRED")
        payload["binance_bridge"] = _binance_bridge(
            frame,
            weights,
            Path(args.binance_cache_root).resolve(),
            Path(args.binance_manifest).resolve(),
            cycles["cycle_2022_2025"]["endpoints"],
        )
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / f"{args.phase}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    pd.DataFrame(base_returns, index=dates).to_csv(
        output_dir / f"{args.phase}_daily_returns.csv", index_label="date"
    )
    print(
        json.dumps(
            {
                "phase": args.phase,
                "candidate_base": period_results["base"][CANDIDATE],
                "buy_hold_base": period_results["base"][BENCHMARK],
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
    cycle = payload["cycles"]["cycle_2022_2025"]["results"]
    period = payload["period_results"]
    bear = payload["bear_segments"]["peak_2025_to_cutoff"]["results"]
    bridge = payload["binance_bridge"]["cycle_2022_2025"]
    checks = {
        "confirmation_cycle_beats_buy_hold_base": cycle["base"][CANDIDATE][
            "total_return"
        ]
        > cycle["base"][BENCHMARK]["total_return"],
        "confirmation_cycle_beats_buy_hold_stress": cycle["stress"][CANDIDATE][
            "total_return"
        ]
        > cycle["stress"][BENCHMARK]["total_return"],
        "confirmation_period_beats_buy_hold_base": period["base"][CANDIDATE][
            "total_return"
        ]
        > period["base"][BENCHMARK]["total_return"],
        "confirmation_drawdown_shallower_than_buy_hold": period["base"][CANDIDATE][
            "max_drawdown"
        ]
        > period["base"][BENCHMARK]["max_drawdown"],
        "observed_post_peak_bear_beats_buy_hold": bear["base"][CANDIDATE][
            "total_return"
        ]
        > bear["base"][BENCHMARK]["total_return"],
        "binance_cycle_beats_spot_buy_hold_proxy_base": bridge["base"]["candidate"][
            "total_return"
        ]
        > bridge["base"]["spot_buy_hold_proxy"]["total_return"],
        "binance_cycle_beats_spot_buy_hold_proxy_stress": bridge["stress"][
            "candidate"
        ]["total_return"]
        > bridge["stress"]["spot_buy_hold_proxy"]["total_return"],
    }
    passed = all(checks.values())
    result = {
        "schema_version": 1,
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "source_sha256": _sha256(source),
        "checks": checks,
        "failed_checks": [name for name, value in checks.items() if not value],
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
    analyze_parser.add_argument("--phase", choices=("development", "confirmation"), required=True)
    analyze_parser.add_argument("--cache-root", required=True)
    analyze_parser.add_argument("--source-manifest", required=True)
    analyze_parser.add_argument("--output-dir", required=True)
    analyze_parser.add_argument("--authorization")
    analyze_parser.add_argument("--binance-cache-root")
    analyze_parser.add_argument("--binance-manifest")
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
