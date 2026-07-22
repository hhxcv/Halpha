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
from scipy.stats import spearmanr, ttest_1samp
import statsmodels
import statsmodels.api as sm
from statsmodels.stats.multitest import multipletests


HERE = Path(__file__).resolve().parent
PARENT_DIR = (
    HERE.parents[2]
    / "strategy-candidate"
    / "2026"
    / "prospect-theory-value-weekly-one-shot-long"
)
PARENT_STUDY = PARENT_DIR / "study.py"


def load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


parent = load_module(PARENT_STUDY, "halpha_short_rmom_parent")
SYMBOLS = list(parent.SYMBOLS)
CATEGORY_MEMBERS = dict(parent.CATEGORY_MEMBERS)
SYMBOL_TO_CATEGORY = dict(parent.SYMBOL_TO_CATEGORY)
UNIVERSE_PATH = parent.UNIVERSE_PATH

STAGES = {
    "development": ("2022-01-03T00:00:00Z", "2024-01-01T00:00:00Z"),
    "evaluation": ("2024-01-01T00:00:00Z", "2024-12-30T00:00:00Z"),
}
VARIANTS = {
    "rmom_90_14": {"beta_days": 90, "signal_days": 14},
    "rmom_60_14": {"beta_days": 60, "signal_days": 14},
    "rmom_120_14": {"beta_days": 120, "signal_days": 14},
    "rmom_90_7": {"beta_days": 90, "signal_days": 7},
    "rmom_90_21": {"beta_days": 90, "signal_days": 21},
}
CONFIG = {
    "predictor_id": "RESEARCH_SHORT_HORIZON_CRYPTO_RMOM_90_14_V1",
    "main_variant": "rmom_90_14",
    "raw_baseline": "raw_mom14",
    "minimum_rankable_symbols": 20,
    "minimum_median_quote_volume_30d": 10_000_000.0,
    "tail_fraction": 0.20,
    "tail_count_rounding": "ceil",
    "cooldown_full_days": 1,
    "target_days": 7,
    "stress_round_trip_underlying": 0.0052,
    "notional_fraction_for_economic_screen": 0.25,
    "annual_full_plan_hurdle": 0.04,
    "economic_floor_underlying_week": 0.0052 + (0.04 / 52.0 / 0.25),
    "minimum_action_weeks": 80,
    "minimum_half_weeks": 35,
    "minimum_selected_symbols": 15,
    "minimum_positive_symbol_fraction": 0.50,
    "maximum_positive_contribution_share": 0.40,
    "maximum_abs_median_signal_raw_spearman": 0.90,
    "bootstrap": {"block_weeks": 4, "repetitions": 5000, "seed": 20260722},
    "variants": VARIANTS,
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
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
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
        (PARENT_STUDY, "reused public daily OHLCV loader only"),
        (PARENT_DIR / "checkpoint.json", "frozen parent adapter identity"),
        (PARENT_DIR / "source_reuse_manifest.json", "public source identity chain"),
        (PARENT_DIR / "data_quality_development.json", "2022-2023 public source quality evidence"),
        (UNIVERSE_PATH, "frozen current research target universe"),
    ]
    output: list[dict[str, Any]] = []
    for path, role in paths:
        if not path.exists():
            raise RuntimeError(f"missing source identity: {path}")
        output.append(
            {"path": str(path), "bytes": path.stat().st_size, "sha256": sha256_file(path), "role": role}
        )
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
        if (
            not source.exists()
            or source.stat().st_size != int(item["bytes"])
            or sha256_file(source) != item["sha256"]
        ):
            raise RuntimeError(f"reused source changed: {source}")
    parent.ensure_checkpoint()
    return checkpoint


def command_checkpoint(_args: argparse.Namespace) -> None:
    if (HERE / "checkpoint.json").exists():
        checkpoint = ensure_checkpoint()
        print(json.dumps({"reused": True, "digest": checkpoint["content_digest"]}, indent=2))
        return
    parent.ensure_checkpoint()
    parent.validate_universe()
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
            "Does a fixed 90-day leave-one-out crypto-market beta residual, standardized over the latest 14 days, "
            "incrementally predict next-week cross-sectional returns beyond plain 14-day momentum at a magnitude "
            "worth a separate retail-cost strategy study?"
        ),
        "replication_status": (
            "Transparent Halpha time-scale adaptation of Blitz-Huij-Martens residual momentum; not a replication "
            "of Li-Zhu 2026 because the auditable public RMOM formula was unavailable at checkpoint time."
        ),
        "known_exposure": (
            "The same public 2022-2023 price paths were viewed in prior Halpha questions, but this RMOM ranking and "
            "its conditional targets had not been computed before the checkpoint. Sequencing prevents local tuning "
            "but does not create genuinely unseen historical evidence."
        ),
        "support_limit": (
            "A pass supports only a predictive relationship and releases a separate costed strategy question. It "
            "does not qualify a strategy, authorize product changes, or establish long-term profitability."
        ),
        "family_stop_rule": (
            "On any development failure, do not search adjacent directions, windows, thresholds, states, symbols, "
            "market definitions or holding periods without new independent mechanism evidence."
        ),
        "configuration": CONFIG,
        "stages": {key: list(value) for key, value in STAGES.items()},
        "symbols": SYMBOLS,
        "categories": CATEGORY_MEMBERS,
        "selection_scope": {"selectable_primary_configurations": 1, "fixed_neighbor_diagnostics": 4},
        "stage_open_rule": "development -> evaluation; evaluation sealed until every development hard gate passes",
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


def daily_frames(bars: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    output: dict[str, pd.DataFrame] = {}
    for symbol, raw in bars.items():
        frame = raw.sort_index().copy()
        full = pd.date_range(frame.index.min(), frame.index.max(), freq="1D")
        frame = frame.reindex(full)
        frame["median_quote_volume_30d"] = frame["quote_volume"].rolling(30, min_periods=30).median()
        output[symbol] = frame
    return output


def fit_beta(y: np.ndarray, market_ex_self: np.ndarray, beta_days: int) -> tuple[float, float]:
    y_fit = np.asarray(y[-beta_days:], dtype=float)
    x_fit = np.asarray(market_ex_self[-beta_days:], dtype=float)
    model = sm.OLS(y_fit, sm.add_constant(x_fit, has_constant="add")).fit()
    alpha, beta = map(float, model.params)
    return alpha, beta


def residual_momentum_score(
    y: np.ndarray, market_ex_self: np.ndarray, beta: float, signal_days: int
) -> float:
    residual = np.asarray(y[-signal_days:], dtype=float) - beta * np.asarray(
        market_ex_self[-signal_days:], dtype=float
    )
    scale = float(np.std(residual, ddof=1))
    if not math.isfinite(scale) or scale <= 0.0:
        return math.nan
    return float(residual.sum() / scale)


def build_panel(
    bars: dict[str, pd.DataFrame], stage: str
) -> tuple[pd.DataFrame, dict[str, Any]]:
    daily = daily_frames(bars)
    rows: list[dict[str, Any]] = []
    week_audit: list[dict[str, Any]] = []
    max_beta_days = max(item["beta_days"] for item in VARIANTS.values())
    for entry in stage_entries(stage):
        cutoff = entry - pd.Timedelta(days=2)
        exit_time = entry + pd.Timedelta(days=int(CONFIG["target_days"]))
        eligible: list[str] = []
        histories: dict[str, np.ndarray] = {}
        future_prices: dict[str, tuple[float, float]] = {}
        future_missing: list[str] = []
        for symbol in SYMBOLS:
            frame = daily[symbol]
            history_dates = pd.date_range(cutoff - pd.Timedelta(days=max_beta_days), cutoff, freq="1D")
            if not history_dates.isin(frame.index).all():
                continue
            history = frame.loc[history_dates]
            if history[["open", "high", "low", "close", "quote_volume"]].isna().any().any():
                continue
            if (history[["open", "high", "low", "close"]] <= 0.0).any().any():
                continue
            if float(frame.at[cutoff, "median_quote_volume_30d"]) < float(
                CONFIG["minimum_median_quote_volume_30d"]
            ):
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
        audit = {
            "entry_time": entry,
            "signal_cutoff": cutoff,
            "decision_eligible_count": len(eligible),
            "future_missing_symbols": sorted(future_missing),
            "status": "NO_ACTION_TOO_FEW_ELIGIBLE",
        }
        if len(eligible) < int(CONFIG["minimum_rankable_symbols"]):
            week_audit.append(audit)
            continue
        if future_missing:
            audit["status"] = "DATA_QUALITY_FAIL_FUTURE_TARGET_MISSING"
            week_audit.append(audit)
            continue
        ordered = sorted(eligible)
        matrix = np.column_stack([histories[symbol] for symbol in ordered])
        next_returns = {
            symbol: future_prices[symbol][1] / future_prices[symbol][0] - 1.0 for symbol in ordered
        }
        next_market_return = float(np.mean(list(next_returns.values())))
        market_sum = matrix.sum(axis=1)
        for column, symbol in enumerate(ordered):
            y = matrix[:, column]
            market_ex_self = (market_sum - y) / (len(ordered) - 1)
            fitted = {
                beta_days: fit_beta(y, market_ex_self, beta_days)
                for beta_days in sorted({item["beta_days"] for item in VARIANTS.values()})
            }
            scores: dict[str, float] = {}
            for name, definition in VARIANTS.items():
                alpha, beta = fitted[definition["beta_days"]]
                scores[name] = residual_momentum_score(
                    y, market_ex_self, beta, definition["signal_days"]
                )
                if name == CONFIG["main_variant"]:
                    scores["main_alpha"] = alpha
                    scores["main_beta"] = beta
            rows.append(
                {
                    "entry_time": entry,
                    "signal_cutoff": cutoff,
                    "exit_time": exit_time,
                    "symbol": symbol,
                    "category": SYMBOL_TO_CATEGORY[symbol],
                    "eligible_count": len(ordered),
                    "raw_mom14": float(y[-14:].sum()),
                    **scores,
                    "entry_price": future_prices[symbol][0],
                    "exit_price": future_prices[symbol][1],
                    "target_asset_return": next_returns[symbol],
                    "target_market_return": next_market_return,
                    "target_excess_return": next_returns[symbol] - next_market_return,
                }
            )
        audit["status"] = "ACTION"
        week_audit.append(audit)
    if not rows:
        raise RuntimeError(f"empty panel: {stage}")
    panel = pd.DataFrame(rows).replace([np.inf, -np.inf], np.nan)
    score_columns = list(VARIANTS) + ["raw_mom14"]
    missing_scores = panel[score_columns].isna().any(axis=1)
    if missing_scores.any():
        raise RuntimeError(f"non-finite score rows: {int(missing_scores.sum())}")
    panel = panel.sort_values(["entry_time", "symbol"]).reset_index(drop=True)
    return panel, {"weeks": week_audit}


def block_bootstrap_mean_ci(values: np.ndarray) -> list[float]:
    values = np.asarray(values, dtype=float)
    if len(values) == 0 or not np.isfinite(values).all():
        raise RuntimeError("bootstrap input empty or non-finite")
    block = int(CONFIG["bootstrap"]["block_weeks"])
    reps = int(CONFIG["bootstrap"]["repetitions"])
    rng = np.random.default_rng(int(CONFIG["bootstrap"]["seed"]))
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


def weekly_for_score(panel: pd.DataFrame, score_column: str, name: str) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for entry, frame in panel.groupby("entry_time", sort=True):
        ordered = frame.sort_values([score_column, "symbol"], ascending=[False, True])
        tail = max(1, int(math.ceil(len(ordered) * float(CONFIG["tail_fraction"]))))
        top = ordered.head(tail)
        bottom = ordered.tail(tail)
        ic = spearmanr(frame[score_column], frame["target_excess_return"]).statistic
        raw_corr = spearmanr(frame[score_column], frame["raw_mom14"]).statistic
        rows.append(
            {
                "entry_time": entry,
                "variant": name,
                "eligible_count": int(len(frame)),
                "tail_count": tail,
                "top_symbols": "|".join(top["symbol"].tolist()),
                "bottom_symbols": "|".join(bottom["symbol"].tolist()),
                "top_asset_return": float(top["target_asset_return"].mean()),
                "top_excess_return": float(top["target_excess_return"].mean()),
                "bottom_excess_return": float(bottom["target_excess_return"].mean()),
                "top_minus_bottom_excess": float(
                    top["target_excess_return"].mean() - bottom["target_excess_return"].mean()
                ),
                "rank_ic": float(ic),
                "signal_raw_spearman": float(raw_corr),
            }
        )
    return pd.DataFrame(rows).sort_values("entry_time").reset_index(drop=True)


def selected_top_rows(panel: pd.DataFrame, score_column: str) -> pd.DataFrame:
    selected: list[pd.DataFrame] = []
    for _entry, frame in panel.groupby("entry_time", sort=True):
        ordered = frame.sort_values([score_column, "symbol"], ascending=[False, True])
        tail = max(1, int(math.ceil(len(ordered) * float(CONFIG["tail_fraction"]))))
        chosen = ordered.head(tail).copy()
        chosen["selection_rank"] = np.arange(1, len(chosen) + 1)
        selected.append(chosen)
    return pd.concat(selected, ignore_index=True)


def summarize_weekly(weekly: pd.DataFrame) -> dict[str, Any]:
    return {
        "action_weeks": int(len(weekly)),
        "top_asset_return": series_summary(weekly["top_asset_return"]),
        "top_excess_return": series_summary(weekly["top_excess_return"]),
        "bottom_excess_return": series_summary(weekly["bottom_excess_return"]),
        "top_minus_bottom_excess": series_summary(weekly["top_minus_bottom_excess"]),
        "rank_ic": series_summary(weekly["rank_ic"]),
        "signal_raw_spearman": {
            **series_summary(weekly["signal_raw_spearman"]),
            "median_absolute": float(weekly["signal_raw_spearman"].abs().median()),
        },
    }


def half_summaries(weekly: pd.DataFrame) -> dict[str, Any]:
    middle = len(weekly) // 2
    halves = {"first": weekly.iloc[:middle], "second": weekly.iloc[middle:]}
    return {
        name: {
            "weeks": int(len(frame)),
            "start": frame["entry_time"].min(),
            "end": frame["entry_time"].max(),
            "top_asset_return_mean": float(frame["top_asset_return"].mean()),
            "top_excess_return_mean": float(frame["top_excess_return"].mean()),
            "top_minus_bottom_excess_mean": float(frame["top_minus_bottom_excess"].mean()),
            "rank_ic_mean": float(frame["rank_ic"].mean()),
        }
        for name, frame in halves.items()
    }


def breadth_summary(selected: pd.DataFrame) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    by_symbol = (
        selected.groupby(["symbol", "category"])
        .agg(
            selections=("target_excess_return", "size"),
            mean_excess_return=("target_excess_return", "mean"),
            total_excess_return=("target_excess_return", "sum"),
            mean_asset_return=("target_asset_return", "mean"),
        )
        .reset_index()
    )
    positive = by_symbol[by_symbol["total_excess_return"] > 0.0]
    positive_total = float(positive["total_excess_return"].sum())
    max_share = (
        float(positive["total_excess_return"].max() / positive_total) if positive_total > 0.0 else 1.0
    )
    fdr_rows: list[dict[str, Any]] = []
    p_values: list[float] = []
    eligible_symbols: list[str] = []
    for symbol, frame in selected.groupby("symbol"):
        if len(frame) < 5:
            continue
        test = ttest_1samp(frame["target_excess_return"], 0.0, alternative="greater")
        eligible_symbols.append(symbol)
        p_values.append(float(test.pvalue))
        fdr_rows.append(
            {
                "symbol": symbol,
                "observations": int(len(frame)),
                "mean_excess_return": float(frame["target_excess_return"].mean()),
                "t_statistic": float(test.statistic),
                "p_value_one_sided": float(test.pvalue),
            }
        )
    if p_values:
        rejected, adjusted, _alpha_sidak, _alpha_bonf = multipletests(p_values, method="fdr_by")
        for row, reject, q_value in zip(fdr_rows, rejected, adjusted):
            row["by_fdr_reject_5pct"] = bool(reject)
            row["by_adjusted_p"] = float(q_value)
    return (
        {
            "selected_symbols": int(len(by_symbol)),
            "positive_mean_symbol_fraction": float((by_symbol["mean_excess_return"] > 0.0).mean()),
            "maximum_positive_contribution_share": max_share,
            "by_symbol": by_symbol.sort_values("symbol").to_dict(orient="records"),
            "by_category": (
                selected.groupby("category")["target_excess_return"]
                .agg(["size", "mean", "sum"])
                .reset_index()
                .sort_values("category")
                .to_dict(orient="records")
            ),
            "by_fdr_rejections_5pct": int(sum(bool(row.get("by_fdr_reject_5pct")) for row in fdr_rows)),
        },
        fdr_rows,
    )


def command_self_test(_args: argparse.Namespace) -> None:
    market = np.linspace(-0.02, 0.02, 120)
    idiosyncratic = np.concatenate([np.zeros(106), np.linspace(0.001, 0.014, 14)])
    y = 0.0005 + 1.7 * market + idiosyncratic
    alpha, beta = fit_beta(y, market, 90)
    score = residual_momentum_score(y, market, beta, 14)
    manual_residual = y[-14:] - beta * market[-14:]
    manual = float(manual_residual.sum() / np.std(manual_residual, ddof=1))
    if not math.isclose(score, manual, rel_tol=0.0, abs_tol=1e-12):
        raise RuntimeError("residual momentum reconciliation failed")
    if not 1.6 < beta < 2.0 or score <= 0.0:
        raise RuntimeError("synthetic beta or score orientation failed")
    sample = np.arange(1.0, 21.0)
    first = block_bootstrap_mean_ci(sample)
    second = block_bootstrap_mean_ci(sample)
    if first != second:
        raise RuntimeError("bootstrap is not deterministic")
    print(
        json.dumps(
            {
                "status": "PASS",
                "synthetic_alpha": alpha,
                "synthetic_beta": beta,
                "score_reconciliation_error": score - manual,
                "bootstrap_deterministic": True,
            },
            indent=2,
        )
    )


def load_bars(stage: str) -> tuple[dict[str, pd.DataFrame], dict[str, Any]]:
    _checkpoint = ensure_checkpoint()
    stage_authorized(stage)
    bars, _funding, metadata = parent.load_stage(stage)
    return bars, metadata


def command_prepare(args: argparse.Namespace) -> None:
    checkpoint = ensure_checkpoint()
    bars, metadata = load_bars(args.stage)
    panel, audit = build_panel(bars, args.stage)
    parent_dq_path = PARENT_DIR / "data_quality_development.json"
    parent_dq = read_json(parent_dq_path)
    future_missing_weeks = [
        item for item in audit["weeks"] if item["status"] == "DATA_QUALITY_FAIL_FUTURE_TARGET_MISSING"
    ]
    action_weeks = int(panel["entry_time"].nunique())
    counts = panel.groupby("entry_time")["symbol"].nunique()
    payload = {
        "checked_at_utc": iso_now(),
        "stage": args.stage,
        "status": "PASS"
        if parent_dq.get("status") == "PASS"
        and metadata.get("overlap_mismatch_rows", 0) == 0
        and not future_missing_weeks
        else "FAIL",
        "checkpoint_digest": checkpoint["content_digest"],
        "parent_data_quality_path": str(parent_dq_path),
        "parent_data_quality_sha256": sha256_file(parent_dq_path),
        "source_overlap": metadata,
        "scheduled_weeks": int(len(stage_entries(args.stage))),
        "action_weeks": action_weeks,
        "global_no_action_weeks": int(
            sum(item["status"] == "NO_ACTION_TOO_FEW_ELIGIBLE" for item in audit["weeks"])
        ),
        "minimum_rankable_on_action_weeks": int(counts.min()),
        "maximum_rankable_on_action_weeks": int(counts.max()),
        "future_target_missing_weeks": future_missing_weeks,
        "week_audit": audit["weeks"],
        "rule": (
            "No interpolation; eligibility uses only data through Saturday cutoff. Missing future target data "
            "fails data quality rather than changing the ranked universe."
        ),
    }
    write_json(HERE / f"data_quality_{args.stage}.json", payload, digest=True)
    print(
        json.dumps(
            {
                "stage": args.stage,
                "status": payload["status"],
                "action_weeks": action_weeks,
                "minimum_rankable": int(counts.min()),
            },
            indent=2,
        )
    )


def command_analyze(args: argparse.Namespace) -> None:
    checkpoint = ensure_checkpoint()
    dq_path = HERE / f"data_quality_{args.stage}.json"
    if not dq_path.exists() or read_json(dq_path).get("status") != "PASS":
        raise RuntimeError(f"data quality is not PASS: {args.stage}")
    bars, _metadata = load_bars(args.stage)
    panel, _audit = build_panel(bars, args.stage)
    weekly_frames = {
        name: weekly_for_score(panel, name, name) for name in VARIANTS
    }
    weekly_frames["raw_mom14"] = weekly_for_score(panel, "raw_mom14", "raw_mom14")
    main_name = str(CONFIG["main_variant"])
    main_weekly = weekly_frames[main_name]
    raw_weekly = weekly_frames["raw_mom14"]
    if not main_weekly["entry_time"].equals(raw_weekly["entry_time"]):
        raise RuntimeError("main and raw baseline dates differ")
    selected = selected_top_rows(panel, main_name)
    breadth, fdr_rows = breadth_summary(selected)
    weekly_summaries = {name: summarize_weekly(frame) for name, frame in weekly_frames.items()}
    incremental = main_weekly["top_asset_return"] - raw_weekly["top_asset_return"]
    halves = half_summaries(main_weekly)
    floor = float(CONFIG["economic_floor_underlying_week"])
    half_gates = {
        name: item["weeks"] >= int(CONFIG["minimum_half_weeks"])
        and item["top_asset_return_mean"] > floor
        and item["top_excess_return_mean"] > 0.0
        and item["top_minus_bottom_excess_mean"] > 0.0
        and item["rank_ic_mean"] > 0.0
        for name, item in halves.items()
    }
    neighbor_gates = {
        name: weekly_summaries[name]["top_excess_return"]["mean"] > 0.0
        and weekly_summaries[name]["top_minus_bottom_excess"]["mean"] > 0.0
        for name in VARIANTS
        if name != main_name
    }
    main_summary = weekly_summaries[main_name]
    incremental_summary = series_summary(incremental)
    hard_gates = {
        "data_quality_pass": read_json(dq_path).get("status") == "PASS",
        "minimum_action_weeks": len(main_weekly) >= int(CONFIG["minimum_action_weeks"]),
        "minimum_half_weeks": all(item["weeks"] >= int(CONFIG["minimum_half_weeks"]) for item in halves.values()),
        "top_asset_mean_above_economic_floor": main_summary["top_asset_return"]["mean"] > floor,
        "top_asset_bootstrap_lower_positive": main_summary["top_asset_return"]["bootstrap_95pct"][0] > 0.0,
        "top_excess_mean_positive": main_summary["top_excess_return"]["mean"] > 0.0,
        "top_excess_bootstrap_lower_positive": main_summary["top_excess_return"]["bootstrap_95pct"][0] > 0.0,
        "spread_mean_positive": main_summary["top_minus_bottom_excess"]["mean"] > 0.0,
        "spread_bootstrap_lower_positive": main_summary["top_minus_bottom_excess"]["bootstrap_95pct"][0] > 0.0,
        "increment_vs_raw_mean_positive": incremental_summary["mean"] > 0.0,
        "increment_vs_raw_bootstrap_lower_positive": incremental_summary["bootstrap_95pct"][0] > 0.0,
        "rank_ic_mean_positive": main_summary["rank_ic"]["mean"] > 0.0,
        "rank_ic_bootstrap_lower_positive": main_summary["rank_ic"]["bootstrap_95pct"][0] > 0.0,
        "both_halves_pass": all(half_gates.values()),
        "minimum_selected_symbols": breadth["selected_symbols"] >= int(CONFIG["minimum_selected_symbols"]),
        "positive_symbol_breadth": breadth["positive_mean_symbol_fraction"]
        >= float(CONFIG["minimum_positive_symbol_fraction"]),
        "positive_contribution_not_concentrated": breadth["maximum_positive_contribution_share"]
        <= float(CONFIG["maximum_positive_contribution_share"]),
        "all_fixed_neighbors_positive": all(neighbor_gates.values()),
        "signal_not_raw_clone": main_summary["signal_raw_spearman"]["median_absolute"]
        < float(CONFIG["maximum_abs_median_signal_raw_spearman"]),
    }
    all_pass = all(hard_gates.values())

    csv_frames = {
        f"{args.stage}_panel.csv": panel,
        f"{args.stage}_weekly.csv": pd.concat(weekly_frames.values(), ignore_index=True),
        f"{args.stage}_main_top_selected.csv": selected,
        f"{args.stage}_symbol_fdr.csv": pd.DataFrame(fdr_rows),
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
        "interpretation_limit": (
            "Predictive gate only. A PASS still requires a separately preregistered strategy study with actual "
            "funding, fees, spread/slippage, risk and execution semantics."
        ),
        "economic_floor_underlying_week": floor,
        "weekly_summaries": weekly_summaries,
        "increment_vs_raw_mom14_top_asset_return": incremental_summary,
        "halves": halves,
        "half_gates": half_gates,
        "neighbor_gates": neighbor_gates,
        "breadth": breadth,
        "symbol_fdr": fdr_rows,
        "hard_gates": hard_gates,
        "failed_hard_gates": [name for name, passed in hard_gates.items() if not passed],
        "csv_sha256": csv_hashes,
    }
    write_json(HERE / f"{args.stage}.json", payload, digest=True)
    if args.stage == "development":
        write_json(HERE / "results.json", payload, digest=True)
    print(
        json.dumps(
            {
                "stage": args.stage,
                "result": payload["question_result"],
                "action_weeks": len(main_weekly),
                "top_asset_mean": main_summary["top_asset_return"]["mean"],
                "top_excess_mean": main_summary["top_excess_return"]["mean"],
                "spread_mean": main_summary["top_minus_bottom_excess"]["mean"],
                "increment_vs_raw": incremental_summary["mean"],
                "rank_ic_mean": main_summary["rank_ic"]["mean"],
                "failed_gates": payload["failed_hard_gates"],
            },
            indent=2,
        )
    )


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
    main = result["weekly_summaries"][CONFIG["main_variant"]]
    comparison = result["increment_vs_raw_mom14_top_asset_return"]
    result_md = f"""# {args.stage} 结果摘要

## Answer first

`{result['question_result']}`

固定 RMOM_90_14 的 top 周均标的收益为 `{main['top_asset_return']['mean']:.4%}`，top 超额收益为 `{main['top_excess_return']['mean']:.4%}`，top-minus-bottom spread 为 `{main['top_minus_bottom_excess']['mean']:.4%}`，周度 rank IC 为 `{main['rank_ic']['mean']:.4f}`。相对普通 MOM14 top 的同周收益增量为 `{comparison['mean']:.4%}`。

经济筛选线为 `{result['economic_floor_underlying_week']:.4%}`；失败硬门：`{', '.join(result['failed_hard_gates']) if result['failed_hard_gates'] else '无'}`。

本结论只回答增量预测性。即使 PASS 也不是策略、可交易 Alpha 或长期盈利证明；FAIL 时 evaluation 保持封存，不做参数救援。完整数值见 `{args.stage}.json`，逐周和逐币派生证据见同目录 CSV。
"""
    (HERE / "result.md").write_text(result_md, encoding="utf-8")
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
    for result_path in sorted(HERE.glob("development.json")) + sorted(HERE.glob("evaluation.json")):
        result = read_json(result_path)
        for name, expected in result.get("csv_sha256", {}).items():
            actual = sha256_file(HERE / name)
            if actual != expected:
                raise RuntimeError(f"CSV digest mismatch: {name}")
            verified_csv[name] = actual
    command_self_test(argparse.Namespace())
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
    root = argparse.ArgumentParser()
    sub = root.add_subparsers(dest="command", required=True)
    for name, func in [
        ("self-test", command_self_test),
        ("checkpoint", command_checkpoint),
        ("validate", command_validate),
    ]:
        item = sub.add_parser(name)
        item.set_defaults(func=func)
    for name, func in [
        ("prepare", command_prepare),
        ("analyze", command_analyze),
        ("gate", command_gate),
    ]:
        item = sub.add_parser(name)
        item.add_argument("--stage", choices=tuple(STAGES), required=True)
        item.set_defaults(func=func)
    return root


def main() -> None:
    args = parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
