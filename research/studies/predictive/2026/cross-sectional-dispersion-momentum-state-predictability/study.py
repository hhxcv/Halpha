from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import platform
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import scipy
import statsmodels
import statsmodels.api as sm


HERE = Path(__file__).resolve().parent
PARENT_DIR = HERE.parent / "short-horizon-crypto-residual-momentum-predictability"
PARENT_STUDY = PARENT_DIR / "study.py"


def load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


parent = load_module(PARENT_STUDY, "halpha_dispersion_parent")
SYMBOLS = list(parent.SYMBOLS)
SYMBOL_TO_CATEGORY = dict(parent.SYMBOL_TO_CATEGORY)
UNIVERSE_PATH = parent.UNIVERSE_PATH

STAGES = {
    "development": ("2022-01-03T00:00:00Z", "2024-01-01T00:00:00Z"),
    "evaluation": ("2024-01-01T00:00:00Z", "2024-12-30T00:00:00Z"),
}
CONFIG = {
    "predictor_id": "RESEARCH_CSSD_MOM20_STATE_PREDICTABILITY_V1",
    "state_history_start": "2021-01-01T00:00:00Z",
    "main_momentum_days": 20,
    "neighbor_momentum_days": [14, 30],
    "daily_history_days": 61,
    "minimum_dispersion_history_days": 252,
    "minimum_rankable_symbols": 20,
    "minimum_median_quote_volume_30d": 10_000_000.0,
    "market_volatility_days": 30,
    "correlation_days": 60,
    "tail_fraction": 0.20,
    "target_days": 7,
    "notional_fraction": 0.25,
    "stress_round_trip_underlying": 0.0052,
    "annual_full_plan_hurdle": 0.04,
    "conditional_underlying_floor": 0.0052 + 0.04 / 52.0 / 0.25,
    "minimum_action_weeks": 80,
    "minimum_state_weeks": 30,
    "minimum_selected_symbols": 15,
    "minimum_positive_symbol_fraction": 0.50,
    "maximum_positive_contribution_share": 0.40,
    "bootstrap": {"block_weeks": 4, "repetitions": 5000, "seed": 20260722},
    "hac_lags": 4,
}
FROZEN_FILES = ["README.md", "sources.md", "preregistration.md", "study.py"]


def iso_now() -> str:
    return pd.Timestamp.now(tz="UTC").isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    if isinstance(value, (pd.Timestamp, np.datetime64)):
        return pd.Timestamp(value).isoformat()
    if isinstance(value, np.ndarray):
        return [jsonable(item) for item in value.tolist()]
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return None if not np.isfinite(value) else float(value)
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def canonical_digest(value: Any) -> str:
    payload = dict(value)
    payload.pop("content_digest", None)
    encoded = json.dumps(jsonable(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def write_json(path: Path, value: dict[str, Any], *, digest: bool = False) -> None:
    payload = jsonable(value)
    if digest:
        payload["content_digest"] = canonical_digest(payload)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def source_entries() -> list[dict[str, Any]]:
    paths = [
        (PARENT_STUDY, "reused public daily OHLCV adapter"),
        (PARENT_DIR / "checkpoint.json", "frozen parent identity"),
        (PARENT_DIR / "source_reuse_manifest.json", "public source reuse chain"),
        (PARENT_DIR / "data_quality_development.json", "parent public-data quality evidence"),
        (UNIVERSE_PATH, "frozen current research universe"),
    ]
    output: list[dict[str, Any]] = []
    for path, role in paths:
        if not path.exists():
            raise RuntimeError(f"missing source identity: {path}")
        output.append({"path": str(path), "bytes": path.stat().st_size, "sha256": sha256_file(path), "role": role})
    return output


def ensure_checkpoint() -> dict[str, Any]:
    path = HERE / "checkpoint.json"
    if not path.exists():
        raise RuntimeError("checkpoint missing")
    checkpoint = read_json(path)
    if canonical_digest(checkpoint) != checkpoint.get("content_digest"):
        raise RuntimeError("checkpoint digest mismatch")
    if checkpoint.get("configuration") != CONFIG:
        raise RuntimeError("checkpoint configuration differs from code")
    if checkpoint.get("stages") != {key: list(value) for key, value in STAGES.items()}:
        raise RuntimeError("checkpoint stages differ from code")
    for name, expected in checkpoint["frozen_file_sha256"].items():
        if sha256_file(HERE / name) != expected:
            raise RuntimeError(f"frozen file changed: {name}")
    reuse = read_json(HERE / "source_reuse_manifest.json")
    if canonical_digest(reuse) != reuse.get("content_digest"):
        raise RuntimeError("source reuse manifest digest mismatch")
    if reuse["content_digest"] != checkpoint["source_reuse_digest"]:
        raise RuntimeError("source reuse identity differs from checkpoint")
    for item in reuse["entries"]:
        source = Path(item["path"])
        if not source.exists() or source.stat().st_size != int(item["bytes"]) or sha256_file(source) != item["sha256"]:
            raise RuntimeError(f"reused source changed: {source}")
    parent.ensure_checkpoint()
    return checkpoint


def command_checkpoint(_args: argparse.Namespace) -> None:
    if (HERE / "checkpoint.json").exists():
        checkpoint = ensure_checkpoint()
        print(json.dumps({"reused": True, "digest": checkpoint["content_digest"]}, indent=2))
        return
    parent.ensure_checkpoint()
    reuse = {"created_at_utc": iso_now(), "entries": source_entries()}
    write_json(HERE / "source_reuse_manifest.json", reuse, digest=True)
    payload = {
        "created_at_utc": iso_now(),
        "baseline_commit": "0bdfeffa616260cebd2d2188ddc8deb9e85c77f4",
        "formal_strategy": {
            "strategy_id": "ONE_SHOT_DONCHIAN_ATR_BREAKOUT",
            "version": "1.0.1",
            "instrument": "BTCUSDT-PERP",
        },
        "research_kind": "PREDICTIVE",
        "question": (
            "Does lagged cross-sectional daily-return dispersion incrementally predict weaker next-week MOM20 "
            "top-minus-bottom returns, and does the low-dispersion state leave enough gross room for a separate "
            "semi-automatic one-shot strategy study?"
        ),
        "replication_status": (
            "Transparent weekly top-long Halpha adaptation of Zhang-Makgolo 2026; not a performance replication "
            "of their dynamic daily long-short CoinGecko study."
        ),
        "known_exposure": (
            "Underlying 2022-2023 prices were viewed in prior Halpha questions, but daily CSSD states, conditional "
            "MOM20 spreads and regressions were not calculated before this checkpoint."
        ),
        "support_limit": (
            "A pass releases only a separate strategy-cost question; it is not a strategy handoff or long-term "
            "profitability claim."
        ),
        "family_stop_rule": (
            "On failure do not search dispersion smoothing, threshold, lookback, momentum window, universe, state "
            "direction or holding period without new independent evidence."
        ),
        "configuration": CONFIG,
        "stages": {key: list(value) for key, value in STAGES.items()},
        "symbols": SYMBOLS,
        "selection_scope": {"selectable_primary_configurations": 1, "fixed_neighbor_checks": 3},
        "stage_open_rule": "development -> evaluation; evaluation sealed until all development hard gates pass",
        "frozen_file_sha256": {name: sha256_file(HERE / name) for name in FROZEN_FILES},
        "source_reuse_digest": read_json(HERE / "source_reuse_manifest.json")["content_digest"],
        "environment": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "scipy": scipy.__version__,
            "statsmodels": statsmodels.__version__,
        },
    }
    write_json(HERE / "checkpoint.json", payload, digest=True)
    checkpoint = read_json(HERE / "checkpoint.json")
    print(json.dumps({"reused": False, "digest": checkpoint["content_digest"]}, indent=2))


def stage_authorized(stage: str) -> None:
    if stage == "evaluation":
        gate = HERE / "development_gate.json"
        if not gate.exists() or read_json(gate).get("status") != "PASS":
            raise RuntimeError("evaluation remains sealed until development PASS")


def stage_entries(stage: str) -> pd.DatetimeIndex:
    start, end = map(pd.Timestamp, STAGES[stage])
    return pd.date_range(start, end, freq="W-MON", inclusive="left")


def load_bars(stage: str) -> tuple[dict[str, pd.DataFrame], dict[str, Any]]:
    ensure_checkpoint()
    stage_authorized(stage)
    bars, _funding, metadata = parent.parent.load_stage(stage)
    return bars, metadata


def make_daily_frames(bars: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    output: dict[str, pd.DataFrame] = {}
    for symbol, raw in bars.items():
        frame = raw.sort_index().copy()
        frame = frame.reindex(pd.date_range(frame.index.min(), frame.index.max(), freq="1D"))
        frame["log_return"] = np.log(frame["close"]).diff()
        frame["median_quote_volume_30d"] = frame["quote_volume"].rolling(30, min_periods=30).median()
        complete = frame[["open", "high", "low", "close", "quote_volume"]].notna().all(axis=1)
        frame["complete_61d"] = complete.rolling(int(CONFIG["daily_history_days"]), min_periods=int(CONFIG["daily_history_days"])).sum().eq(int(CONFIG["daily_history_days"]))
        output[symbol] = frame
    return output


def eligible_at(daily: dict[str, pd.DataFrame], date: pd.Timestamp) -> list[str]:
    output: list[str] = []
    for symbol in SYMBOLS:
        frame = daily[symbol]
        if date not in frame.index:
            continue
        if not bool(frame.at[date, "complete_61d"]):
            continue
        if float(frame.at[date, "median_quote_volume_30d"]) < float(CONFIG["minimum_median_quote_volume_30d"]):
            continue
        output.append(symbol)
    return sorted(output)


def build_daily_state(daily: dict[str, pd.DataFrame], stage: str) -> pd.DataFrame:
    _stage_start, stage_end = map(pd.Timestamp, STAGES[stage])
    start = pd.Timestamp(CONFIG["state_history_start"])
    end = stage_end + pd.Timedelta(days=int(CONFIG["target_days"]))
    rows: list[dict[str, Any]] = []
    correlation_days = int(CONFIG["correlation_days"])
    for date in pd.date_range(start, end, freq="1D", inclusive="left"):
        eligible = eligible_at(daily, date)
        if len(eligible) < int(CONFIG["minimum_rankable_symbols"]):
            continue
        current = np.asarray([daily[symbol].at[date, "log_return"] for symbol in eligible], dtype=float)
        if not np.isfinite(current).all():
            continue
        return_matrix = np.column_stack([
            daily[symbol].loc[:date, "log_return"].tail(correlation_days).to_numpy(float)
            for symbol in eligible
        ])
        if return_matrix.shape != (correlation_days, len(eligible)) or not np.isfinite(return_matrix).all():
            continue
        correlation = np.corrcoef(return_matrix, rowvar=False)
        off_diagonal = correlation[~np.eye(len(eligible), dtype=bool)]
        rows.append({
            "date": date,
            "eligible_count": len(eligible),
            "eligible_symbols": "|".join(eligible),
            "dispersion": float(np.std(current, ddof=1)),
            "market_return": float(np.mean(current)),
            "average_correlation_60d": float(np.mean(off_diagonal)),
        })
    state = pd.DataFrame(rows).set_index("date").sort_index()
    state["market_volatility_30d"] = state["market_return"].rolling(
        int(CONFIG["market_volatility_days"]), min_periods=int(CONFIG["market_volatility_days"])
    ).std(ddof=1)
    expanding = state["dispersion"].expanding(min_periods=int(CONFIG["minimum_dispersion_history_days"]))
    state["dispersion_expanding_median"] = expanding.median()
    state["dispersion_expanding_q75"] = expanding.quantile(0.75)
    state["log_dispersion_ratio"] = np.log(state["dispersion"] / state["dispersion_expanding_median"])
    state["high_dispersion"] = state["log_dispersion_ratio"] > 0.0
    state["high_tail_dispersion"] = state["dispersion"] > state["dispersion_expanding_q75"]
    state["paper_exposure_scale"] = np.minimum(
        1.0, np.maximum(0.10, state["dispersion_expanding_median"] / state["dispersion"])
    )
    return state.reset_index()


def build_panel(
    daily: dict[str, pd.DataFrame], state: pd.DataFrame, stage: str
) -> tuple[pd.DataFrame, dict[str, Any]]:
    state_index = state.set_index("date")
    rows: list[dict[str, Any]] = []
    audits: list[dict[str, Any]] = []
    for entry in stage_entries(stage):
        cutoff = entry - pd.Timedelta(days=2)
        exit_time = entry + pd.Timedelta(days=int(CONFIG["target_days"]))
        eligible = eligible_at(daily, cutoff)
        audit = {
            "entry_time": entry,
            "signal_cutoff": cutoff,
            "eligible_count": len(eligible),
            "status": "NO_ACTION_TOO_FEW_ELIGIBLE",
            "future_missing_symbols": [],
        }
        if len(eligible) < int(CONFIG["minimum_rankable_symbols"]):
            audits.append(audit)
            continue
        if cutoff not in state_index.index or pd.isna(state_index.at[cutoff, "log_dispersion_ratio"]):
            audit["status"] = "NO_ACTION_STATE_NOT_READY"
            audits.append(audit)
            continue
        future_missing = [
            symbol for symbol in eligible
            if entry not in daily[symbol].index
            or exit_time not in daily[symbol].index
            or pd.isna(daily[symbol].at[entry, "open"])
            or pd.isna(daily[symbol].at[exit_time, "open"])
        ]
        if future_missing:
            audit["status"] = "DATA_QUALITY_FAIL_FUTURE_TARGET_MISSING"
            audit["future_missing_symbols"] = future_missing
            audits.append(audit)
            continue
        future = {
            symbol: float(daily[symbol].at[exit_time, "open"] / daily[symbol].at[entry, "open"] - 1.0)
            for symbol in eligible
        }
        market_future = float(np.mean(list(future.values())))
        state_row = state_index.loc[cutoff]
        for symbol in eligible:
            returns = daily[symbol].loc[:cutoff, "log_return"].tail(30).to_numpy(float)
            if len(returns) != 30 or not np.isfinite(returns).all():
                raise RuntimeError(f"momentum history invalid: {entry} {symbol}")
            rows.append({
                "entry_time": entry,
                "signal_cutoff": cutoff,
                "exit_time": exit_time,
                "symbol": symbol,
                "category": SYMBOL_TO_CATEGORY[symbol],
                "eligible_count": len(eligible),
                "mom14": float(returns[-14:].sum()),
                "mom20": float(returns[-20:].sum()),
                "mom30": float(returns.sum()),
                "dispersion": float(state_row["dispersion"]),
                "dispersion_expanding_median": float(state_row["dispersion_expanding_median"]),
                "dispersion_expanding_q75": float(state_row["dispersion_expanding_q75"]),
                "log_dispersion_ratio": float(state_row["log_dispersion_ratio"]),
                "high_dispersion": bool(state_row["high_dispersion"]),
                "high_tail_dispersion": bool(state_row["high_tail_dispersion"]),
                "paper_exposure_scale": float(state_row["paper_exposure_scale"]),
                "market_volatility_30d": float(state_row["market_volatility_30d"]),
                "average_correlation_60d": float(state_row["average_correlation_60d"]),
                "entry_price": float(daily[symbol].at[entry, "open"]),
                "exit_price": float(daily[symbol].at[exit_time, "open"]),
                "target_asset_return": future[symbol],
                "target_market_return": market_future,
                "target_excess_return": future[symbol] - market_future,
            })
        audit["status"] = "ACTION"
        audits.append(audit)
    if not rows:
        raise RuntimeError(f"empty panel: {stage}")
    return (
        pd.DataFrame(rows).sort_values(["entry_time", "symbol"]).reset_index(drop=True),
        {"weeks": audits},
    )


def weekly_for_momentum(panel: pd.DataFrame, days: int) -> pd.DataFrame:
    column = f"mom{days}"
    rows: list[dict[str, Any]] = []
    for entry, frame in panel.groupby("entry_time", sort=True):
        ordered = frame.sort_values([column, "symbol"], ascending=[False, True])
        tail = max(1, int(math.ceil(len(ordered) * float(CONFIG["tail_fraction"]))))
        top, bottom = ordered.head(tail), ordered.tail(tail)
        first = frame.iloc[0]
        rows.append({
            "entry_time": entry,
            "momentum_days": days,
            "eligible_count": int(len(frame)),
            "tail_count": tail,
            "top_symbols": "|".join(top["symbol"].tolist()),
            "bottom_symbols": "|".join(bottom["symbol"].tolist()),
            "top_asset_return": float(top["target_asset_return"].mean()),
            "top_excess_return": float(top["target_excess_return"].mean()),
            "bottom_excess_return": float(bottom["target_excess_return"].mean()),
            "spread": float(top["target_excess_return"].mean() - bottom["target_excess_return"].mean()),
            "log_dispersion_ratio": float(first["log_dispersion_ratio"]),
            "high_dispersion": bool(first["high_dispersion"]),
            "high_tail_dispersion": bool(first["high_tail_dispersion"]),
            "paper_exposure_scale": float(first["paper_exposure_scale"]),
            "market_volatility_30d": float(first["market_volatility_30d"]),
            "average_correlation_60d": float(first["average_correlation_60d"]),
        })
    return pd.DataFrame(rows).sort_values("entry_time").reset_index(drop=True)


def block_bootstrap_mean_ci(values: np.ndarray) -> list[float]:
    values = np.asarray(values, dtype=float)
    if len(values) == 0 or not np.isfinite(values).all():
        raise RuntimeError("bootstrap input empty or non-finite")
    block = int(CONFIG["bootstrap"]["block_weeks"])
    reps = int(CONFIG["bootstrap"]["repetitions"])
    rng = np.random.default_rng(int(CONFIG["bootstrap"]["seed"]))
    means = np.empty(reps)
    for index in range(reps):
        chosen: list[int] = []
        while len(chosen) < len(values):
            start = int(rng.integers(0, len(values)))
            chosen.extend(((start + np.arange(block)) % len(values)).tolist())
        means[index] = float(values[np.asarray(chosen[: len(values)])].mean())
    return [float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975))]


def bootstrap_state_difference(
    weekly: pd.DataFrame, metric: str, state_column: str = "high_dispersion"
) -> list[float]:
    n = len(weekly)
    block = int(CONFIG["bootstrap"]["block_weeks"])
    reps = int(CONFIG["bootstrap"]["repetitions"])
    rng = np.random.default_rng(int(CONFIG["bootstrap"]["seed"]))
    values: list[float] = []
    for _index in range(reps):
        chosen: list[int] = []
        while len(chosen) < n:
            start = int(rng.integers(0, n))
            chosen.extend(((start + np.arange(block)) % n).tolist())
        sample = weekly.iloc[np.asarray(chosen[:n])]
        low = sample.loc[~sample[state_column], metric]
        high = sample.loc[sample[state_column], metric]
        if len(low) and len(high):
            values.append(float(low.mean() - high.mean()))
    if len(values) < int(reps * 0.95):
        raise RuntimeError("too few valid state bootstrap samples")
    return [float(np.quantile(values, 0.025)), float(np.quantile(values, 0.975))]


def series_summary(series: pd.Series) -> dict[str, Any]:
    values = series.to_numpy(float)
    return {
        "observations": int(len(values)),
        "mean": float(np.mean(values)),
        "median": float(np.median(values)),
        "bootstrap_95pct": block_bootstrap_mean_ci(values),
        "positive_fraction": float(np.mean(values > 0.0)),
        "minimum": float(np.min(values)),
        "maximum": float(np.max(values)),
    }


def state_summary(weekly: pd.DataFrame, state_column: str = "high_dispersion") -> dict[str, Any]:
    low = weekly[~weekly[state_column]]
    high = weekly[weekly[state_column]]
    metrics = ["top_asset_return", "top_excess_return", "spread"]
    return {
        "low_weeks": int(len(low)),
        "high_weeks": int(len(high)),
        "low": {metric: series_summary(low[metric]) for metric in metrics},
        "high": {metric: series_summary(high[metric]) for metric in metrics},
        "low_minus_high": {
            metric: {
                "mean": float(low[metric].mean() - high[metric].mean()),
                "bootstrap_95pct": bootstrap_state_difference(weekly, metric, state_column),
            }
            for metric in metrics
        },
    }


def regression_summary(weekly: pd.DataFrame, controlled: bool) -> dict[str, Any]:
    columns = ["log_dispersion_ratio"]
    if controlled:
        columns += ["market_volatility_30d", "average_correlation_60d"]
    x = weekly[columns].copy()
    x = (x - x.mean()) / x.std(ddof=1)
    result = sm.OLS(weekly["spread"].to_numpy(float), sm.add_constant(x, has_constant="add")).fit(
        cov_type="HAC",
        cov_kwds={"maxlags": int(CONFIG["hac_lags"]), "use_correction": True},
    )
    coefficient = float(result.params["log_dispersion_ratio"])
    two_sided = float(result.pvalues["log_dispersion_ratio"])
    one_sided_negative = two_sided / 2.0 if coefficient < 0.0 else 1.0 - two_sided / 2.0
    return {
        "controlled": controlled,
        "observations": int(result.nobs),
        "r_squared": float(result.rsquared),
        "coefficients": {name: float(value) for name, value in result.params.items()},
        "hac_standard_errors": {name: float(value) for name, value in result.bse.items()},
        "two_sided_p_values": {name: float(value) for name, value in result.pvalues.items()},
        "dispersion_one_sided_negative_p": one_sided_negative,
    }


def max_drawdown(returns: pd.Series) -> float:
    equity = (1.0 + returns).cumprod()
    peak = pd.concat([pd.Series([1.0]), equity.reset_index(drop=True)]).cummax().iloc[1:].to_numpy()
    return float(np.min(equity.to_numpy() / peak - 1.0))


def selected_low_top(panel: pd.DataFrame) -> pd.DataFrame:
    selected: list[pd.DataFrame] = []
    for _entry, frame in panel.groupby("entry_time", sort=True):
        if bool(frame.iloc[0]["high_dispersion"]):
            continue
        ordered = frame.sort_values(["mom20", "symbol"], ascending=[False, True])
        tail = max(1, int(math.ceil(len(ordered) * float(CONFIG["tail_fraction"]))))
        chosen = ordered.head(tail).copy()
        chosen["selection_rank"] = np.arange(1, len(chosen) + 1)
        selected.append(chosen)
    if not selected:
        raise RuntimeError("no low-dispersion top selections")
    return pd.concat(selected, ignore_index=True)


def breadth_summary(selected: pd.DataFrame) -> dict[str, Any]:
    by_symbol = (
        selected.groupby(["symbol", "category"])
        .agg(
            selections=("target_excess_return", "size"),
            mean_excess_return=("target_excess_return", "mean"),
            total_excess_return=("target_excess_return", "sum"),
        )
        .reset_index()
    )
    positive = by_symbol[by_symbol["total_excess_return"] > 0.0]
    total = float(positive["total_excess_return"].sum())
    max_share = float(positive["total_excess_return"].max() / total) if total > 0.0 else 1.0
    return {
        "selected_symbols": int(len(by_symbol)),
        "positive_mean_symbol_fraction": float((by_symbol["mean_excess_return"] > 0.0).mean()),
        "maximum_positive_contribution_share": max_share,
        "by_symbol": by_symbol.sort_values("symbol").to_dict(orient="records"),
    }


def command_self_test(_args: argparse.Namespace) -> None:
    dispersion = pd.Series(np.r_[np.ones(252), 2.0, 0.5])
    median = dispersion.expanding(min_periods=252).median()
    ratios = np.log(dispersion / median)
    if not ratios.iloc[252] > 0.0 or not ratios.iloc[253] < 0.0:
        raise RuntimeError("dispersion state orientation failed")
    x = np.linspace(-2.0, 2.0, 104)
    control = np.sin(np.arange(104) / 7.0)
    y = 0.01 - 0.02 * x + 0.003 * control
    sample = pd.DataFrame({
        "spread": y,
        "log_dispersion_ratio": x,
        "market_volatility_30d": control,
        "average_correlation_60d": np.cos(np.arange(104) / 9.0),
    })
    regression = regression_summary(sample, controlled=True)
    if regression["coefficients"]["log_dispersion_ratio"] >= 0.0:
        raise RuntimeError("regression dispersion orientation failed")
    values = np.arange(1.0, 21.0)
    if block_bootstrap_mean_ci(values) != block_bootstrap_mean_ci(values):
        raise RuntimeError("bootstrap is not deterministic")
    print(json.dumps({
        "status": "PASS",
        "high_state_ratio": float(ratios.iloc[252]),
        "low_state_ratio": float(ratios.iloc[253]),
        "synthetic_dispersion_coefficient": regression["coefficients"]["log_dispersion_ratio"],
        "bootstrap_deterministic": True,
    }, indent=2))


def command_prepare(args: argparse.Namespace) -> None:
    checkpoint = ensure_checkpoint()
    bars, metadata = load_bars(args.stage)
    daily = make_daily_frames(bars)
    state = build_daily_state(daily, args.stage)
    panel, audit = build_panel(daily, state, args.stage)
    parent_dq_path = PARENT_DIR / "data_quality_development.json"
    parent_dq = read_json(parent_dq_path)
    target_failures = [item for item in audit["weeks"] if item["status"] == "DATA_QUALITY_FAIL_FUTURE_TARGET_MISSING"]
    action_counts = panel.groupby("entry_time")["symbol"].nunique()
    payload = {
        "checked_at_utc": iso_now(),
        "stage": args.stage,
        "status": "PASS" if parent_dq.get("status") == "PASS" and metadata.get("overlap_mismatch_rows", 0) == 0 and not target_failures else "FAIL",
        "checkpoint_digest": checkpoint["content_digest"],
        "parent_data_quality_sha256": sha256_file(parent_dq_path),
        "source_overlap": metadata,
        "scheduled_weeks": int(len(stage_entries(args.stage))),
        "action_weeks": int(panel["entry_time"].nunique()),
        "minimum_rankable_on_action_weeks": int(action_counts.min()),
        "maximum_rankable_on_action_weeks": int(action_counts.max()),
        "valid_daily_state_rows": int(state["log_dispersion_ratio"].notna().sum()),
        "future_target_missing_weeks": target_failures,
        "week_audit": audit["weeks"],
        "rule": "All state and eligibility inputs end at Saturday close; future target missing fails DQ rather than changing the ranked universe.",
    }
    write_json(HERE / f"data_quality_{args.stage}.json", payload, digest=True)
    print(json.dumps({
        "stage": args.stage,
        "status": payload["status"],
        "action_weeks": payload["action_weeks"],
        "minimum_rankable": payload["minimum_rankable_on_action_weeks"],
        "valid_daily_state_rows": payload["valid_daily_state_rows"],
    }, indent=2))


def command_analyze(args: argparse.Namespace) -> None:
    checkpoint = ensure_checkpoint()
    dq_path = HERE / f"data_quality_{args.stage}.json"
    if not dq_path.exists() or read_json(dq_path).get("status") != "PASS":
        raise RuntimeError(f"data quality is not PASS: {args.stage}")
    bars, _metadata = load_bars(args.stage)
    daily = make_daily_frames(bars)
    state = build_daily_state(daily, args.stage)
    panel, _audit = build_panel(daily, state, args.stage)
    weekly_frames = {days: weekly_for_momentum(panel, days) for days in [14, 20, 30]}
    weekly = weekly_frames[20]
    main_state = state_summary(weekly)
    tail_state = state_summary(weekly, "high_tail_dispersion")
    regressions = {
        "uncontrolled": regression_summary(weekly, controlled=False),
        "controlled": regression_summary(weekly, controlled=True),
    }
    notional = float(CONFIG["notional_fraction"])
    cost = float(CONFIG["stress_round_trip_underlying"])
    hurdle = float(CONFIG["annual_full_plan_hurdle"]) / 52.0
    low = ~weekly["high_dispersion"]
    gated_proxy = pd.Series(np.where(low, notional * (weekly["top_asset_return"] - cost), 0.0) - hurdle)
    unconditional_proxy = notional * (weekly["top_asset_return"] - cost) - hurdle
    proxy_increment = gated_proxy - unconditional_proxy
    proxy = {
        "gated_low_dispersion_high_cash_after_cost_hurdle": series_summary(gated_proxy),
        "unconditional_mom20_after_cost_hurdle": series_summary(unconditional_proxy),
        "gated_minus_unconditional": series_summary(proxy_increment),
        "gated_max_drawdown": max_drawdown(gated_proxy),
        "unconditional_max_drawdown": max_drawdown(unconditional_proxy),
        "funding_included": False,
    }
    years: dict[str, Any] = {}
    for year, frame in weekly.groupby(weekly["entry_time"].dt.year):
        summary = state_summary(frame)
        years[str(year)] = summary
    neighbor_states = {f"mom{days}": state_summary(frame) for days, frame in weekly_frames.items() if days != 20}
    selected = selected_low_top(panel)
    breadth = breadth_summary(selected)
    low_summary = main_state["low"]
    state_diff = main_state["low_minus_high"]
    yearly_gates = {
        year: item["low_minus_high"]["spread"]["mean"] > 0.0
        and item["low"]["spread"]["mean"] > 0.0
        and item["low"]["top_excess_return"]["mean"] > 0.0
        for year, item in years.items()
    }
    neighbor_gates = {
        name: item["low_minus_high"]["spread"]["mean"] > 0.0 for name, item in neighbor_states.items()
    }
    neighbor_gates["high_tail"] = tail_state["low_minus_high"]["spread"]["mean"] > 0.0
    hard_gates = {
        "data_quality_pass": read_json(dq_path).get("status") == "PASS",
        "minimum_action_weeks": len(weekly) >= int(CONFIG["minimum_action_weeks"]),
        "minimum_low_state_weeks": main_state["low_weeks"] >= int(CONFIG["minimum_state_weeks"]),
        "minimum_high_state_weeks": main_state["high_weeks"] >= int(CONFIG["minimum_state_weeks"]),
        "low_spread_mean_positive": low_summary["spread"]["mean"] > 0.0,
        "low_spread_bootstrap_lower_positive": low_summary["spread"]["bootstrap_95pct"][0] > 0.0,
        "low_top_excess_mean_positive": low_summary["top_excess_return"]["mean"] > 0.0,
        "low_top_excess_bootstrap_lower_positive": low_summary["top_excess_return"]["bootstrap_95pct"][0] > 0.0,
        "low_minus_high_spread_mean_positive": state_diff["spread"]["mean"] > 0.0,
        "low_minus_high_spread_bootstrap_lower_positive": state_diff["spread"]["bootstrap_95pct"][0] > 0.0,
        "uncontrolled_dispersion_slope_negative_significant": regressions["uncontrolled"]["coefficients"]["log_dispersion_ratio"] < 0.0 and regressions["uncontrolled"]["dispersion_one_sided_negative_p"] < 0.05,
        "controlled_dispersion_slope_negative_significant": regressions["controlled"]["coefficients"]["log_dispersion_ratio"] < 0.0 and regressions["controlled"]["dispersion_one_sided_negative_p"] < 0.05,
        "low_top_asset_above_conditional_floor": low_summary["top_asset_return"]["mean"] > float(CONFIG["conditional_underlying_floor"]),
        "gated_proxy_mean_positive": proxy["gated_low_dispersion_high_cash_after_cost_hurdle"]["mean"] > 0.0,
        "gated_proxy_bootstrap_lower_positive": proxy["gated_low_dispersion_high_cash_after_cost_hurdle"]["bootstrap_95pct"][0] > 0.0,
        "gated_beats_unconditional_mean": proxy["gated_minus_unconditional"]["mean"] > 0.0,
        "gated_beats_unconditional_bootstrap_lower_positive": proxy["gated_minus_unconditional"]["bootstrap_95pct"][0] > 0.0,
        "all_calendar_years_directionally_pass": all(yearly_gates.values()),
        "all_fixed_neighbors_directionally_pass": all(neighbor_gates.values()),
        "minimum_selected_symbols": breadth["selected_symbols"] >= int(CONFIG["minimum_selected_symbols"]),
        "positive_symbol_breadth": breadth["positive_mean_symbol_fraction"] >= float(CONFIG["minimum_positive_symbol_fraction"]),
        "positive_contribution_not_concentrated": breadth["maximum_positive_contribution_share"] <= float(CONFIG["maximum_positive_contribution_share"]),
    }
    all_pass = all(hard_gates.values())
    csv_frames = {
        f"{args.stage}_daily_state.csv": state,
        f"{args.stage}_panel.csv": panel,
        f"{args.stage}_weekly.csv": pd.concat(weekly_frames.values(), ignore_index=True),
        f"{args.stage}_low_dispersion_top_selected.csv": selected,
    }
    csv_hashes: dict[str, str] = {}
    for name, frame in csv_frames.items():
        path = HERE / name
        frame.to_csv(path, index=False, date_format="%Y-%m-%dT%H:%M:%SZ", float_format="%.12g")
        csv_hashes[name] = sha256_file(path)
    payload = {
        "generated_at_utc": iso_now(),
        "stage": args.stage,
        "checkpoint_digest": checkpoint["content_digest"],
        "data_quality_digest": read_json(dq_path)["content_digest"],
        "question_result": "SUPPORTS_WITHIN_SCOPE" if all_pass else "DOES_NOT_SUPPORT",
        "release_next_stage": all_pass,
        "main_state_summary": main_state,
        "high_tail_state_summary": tail_state,
        "regressions": regressions,
        "economic_proxy": proxy,
        "calendar_years": years,
        "calendar_year_gates": yearly_gates,
        "neighbor_state_summaries": neighbor_states,
        "neighbor_gates": neighbor_gates,
        "breadth": breadth,
        "hard_gates": hard_gates,
        "failed_hard_gates": [name for name, passed in hard_gates.items() if not passed],
        "interpretation_limit": "Predictive state gate only; no actual funding or strategy handoff.",
        "csv_sha256": csv_hashes,
    }
    write_json(HERE / f"{args.stage}.json", payload, digest=True)
    if args.stage == "development":
        write_json(HERE / "results.json", payload, digest=True)
    print(json.dumps({
        "stage": args.stage,
        "result": payload["question_result"],
        "low_weeks": main_state["low_weeks"],
        "high_weeks": main_state["high_weeks"],
        "low_spread": low_summary["spread"]["mean"],
        "high_spread": main_state["high"]["spread"]["mean"],
        "low_minus_high": state_diff["spread"]["mean"],
        "controlled_dispersion_slope": regressions["controlled"]["coefficients"]["log_dispersion_ratio"],
        "controlled_one_sided_p": regressions["controlled"]["dispersion_one_sided_negative_p"],
        "gated_proxy_mean": proxy["gated_low_dispersion_high_cash_after_cost_hurdle"]["mean"],
        "failed_gates": payload["failed_hard_gates"],
    }, indent=2))


def command_gate(args: argparse.Namespace) -> None:
    checkpoint = ensure_checkpoint()
    result_path = HERE / f"{args.stage}.json"
    if not result_path.exists():
        raise RuntimeError(f"missing result: {result_path.name}")
    result = read_json(result_path)
    if canonical_digest(result) != result.get("content_digest"):
        raise RuntimeError("result digest mismatch")
    status = "PASS" if result.get("release_next_stage") and all(result["hard_gates"].values()) else "FAIL"
    gate = {
        "checked_at_utc": iso_now(),
        "stage": args.stage,
        "status": status,
        "checkpoint_digest": checkpoint["content_digest"],
        "result_digest": result["content_digest"],
        "question_result": result["question_result"],
        "failed_hard_gates": result["failed_hard_gates"],
        "next_stage_released": status == "PASS",
    }
    write_json(HERE / f"{args.stage}_gate.json", gate, digest=True)
    state = result["main_state_summary"]
    regression = result["regressions"]["controlled"]
    proxy = result["economic_proxy"]["gated_low_dispersion_high_cash_after_cost_hurdle"]
    text = f"""# {args.stage} 结果摘要

## Answer first

`{result['question_result']}`

低/高分散状态分别有 `{state['low_weeks']}/{state['high_weeks']}` 周；MOM20 spread 分别为 `{state['low']['spread']['mean']:.4%}` / `{state['high']['spread']['mean']:.4%}`，低减高为 `{state['low_minus_high']['spread']['mean']:.4%}`。控制市场波动和平均相关后的标准化 dispersion 系数为 `{regression['coefficients']['log_dispersion_ratio']:.6f}`，单侧 HAC p=`{regression['dispersion_one_sided_negative_p']:.4f}`。

低分散行动、高分散现金的 0.25x 粗略成本/资金门代理周均为 `{proxy['mean']:.4%}`。失败硬门：`{', '.join(result['failed_hard_gates']) if result['failed_hard_gates'] else '无'}`。

本题不包含实际 funding 或策略执行；FAIL 时 evaluation 与策略转换保持封存，不按结果调整分散度或动量定义。
"""
    (HERE / "result.md").write_text(text, encoding="utf-8")
    print(json.dumps({"stage": args.stage, "status": status, "result": result["question_result"]}, indent=2))


def command_validate(_args: argparse.Namespace) -> None:
    checkpoint = ensure_checkpoint()
    verified_json: dict[str, str] = {}
    for path in sorted(HERE.glob("*.json")):
        payload = read_json(path)
        if "content_digest" not in payload:
            continue
        if canonical_digest(payload) != payload["content_digest"]:
            raise RuntimeError(f"JSON digest mismatch: {path.name}")
        verified_json[path.name] = payload["content_digest"]
    verified_csv: dict[str, str] = {}
    for result_path in [HERE / "development.json", HERE / "evaluation.json"]:
        if not result_path.exists():
            continue
        result = read_json(result_path)
        for name, expected in result.get("csv_sha256", {}).items():
            actual = sha256_file(HERE / name)
            if actual != expected:
                raise RuntimeError(f"CSV digest mismatch: {name}")
            verified_csv[name] = actual
    command_self_test(argparse.Namespace())
    print(json.dumps({
        "status": "PASS",
        "checkpoint_digest": checkpoint["content_digest"],
        "verified_json": verified_json,
        "verified_csv": verified_csv,
    }, indent=2))


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser()
    sub = root.add_subparsers(dest="command", required=True)
    for name, func in [("self-test", command_self_test), ("checkpoint", command_checkpoint), ("validate", command_validate)]:
        item = sub.add_parser(name)
        item.set_defaults(func=func)
    for name, func in [("prepare", command_prepare), ("analyze", command_analyze), ("gate", command_gate)]:
        item = sub.add_parser(name)
        item.add_argument("--stage", choices=tuple(STAGES), required=True)
        item.set_defaults(func=func)
    return root


def main() -> None:
    args = parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
