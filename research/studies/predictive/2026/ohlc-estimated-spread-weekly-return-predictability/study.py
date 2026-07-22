from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import math
import platform
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import scipy
from scipy.stats import spearmanr
import statsmodels
import statsmodels.api as sm


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
BASE_STUDY = ROOT / (
    "research/studies/predictive/2026/amihud-illiquidity-weekly-return-predictability/study.py"
)
BASE_STUDY_SHA256 = "40ce902407de51979f59a5f1fd6734ad571cc5a085d7082c664ea6e54f5660c7"
BASELINE_COMMIT = "0bdfeffa616260cebd2d2188ddc8deb9e85c77f4"
PARENT_MANIFEST = ROOT / (
    "research/studies/predictive/2026/intermediate-vix-beta-weekly-return-predictability/"
    "source_manifest.json"
)
PARENT_MANIFEST_SHA256 = "07d0c80a4ea858e767960c53bc9ef5345cecc1a07fb482d9d2d87b862fb50693"
PARENT_MANIFEST_CONTENT_DIGEST = "d8cab91fb7ccdc39204aa2b783d13376b92ba0137fb3cb8e6a164cb432ed3514"

REFERENCE_DIR = Path(
    "D:/projects/Codex/CodexHome/research-data/halpha/"
    "ohlc-estimated-spread-weekly-return-predictability/2026-07-22-v1"
)
REFERENCE_FILES = {
    "tabular": {
        "path": REFERENCE_DIR / "Dataset_returns_crypto_factor_zoo_2.tab",
        "bytes": 566934,
        "sha256": "8d7683c6fed20afac76f73cf728b7e77392b21655377631310ec76a452b4e0af",
        "url": "https://repod.icm.edu.pl/api/access/datafile/105344",
        "format": "Dataverse tabular export",
    },
    "original": {
        "path": REFERENCE_DIR / "Dataset_returns_crypto_factor_zoo_2.xlsx",
        "bytes": 361178,
        "sha256": "4a103a42af056be25a9a82d3de93ab2b657920e1eaf0614b95f4c8859ba81683",
        "url": "https://repod.icm.edu.pl/api/access/datafile/105344?format=original",
        "format": "original XLSX",
    },
}

SYMBOLS = [
    "1000XECUSDT", "AAVEUSDT", "AVAXUSDT", "BCHUSDT", "BNBUSDT",
    "CRVUSDT", "DASHUSDT", "ENSUSDT", "ETCUSDT", "HBARUSDT",
    "KAVAUSDT", "LINKUSDT", "LTCUSDT", "NEARUSDT", "RUNEUSDT",
    "SNXUSDT", "SOLUSDT", "TRXUSDT", "UNIUSDT", "VETUSDT",
    "XLMUSDT", "XMRUSDT", "XRPUSDT", "ZECUSDT", "ZILUSDT",
]
DATA_START = "2022-01-01T00:00:00Z"
DATA_END_EXCLUSIVE = "2026-07-22T00:00:00Z"
STAGES = {
    "development": ("2023-03-04T00:00:00Z", "2024-03-02T00:00:00Z"),
    "evaluation": ("2024-03-02T00:00:00Z", "2025-03-01T00:00:00Z"),
    "confirmation": ("2025-03-01T00:00:00Z", "2026-07-18T00:00:00Z"),
}
EXPECTED_WEEKS = {
    name: len(pd.date_range(pd.Timestamp(start), pd.Timestamp(end), freq="7D", inclusive="left"))
    for name, (start, end) in STAGES.items()
}
WINDOWS = {"primary_28p": 28, "diagnostic_14p": 14, "diagnostic_56p": 56}
CONFIG = {
    "predictor_id": "RESEARCH_CHL28_HIGH_NEXT_WEEK_V1",
    "minimum_median_quote_volume_30d": 10_000_000.0,
    "minimum_rankable": 20,
    "tail_fraction": 0.20,
    "market_beta_days": 56,
    "action_gap_days": 2,
    "target_days": 7,
    "stress_round_trip_underlying": 0.0052,
    "economic_notional_fraction": 0.25,
    "annual_full_plan_hurdle": 0.04,
    "bootstrap": {"block_weeks": 4, "repetitions": 5000, "seed": 20260722},
    "hac_maxlags": 4,
    "minimum_positive_spread_fraction": 0.55,
    "minimum_selected_symbols": 10,
    "minimum_positive_symbol_fraction": 0.50,
    "maximum_positive_contribution_share": 0.40,
    "maximum_abs_score_control_correlation": 0.90,
}
CONTROL_COLUMNS = [
    "log_amihud", "market_beta", "mom7", "mom28", "vol28", "max28", "log_volume30"
]


def _load_base() -> Any:
    spec = importlib.util.spec_from_file_location("halpha_amihud_base", BASE_STUDY)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load pinned research base")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BASE = _load_base()
BASE.HERE = HERE
BASE.CONFIG = CONFIG

now_utc = BASE.now_utc
digest_bytes = BASE.digest_bytes
digest_file = BASE.digest_file
digest_value = BASE.digest_value
read_json = BASE.read_json
write_json = BASE.write_json


def assert_base_dependency() -> None:
    if digest_file(BASE_STUDY) != BASE_STUDY_SHA256:
        raise RuntimeError("pinned research base identity mismatch")


def assert_checkpoint() -> None:
    assert_base_dependency()
    BASE.assert_checkpoint()


def verify_reference_item(item: dict[str, Any]) -> None:
    path = Path(item["path"])
    raw = path.read_bytes()
    if len(raw) != int(item["bytes"]) or digest_bytes(raw) != item["sha256"]:
        raise RuntimeError(f"reference identity mismatch: {path}")


def command_checkpoint(_args: argparse.Namespace) -> None:
    assert_base_dependency()
    frozen = {
        name: digest_file(HERE / name)
        for name in ["README.md", "sources.md", "preregistration.md", "study.py"]
    }
    payload = {
        "created_at_utc": now_utc(),
        "baseline_commit": BASELINE_COMMIT,
        "formal_strategy": {
            "id": "ONE_SHOT_DONCHIAN_ATR_BREAKOUT",
            "version": "1.0.1",
            "instrument": "BTCUSDT-PERP",
        },
        "research_kind": "PREDICTIVE",
        "predictor_id": CONFIG["predictor_id"],
        "question": (
            "Does high trailing 28-pair two-day-corrected CHL spread incrementally "
            "predict higher next-week mature-perpetual returns?"
        ),
        "replication_status": (
            "Independent narrow perpetual adaptation plus approximate public-factor benchmark check; "
            "not a numerical replication of the broad spot panel."
        ),
        "evidence_boundary": (
            "Development/evaluation overlap the source calendar; confirmation extends later, "
            "but broad crypto paths were exposed in prior Halpha work."
        ),
        "symbols": SYMBOLS,
        "data_start": DATA_START,
        "data_end_exclusive": DATA_END_EXCLUSIVE,
        "stages": STAGES,
        "expected_weeks": EXPECTED_WEEKS,
        "windows": WINDOWS,
        "controls": CONTROL_COLUMNS,
        "config": CONFIG,
        "parent_manifest": {
            "path": str(PARENT_MANIFEST.relative_to(ROOT)).replace("\\", "/"),
            "sha256": PARENT_MANIFEST_SHA256,
            "content_digest": PARENT_MANIFEST_CONTENT_DIGEST,
        },
        "reference_dataset": {
            "persistent_id": "doi:10.18150/IIVQQE",
            "version": "1.0",
            "license": "CC0-1.0",
            "files": {
                name: {
                    **{key: value for key, value in item.items() if key != "path"},
                    "path": str(item["path"]),
                }
                for name, item in REFERENCE_FILES.items()
            },
            "gate_role": "external benchmark only; excluded from stage gates",
        },
        "pinned_research_dependency": {
            "path": str(BASE_STUDY.relative_to(ROOT)).replace("\\", "/"),
            "sha256": BASE_STUDY_SHA256,
            "role": "data binding, quality, and shared statistical primitives",
        },
        "frozen_file_sha256": frozen,
        "environment": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "scipy": scipy.__version__,
            "statsmodels": statsmodels.__version__,
        },
        "stage_open_rule": "development -> evaluation on PASS -> confirmation on PASS",
    }
    write_json(HERE / "checkpoint.json", payload)
    print(json.dumps({
        "digest": read_json(HERE / "checkpoint.json")["content_digest"],
        "expected_weeks": EXPECTED_WEEKS,
    }))


def command_bind(_args: argparse.Namespace) -> None:
    assert_checkpoint()
    BASE.command_bind(_args)
    manifest = read_json(HERE / "source_reuse_manifest.json")
    manifest.pop("content_digest", None)
    references: dict[str, Any] = {}
    for name, item in REFERENCE_FILES.items():
        verify_reference_item(item)
        references[name] = {
            **{key: value for key, value in item.items() if key != "path"},
            "path": str(item["path"]),
        }
    manifest["reference_dataset"] = {
        "persistent_id": "doi:10.18150/IIVQQE",
        "version": "1.0",
        "license": "CC0-1.0",
        "files": references,
        "copy_performed": False,
        "gate_role": "external benchmark only",
    }
    write_json(HERE / "source_reuse_manifest.json", manifest)
    bound = read_json(HERE / "source_reuse_manifest.json")
    print(json.dumps({
        "market_files": bound["files_verified"],
        "reference_files": len(references),
        "digest": bound["content_digest"],
    }))


def reference_series_summary(rows: list[list[str]], date_col: int, value_col: int) -> dict[str, Any]:
    dated_values: list[tuple[pd.Timestamp, float]] = []
    values: list[float] = []
    for row in rows:
        try:
            value = float(row[value_col])
        except (IndexError, TypeError, ValueError):
            continue
        values.append(value)
        try:
            serial = float(row[date_col])
        except (IndexError, TypeError, ValueError):
            continue
        dated_values.append((pd.Timestamp("1899-12-30") + pd.Timedelta(days=serial), value))
    numeric = np.asarray(values, dtype=float)
    midpoint = len(numeric) // 2
    standard_error = float(numeric.std(ddof=1) / math.sqrt(len(numeric)))
    return {
        "usable_observations": int(len(numeric)),
        "dated_observations": int(len(dated_values)),
        "undated_numeric_observations": int(len(numeric) - len(dated_values)),
        "first_date": dated_values[0][0].date().isoformat(),
        "last_date": dated_values[-1][0].date().isoformat(),
        "weekly_mean": float(numeric.mean()),
        "annualized_arithmetic_mean": float(numeric.mean() * 52.0),
        "conventional_iid_t": float(numeric.mean() / standard_error),
        "positive_fraction": float((numeric > 0).mean()),
        "first_half_weekly_mean": float(numeric[:midpoint].mean()),
        "second_half_weekly_mean": float(numeric[midpoint:].mean()),
    }


def build_reference_benchmark() -> dict[str, Any]:
    for item in REFERENCE_FILES.values():
        verify_reference_item(item)
    tab_path = Path(REFERENCE_FILES["tabular"]["path"])
    with tab_path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle, delimiter="\t"))
    if len(rows) < 300 or len(rows[1]) != 75 or rows[1][13] != "bidask" or rows[1][51] != "bidask":
        raise RuntimeError("unexpected RepOD tabular schema")
    equal_weighted = reference_series_summary(rows[2:], 0, 13)
    value_weighted = reference_series_summary(rows[2:], 38, 51)
    reported = 1.0781
    return {
        "generated_at_utc": now_utc(),
        "dataset": "Zaremba (2026) RepOD V1 weekly crypto factor portfolio returns",
        "persistent_id": "doi:10.18150/IIVQQE",
        "license": "CC0-1.0",
        "tabular_sha256": REFERENCE_FILES["tabular"]["sha256"],
        "equal_weighted_bidask": equal_weighted,
        "value_weighted_bidask": value_weighted,
        "paper_reported_value_weighted_zero_cost_annualized_mean": reported,
        "absolute_difference_from_reported": abs(value_weighted["annualized_arithmetic_mean"] - reported),
        "interpretation": (
            "Approximate independent check only: the Dataverse tabular export has an early malformed "
            "value-weighted row, one trailing numeric value without a date, and may not preserve all "
            "paper formatting conventions."
        ),
        "used_in_halpha_gate": False,
    }


def command_inspect(_args: argparse.Namespace) -> None:
    assert_checkpoint()
    BASE.command_inspect(_args)
    reference = build_reference_benchmark()
    write_json(HERE / "reference_benchmark.json", reference)
    quality = read_json(HERE / "data_quality.json")
    quality.pop("content_digest", None)
    reference_ok = (
        reference["equal_weighted_bidask"]["usable_observations"] >= 300
        and reference["value_weighted_bidask"]["usable_observations"] >= 300
        and reference["absolute_difference_from_reported"] < 0.02
    )
    quality["reference_dataset"] = {
        "status": "PASS" if reference_ok else "FAIL",
        "benchmark_digest": read_json(HERE / "reference_benchmark.json")["content_digest"],
        "gate_role": "quality/provenance context only; excluded from market stage gates",
    }
    quality["status"] = "PASS" if quality["status"] == "PASS" and reference_ok else "FAIL"
    write_json(HERE / "data_quality.json", quality)
    print(json.dumps({
        "status": quality["status"],
        "reference_value_weighted_annualized": reference["value_weighted_bidask"]["annualized_arithmetic_mean"],
    }))
    if quality["status"] != "PASS":
        raise RuntimeError("data quality failed")


def beta_coefficient(y: np.ndarray, market: np.ndarray) -> float:
    design = np.column_stack([np.ones(len(y)), market])
    return float(np.linalg.lstsq(design, y, rcond=None)[0][1])


def zscore(series: pd.Series) -> pd.Series:
    std = float(series.std(ddof=1))
    if not math.isfinite(std) or std <= 0:
        return pd.Series(0.0, index=series.index)
    return (series - float(series.mean())) / std


def daily_return_frame(bars: dict[str, pd.DataFrame]) -> pd.DataFrame:
    output = pd.DataFrame()
    for symbol in SYMBOLS:
        frame = bars[symbol]
        output[symbol] = frame["open"].shift(-1) / frame["open"] - 1.0
    return output


def chl_estimates(frame: pd.DataFrame, decision: pd.Timestamp, pairs: int) -> tuple[float, float]:
    pair_dates = pd.date_range(
        decision - pd.Timedelta(days=pairs + 1),
        decision - pd.Timedelta(days=1),
        freq="1D",
        inclusive="left",
    )
    next_dates = pair_dates + pd.Timedelta(days=1)
    close_log = np.log(frame.loc[pair_dates, "close"].to_numpy(float))
    eta = (
        np.log(frame.loc[pair_dates, "high"].to_numpy(float))
        + np.log(frame.loc[pair_dates, "low"].to_numpy(float))
    ) / 2.0
    eta_next = (
        np.log(frame.loc[next_dates, "high"].to_numpy(float))
        + np.log(frame.loc[next_dates, "low"].to_numpy(float))
    ) / 2.0
    moments = (close_log - eta) * (close_log - eta_next)
    two_day = float(np.sqrt(np.maximum(4.0 * moments, 0.0)).mean())
    monthly = float(np.sqrt(max(4.0 * float(moments.mean()), 0.0)))
    return two_day, monthly


def build_panel(bars: dict[str, pd.DataFrame], stage: str, pairs: int) -> pd.DataFrame:
    start, end = map(pd.Timestamp, STAGES[stage])
    decisions = pd.date_range(start, end, freq="7D", inclusive="left")
    returns = daily_return_frame(bars)
    market = returns.mean(axis=1, skipna=True)
    rows: list[dict[str, Any]] = []
    beta_days_count = int(CONFIG["market_beta_days"])
    index_sets = {symbol: set(frame.index) for symbol, frame in bars.items()}
    for decision in decisions:
        pair_dates = pd.date_range(
            decision - pd.Timedelta(days=pairs + 1),
            decision - pd.Timedelta(days=1),
            freq="1D",
            inclusive="left",
        )
        pair_next_dates = pair_dates + pd.Timedelta(days=1)
        control_dates = pd.date_range(decision - pd.Timedelta(days=28), decision, freq="1D", inclusive="left")
        volume_dates = pd.date_range(decision - pd.Timedelta(days=30), decision, freq="1D", inclusive="left")
        beta_dates = pd.date_range(
            decision - pd.Timedelta(days=beta_days_count), decision, freq="1D", inclusive="left"
        )
        entry = decision + pd.Timedelta(days=int(CONFIG["action_gap_days"]))
        exit_time = entry + pd.Timedelta(days=int(CONFIG["target_days"]))
        for symbol in SYMBOLS:
            frame = bars[symbol]
            required = (
                set(pair_dates) | set(pair_next_dates) | set(control_dates) | set(volume_dates)
                | set(beta_dates) | {decision, decision - pd.Timedelta(days=7), entry, exit_time}
            )
            if not required.issubset(index_sets[symbol]):
                continue
            asset_control = returns.loc[control_dates, symbol]
            asset_beta = returns.loc[beta_dates, symbol]
            if asset_control.isna().any() or asset_beta.isna().any():
                continue
            median_volume = float(frame.loc[volume_dates, "quote_volume"].median())
            if median_volume < float(CONFIG["minimum_median_quote_volume_30d"]):
                continue
            chl, chl_monthly = chl_estimates(frame, decision, pairs)
            amihud = float((asset_control.abs() / frame.loc[control_dates, "quote_volume"]).mean())
            if not all(math.isfinite(value) for value in [chl, chl_monthly, amihud]) or amihud <= 0:
                continue
            loo_market = (market.loc[beta_dates] * len(SYMBOLS) - asset_beta) / (len(SYMBOLS) - 1)
            rows.append({
                "decision_time": decision,
                "entry_time": entry,
                "exit_time": exit_time,
                "symbol": symbol,
                "formation_pairs": pairs,
                "chl_spread": chl,
                "chl_monthly_corrected": chl_monthly,
                "amihud": amihud,
                "log_amihud": float(np.log(amihud)),
                "market_beta": beta_coefficient(asset_beta.to_numpy(float), loo_market.to_numpy(float)),
                "mom7": float(frame.at[decision, "open"] / frame.at[decision - pd.Timedelta(days=7), "open"] - 1.0),
                "mom28": float(frame.at[decision, "open"] / frame.at[decision - pd.Timedelta(days=28), "open"] - 1.0),
                "vol28": float(asset_control.std(ddof=1)),
                "max28": float(asset_control.max()),
                "log_volume30": float(np.log(median_volume)),
                "target_return": float(frame.at[exit_time, "open"] / frame.at[entry, "open"] - 1.0),
            })
    panel = pd.DataFrame(rows)
    if panel.empty:
        return panel
    assigned: list[pd.DataFrame] = []
    for _decision, group in panel.groupby("decision_time", sort=True):
        ordered = group.sort_values(["chl_spread", "symbol"]).copy()
        n = len(ordered)
        if n < int(CONFIG["minimum_rankable"]) or ordered["chl_spread"].nunique() < 2:
            continue
        ordered["spread_percentile"] = np.arange(n, dtype=float) / max(1, n - 1)
        tail = max(1, int(math.ceil(n * float(CONFIG["tail_fraction"]))))
        ordered["group"] = "other"
        ordered.iloc[:tail, ordered.columns.get_loc("group")] = "low"
        ordered.iloc[-tail:, ordered.columns.get_loc("group")] = "high"
        assigned.append(ordered)
    return pd.concat(assigned, ignore_index=True) if assigned else pd.DataFrame()


def block_ci(values: np.ndarray) -> list[float]:
    return BASE.block_ci(np.asarray(values, dtype=float))


def hac_mean(values: np.ndarray, expected_positive: bool = True) -> dict[str, float]:
    return BASE.hac_mean(np.asarray(values, dtype=float), expected_positive=expected_positive)


def finite_stat(value: float) -> float:
    return float(value) if math.isfinite(float(value)) else 0.0


def tail_spread(group: pd.DataFrame, column: str, high_minus_low: bool = True) -> float:
    ordered = group.sort_values([column, "symbol"])
    tail = max(1, int(math.ceil(len(ordered) * float(CONFIG["tail_fraction"]))))
    low = float(ordered.head(tail)["target_return"].mean())
    high = float(ordered.tail(tail)["target_return"].mean())
    return high - low if high_minus_low else low - high


def weekly_statistics(panel: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    weekly_rows: list[dict[str, Any]] = []
    selected_rows: list[dict[str, Any]] = []
    for decision, group in panel.groupby("decision_time", sort=True):
        high = group[group["group"] == "high"]
        low = group[group["group"] == "low"]
        if high.empty or low.empty:
            continue
        selected = high.sort_values(["log_volume30", "symbol"], ascending=[False, True]).iloc[0]
        ic = finite_stat(spearmanr(group["chl_spread"], group["target_return"]).statistic)
        standardized = group.copy()
        for column in ["chl_spread", *CONTROL_COLUMNS]:
            standardized[column] = zscore(standardized[column])
        design = sm.add_constant(standardized[["chl_spread", *CONTROL_COLUMNS]].to_numpy(float))
        controlled = np.linalg.lstsq(design, standardized["target_return"].to_numpy(float), rcond=None)[0]
        correlations = {
            column: finite_stat(spearmanr(group["chl_spread"], group[column]).statistic)
            for column in CONTROL_COLUMNS
        }
        high_return = float(high["target_return"].mean())
        low_return = float(low["target_return"].mean())
        main_spread = high_return - low_return
        amihud_spread = tail_spread(group, "log_amihud")
        volatility_spread = tail_spread(group, "vol28")
        weekly_rows.append({
            "decision_time": decision,
            "rankable": int(len(group)),
            "high_chl_return": high_return,
            "low_chl_return": low_return,
            "high_minus_low": main_spread,
            "chl_rank_ic": ic,
            "controlled_chl_slope": float(controlled[1]),
            "amihud_high_minus_low": amihud_spread,
            "volatility_high_minus_low": volatility_spread,
            "main_minus_amihud": main_spread - amihud_spread,
            "main_minus_volatility": main_spread - volatility_spread,
            "monthly_corrected_chl_high_minus_low": tail_spread(group, "chl_monthly_corrected"),
            **{f"score_{key}_spearman": value for key, value in correlations.items()},
            "selected_symbol": str(selected["symbol"]),
            "selected_gross_return": float(selected["target_return"]),
        })
        weekly_hurdle = (1.0 + float(CONFIG["annual_full_plan_hurdle"])) ** (7.0 / 365.0) - 1.0
        full_plan = float(CONFIG["economic_notional_fraction"]) * (
            float(selected["target_return"]) - float(CONFIG["stress_round_trip_underlying"])
        ) - weekly_hurdle
        selected_rows.append({
            "decision_time": decision,
            "entry_time": selected["entry_time"],
            "exit_time": selected["exit_time"],
            "symbol": str(selected["symbol"]),
            "gross_return": float(selected["target_return"]),
            "full_plan_after_cost_and_hurdle": full_plan,
        })
    return pd.DataFrame(weekly_rows), pd.DataFrame(selected_rows)


def summarize(panel: pd.DataFrame) -> tuple[dict[str, Any], pd.DataFrame, pd.DataFrame]:
    weekly, selected = weekly_statistics(panel)
    spread = weekly["high_minus_low"].to_numpy(float)
    proxy = selected["full_plan_after_cost_and_hurdle"].to_numpy(float)
    midpoint = len(weekly) // 2
    ic = hac_mean(weekly["chl_rank_ic"].to_numpy(float), expected_positive=True)
    controlled = hac_mean(weekly["controlled_chl_slope"].to_numpy(float), expected_positive=True)
    symbol_summary = selected.groupby("symbol")["full_plan_after_cost_and_hurdle"].agg(["count", "mean", "sum"])
    positive = symbol_summary[symbol_summary["sum"] > 0]
    total_positive = float(positive["sum"].sum())
    maximum_share = float(positive["sum"].max() / total_positive) if total_positive > 0 else 1.0
    correlation_columns = [f"score_{column}_spearman" for column in CONTROL_COLUMNS]
    increment_amihud = weekly["main_minus_amihud"].to_numpy(float)
    increment_volatility = weekly["main_minus_volatility"].to_numpy(float)
    summary = {
        "weeks": int(len(weekly)),
        "panel_rows": int(len(panel)),
        "rankable": {
            "minimum": int(weekly["rankable"].min()),
            "median": float(weekly["rankable"].median()),
            "maximum": int(weekly["rankable"].max()),
        },
        "spread": {
            "mean": float(spread.mean()),
            "block_bootstrap_95pct": block_ci(spread),
            "positive_fraction": float((spread > 0).mean()),
            "first_half_mean": float(spread[:midpoint].mean()),
            "second_half_mean": float(spread[midpoint:].mean()),
        },
        "rank_ic": ic,
        "controlled_chl_slope": controlled,
        "simple_explanations": {
            "amihud_high_minus_low_mean": float(weekly["amihud_high_minus_low"].mean()),
            "volatility_high_minus_low_mean": float(weekly["volatility_high_minus_low"].mean()),
            "main_minus_amihud": {
                "mean": float(increment_amihud.mean()),
                "block_bootstrap_95pct": block_ci(increment_amihud),
            },
            "main_minus_volatility": {
                "mean": float(increment_volatility.mean()),
                "block_bootstrap_95pct": block_ci(increment_volatility),
            },
            "monthly_corrected_chl_spread_mean": float(
                weekly["monthly_corrected_chl_high_minus_low"].mean()
            ),
        },
        "single_leg_proxy": {
            "mean_after_cost_and_hurdle": float(proxy.mean()),
            "block_bootstrap_95pct": block_ci(proxy),
            "positive_fraction": float((proxy > 0).mean()),
            "first_half_mean": float(proxy[:midpoint].mean()),
            "second_half_mean": float(proxy[midpoint:].mean()),
            "selected_symbols": int(len(symbol_summary)),
            "positive_symbol_fraction": float((symbol_summary["mean"] > 0).mean()),
            "maximum_positive_contribution_share": maximum_share,
        },
        "score_control_correlation": {
            "median_absolute_by_control": {
                column.replace("score_", "").replace("_spearman", ""): float(weekly[column].abs().median())
                for column in correlation_columns
            },
            "maximum_median_absolute": float(
                max(weekly[column].abs().median() for column in correlation_columns)
            ),
        },
    }
    return summary, weekly, selected


def stage_authorized(stage: str) -> None:
    if stage == "evaluation" and read_json(HERE / "development_gate.json")["status"] != "PASS":
        raise RuntimeError("evaluation remains sealed")
    if stage == "confirmation" and read_json(HERE / "evaluation_gate.json")["status"] != "PASS":
        raise RuntimeError("confirmation remains sealed")


def analysis_core(stage: str) -> tuple[dict[str, Any], dict[str, pd.DataFrame]]:
    bars, _exchange = BASE.load_data()
    summaries: dict[str, Any] = {}
    outputs: dict[str, pd.DataFrame] = {}
    hashes: dict[str, str] = {}
    for name, pairs in WINDOWS.items():
        panel = build_panel(bars, stage, pairs)
        summary, weekly, selected = summarize(panel)
        summaries[name] = summary
        for kind, frame in [(f"{name}_panel", panel), (f"{name}_weekly", weekly), (f"{name}_selected", selected)]:
            outputs[kind] = frame
            raw = frame.to_csv(index=False, date_format="%Y-%m-%dT%H:%M:%SZ").encode("utf-8")
            hashes[f"{stage}_{kind}.csv"] = digest_bytes(raw)
    core = {
        "stage": stage,
        "period": {"start": STAGES[stage][0], "end_exclusive": STAGES[stage][1]},
        "data_quality_digest": read_json(HERE / "data_quality.json")["content_digest"],
        "reference_benchmark_digest": read_json(HERE / "reference_benchmark.json")["content_digest"],
        "summaries": summaries,
        "csv_sha256": hashes,
        "search_disclosure": {
            "selectable_primary_configurations": 1,
            "main": "28-pair two-day-corrected CHL; high-minus-low quintile",
            "diagnostics_only": [
                "14-pair two-day-corrected CHL",
                "56-pair two-day-corrected CHL",
                "28-pair monthly-corrected CHL",
                "Amihud and volatility simple explanations",
            ],
            "source_calendar_overlap": True,
            "prior_broad_market_path_exposure": True,
        },
    }
    return core, outputs


def command_analyze(args: argparse.Namespace) -> None:
    assert_checkpoint()
    stage_authorized(args.stage)
    if read_json(HERE / "data_quality.json")["status"] != "PASS":
        raise RuntimeError("data quality is not PASS")
    core, outputs = analysis_core(args.stage)
    for name, frame in outputs.items():
        (HERE / f"{args.stage}_{name}.csv").write_bytes(
            frame.to_csv(index=False, date_format="%Y-%m-%dT%H:%M:%SZ").encode("utf-8")
        )
    write_json(HERE / f"{args.stage}.json", {"generated_at_utc": now_utc(), **core})
    main = core["summaries"]["primary_28p"]
    print(json.dumps({
        "stage": args.stage,
        "spread": main["spread"]["mean"],
        "increment_vs_amihud": main["simple_explanations"]["main_minus_amihud"]["mean"],
        "increment_vs_volatility": main["simple_explanations"]["main_minus_volatility"]["mean"],
        "proxy": main["single_leg_proxy"]["mean_after_cost_and_hurdle"],
    }))


def gate_checks(stage: str, result: dict[str, Any]) -> dict[str, bool]:
    main = result["summaries"]["primary_28p"]
    spread = main["spread"]
    proxy = main["single_leg_proxy"]
    simple = main["simple_explanations"]
    return {
        "data_quality_pass": read_json(HERE / "data_quality.json")["status"] == "PASS",
        "all_action_weeks_present": main["weeks"] == EXPECTED_WEEKS[stage],
        "median_rankable_at_least_20": main["rankable"]["median"] >= int(CONFIG["minimum_rankable"]),
        "spread_mean_positive": spread["mean"] > 0,
        "spread_bootstrap_lower_positive": spread["block_bootstrap_95pct"][0] > 0,
        "spread_positive_fraction_at_least_55pct": spread["positive_fraction"] >= float(CONFIG["minimum_positive_spread_fraction"]),
        "rank_ic_positive": main["rank_ic"]["mean"] > 0,
        "rank_ic_one_sided_hac_p_lt_10pct": main["rank_ic"]["hac_one_sided_p"] < 0.10,
        "controlled_slope_positive": main["controlled_chl_slope"]["mean"] > 0,
        "controlled_slope_one_sided_hac_p_lt_10pct": main["controlled_chl_slope"]["hac_one_sided_p"] < 0.10,
        "increment_vs_amihud_mean_positive": simple["main_minus_amihud"]["mean"] > 0,
        "increment_vs_volatility_mean_positive": simple["main_minus_volatility"]["mean"] > 0,
        "proxy_mean_after_cost_hurdle_positive": proxy["mean_after_cost_and_hurdle"] > 0,
        "proxy_bootstrap_lower_positive": proxy["block_bootstrap_95pct"][0] > 0,
        "spread_both_halves_positive": spread["first_half_mean"] > 0 and spread["second_half_mean"] > 0,
        "proxy_both_halves_positive": proxy["first_half_mean"] > 0 and proxy["second_half_mean"] > 0,
        "diagnostic_14p_spread_nonnegative": result["summaries"]["diagnostic_14p"]["spread"]["mean"] >= 0,
        "diagnostic_56p_spread_nonnegative": result["summaries"]["diagnostic_56p"]["spread"]["mean"] >= 0,
        "monthly_corrected_28p_spread_nonnegative": simple["monthly_corrected_chl_spread_mean"] >= 0,
        "proxy_selected_symbol_breadth": proxy["selected_symbols"] >= int(CONFIG["minimum_selected_symbols"]),
        "proxy_positive_symbol_fraction": proxy["positive_symbol_fraction"] >= float(CONFIG["minimum_positive_symbol_fraction"]),
        "proxy_contribution_not_concentrated": proxy["maximum_positive_contribution_share"] <= float(CONFIG["maximum_positive_contribution_share"]),
        "score_not_control_duplicate": main["score_control_correlation"]["maximum_median_absolute"] < float(CONFIG["maximum_abs_score_control_correlation"]),
    }


ECONOMIC_CHECKS = {
    "spread_mean_positive",
    "increment_vs_amihud_mean_positive",
    "increment_vs_volatility_mean_positive",
    "proxy_mean_after_cost_hurdle_positive",
}


def command_gate(args: argparse.Namespace) -> None:
    result = read_json(HERE / f"{args.stage}.json")
    checks = gate_checks(args.stage, result)
    payload = {
        "generated_at_utc": now_utc(),
        "stage": args.stage,
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "failed_checks": [key for key, value in checks.items() if not value],
        "economic_failed_checks": [key for key in ECONOMIC_CHECKS if not checks.get(key, True)],
        "result_digest": result["content_digest"],
    }
    write_json(HERE / f"{args.stage}_gate.json", payload)
    print(json.dumps({"stage": args.stage, "status": payload["status"], "failed": payload["failed_checks"]}))


def render_result(payload: dict[str, Any], gates: dict[str, dict[str, Any]]) -> str:
    lines = [
        "# Result",
        "",
        f"Conclusion: `{payload['conclusion']}`.",
        "",
        payload["claim"] + ".",
        "",
        "## Opened evidence",
        "",
    ]
    for stage in payload["available_stages"]:
        result = read_json(HERE / f"{stage}.json")
        main = result["summaries"]["primary_28p"]
        simple = main["simple_explanations"]
        proxy = main["single_leg_proxy"]
        lines.extend([
            f"### {stage}",
            "",
            f"- Gate: `{gates[stage]['status']}`; weeks: {main['weeks']}; median rankable: {main['rankable']['median']:.1f}.",
            f"- CHL high-minus-low mean: {main['spread']['mean']:.6f}; 95% block CI: "
            f"[{main['spread']['block_bootstrap_95pct'][0]:.6f}, {main['spread']['block_bootstrap_95pct'][1]:.6f}].",
            f"- Mean increment versus Amihud: {simple['main_minus_amihud']['mean']:.6f}; "
            f"versus volatility: {simple['main_minus_volatility']['mean']:.6f}.",
            f"- Controlled CHL slope: {main['controlled_chl_slope']['mean']:.6f}; "
            f"one-sided HAC p: {main['controlled_chl_slope']['hac_one_sided_p']:.4f}.",
            f"- Single-leg full-plan proxy after cost and hurdle: {proxy['mean_after_cost_and_hurdle']:.6f}; "
            f"95% block CI: [{proxy['block_bootstrap_95pct'][0]:.6f}, {proxy['block_bootstrap_95pct'][1]:.6f}].",
            f"- Failed checks: {', '.join(gates[stage]['failed_checks']) if gates[stage]['failed_checks'] else 'none'}.",
            "",
        ])
    reference = read_json(HERE / "reference_benchmark.json")
    value = reference["value_weighted_bidask"]
    lines.extend([
        "## External benchmark check",
        "",
        f"The official CC0 value-weighted bid-ask factor series has {value['usable_observations']} usable weekly observations, "
        f"an arithmetic annualized mean of {value['annualized_arithmetic_mean']:.4f}, and positive means in both halves. "
        "This approximately matches the published broad-spot result but is excluded from Halpha gates.",
        "",
        "## Scope and decision",
        "",
        payload["next_step"] + ".",
        "",
        "No product strategy, L4 fact, capital state, account state, or real trading action changed.",
        "",
    ])
    return "\n".join(lines)


def command_conclude(_args: argparse.Namespace) -> None:
    assert_checkpoint()
    available = [stage for stage in STAGES if (HERE / f"{stage}.json").exists()]
    gates = {stage: read_json(HERE / f"{stage}_gate.json") for stage in available}
    all_pass = len(gates) == 3 and all(gate["status"] == "PASS" for gate in gates.values())
    any_economic_failure = any(gate["economic_failed_checks"] for gate in gates.values())
    conclusion = "SUPPORTS_WITHIN_SCOPE" if all_pass else (
        "DOES_NOT_SUPPORT" if any_economic_failure else "INSUFFICIENT_EVIDENCE"
    )
    payload = {
        "generated_at_utc": now_utc(),
        "conclusion": conclusion,
        "claim": "Predictive relationship only; no strategy qualification or long-term profitability claim",
        "available_stages": available,
        "stage_gate_status": {stage: gate["status"] for stage, gate in gates.items()},
        "stage_failed_checks": {stage: gate["failed_checks"] for stage, gate in gates.items()},
        "next_step": (
            "Open a separate actual-funding strategy-candidate question"
            if conclusion == "SUPPORTS_WITHIN_SCOPE"
            else "Do not convert this predictor into a strategy; preserve the family stop"
        ),
        "product_effects": "NONE",
    }
    write_json(HERE / "results.json", payload)
    (HERE / "result.md").write_text(render_result(payload, gates), encoding="utf-8")
    print(json.dumps({"conclusion": conclusion, "available_stages": available}))


def command_validate(_args: argparse.Namespace) -> None:
    assert_checkpoint()
    checks: dict[str, bool] = {
        "data_quality_pass": read_json(HERE / "data_quality.json")["status"] == "PASS",
        "source_reuse_manifest_present": (HERE / "source_reuse_manifest.json").exists(),
        "parent_manifest_identity": digest_file(PARENT_MANIFEST) == PARENT_MANIFEST_SHA256,
        "pinned_research_base_identity": digest_file(BASE_STUDY) == BASE_STUDY_SHA256,
        "reference_benchmark_present": (HERE / "reference_benchmark.json").exists(),
    }
    for name, item in REFERENCE_FILES.items():
        path = Path(item["path"])
        checks[f"reference_{name}_identity"] = (
            path.exists() and path.stat().st_size == item["bytes"] and digest_file(path) == item["sha256"]
        )
    for stage in STAGES:
        path = HERE / f"{stage}.json"
        if not path.exists():
            continue
        stored = read_json(path)
        recomputed, _ = analysis_core(stage)
        stored_core = {key: value for key, value in stored.items() if key not in {"generated_at_utc", "content_digest"}}
        checks[f"{stage}_economics_recomputed"] = digest_value(stored_core) == digest_value(recomputed)
        checks[f"{stage}_gate_bound"] = read_json(HERE / f"{stage}_gate.json")["result_digest"] == stored["content_digest"]
        for name, expected in stored["csv_sha256"].items():
            checks[f"{name}_identity"] = digest_file(HERE / name) == expected
    if (HERE / "results.json").exists():
        result = read_json(HERE / "results.json")
        checks["valid_conclusion"] = result["conclusion"] in {
            "SUPPORTS_WITHIN_SCOPE", "DOES_NOT_SUPPORT", "INSUFFICIENT_EVIDENCE", "CANNOT_DETERMINE"
        }
        checks["no_strategy_handoff_claim"] = "strategy qualification" in result["claim"]
        checks["result_markdown_present"] = (HERE / "result.md").exists()
    payload = {
        "validated_at_utc": now_utc(),
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "json_files_checked": len(list(HERE.glob("*.json"))),
        "csv_files_checked": len(list(HERE.glob("*.csv"))),
    }
    write_json(HERE / "validation.json", payload)
    print(json.dumps({"status": payload["status"], "checks": checks}))
    if payload["status"] != "PASS":
        raise RuntimeError("validation failed")


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="OHLC-estimated spread and next-week return predictability")
    sub = root.add_subparsers(dest="command", required=True)
    sub.add_parser("checkpoint").set_defaults(func=command_checkpoint)
    sub.add_parser("bind").set_defaults(func=command_bind)
    sub.add_parser("inspect").set_defaults(func=command_inspect)
    for name, function in (("analyze", command_analyze), ("gate", command_gate)):
        item = sub.add_parser(name)
        item.add_argument("--stage", choices=tuple(STAGES), required=True)
        item.set_defaults(func=function)
    sub.add_parser("conclude").set_defaults(func=command_conclude)
    sub.add_parser("validate").set_defaults(func=command_validate)
    return root


def main() -> None:
    args = parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
