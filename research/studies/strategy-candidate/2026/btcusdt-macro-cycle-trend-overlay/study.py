"""Audit a fixed BTC macro-cycle trend overlay against raw buy-and-hold."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import sys
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
import pandas as pd
import vectorbt as vbt


STUDY_DIR = Path(__file__).resolve().parent
BASE_STUDY_PATH = STUDY_DIR.parent / "btcusdt-daily-donchian-ensemble" / "study.py"
DAY_MS = 86_400_000
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
COIN_METRICS_SCENARIOS = {
    "favorable": {"cost": 0.0010, "annual_financing": 0.00},
    "base": {"cost": 0.0025, "annual_financing": 0.05},
    "stress": {"cost": 0.0050, "annual_financing": 0.10},
}
BINANCE_SCENARIOS = {
    "favorable": {"fee": 0.0004, "slippage": 0.0002},
    "base": {"fee": 0.0004, "slippage": 0.0010},
    "stress": {"fee": 0.0004, "slippage": 0.0015},
}
BOOTSTRAP_REPLICATIONS = 20_000
BOOTSTRAP_BLOCK_DAYS = 180
BOOTSTRAP_SEED = 20260722


def _load_base() -> ModuleType:
    spec = importlib.util.spec_from_file_location("halpha_macro_cycle_base", BASE_STUDY_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("BASE_STUDY_IMPORT_UNAVAILABLE")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


BASE = _load_base()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _utc_ms(value: str | pd.Timestamp) -> int:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize("UTC")
    else:
        timestamp = timestamp.tz_convert("UTC")
    return int(timestamp.timestamp() * 1000)


def _load_coin_metrics(cache_root: Path, manifest_path: Path) -> pd.DataFrame:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw_path = cache_root / manifest["cache_relative_path"]
    if _sha256(raw_path) != manifest["raw_sha256"]:
        raise ValueError("COIN_METRICS_RAW_SHA256_MISMATCH")
    payload = json.loads(raw_path.read_text(encoding="utf-8"))
    rows = payload["data"]
    normalized = [
        {
            "time": item["time"],
            "PriceUSD": item["PriceUSD"],
            "CapMVRVCur": item["CapMVRVCur"],
        }
        for item in rows
    ]
    identity = hashlib.sha256(
        json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    if identity != manifest["content_identity"]:
        raise ValueError("COIN_METRICS_CONTENT_IDENTITY_MISMATCH")
    frame = pd.DataFrame(normalized)
    frame["time"] = pd.to_datetime(frame["time"], utc=True)
    frame["price"] = pd.to_numeric(frame["PriceUSD"], errors="raise")
    frame["mvrv"] = pd.to_numeric(frame["CapMVRVCur"], errors="raise")
    frame = frame[["time", "price", "mvrv"]].sort_values("time").reset_index(drop=True)
    if frame["time"].duplicated().any():
        raise ValueError("COIN_METRICS_DUPLICATE_DATES")
    intervals = frame["time"].diff().dropna()
    if not (intervals == pd.Timedelta(days=1)).all():
        raise ValueError("COIN_METRICS_NON_CONTINUOUS_DAILY")
    if not np.isfinite(frame[["price", "mvrv"]].to_numpy()).all():
        raise ValueError("COIN_METRICS_NON_FINITE")
    if not (frame[["price", "mvrv"]] > 0).all().all():
        raise ValueError("COIN_METRICS_NON_POSITIVE")
    return frame


def _weights(frame: pd.DataFrame) -> dict[str, np.ndarray]:
    price = frame["price"]
    sma50 = price.rolling(50, min_periods=50).mean()
    sma200 = price.rolling(200, min_periods=200).mean()
    momentum84 = price / price.shift(84) - 1.0
    votes = (
        (price > sma200).astype(float)
        + (sma50 > sma200).astype(float)
        + (momentum84 > 0.0).astype(float)
    )
    valid = sma200.notna() & momentum84.notna()
    macro = (0.5 * votes).where(valid, 0.0).to_numpy(dtype=np.float64)
    no_leverage = ((votes / 3.0).where(valid, 0.0)).to_numpy(dtype=np.float64)
    simple_sma = (1.5 * (price > sma200).astype(float)).where(valid, 0.0)
    return {
        "BTC_MACRO_SCORE_3_MAX_1P5": macro,
        "BTC_MACRO_SCORE_3_MAX_1P0": no_leverage,
        "BTC_SMA200_BINARY_MAX_1P5": simple_sma.to_numpy(dtype=np.float64),
        "BTC_BUY_HOLD_1P0": np.ones(len(frame), dtype=np.float64),
    }


def _coin_metrics_market(
    frame: pd.DataFrame, manifest_identity: str, annual_financing: float
) -> Any:
    price = frame["price"].to_numpy(dtype=np.float64)
    open_time = (frame["time"].astype("int64") // 1_000_000).to_numpy(dtype=np.int64)
    daily_rate = annual_financing / 365.25
    return BASE.MarketData(
        open_time=open_time,
        open=price.copy(),
        high=price.copy(),
        low=price.copy(),
        close=price.copy(),
        funding_boundary_value=price * daily_rate,
        funding_intraday_value=np.zeros(len(frame), dtype=np.float64),
        manifest_identity=manifest_identity,
        quality={
            "bars": len(frame),
            "first_time": frame["time"].iloc[0].isoformat(),
            "last_time": frame["time"].iloc[-1].isoformat(),
            "continuous_daily": True,
            "positive_price_and_mvrv": True,
            "price_definition": "Coin Metrics PriceUSD daily; open/high/low proxy equals daily price",
        },
    )


def _zero_funding(data: Any) -> Any:
    return replace(
        data,
        funding_boundary_value=np.zeros(len(data.open_time), dtype=np.float64),
        funding_intraday_value=np.zeros(len(data.open_time), dtype=np.float64),
    )


def _simulate(
    data: Any,
    weight: np.ndarray,
    period: tuple[str, str],
    fee: float,
    slippage: float,
) -> Any:
    return BASE._simulate(
        data,
        weight,
        start_ms=_utc_ms(period[0]),
        end_ms=_utc_ms(period[1]),
        fee_rate=fee,
        slippage_rate=slippage,
    )


def _coin_metrics_variants(
    frame: pd.DataFrame,
    manifest_identity: str,
    weights: dict[str, np.ndarray],
    period: tuple[str, str],
) -> tuple[dict[str, Any], dict[str, np.ndarray], pd.DatetimeIndex]:
    results: dict[str, Any] = {}
    base_returns: dict[str, np.ndarray] = {}
    dates: pd.DatetimeIndex | None = None
    for scenario, assumptions in COIN_METRICS_SCENARIOS.items():
        candidate_data = _coin_metrics_market(
            frame, manifest_identity, assumptions["annual_financing"]
        )
        scenario_results: dict[str, Any] = {}
        for candidate_id in (
            "BTC_MACRO_SCORE_3_MAX_1P5",
            "BTC_MACRO_SCORE_3_MAX_1P0",
            "BTC_SMA200_BINARY_MAX_1P5",
        ):
            simulation = _simulate(
                candidate_data,
                weights[candidate_id],
                period,
                assumptions["cost"],
                0.0,
            )
            scenario_results[candidate_id] = simulation.metrics
            if scenario == "base":
                base_returns[candidate_id] = simulation.returns
                dates = simulation.dates
        benchmark = _simulate(
            _zero_funding(candidate_data),
            weights["BTC_BUY_HOLD_1P0"],
            period,
            assumptions["cost"],
            0.0,
        )
        scenario_results["BTC_BUY_HOLD_1P0"] = benchmark.metrics
        if scenario == "base":
            base_returns["BTC_BUY_HOLD_1P0"] = benchmark.returns
            dates = benchmark.dates
        results[scenario] = scenario_results
    if dates is None:
        raise RuntimeError("BASE_DATES_MISSING")
    return results, base_returns, dates


def _cycle_endpoints(frame: pd.DataFrame, cycle: dict[str, Any]) -> dict[str, Any]:
    bottom_start, bottom_end = map(pd.Timestamp, cycle["bottom_window"])
    peak_start, peak_end = map(pd.Timestamp, cycle["peak_window"])
    bottom_start = bottom_start.tz_localize("UTC")
    bottom_end = bottom_end.tz_localize("UTC")
    peak_start = peak_start.tz_localize("UTC")
    peak_end = peak_end.tz_localize("UTC")
    bottom_slice = frame[(frame["time"] >= bottom_start) & (frame["time"] < bottom_end)]
    peak_slice = frame[(frame["time"] >= peak_start) & (frame["time"] < peak_end)]
    if bottom_slice.empty or peak_slice.empty:
        raise ValueError("CYCLE_WINDOW_EMPTY")
    bottom = bottom_slice.loc[bottom_slice["price"].idxmin()]
    peak = peak_slice.loc[peak_slice["price"].idxmax()]
    if peak["time"] <= bottom["time"]:
        raise ValueError("CYCLE_ENDPOINT_ORDER")
    return {
        "bottom_date": bottom["time"].strftime("%Y-%m-%d"),
        "bottom_price": float(bottom["price"]),
        "peak_date": peak["time"].strftime("%Y-%m-%d"),
        "peak_price": float(peak["price"]),
        "perfect_close_to_close_return": float(peak["price"] / bottom["price"] - 1.0),
    }


def _cycle_period(endpoints: dict[str, Any]) -> tuple[str, str]:
    start = pd.Timestamp(endpoints["bottom_date"], tz="UTC") + pd.Timedelta(days=1)
    end = pd.Timestamp(endpoints["peak_date"], tz="UTC") + pd.Timedelta(days=1)
    return start.isoformat(), end.isoformat()


def _cycle_results(
    frame: pd.DataFrame,
    manifest_identity: str,
    weights: dict[str, np.ndarray],
    cycle_names: list[str],
) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for name in cycle_names:
        endpoints = _cycle_endpoints(frame, CYCLES[name])
        period = _cycle_period(endpoints)
        results, _, _ = _coin_metrics_variants(
            frame, manifest_identity, weights, period
        )
        output[name] = {"endpoints": endpoints, "period": period, "results": results}
    return output


def _transition_lags(
    frame: pd.DataFrame,
    weight: np.ndarray,
    endpoints: dict[str, Any],
) -> dict[str, int | None]:
    dates = pd.DatetimeIndex(frame["time"])
    series = pd.Series(weight, index=dates)
    bottom = pd.Timestamp(endpoints["bottom_date"], tz="UTC")
    peak = pd.Timestamp(endpoints["peak_date"], tz="UTC")
    bull = series[(series.index >= bottom) & (series.index <= peak)]
    entry_hits = bull[bull >= 1.0]
    post_peak = series[series.index >= peak]
    exit_hits = post_peak[post_peak <= 0.5]
    entry_lag = None
    exit_lag = None
    if not entry_hits.empty:
        entry_lag = int((entry_hits.index[0] - bottom).days + 1)
    if not exit_hits.empty:
        exit_lag = int((exit_hits.index[0] - peak).days + 1)
    return {"entry_to_at_least_1x_days": entry_lag, "exit_to_at_most_0p5x_days": exit_lag}


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
    results, _, _ = _coin_metrics_variants(frame, manifest_identity, weights, period)
    return {"period": period, "results": results}


def _dsr(base_returns: dict[str, np.ndarray], dates: pd.DatetimeIndex) -> dict[str, float]:
    columns = [
        "BTC_MACRO_SCORE_3_MAX_1P5",
        "BTC_MACRO_SCORE_3_MAX_1P0",
        "BTC_SMA200_BINARY_MAX_1P5",
    ]
    frame = pd.DataFrame({name: base_returns[name] for name in columns}, index=dates)
    output: dict[str, float] = {}
    for trials in (3, 20, 40):
        values = frame.vbt.returns.deflated_sharpe_ratio(nb_trials=trials)
        output[str(trials)] = float(values["BTC_MACRO_SCORE_3_MAX_1P5"])
    return output


def _bootstrap_excess(
    candidate: np.ndarray,
    benchmark: np.ndarray,
) -> dict[str, float | int]:
    if len(candidate) != len(benchmark):
        raise ValueError("BOOTSTRAP_LENGTH_MISMATCH")
    n = len(candidate)
    blocks = math.ceil(n / BOOTSTRAP_BLOCK_DAYS)
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    candidate_log = np.log1p(candidate)
    benchmark_log = np.log1p(benchmark)
    excess = np.empty(BOOTSTRAP_REPLICATIONS, dtype=np.float64)
    cursor = 0
    batch_size = 250
    offsets = np.arange(BOOTSTRAP_BLOCK_DAYS, dtype=np.int64)
    while cursor < BOOTSTRAP_REPLICATIONS:
        batch = min(batch_size, BOOTSTRAP_REPLICATIONS - cursor)
        starts = rng.integers(0, n, size=(batch, blocks), endpoint=False)
        indices = (starts[:, :, None] + offsets[None, None, :]) % n
        indices = indices.reshape(batch, -1)[:, :n]
        candidate_total = np.expm1(candidate_log[indices].sum(axis=1))
        benchmark_total = np.expm1(benchmark_log[indices].sum(axis=1))
        excess[cursor : cursor + batch] = candidate_total - benchmark_total
        cursor += batch
    return {
        "block_days": BOOTSTRAP_BLOCK_DAYS,
        "replications": BOOTSTRAP_REPLICATIONS,
        "seed": BOOTSTRAP_SEED,
        "probability_candidate_beats_buy_hold": float((excess > 0.0).mean()),
        "excess_total_return_p05": float(np.quantile(excess, 0.05)),
        "excess_total_return_median": float(np.quantile(excess, 0.50)),
        "excess_total_return_p95": float(np.quantile(excess, 0.95)),
    }


def _strictly_dominates(left: dict[str, Any], right: dict[str, Any]) -> bool:
    weak = (
        left["total_return"] >= right["total_return"]
        and left["sharpe"] >= right["sharpe"]
        and left["max_drawdown"] >= right["max_drawdown"]
    )
    strict = (
        left["total_return"] > right["total_return"]
        or left["sharpe"] > right["sharpe"]
        or left["max_drawdown"] > right["max_drawdown"]
    )
    return bool(weak and strict)


def _align_binance_weights(
    frame: pd.DataFrame, weights: dict[str, np.ndarray], data: Any
) -> dict[str, np.ndarray]:
    index = pd.DatetimeIndex(frame["time"])
    target_index = pd.to_datetime(data.open_time, unit="ms", utc=True)
    aligned: dict[str, np.ndarray] = {}
    for name, values in weights.items():
        series = pd.Series(values, index=index)
        selected = series.reindex(target_index)
        if selected.isna().any():
            raise ValueError(f"BINANCE_SIGNAL_ALIGNMENT_GAP:{name}")
        aligned[name] = selected.to_numpy(dtype=np.float64)
    return aligned


def _binance_results(
    frame: pd.DataFrame,
    weights: dict[str, np.ndarray],
    cache_root: Path,
    manifest_path: Path,
    endpoints: dict[str, Any],
) -> dict[str, Any]:
    data = BASE._load_market_data(cache_root, manifest_path)
    aligned = _align_binance_weights(frame, weights, data)
    periods = {
        "full_2020_2026": ("2020-01-02T00:00:00Z", "2026-07-01T00:00:00Z"),
        "cycle_2022_2025": _cycle_period(endpoints),
        "confirmation_2022_2026": PERIODS["confirmation"],
    }
    output: dict[str, Any] = {}
    for period_name, period in periods.items():
        scenarios: dict[str, Any] = {}
        for scenario, assumptions in BINANCE_SCENARIOS.items():
            candidate = _simulate(
                data,
                aligned["BTC_MACRO_SCORE_3_MAX_1P5"],
                period,
                assumptions["fee"],
                assumptions["slippage"],
            )
            benchmark = _simulate(
                _zero_funding(data),
                aligned["BTC_BUY_HOLD_1P0"],
                period,
                assumptions["fee"],
                assumptions["slippage"],
            )
            scenarios[scenario] = {
                "candidate": candidate.metrics,
                "spot_buy_hold_proxy": benchmark.metrics,
            }
        output[period_name] = scenarios
    output["data_quality"] = data.quality
    output["data_identity"] = data.manifest_identity
    output["manifest_sha256"] = _sha256(manifest_path)
    return output


def _development_checks(payload: dict[str, Any]) -> dict[str, bool]:
    full = payload["period_results"]
    cycles = payload["cycles"]
    candidate = "BTC_MACRO_SCORE_3_MAX_1P5"
    benchmark = "BTC_BUY_HOLD_1P0"
    cycle_checks: list[bool] = []
    for name in ("cycle_2015_2017", "cycle_2018_2021"):
        result = cycles[name]["results"]
        cycle_checks.extend(
            [
                result["base"][candidate]["total_return"]
                > result["base"][benchmark]["total_return"],
                result["stress"][candidate]["total_return"]
                > result["stress"][benchmark]["total_return"],
            ]
        )
    base_candidate = full["base"][candidate]
    base_benchmark = full["base"][benchmark]
    stress_candidate = full["stress"][candidate]
    stress_benchmark = full["stress"][benchmark]
    simple = full["base"]["BTC_SMA200_BINARY_MAX_1P5"]
    bear = payload["bear_segments"]["peak_2017_to_bottom_2018"]["results"]
    lags = payload["transition_lags"]
    return {
        "both_development_bull_legs_beat_buy_hold_base_and_stress": all(cycle_checks),
        "development_base_beats_buy_hold": base_candidate["total_return"]
        > base_benchmark["total_return"],
        "development_stress_beats_buy_hold": stress_candidate["total_return"]
        > stress_benchmark["total_return"],
        "development_drawdown_shallower_than_buy_hold": base_candidate["max_drawdown"]
        > base_benchmark["max_drawdown"],
        "complete_bear_leg_beats_buy_hold": bear["base"][candidate]["total_return"]
        > bear["base"][benchmark]["total_return"],
        "both_entry_lags_at_most_180d": all(
            lags[name]["entry_to_at_least_1x_days"] is not None
            and lags[name]["entry_to_at_least_1x_days"] <= 180
            for name in ("cycle_2015_2017", "cycle_2018_2021")
        ),
        "first_exit_lag_at_most_120d": lags["cycle_2015_2017"][
            "exit_to_at_most_0p5x_days"
        ]
        is not None
        and lags["cycle_2015_2017"]["exit_to_at_most_0p5x_days"] <= 120,
        "not_strictly_dominated_by_simple_sma200": not _strictly_dominates(
            simple, base_candidate
        ),
        "twenty_trial_dsr_at_least_0p80": payload["selection_bias"][
            "deflated_sharpe_probability"
        ]["20"]
        >= 0.80,
        "bootstrap_probability_beats_buy_hold_at_least_0p80": payload[
            "paired_block_bootstrap"
        ]["probability_candidate_beats_buy_hold"]
        >= 0.80,
    }


def analyze(args: argparse.Namespace) -> None:
    if args.phase == "confirmation":
        if not args.authorization:
            raise ValueError("CONFIRMATION_AUTHORIZATION_REQUIRED")
        authorization = json.loads(Path(args.authorization).read_text(encoding="utf-8"))
        if not authorization.get("confirmation_authorized"):
            raise ValueError("CONFIRMATION_NOT_AUTHORIZED")
    manifest_path = Path(args.source_manifest).resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    cache_root = Path(args.cache_root).resolve()
    frame = _load_coin_metrics(cache_root, manifest_path)
    weights = _weights(frame)
    period = PERIODS[args.phase]
    period_results, base_returns, dates = _coin_metrics_variants(
        frame, manifest["content_identity"], weights, period
    )
    cycle_names = [
        name for name, definition in CYCLES.items() if definition["phase"] == args.phase
    ]
    cycles = _cycle_results(
        frame, manifest["content_identity"], weights, cycle_names
    )
    transition_lags = {
        name: _transition_lags(
            frame,
            weights["BTC_MACRO_SCORE_3_MAX_1P5"],
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
        start = pd.Timestamp(
            cycles["cycle_2022_2025"]["endpoints"]["peak_date"], tz="UTC"
        ) + pd.Timedelta(days=1)
        bear_period = (start.isoformat(), PERIODS["confirmation"][1])
        results, _, _ = _coin_metrics_variants(
            frame, manifest["content_identity"], weights, bear_period
        )
        bear_segments["peak_2025_to_cutoff"] = {
            "period": bear_period,
            "results": results,
        }
    payload: dict[str, Any] = {
        "schema_version": 1,
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "phase": args.phase,
        "period": list(period),
        "candidate_id": "BTC_MACRO_SCORE_3_MAX_1P5",
        "framework_versions": {
            "vectorbt": vbt.__version__,
            "pandas": pd.__version__,
            "numpy": np.__version__,
        },
        "method_identity": {
            "study_sha256": _sha256(Path(__file__).resolve()),
            "base_study_sha256": _sha256(BASE_STUDY_PATH),
            "source_manifest_sha256": _sha256(manifest_path),
            "source_content_identity": manifest["content_identity"],
        },
        "data_quality": {
            "rows": len(frame),
            "first_time": frame["time"].iloc[0].isoformat(),
            "last_time": frame["time"].iloc[-1].isoformat(),
            "continuous_daily": True,
            "positive_price_and_mvrv": True,
        },
        "rules": {
            "votes": ["price_above_sma200", "sma50_above_sma200", "return_84d_positive"],
            "weight_per_vote": 0.5,
            "weights": [0.0, 0.5, 1.0, 1.5],
            "action_time": "next daily observation",
            "rebalance_relative_tolerance": 0.20,
        },
        "coin_metrics_scenarios": COIN_METRICS_SCENARIOS,
        "period_results": period_results,
        "cycles": cycles,
        "transition_lags": transition_lags,
        "bear_segments": bear_segments,
        "product_effects": "NONE",
    }
    if args.phase == "development":
        payload["selection_bias"] = {
            "deflated_sharpe_probability": _dsr(base_returns, dates),
            "interpretation": "3 is the fixed local comparison; 20 and 40 are related-history sensitivity counts, not independent trials.",
        }
        payload["paired_block_bootstrap"] = _bootstrap_excess(
            base_returns["BTC_MACRO_SCORE_3_MAX_1P5"],
            base_returns["BTC_BUY_HOLD_1P0"],
        )
    else:
        full_results, _, _ = _coin_metrics_variants(
            frame, manifest["content_identity"], weights, PERIODS["full"]
        )
        payload["full_period_results"] = full_results
        if not args.binance_cache_root or not args.binance_manifest:
            raise ValueError("BINANCE_BRIDGE_INPUTS_REQUIRED")
        payload["binance_bridge"] = _binance_results(
            frame,
            weights,
            Path(args.binance_cache_root).resolve(),
            Path(args.binance_manifest).resolve(),
            cycles["cycle_2022_2025"]["endpoints"],
        )
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{args.phase}.json"
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    pd.DataFrame(base_returns, index=dates).to_csv(
        output_dir / f"{args.phase}_daily_returns.csv", index_label="date"
    )
    print(
        json.dumps(
            {
                "phase": args.phase,
                "candidate": payload["candidate_id"],
                "period_base": period_results["base"][
                    "BTC_MACRO_SCORE_3_MAX_1P5"
                ],
            },
            ensure_ascii=False,
        )
    )


def qualify_development(args: argparse.Namespace) -> None:
    source = Path(args.input).resolve()
    payload = json.loads(source.read_text(encoding="utf-8"))
    if payload.get("phase") != "development":
        raise ValueError("NOT_DEVELOPMENT_RESULT")
    checks = _development_checks(payload)
    result = {
        "schema_version": 1,
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "source_sha256": _sha256(source),
        "checks": checks,
        "failed_checks": [name for name, passed in checks.items() if not passed],
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
        raise ValueError("NOT_CONFIRMATION_RESULT")
    candidate = "BTC_MACRO_SCORE_3_MAX_1P5"
    benchmark = "BTC_BUY_HOLD_1P0"
    cycle = payload["cycles"]["cycle_2022_2025"]["results"]
    period = payload["period_results"]
    bear = payload["bear_segments"]["peak_2025_to_cutoff"]["results"]
    bridge = payload["binance_bridge"]
    checks = {
        "confirmation_cycle_beats_buy_hold_base": cycle["base"][candidate][
            "total_return"
        ]
        > cycle["base"][benchmark]["total_return"],
        "confirmation_cycle_beats_buy_hold_stress": cycle["stress"][candidate][
            "total_return"
        ]
        > cycle["stress"][benchmark]["total_return"],
        "confirmation_period_beats_buy_hold_base": period["base"][candidate][
            "total_return"
        ]
        > period["base"][benchmark]["total_return"],
        "confirmation_drawdown_shallower_than_buy_hold": period["base"][candidate][
            "max_drawdown"
        ]
        > period["base"][benchmark]["max_drawdown"],
        "observed_post_peak_bear_beats_buy_hold": bear["base"][candidate][
            "total_return"
        ]
        > bear["base"][benchmark]["total_return"],
        "binance_cycle_beats_spot_buy_hold_proxy_base": bridge["cycle_2022_2025"][
            "base"
        ]["candidate"]["total_return"]
        > bridge["cycle_2022_2025"]["base"]["spot_buy_hold_proxy"]["total_return"],
        "binance_cycle_beats_spot_buy_hold_proxy_stress": bridge["cycle_2022_2025"][
            "stress"
        ]["candidate"]["total_return"]
        > bridge["cycle_2022_2025"]["stress"]["spot_buy_hold_proxy"]["total_return"],
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
