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
from scipy.stats import spearmanr
import statsmodels
import statsmodels.api as sm


HERE = Path(__file__).resolve().parent
BASE_DIR = HERE.parent / "cross-sectional-dispersion-momentum-state-predictability"
BASE_STUDY = BASE_DIR / "study.py"


def load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


base = load_module(BASE_STUDY, "halpha_ivol_public_data_adapter")
ptv = base.parent.parent
SYMBOLS = list(base.parent.SYMBOLS)
CATEGORY_MEMBERS = dict(base.parent.CATEGORY_MEMBERS)
SYMBOL_TO_CATEGORY = dict(base.parent.SYMBOL_TO_CATEGORY)
UNIVERSE_PATH = base.parent.UNIVERSE_PATH
Q20_DIR = ptv.Q21_DIR.parent / "price-path-continuity-weekly-winner-long"

STAGES = {
    "development": ("2022-01-01T00:00:00Z", "2024-01-01T00:00:00Z"),
    "evaluation": ("2024-01-01T00:00:00Z", "2025-01-01T00:00:00Z"),
}
VARIANTS = {"ivol60": 60, "ivol90": 90, "ivol120": 120}
CONTROL_COLUMNS = ["tvol90", "max28", "mom90", "beta90", "log_volume30"]
CONFIG = {
    "predictor_id": "RESEARCH_MATURE_PERP_IVOL90_MONTHLY_RETURN_V1",
    "main_variant": "ivol90",
    "minimum_rankable_symbols": 20,
    "minimum_median_quote_volume_30d": 10_000_000.0,
    "history_returns": 120,
    "tail_fraction": 0.20,
    "gap_full_days": 1,
    "notional_fraction": 0.25,
    "stress_round_trip_underlying": 0.0052,
    "annual_full_plan_hurdle": 0.04,
    "bootstrap": {"block_months": 3, "repetitions": 5000, "seed": 20260722},
    "hac_maxlags": 3,
}
FROZEN_FILES = ["README.md", "sources.md", "preregistration.md", "study.py"]


def iso_now() -> str:
    return pd.Timestamp.now(tz="UTC").isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    if isinstance(value, (pd.Timestamp, np.datetime64)):
        return pd.Timestamp(value).isoformat()
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return None if not np.isfinite(value) else float(value)
    if isinstance(value, float):
        return None if not math.isfinite(value) else value
    if isinstance(value, np.bool_):
        return bool(value)
    return value


def canonical_digest(value: Any) -> str:
    payload = dict(value)
    payload.pop("content_digest", None)
    encoded = json.dumps(jsonable(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def write_json(path: Path, value: dict[str, Any], *, digest: bool = True) -> None:
    payload = jsonable(value)
    if digest:
        payload["content_digest"] = canonical_digest(payload)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def source_entries() -> list[dict[str, Any]]:
    paths = [
        (BASE_DIR / "checkpoint.json", "immediate public-data adapter checkpoint"),
        (BASE_DIR / "source_reuse_manifest.json", "immediate public-data identity chain"),
        (BASE_DIR / "data_quality_development.json", "reused 2022-2023 source quality evidence"),
        (ptv.HERE / "checkpoint.json", "public-data loader checkpoint"),
        (ptv.HERE / "source_reuse_manifest.json", "development source identity chain"),
        (Q20_DIR / "checkpoint.json", "sealed 2024 public-data adapter checkpoint"),
        (Q20_DIR / "data_quality_development.json", "2024 source quality evidence"),
        (UNIVERSE_PATH, "frozen current target universe and categories"),
    ]
    entries: list[dict[str, Any]] = []
    for path, role in paths:
        if not path.exists():
            raise RuntimeError(f"missing source identity: {path}")
        entries.append(
            {
                "path": str(path.resolve()),
                "role": role,
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return entries


def ensure_checkpoint() -> dict[str, Any]:
    path = HERE / "checkpoint.json"
    if not path.exists():
        raise RuntimeError("checkpoint missing")
    checkpoint = read_json(path)
    if checkpoint.get("content_digest") != canonical_digest(checkpoint):
        raise RuntimeError("checkpoint digest mismatch")
    if checkpoint.get("config") != CONFIG:
        raise RuntimeError("config differs from checkpoint")
    if checkpoint.get("stages") != {key: list(value) for key, value in STAGES.items()}:
        raise RuntimeError("stages differ from checkpoint")
    for name, expected in checkpoint["frozen_file_sha256"].items():
        if sha256_file(HERE / name) != expected:
            raise RuntimeError(f"frozen file changed: {name}")
    reuse = read_json(HERE / "source_reuse_manifest.json")
    if reuse.get("content_digest") != canonical_digest(reuse):
        raise RuntimeError("source reuse manifest digest mismatch")
    if reuse["content_digest"] != checkpoint["source_reuse_digest"]:
        raise RuntimeError("source identity differs from checkpoint")
    for item in reuse["entries"]:
        source = Path(item["path"])
        if (
            not source.exists()
            or source.stat().st_size != int(item["bytes"])
            or sha256_file(source) != item["sha256"]
        ):
            raise RuntimeError(f"reused source changed: {source}")
    return checkpoint


def command_checkpoint(_args: argparse.Namespace) -> None:
    path = HERE / "checkpoint.json"
    if path.exists():
        checkpoint = ensure_checkpoint()
        print(json.dumps({"reused": True, "digest": checkpoint["content_digest"]}, indent=2))
        return
    ptv.validate_universe()
    reuse = {"created_at_utc": iso_now(), "entries": source_entries()}
    write_json(HERE / "source_reuse_manifest.json", reuse)
    payload = {
        "created_at_utc": iso_now(),
        "baseline_commit": "0bdfeffa616260cebd2d2188ddc8deb9e85c77f4",
        "formal_strategy_background": "ONE_SHOT_DONCHIAN_ATR_BREAKOUT 1.0.1 / BTCUSDT-PERP",
        "research_kind": "PREDICTIVE",
        "question": (
            "Does trailing leave-one-out market-model idiosyncratic volatility negatively predict next-month "
            "returns among 25 mature Binance USD-M perpetuals after total-volatility, MAX, momentum, beta and "
            "volume controls, with enough gross room to justify a separate one-shot strategy study?"
        ),
        "hypothesis_direction": "negative IVOL90 coefficient; positive low-minus-high return spread",
        "stages": {key: list(value) for key, value in STAGES.items()},
        "config": CONFIG,
        "universe": {"symbols": SYMBOLS, "categories": CATEGORY_MEMBERS},
        "stage_open_rule": "development must pass every frozen gate before evaluation may be opened",
        "family_stop_rule": (
            "Any development failure seals evaluation and prohibits changing direction, universe, factor model, "
            "formation window, tail, controls, cost proxy, stage or threshold without a new independent mechanism."
        ),
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
    write_json(path, payload)
    checkpoint = read_json(path)
    print(json.dumps({"reused": False, "digest": checkpoint["content_digest"]}, indent=2))


def stage_authorized(stage: str) -> None:
    if stage == "evaluation":
        gate_path = HERE / "development_gate.json"
        if not gate_path.exists() or read_json(gate_path).get("status") != "PASS":
            raise RuntimeError("evaluation remains sealed until development PASS")


def month_entries(stage: str) -> pd.DatetimeIndex:
    start, end = map(pd.Timestamp, STAGES[stage])
    return pd.date_range(start, end, freq="MS", inclusive="left")


def load_bars(stage: str) -> tuple[dict[str, pd.DataFrame], dict[str, Any]]:
    ensure_checkpoint()
    stage_authorized(stage)
    bars, _funding, metadata = ptv.load_stage(stage)
    return bars, metadata


def daily_frames(bars: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    output: dict[str, pd.DataFrame] = {}
    for symbol, raw in bars.items():
        frame = raw.sort_index().copy()
        frame = frame.reindex(pd.date_range(frame.index.min(), frame.index.max(), freq="1D"))
        frame["log_return"] = np.log(frame["close"]).diff()
        frame["median_quote_volume_30d"] = frame["quote_volume"].rolling(30, min_periods=30).median()
        output[symbol] = frame
    return output


def fit_market_model(y: np.ndarray, x: np.ndarray) -> tuple[float, float, float]:
    model = sm.OLS(np.asarray(y, float), sm.add_constant(np.asarray(x, float), has_constant="add")).fit()
    alpha, beta = map(float, model.params)
    residual = np.asarray(model.resid, float)
    return alpha, beta, float(np.std(residual, ddof=1))


def build_panel(bars: dict[str, pd.DataFrame], stage: str) -> tuple[pd.DataFrame, dict[str, Any]]:
    daily = daily_frames(bars)
    rows: list[dict[str, Any]] = []
    audit: list[dict[str, Any]] = []
    history_returns = int(CONFIG["history_returns"])
    for entry in month_entries(stage):
        cutoff = entry - pd.Timedelta(days=2)
        exit_time = entry + pd.offsets.MonthBegin(1)
        eligible: list[str] = []
        histories: dict[str, np.ndarray] = {}
        future_prices: dict[str, tuple[float, float]] = {}
        future_missing: list[str] = []
        for symbol in SYMBOLS:
            frame = daily[symbol]
            dates = pd.date_range(cutoff - pd.Timedelta(days=history_returns), cutoff, freq="1D")
            if not dates.isin(frame.index).all():
                continue
            history = frame.loc[dates]
            if history[["open", "high", "low", "close", "quote_volume"]].isna().any().any():
                continue
            if (history[["open", "high", "low", "close"]] <= 0.0).any().any():
                continue
            volume = frame.at[cutoff, "median_quote_volume_30d"]
            if pd.isna(volume) or float(volume) < float(CONFIG["minimum_median_quote_volume_30d"]):
                continue
            eligible.append(symbol)
            histories[symbol] = np.diff(np.log(history["close"].to_numpy(float)))
            if (
                entry not in frame.index
                or exit_time not in frame.index
                or pd.isna(frame.at[entry, "open"])
                or pd.isna(frame.at[exit_time, "open"])
            ):
                future_missing.append(symbol)
            else:
                future_prices[symbol] = (
                    float(frame.at[entry, "open"]),
                    float(frame.at[exit_time, "open"]),
                )
        item = {
            "entry_time": entry,
            "signal_cutoff": cutoff,
            "exit_time": exit_time,
            "decision_eligible_count": len(eligible),
            "future_missing_symbols": sorted(future_missing),
            "status": "NO_ACTION_TOO_FEW_ELIGIBLE",
        }
        if len(eligible) < int(CONFIG["minimum_rankable_symbols"]):
            audit.append(item)
            continue
        if future_missing:
            item["status"] = "DATA_QUALITY_FAIL_FUTURE_TARGET_MISSING"
            audit.append(item)
            continue
        ordered = sorted(eligible)
        matrix = np.column_stack([histories[symbol] for symbol in ordered])
        market_sum = matrix.sum(axis=1)
        next_returns = {
            symbol: future_prices[symbol][1] / future_prices[symbol][0] - 1.0 for symbol in ordered
        }
        next_market = float(np.mean(list(next_returns.values())))
        for column, symbol in enumerate(ordered):
            y = matrix[:, column]
            market_ex_self = (market_sum - y) / (len(ordered) - 1)
            features: dict[str, float] = {}
            main_alpha = math.nan
            main_beta = math.nan
            for name, days in VARIANTS.items():
                alpha, beta, ivol = fit_market_model(y[-days:], market_ex_self[-days:])
                features[name] = ivol
                if name == CONFIG["main_variant"]:
                    main_alpha, main_beta = alpha, beta
            frame = daily[symbol]
            volume = float(frame.at[cutoff, "median_quote_volume_30d"])
            rows.append(
                {
                    "entry_time": entry,
                    "signal_cutoff": cutoff,
                    "exit_time": exit_time,
                    "holding_days": int((exit_time - entry).days),
                    "symbol": symbol,
                    "category": SYMBOL_TO_CATEGORY[symbol],
                    "eligible_count": len(ordered),
                    **features,
                    "alpha90": main_alpha,
                    "beta90": main_beta,
                    "tvol90": float(np.std(y[-90:], ddof=1)),
                    "max28": float(np.max(y[-28:])),
                    "mom90": float(np.sum(y[-90:])),
                    "log_volume30": float(np.log(volume)),
                    "entry_price": future_prices[symbol][0],
                    "exit_price": future_prices[symbol][1],
                    "target_asset_return": next_returns[symbol],
                    "target_market_return": next_market,
                    "target_excess_return": next_returns[symbol] - next_market,
                }
            )
        item["status"] = "ACTION"
        audit.append(item)
    if not rows:
        raise RuntimeError(f"empty panel: {stage}")
    panel = pd.DataFrame(rows).replace([np.inf, -np.inf], np.nan)
    required = list(VARIANTS) + CONTROL_COLUMNS + ["target_asset_return", "target_excess_return"]
    if panel[required].isna().any().any():
        raise RuntimeError("panel contains non-finite required values")
    return panel.sort_values(["entry_time", "symbol"]).reset_index(drop=True), {"months": audit}


def block_bootstrap_mean_ci(values: np.ndarray) -> list[float]:
    values = np.asarray(values, float)
    if len(values) == 0 or not np.isfinite(values).all():
        raise RuntimeError("bootstrap input empty or non-finite")
    block = int(CONFIG["bootstrap"]["block_months"])
    reps = int(CONFIG["bootstrap"]["repetitions"])
    rng = np.random.default_rng(int(CONFIG["bootstrap"]["seed"])+len(values))
    means = np.empty(reps)
    for index in range(reps):
        selected: list[int] = []
        while len(selected) < len(values):
            start = int(rng.integers(0, len(values)))
            selected.extend(((start + np.arange(block)) % len(values)).tolist())
        means[index] = float(values[np.asarray(selected[: len(values)])].mean())
    return [float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975))]


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


def monthly_for_variant(panel: pd.DataFrame, score_column: str) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for entry, frame in panel.groupby("entry_time", sort=True):
        ordered = frame.sort_values([score_column, "symbol"], ascending=[True, True])
        tail = max(1, int(math.ceil(len(ordered) * float(CONFIG["tail_fraction"]))))
        low = ordered.head(tail)
        high = ordered.tail(tail)
        tvol_high = frame.sort_values(["tvol90", "symbol"], ascending=[False, True]).head(tail)
        rank_ic = spearmanr(frame[score_column], frame["target_excess_return"]).statistic
        ivol_tvol = spearmanr(frame[score_column], frame["tvol90"]).statistic
        ivol_max = spearmanr(frame[score_column], frame["max28"]).statistic
        high_return = float(high["target_asset_return"].mean())
        holding_days = int(frame["holding_days"].iloc[0])
        proxy = (
            float(CONFIG["notional_fraction"])
            * (-high_return - float(CONFIG["stress_round_trip_underlying"]))
            - float(CONFIG["annual_full_plan_hurdle"]) * holding_days / 365.0
        )
        rows.append(
            {
                "entry_time": entry,
                "variant": score_column,
                "eligible_count": int(len(frame)),
                "tail_count": tail,
                "holding_days": holding_days,
                "low_symbols": "|".join(low["symbol"].tolist()),
                "high_symbols": "|".join(high["symbol"].tolist()),
                "low_asset_return": float(low["target_asset_return"].mean()),
                "high_asset_return": high_return,
                "low_minus_high_return": float(
                    low["target_asset_return"].mean() - high["target_asset_return"].mean()
                ),
                "rank_ic": float(rank_ic),
                "ivol_tvol_spearman": float(ivol_tvol),
                "ivol_max_spearman": float(ivol_max),
                "tvol_high_asset_return": float(tvol_high["target_asset_return"].mean()),
                "tvol_high_minus_ivol_high": float(
                    tvol_high["target_asset_return"].mean() - high["target_asset_return"].mean()
                ),
                "high_ivol_short_proxy": proxy,
            }
        )
    return pd.DataFrame(rows).sort_values("entry_time").reset_index(drop=True)


def selected_high_rows(panel: pd.DataFrame, score_column: str) -> pd.DataFrame:
    selected: list[pd.DataFrame] = []
    for _entry, frame in panel.groupby("entry_time", sort=True):
        ordered = frame.sort_values([score_column, "symbol"], ascending=[False, True])
        tail = max(1, int(math.ceil(len(ordered) * float(CONFIG["tail_fraction"]))))
        chosen = ordered.head(tail).copy()
        chosen["selection_rank"] = np.arange(1, len(chosen) + 1)
        selected.append(chosen)
    return pd.concat(selected, ignore_index=True)


def summarize_monthly(monthly: pd.DataFrame) -> dict[str, Any]:
    return {
        "action_months": int(len(monthly)),
        "low_asset_return": series_summary(monthly["low_asset_return"]),
        "high_asset_return": series_summary(monthly["high_asset_return"]),
        "low_minus_high_return": series_summary(monthly["low_minus_high_return"]),
        "rank_ic": series_summary(monthly["rank_ic"]),
        "high_ivol_short_proxy": series_summary(monthly["high_ivol_short_proxy"]),
        "tvol_high_minus_ivol_high": series_summary(monthly["tvol_high_minus_ivol_high"]),
        "ivol_tvol_spearman": {
            **series_summary(monthly["ivol_tvol_spearman"]),
            "median_absolute": float(monthly["ivol_tvol_spearman"].abs().median()),
        },
        "ivol_max_spearman": {
            **series_summary(monthly["ivol_max_spearman"]),
            "median_absolute": float(monthly["ivol_max_spearman"].abs().median()),
        },
    }


def fama_macbeth(panel: pd.DataFrame, controlled: bool) -> tuple[dict[str, Any], pd.DataFrame]:
    predictors = ["ivol90"] + (CONTROL_COLUMNS if controlled else [])
    rows: list[dict[str, Any]] = []
    for entry, frame in panel.groupby("entry_time", sort=True):
        design = pd.DataFrame(index=frame.index)
        for column in predictors:
            scale = float(frame[column].std(ddof=1))
            if not math.isfinite(scale) or scale <= 0.0:
                raise RuntimeError(f"zero cross-sectional scale: {entry} {column}")
            design[column] = (frame[column] - float(frame[column].mean())) / scale
        model = sm.OLS(
            frame["target_excess_return"].to_numpy(float),
            sm.add_constant(design.to_numpy(float), has_constant="add"),
        ).fit()
        row: dict[str, Any] = {"entry_time": entry, "intercept": float(model.params[0])}
        row.update({name: float(model.params[index + 1]) for index, name in enumerate(predictors)})
        rows.append(row)
    coefficients = pd.DataFrame(rows).sort_values("entry_time").reset_index(drop=True)
    values = coefficients["ivol90"].to_numpy(float)
    hac = sm.OLS(values, np.ones((len(values), 1))).fit(
        cov_type="HAC", cov_kwds={"maxlags": int(CONFIG["hac_maxlags"])}
    )
    mean = float(hac.params[0])
    two_sided = float(hac.pvalues[0])
    one_sided_negative = two_sided / 2.0 if mean < 0.0 else 1.0 - two_sided / 2.0
    return (
        {
            "controlled": controlled,
            "months": int(len(values)),
            "predictors": predictors,
            "ivol90_coefficient_mean": mean,
            "hac_standard_error": float(hac.bse[0]),
            "hac_t_statistic": float(hac.tvalues[0]),
            "hac_two_sided_p": two_sided,
            "hac_one_sided_negative_p": one_sided_negative,
            "coefficient_bootstrap_95pct": block_bootstrap_mean_ci(values),
        },
        coefficients,
    )


def year_summaries(monthly: pd.DataFrame) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for year, frame in monthly.groupby(monthly["entry_time"].dt.year, sort=True):
        output[str(int(year))] = {
            "months": int(len(frame)),
            "low_minus_high_return_mean": float(frame["low_minus_high_return"].mean()),
            "rank_ic_mean": float(frame["rank_ic"].mean()),
            "high_ivol_short_proxy_mean": float(frame["high_ivol_short_proxy"].mean()),
        }
    return output


def breadth_summary(selected: pd.DataFrame) -> dict[str, Any]:
    by_symbol = (
        selected.groupby(["symbol", "category"])
        .agg(
            selections=("target_asset_return", "size"),
            mean_asset_return=("target_asset_return", "mean"),
            total_short_gross=("target_asset_return", lambda value: float(-value.sum())),
        )
        .reset_index()
    )
    eligible = by_symbol[by_symbol["selections"] >= 2]
    positive = by_symbol[by_symbol["total_short_gross"] > 0.0]
    positive_total = float(positive["total_short_gross"].sum())
    max_share = (
        float(positive["total_short_gross"].max() / positive_total) if positive_total > 0.0 else 1.0
    )
    return {
        "selected_symbols": int(len(by_symbol)),
        "selected_categories": int(by_symbol["category"].nunique()),
        "symbols_with_at_least_two_selections": int(len(eligible)),
        "negative_mean_fraction_among_repeat_symbols": (
            float((eligible["mean_asset_return"] < 0.0).mean()) if len(eligible) else 0.0
        ),
        "maximum_positive_short_contribution_share": max_share,
        "by_symbol": by_symbol.sort_values("symbol").to_dict(orient="records"),
    }


def command_self_test(_args: argparse.Namespace) -> None:
    market = np.linspace(-0.02, 0.02, 120)
    low_noise = 0.002 * np.sin(np.arange(120))
    high_noise = 0.02 * np.sin(np.arange(120))
    _a1, beta1, ivol1 = fit_market_model(1.2 * market + low_noise, market)
    _a2, beta2, ivol2 = fit_market_model(0.7 * market + high_noise, market)
    if not ivol2 > ivol1 or abs(beta1 - 1.2) > 0.05 or abs(beta2 - 0.7) > 0.05:
        raise RuntimeError("market-model IVOL orientation failed")
    synthetic_months = pd.date_range("2022-01-01T00:00:00Z", periods=12, freq="MS")
    synthetic = pd.DataFrame(
        {
            "entry_time": np.repeat(synthetic_months, 20),
            "target_excess_return": np.tile(np.linspace(0.10, -0.10, 20), 12),
            "ivol90": np.tile(np.linspace(0.01, 0.20, 20), 12),
            "tvol90": np.tile(np.linspace(0.02, 0.21, 20), 12),
            "max28": np.tile(np.linspace(0.03, 0.22, 20), 12),
            "mom90": np.zeros(240),
            "beta90": np.tile(np.linspace(0.5, 1.5, 20), 12),
            "log_volume30": np.tile(np.linspace(15.0, 18.0, 20), 12),
        }
    )
    uncontrolled, _coefficients = fama_macbeth(synthetic, controlled=False)
    if uncontrolled["ivol90_coefficient_mean"] >= 0.0:
        raise RuntimeError("Fama-MacBeth IVOL direction failed")
    values = np.arange(1.0, 25.0)
    if block_bootstrap_mean_ci(values) != block_bootstrap_mean_ci(values):
        raise RuntimeError("bootstrap is not deterministic")
    print(
        json.dumps(
            {
                "status": "PASS",
                "low_ivol": ivol1,
                "high_ivol": ivol2,
                "synthetic_ivol_slope": uncontrolled["ivol90_coefficient_mean"],
                "bootstrap_deterministic": True,
            },
            indent=2,
        )
    )


def command_prepare(args: argparse.Namespace) -> None:
    checkpoint = ensure_checkpoint()
    bars, metadata = load_bars(args.stage)
    panel, audit = build_panel(bars, args.stage)
    target_failures = [
        item for item in audit["months"] if item["status"] == "DATA_QUALITY_FAIL_FUTURE_TARGET_MISSING"
    ]
    counts = panel.groupby("entry_time")["symbol"].nunique()
    payload = {
        "checked_at_utc": iso_now(),
        "stage": args.stage,
        "status": "PASS" if metadata.get("overlap_mismatch_rows", 0) == 0 and not target_failures else "FAIL",
        "checkpoint_digest": checkpoint["content_digest"],
        "source_overlap": metadata,
        "scheduled_months": int(len(month_entries(args.stage))),
        "action_months": int(panel["entry_time"].nunique()),
        "global_no_action_months": int(
            sum(item["status"] == "NO_ACTION_TOO_FEW_ELIGIBLE" for item in audit["months"])
        ),
        "minimum_rankable_on_action_months": int(counts.min()),
        "maximum_rankable_on_action_months": int(counts.max()),
        "future_target_missing_months": target_failures,
        "month_audit": audit["months"],
        "rule": "All signals end two UTC days before entry; future target missing fails DQ rather than changing tails.",
    }
    panel.to_csv(HERE / f"{args.stage}_panel.csv", index=False)
    write_json(HERE / f"data_quality_{args.stage}.json", payload)
    print(
        json.dumps(
            {
                "stage": args.stage,
                "status": payload["status"],
                "action_months": payload["action_months"],
                "minimum_rankable": payload["minimum_rankable_on_action_months"],
            },
            indent=2,
        )
    )


def load_panel(stage: str) -> pd.DataFrame:
    path = HERE / f"{stage}_panel.csv"
    if not path.exists():
        raise RuntimeError(f"panel missing: {stage}")
    return pd.read_csv(path, parse_dates=["entry_time", "signal_cutoff", "exit_time"])


def command_analyze(args: argparse.Namespace) -> None:
    checkpoint = ensure_checkpoint()
    dq_path = HERE / f"data_quality_{args.stage}.json"
    if not dq_path.exists() or read_json(dq_path).get("status") != "PASS":
        raise RuntimeError(f"data quality is not PASS: {args.stage}")
    panel = load_panel(args.stage)
    monthly_frames = {name: monthly_for_variant(panel, name) for name in VARIANTS}
    main = monthly_frames[str(CONFIG["main_variant"])]
    selected = selected_high_rows(panel, str(CONFIG["main_variant"]))
    uncontrolled, uncontrolled_coefficients = fama_macbeth(panel, controlled=False)
    controlled, controlled_coefficients = fama_macbeth(panel, controlled=True)
    result = {
        "analyzed_at_utc": iso_now(),
        "stage": args.stage,
        "checkpoint_digest": checkpoint["content_digest"],
        "period": {"start": STAGES[args.stage][0], "end_exclusive": STAGES[args.stage][1]},
        "main": summarize_monthly(main),
        "neighbors": {
            name: summarize_monthly(frame)
            for name, frame in monthly_frames.items()
            if name != CONFIG["main_variant"]
        },
        "regressions": {"uncontrolled": uncontrolled, "controlled": controlled},
        "calendar_years": year_summaries(main),
        "breadth": breadth_summary(selected),
        "cost_proxy_scope": (
            "0.25x high-IVOL short gross price proxy after 52bp underlying round-trip and 4% full-capital "
            "annual hurdle; funding, intramonth margin path and execution are intentionally absent."
        ),
        "limitations": [
            "fixed current-survivor universe rather than a point-in-time full market",
            "no market-cap control, delisted coins, micro-caps or newly listed coins",
            "daily OHLCV cannot model intramonth squeeze, book depth, queue, partial fills or manual activation delay",
            "predictive result cannot authorize a strategy, capital use or live-account action",
        ],
    }
    for name, frame in monthly_frames.items():
        frame.to_csv(HERE / f"{args.stage}_{name}_monthly.csv", index=False)
    selected.to_csv(HERE / f"{args.stage}_high_ivol_selected.csv", index=False)
    uncontrolled_coefficients.to_csv(HERE / f"{args.stage}_fmb_uncontrolled.csv", index=False)
    controlled_coefficients.to_csv(HERE / f"{args.stage}_fmb_controlled.csv", index=False)
    write_json(HERE / f"{args.stage}.json", result)
    write_json(HERE / "results.json", result)
    print(
        json.dumps(
            {
                "stage": args.stage,
                "months": result["main"]["action_months"],
                "low_minus_high": result["main"]["low_minus_high_return"]["mean"],
                "rank_ic": result["main"]["rank_ic"]["mean"],
                "controlled_ivol_slope": controlled["ivol90_coefficient_mean"],
                "controlled_one_sided_p": controlled["hac_one_sided_negative_p"],
                "short_proxy": result["main"]["high_ivol_short_proxy"]["mean"],
            },
            indent=2,
        )
    )


def gate_checks(stage: str, result: dict[str, Any], dq: dict[str, Any]) -> dict[str, bool]:
    main = result["main"]
    regressions = result["regressions"]
    years = result["calendar_years"]
    neighbors = result["neighbors"]
    breadth = result["breadth"]
    checks = {
        "data_quality_pass": dq.get("status") == "PASS",
        "minimum_21_action_months": int(main["action_months"]) >= (21 if stage == "development" else 10),
        "minimum_20_rankable_each_action_month": int(dq["minimum_rankable_on_action_months"]) >= 20,
        "no_future_target_missing": not dq["future_target_missing_months"],
        "low_minus_high_mean_positive": float(main["low_minus_high_return"]["mean"]) > 0.0,
        "low_minus_high_bootstrap_lower_positive": float(main["low_minus_high_return"]["bootstrap_95pct"][0]) > 0.0,
        "rank_ic_mean_negative": float(main["rank_ic"]["mean"]) < 0.0,
        "rank_ic_bootstrap_upper_negative": float(main["rank_ic"]["bootstrap_95pct"][1]) < 0.0,
        "uncontrolled_ivol_slope_negative_significant": (
            float(regressions["uncontrolled"]["ivol90_coefficient_mean"]) < 0.0
            and float(regressions["uncontrolled"]["hac_one_sided_negative_p"]) < 0.05
        ),
        "controlled_ivol_slope_negative_significant": (
            float(regressions["controlled"]["ivol90_coefficient_mean"]) < 0.0
            and float(regressions["controlled"]["hac_one_sided_negative_p"]) < 0.05
        ),
        "short_proxy_mean_positive": float(main["high_ivol_short_proxy"]["mean"]) > 0.0,
        "short_proxy_bootstrap_lower_positive": float(main["high_ivol_short_proxy"]["bootstrap_95pct"][0]) > 0.0,
        "ivol_increment_vs_tvol_mean_positive": float(main["tvol_high_minus_ivol_high"]["mean"]) > 0.0,
        "ivol_increment_vs_tvol_bootstrap_lower_positive": float(
            main["tvol_high_minus_ivol_high"]["bootstrap_95pct"][0]
        )
        > 0.0,
        "all_calendar_years_directionally_pass": all(
            float(item["low_minus_high_return_mean"]) > 0.0
            and float(item["rank_ic_mean"]) < 0.0
            and float(item["high_ivol_short_proxy_mean"]) > 0.0
            for item in years.values()
        ),
        "all_fixed_neighbors_directionally_pass": all(
            float(item["low_minus_high_return"]["mean"]) > 0.0
            and float(item["rank_ic"]["mean"]) < 0.0
            and float(item["high_ivol_short_proxy"]["mean"]) > 0.0
            for item in neighbors.values()
        ),
        "minimum_8_selected_symbols": int(breadth["selected_symbols"]) >= 8,
        "minimum_3_selected_categories": int(breadth["selected_categories"]) >= 3,
        "half_repeat_symbols_negative_mean": float(
            breadth["negative_mean_fraction_among_repeat_symbols"]
        )
        >= 0.50,
        "largest_positive_short_contribution_at_most_35pct": float(
            breadth["maximum_positive_short_contribution_share"]
        )
        <= 0.35,
    }
    return checks


def write_result_markdown(stage: str, status: str, failed: list[str], result: dict[str, Any]) -> None:
    main = result["main"]
    controlled = result["regressions"]["controlled"]
    conclusion = "INSUFFICIENT_EVIDENCE" if status == "PASS" and stage == "development" else (
        "SUPPORTS_WITHIN_SCOPE" if status == "PASS" else "DOES_NOT_SUPPORT"
    )
    if stage == "development" and status == "PASS":
        next_step = "development 全门通过，仅允许打开事前封存的 2024 evaluation；尚不是策略。"
    elif status == "PASS":
        next_step = "预测证据在范围内通过；只允许另建策略转换题，不直接交付交易核心。"
    else:
        next_step = "按预注册停止；评估期保持封存，不允许策略转换或事后换参。"
    content = f"""# 结果：特质波动率与下月收益

## 结论

`{conclusion}`

{next_step}

## 主要证据

- 阶段 / ACTION months：`{stage} / {main['action_months']}`。
- IVOL90 low-minus-high 均值：`{main['low_minus_high_return']['mean']:.6%}`；95% block-bootstrap `[{main['low_minus_high_return']['bootstrap_95pct'][0]:.6%}, {main['low_minus_high_return']['bootstrap_95pct'][1]:.6%}]`。
- rank IC 均值：`{main['rank_ic']['mean']:.6f}`；95% block-bootstrap `[{main['rank_ic']['bootstrap_95pct'][0]:.6f}, {main['rank_ic']['bootstrap_95pct'][1]:.6f}]`。
- 完整控制 Fama–MacBeth IVOL 系数：`{controlled['ivol90_coefficient_mean']:.6%}`；负向单侧 HAC p `{controlled['hac_one_sided_negative_p']:.6f}`。
- high-IVOL SHORT 粗经济代理月均：`{main['high_ivol_short_proxy']['mean']:.6%}`；95% block-bootstrap `[{main['high_ivol_short_proxy']['bootstrap_95pct'][0]:.6%}, {main['high_ivol_short_proxy']['bootstrap_95pct'][1]:.6%}]`。
- TVOL-high 减 IVOL-high 下月收益：`{main['tvol_high_minus_ivol_high']['mean']:.6%}`；正值才表示 IVOL-high 更差。

## 失败门

{chr(10).join('- `' + item + '`' for item in failed) if failed else '- 无'}

## 边界

固定当前幸存者名单缺历史市值/退市币，不代表微型币总体。日线预测没有 funding、真实历史盘口、保证金路径或人工激活延迟。任何正回测都不证明长期 Alpha，本题不修改正式策略、产品代码、资金或账户。
"""
    (HERE / "result.md").write_text(content, encoding="utf-8")


def command_gate(args: argparse.Namespace) -> None:
    ensure_checkpoint()
    result_path = HERE / f"{args.stage}.json"
    dq_path = HERE / f"data_quality_{args.stage}.json"
    if not result_path.exists() or not dq_path.exists():
        raise RuntimeError(f"analysis or data quality missing: {args.stage}")
    result = read_json(result_path)
    dq = read_json(dq_path)
    checks = gate_checks(args.stage, result, dq)
    failed = [name for name, passed in checks.items() if not passed]
    status = "PASS" if not failed else "FAIL"
    conclusion = "INSUFFICIENT_EVIDENCE" if status == "PASS" and args.stage == "development" else (
        "SUPPORTS_WITHIN_SCOPE" if status == "PASS" else "DOES_NOT_SUPPORT"
    )
    payload = {
        "checked_at_utc": iso_now(),
        "stage": args.stage,
        "status": status,
        "conclusion": conclusion,
        "checks": checks,
        "failed_gates": failed,
        "result_digest": result["content_digest"],
        "stage_open_decision": (
            "OPEN_EVALUATION" if args.stage == "development" and status == "PASS" else "STOP_AND_SEAL"
        ),
    }
    write_json(HERE / f"{args.stage}_gate.json", payload)
    write_result_markdown(args.stage, status, failed, result)
    print(json.dumps({"stage": args.stage, "status": status, "conclusion": conclusion, "failed_gates": failed}, indent=2))


def command_validate(_args: argparse.Namespace) -> None:
    command_self_test(argparse.Namespace())
    checkpoint = ensure_checkpoint()
    verified_json: dict[str, str] = {"checkpoint.json": checkpoint["content_digest"]}
    for name in [
        "source_reuse_manifest.json",
        "data_quality_development.json",
        "development.json",
        "results.json",
        "development_gate.json",
        "data_quality_evaluation.json",
        "evaluation.json",
        "evaluation_gate.json",
    ]:
        path = HERE / name
        if not path.exists():
            continue
        payload = read_json(path)
        if payload.get("content_digest") != canonical_digest(payload):
            raise RuntimeError(f"JSON digest mismatch: {name}")
        verified_json[name] = payload["content_digest"]
    verified_csv: dict[str, str] = {}
    for path in sorted(HERE.glob("*.csv")):
        if path.stat().st_size <= 0:
            raise RuntimeError(f"empty CSV: {path.name}")
        verified_csv[path.name] = sha256_file(path)
    print(
        json.dumps(
            {
                "status": "PASS",
                "checkpoint_digest": checkpoint["content_digest"],
                "verified_json": verified_json,
                "verified_csv": verified_csv,
            },
            indent=2,
        )
    )


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Monthly crypto idiosyncratic-volatility predictability study")
    sub = root.add_subparsers(dest="command", required=True)
    sub.add_parser("self-test").set_defaults(func=command_self_test)
    sub.add_parser("checkpoint").set_defaults(func=command_checkpoint)
    sub.add_parser("validate").set_defaults(func=command_validate)
    for name, function in [("prepare", command_prepare), ("analyze", command_analyze), ("gate", command_gate)]:
        item = sub.add_parser(name)
        item.add_argument("--stage", choices=tuple(STAGES), required=True)
        item.set_defaults(func=function)
    return root


def main() -> None:
    args = parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
