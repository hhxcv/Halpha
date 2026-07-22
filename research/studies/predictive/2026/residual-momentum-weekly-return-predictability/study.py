from __future__ import annotations

import argparse
import hashlib
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
BASELINE_COMMIT = "0bdfeffa616260cebd2d2188ddc8deb9e85c77f4"
PARENT_MANIFEST = ROOT / (
    "research/studies/predictive/2026/intermediate-vix-beta-weekly-return-predictability/"
    "source_manifest.json"
)
PARENT_MANIFEST_SHA256 = "07d0c80a4ea858e767960c53bc9ef5345cecc1a07fb482d9d2d87b862fb50693"
PARENT_MANIFEST_CONTENT_DIGEST = "d8cab91fb7ccdc39204aa2b783d13376b92ba0137fb3cb8e6a164cb432ed3514"
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
WINDOWS = {"diagnostic_7d": 7, "primary_14d": 14, "diagnostic_28d": 28}
CONFIG = {
    "predictor_id": "RESEARCH_RESIDUAL_MOM14_NEXT_WEEK_V1",
    "beta_days": 84,
    "minimum_median_quote_volume_30d": 10_000_000.0,
    "minimum_rankable": 20,
    "tail_fraction": 0.20,
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
    "raw_mom14", "beta84", "idio_vol84", "total_vol28", "max28", "log_volume30"
]


def now_utc() -> str:
    return pd.Timestamp.now(tz="UTC").isoformat()


def digest_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def digest_file(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def digest_value(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(raw).hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: dict[str, Any]) -> None:
    payload = dict(value)
    payload["content_digest"] = digest_value(payload)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def command_checkpoint(_args: argparse.Namespace) -> None:
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
            "role": "fixed comparison context only",
        },
        "research_kind": "PREDICTIVE",
        "predictor_id": CONFIG["predictor_id"],
        "question": "Does standardized 14-day residual momentum incrementally predict next-week mature-perpetual returns?",
        "replication_status": "Operational weekly perpetual adaptation; not a numerical replication.",
        "evidence_boundary": "Exact rule is new; broad crypto paths and part of the source-paper period were previously exposed.",
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
        "frozen_file_sha256": frozen,
        "environment": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "scipy": scipy.__version__,
            "statsmodels": statsmodels.__version__,
        },
        "framework_decision": "Predictive statistics use pandas/statsmodels; vectorbt is deferred until a strategy conversion is authorized by three passing stages.",
        "stage_open_rule": "development -> evaluation on PASS -> confirmation on PASS",
    }
    write_json(HERE / "checkpoint.json", payload)
    print(json.dumps({"digest": read_json(HERE / "checkpoint.json")["content_digest"], "expected_weeks": EXPECTED_WEEKS}))


def assert_checkpoint() -> None:
    checkpoint = read_json(HERE / "checkpoint.json")
    checks = {
        name: checkpoint["frozen_file_sha256"][name] == digest_file(HERE / name)
        for name in checkpoint["frozen_file_sha256"]
    }
    if not all(checks.values()):
        raise RuntimeError(f"frozen identity mismatch: {checks}")


def verified_bytes(item: dict[str, Any]) -> bytes:
    path = Path(item["path"])
    raw = path.read_bytes()
    if len(raw) != int(item["bytes"]) or digest_bytes(raw) != item["sha256"]:
        raise RuntimeError(f"source identity mismatch: {path}")
    return raw


def command_bind(_args: argparse.Namespace) -> None:
    assert_checkpoint()
    if digest_file(PARENT_MANIFEST) != PARENT_MANIFEST_SHA256:
        raise RuntimeError("parent manifest byte identity mismatch")
    parent = read_json(PARENT_MANIFEST)
    if parent["content_digest"] != PARENT_MANIFEST_CONTENT_DIGEST:
        raise RuntimeError("parent manifest content identity mismatch")
    pages = [item for item in parent["kline_pages"] if item["symbol"] in SYMBOLS]
    if len(pages) != 50 or {item["symbol"] for item in pages} != set(SYMBOLS):
        raise RuntimeError("parent kline page coverage mismatch")
    items = [parent["exchange_info"], *pages]
    for item in items:
        verified_bytes(item)
    payload = {
        "bound_at_utc": now_utc(),
        "parent_manifest_path": str(PARENT_MANIFEST.relative_to(ROOT)).replace("\\", "/"),
        "parent_manifest_sha256": PARENT_MANIFEST_SHA256,
        "parent_manifest_content_digest": PARENT_MANIFEST_CONTENT_DIGEST,
        "data_start": parent["data_start"],
        "data_end_exclusive": parent["data_end_exclusive"],
        "exchange_info": parent["exchange_info"],
        "kline_pages": pages,
        "files_verified": len(items),
        "bytes_verified": sum(int(item["bytes"]) for item in items),
        "raw_item_identity_digest": digest_value([
            {"path": item["path"], "bytes": item["bytes"], "sha256": item["sha256"]}
            for item in items
        ]),
        "copy_performed": False,
    }
    write_json(HERE / "source_reuse_manifest.json", payload)
    print(json.dumps({"files": payload["files_verified"], "bytes": payload["bytes_verified"], "digest": read_json(HERE / "source_reuse_manifest.json")["content_digest"]}))


def load_data() -> tuple[dict[str, pd.DataFrame], dict[str, Any]]:
    if digest_file(PARENT_MANIFEST) != PARENT_MANIFEST_SHA256:
        raise RuntimeError("parent manifest changed")
    manifest = read_json(HERE / "source_reuse_manifest.json")
    if manifest["parent_manifest_sha256"] != PARENT_MANIFEST_SHA256:
        raise RuntimeError("reuse binding mismatch")
    by_symbol: dict[str, list[Any]] = {symbol: [] for symbol in SYMBOLS}
    for item in manifest["kline_pages"]:
        by_symbol[item["symbol"]].extend(json.loads(verified_bytes(item)))
    columns = [
        "open_time", "open", "high", "low", "close", "volume", "close_time",
        "quote_volume", "trades", "taker_base", "taker_quote", "ignore",
    ]
    bars: dict[str, pd.DataFrame] = {}
    for symbol, rows in by_symbol.items():
        frame = pd.DataFrame(rows, columns=columns)
        frame["open_time"] = pd.to_datetime(frame["open_time"], unit="ms", utc=True)
        for column in ["open", "high", "low", "close", "volume", "quote_volume"]:
            frame[column] = pd.to_numeric(frame[column], errors="raise")
        bars[symbol] = frame.drop_duplicates("open_time", keep="last").sort_values("open_time").set_index("open_time")
    exchange = json.loads(verified_bytes(manifest["exchange_info"]))
    return bars, exchange


def command_inspect(_args: argparse.Namespace) -> None:
    assert_checkpoint()
    bars, exchange = load_data()
    expected = pd.date_range(pd.Timestamp(DATA_START), pd.Timestamp(DATA_END_EXCLUSIVE), freq="1D", inclusive="left")
    symbol_checks: dict[str, Any] = {}
    status = True
    for symbol, frame in bars.items():
        selected = frame[(frame.index >= expected[0]) & (frame.index < pd.Timestamp(DATA_END_EXCLUSIVE))]
        invalid_ohlc = int(((selected[["open", "high", "low", "close"]] <= 0).any(axis=1)).sum())
        invalid_range = int(((selected["high"] < selected[["open", "close"]].max(axis=1)) | (selected["low"] > selected[["open", "close"]].min(axis=1))).sum())
        check = {
            "rows": int(len(selected)),
            "first": selected.index.min().isoformat(),
            "last": selected.index.max().isoformat(),
            "missing": int(len(expected.difference(selected.index))),
            "duplicates": int(selected.index.duplicated().sum()),
            "invalid_ohlc": invalid_ohlc,
            "invalid_range": invalid_range,
            "nonpositive_quote_volume": int((selected["quote_volume"] <= 0).sum()),
            "median_quote_volume": float(selected["quote_volume"].median()),
        }
        symbol_checks[symbol] = check
        status = status and all([
            check["missing"] == 0, check["duplicates"] == 0,
            invalid_ohlc == 0, invalid_range == 0,
            check["nonpositive_quote_volume"] == 0,
        ])
    current = {item["symbol"]: item for item in exchange["symbols"] if item["symbol"] in SYMBOLS}
    current_ok = len(current) == len(SYMBOLS) and all(
        item["status"] == "TRADING" and item["contractType"] == "PERPETUAL"
        for item in current.values()
    )
    payload = {
        "checked_at_utc": now_utc(),
        "status": "PASS" if status and current_ok else "FAIL",
        "symbols": symbol_checks,
        "current_exchange": {"present": len(current), "all_trading_perpetual": current_ok},
        "source_reuse_manifest_digest": read_json(HERE / "source_reuse_manifest.json")["content_digest"],
    }
    write_json(HERE / "data_quality.json", payload)
    print(json.dumps({"status": payload["status"], "symbols": len(symbol_checks), "rows_each": sorted({v["rows"] for v in symbol_checks.values()})}))
    if payload["status"] != "PASS":
        raise RuntimeError("data quality failed")


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


def fit_beta(asset: pd.Series, market: pd.Series) -> float:
    design = np.column_stack([np.ones(len(asset)), market.to_numpy(float)])
    return float(np.linalg.lstsq(design, asset.to_numpy(float), rcond=None)[0][1])


def compounded(values: pd.Series) -> float:
    return float(np.prod(1.0 + values.to_numpy(float)) - 1.0)


def build_panel(bars: dict[str, pd.DataFrame], stage: str, formation_days: int) -> pd.DataFrame:
    start, end = map(pd.Timestamp, STAGES[stage])
    decisions = pd.date_range(start, end, freq="7D", inclusive="left")
    returns = daily_return_frame(bars)
    market_sum = returns.sum(axis=1, min_count=len(SYMBOLS))
    rows: list[dict[str, Any]] = []
    beta_days = int(CONFIG["beta_days"])
    for decision in decisions:
        beta_dates = pd.date_range(decision - pd.Timedelta(days=beta_days), decision, freq="1D", inclusive="left")
        formation_dates = pd.date_range(decision - pd.Timedelta(days=formation_days), decision, freq="1D", inclusive="left")
        mom14_dates = pd.date_range(decision - pd.Timedelta(days=14), decision, freq="1D", inclusive="left")
        control_dates = pd.date_range(decision - pd.Timedelta(days=28), decision, freq="1D", inclusive="left")
        volume_dates = pd.date_range(decision - pd.Timedelta(days=30), decision, freq="1D", inclusive="left")
        entry = decision + pd.Timedelta(days=int(CONFIG["action_gap_days"]))
        exit_time = entry + pd.Timedelta(days=int(CONFIG["target_days"]))
        for symbol in SYMBOLS:
            frame = bars[symbol]
            required = set(beta_dates) | set(formation_dates) | set(mom14_dates) | set(control_dates) | set(volume_dates) | {entry, exit_time}
            if not required.issubset(set(frame.index)):
                continue
            asset_beta = returns.loc[beta_dates, symbol]
            if asset_beta.isna().any():
                continue
            loo_market = (market_sum.loc[beta_dates] - asset_beta) / (len(SYMBOLS) - 1)
            if loo_market.isna().any():
                continue
            median_volume = float(frame.loc[volume_dates, "quote_volume"].median())
            if median_volume < float(CONFIG["minimum_median_quote_volume_30d"]):
                continue
            beta = fit_beta(asset_beta, loo_market)
            residual_full = asset_beta - beta * loo_market
            residual_formation = residual_full.loc[formation_dates]
            residual_std = float(residual_formation.std(ddof=1))
            if not math.isfinite(residual_std) or residual_std <= 0:
                continue
            asset_control = returns.loc[control_dates, symbol]
            row = {
                "decision_time": decision,
                "entry_time": entry,
                "exit_time": exit_time,
                "symbol": symbol,
                "formation_days": formation_days,
                "residual_momentum": float(residual_formation.mean() / residual_std),
                "raw_mom14": compounded(returns.loc[mom14_dates, symbol]),
                "beta84": beta,
                "idio_vol84": float(residual_full.std(ddof=1)),
                "total_vol28": float(asset_control.std(ddof=1)),
                "max28": float(asset_control.max()),
                "log_volume30": float(np.log(median_volume)),
                "target_return": float(frame.at[exit_time, "open"] / frame.at[entry, "open"] - 1.0),
            }
            rows.append(row)
    panel = pd.DataFrame(rows)
    if panel.empty:
        return panel
    assigned: list[pd.DataFrame] = []
    for _decision, group in panel.groupby("decision_time", sort=True):
        ordered = group.sort_values(["residual_momentum", "symbol"]).copy()
        n = len(ordered)
        if n < int(CONFIG["minimum_rankable"]):
            continue
        tail = max(1, int(math.ceil(n * float(CONFIG["tail_fraction"]))))
        ordered["group"] = "other"
        ordered.iloc[:tail, ordered.columns.get_loc("group")] = "low"
        ordered.iloc[-tail:, ordered.columns.get_loc("group")] = "high"
        assigned.append(ordered)
    return pd.concat(assigned, ignore_index=True) if assigned else pd.DataFrame()


def block_ci(values: np.ndarray) -> list[float]:
    values = np.asarray(values, dtype=float)
    rng = np.random.default_rng(int(CONFIG["bootstrap"]["seed"]))
    block = int(CONFIG["bootstrap"]["block_weeks"])
    means = np.empty(int(CONFIG["bootstrap"]["repetitions"]))
    for repetition in range(len(means)):
        chosen: list[int] = []
        while len(chosen) < len(values):
            start = int(rng.integers(0, len(values)))
            chosen.extend(((start + np.arange(block)) % len(values)).tolist())
        means[repetition] = values[np.asarray(chosen[:len(values)])].mean()
    return [float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975))]


def hac_mean(values: np.ndarray, expected_positive: bool = True) -> dict[str, float]:
    fit = sm.OLS(np.asarray(values, dtype=float), np.ones((len(values), 1))).fit(
        cov_type="HAC", cov_kwds={"maxlags": int(CONFIG["hac_maxlags"])}
    )
    coefficient = float(fit.params[0])
    two_sided = float(fit.pvalues[0])
    favorable = coefficient >= 0 if expected_positive else coefficient <= 0
    return {
        "mean": coefficient,
        "hac_t": float(fit.tvalues[0]),
        "hac_two_sided_p": two_sided,
        "hac_one_sided_p": two_sided / 2.0 if favorable else 1.0 - two_sided / 2.0,
    }


def tail_means(group: pd.DataFrame, column: str) -> tuple[float, float]:
    ordered = group.sort_values([column, "symbol"])
    tail = max(1, int(math.ceil(len(ordered) * float(CONFIG["tail_fraction"]))))
    return float(ordered.head(tail)["target_return"].mean()), float(ordered.tail(tail)["target_return"].mean())


def tail_beta_spread(group: pd.DataFrame, column: str) -> float:
    ordered = group.sort_values([column, "symbol"])
    tail = max(1, int(math.ceil(len(ordered) * float(CONFIG["tail_fraction"]))))
    return float(ordered.tail(tail)["beta84"].mean() - ordered.head(tail)["beta84"].mean())


def weekly_statistics(panel: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    weekly_rows: list[dict[str, Any]] = []
    selected_rows: list[dict[str, Any]] = []
    for decision, group in panel.groupby("decision_time", sort=True):
        high = group[group["group"] == "high"]
        low = group[group["group"] == "low"]
        if high.empty or low.empty:
            continue
        selected = high.sort_values(["log_volume30", "symbol"], ascending=[False, True]).iloc[0]
        ic = float(spearmanr(group["residual_momentum"], group["target_return"]).statistic)
        standardized = group.copy()
        for column in ["residual_momentum", *CONTROL_COLUMNS]:
            standardized[column] = zscore(standardized[column])
        design = sm.add_constant(standardized[["residual_momentum", *CONTROL_COLUMNS]].to_numpy(float))
        controlled = np.linalg.lstsq(design, standardized["target_return"].to_numpy(float), rcond=None)[0]
        raw_low, raw_high = tail_means(group, "raw_mom14")
        correlations = {
            column: float(spearmanr(group["residual_momentum"], group[column]).statistic)
            for column in CONTROL_COLUMNS
        }
        rmom_spread = float(high["target_return"].mean() - low["target_return"].mean())
        raw_spread = raw_high - raw_low
        weekly_rows.append({
            "decision_time": decision,
            "rankable": int(len(group)),
            "rmom_high_return": float(high["target_return"].mean()),
            "rmom_low_return": float(low["target_return"].mean()),
            "rmom_high_minus_low": rmom_spread,
            "raw_mom_high_minus_low": raw_spread,
            "rmom_minus_raw_spread": rmom_spread - raw_spread,
            "rmom_rank_ic": ic,
            "controlled_rmom_slope": float(controlled[1]),
            "rmom_tail_beta_spread": float(high["beta84"].mean() - low["beta84"].mean()),
            "raw_mom_tail_beta_spread": tail_beta_spread(group, "raw_mom14"),
            "equal_weight_market_return": float(group["target_return"].mean()),
            **{f"score_{key}_spearman": value for key, value in correlations.items()},
            "selected_symbol": str(selected["symbol"]),
            "selected_gross_return": float(selected["target_return"]),
        })
        weekly_hurdle = (1.0 + float(CONFIG["annual_full_plan_hurdle"])) ** (7.0 / 365.0) - 1.0
        proxy = float(CONFIG["economic_notional_fraction"]) * (
            float(selected["target_return"]) - float(CONFIG["stress_round_trip_underlying"])
        ) - weekly_hurdle
        selected_rows.append({
            "decision_time": decision,
            "entry_time": selected["entry_time"],
            "exit_time": selected["exit_time"],
            "symbol": str(selected["symbol"]),
            "gross_return": float(selected["target_return"]),
            "full_plan_after_cost_and_hurdle": proxy,
        })
    return pd.DataFrame(weekly_rows), pd.DataFrame(selected_rows)


def summarize(panel: pd.DataFrame) -> tuple[dict[str, Any], pd.DataFrame, pd.DataFrame]:
    weekly, selected = weekly_statistics(panel)
    spread = weekly["rmom_high_minus_low"].to_numpy(float)
    proxy = selected["full_plan_after_cost_and_hurdle"].to_numpy(float)
    midpoint = len(weekly) // 2
    symbol_summary = selected.groupby("symbol")["full_plan_after_cost_and_hurdle"].agg(["count", "mean", "sum"])
    positive = symbol_summary[symbol_summary["sum"] > 0]
    total_positive = float(positive["sum"].sum())
    maximum_share = float(positive["sum"].max() / total_positive) if total_positive > 0 else 1.0
    correlation_columns = [f"score_{column}_spearman" for column in CONTROL_COLUMNS]
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
        "rank_ic": hac_mean(weekly["rmom_rank_ic"].to_numpy(float)),
        "controlled_rmom_slope": hac_mean(weekly["controlled_rmom_slope"].to_numpy(float)),
        "ordinary_momentum_baseline": {
            "spread_mean": float(weekly["raw_mom_high_minus_low"].mean()),
            "rmom_minus_raw_mean": float(weekly["rmom_minus_raw_spread"].mean()),
        },
        "market_exposure_mechanism": {
            "rmom_tail_beta_spread_median_abs": float(weekly["rmom_tail_beta_spread"].abs().median()),
            "raw_mom_tail_beta_spread_median_abs": float(weekly["raw_mom_tail_beta_spread"].abs().median()),
        },
        "equal_weight_market_return_mean": float(weekly["equal_weight_market_return"].mean()),
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
            "maximum_median_absolute": float(max(weekly[column].abs().median() for column in correlation_columns)),
        },
    }
    return summary, weekly, selected


def stage_authorized(stage: str) -> None:
    if stage == "evaluation" and read_json(HERE / "development_gate.json")["status"] != "PASS":
        raise RuntimeError("evaluation remains sealed")
    if stage == "confirmation" and read_json(HERE / "evaluation_gate.json")["status"] != "PASS":
        raise RuntimeError("confirmation remains sealed")


def analysis_core(stage: str) -> tuple[dict[str, Any], dict[str, pd.DataFrame]]:
    bars, _exchange = load_data()
    summaries: dict[str, Any] = {}
    outputs: dict[str, pd.DataFrame] = {}
    hashes: dict[str, str] = {}
    for name, window in WINDOWS.items():
        panel = build_panel(bars, stage, window)
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
        "summaries": summaries,
        "csv_sha256": hashes,
        "search_disclosure": {
            "selectable_primary_configurations": 1,
            "main": "standardized RMOM14; high-minus-low quintile",
            "diagnostics_only": ["RMOM7", "RMOM28"],
            "source_sample_partly_overlaps_development": True,
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
    main = core["summaries"]["primary_14d"]
    print(json.dumps({
        "stage": args.stage,
        "spread": main["spread"]["mean"],
        "ordinary_momentum": main["ordinary_momentum_baseline"]["spread_mean"],
        "proxy": main["single_leg_proxy"]["mean_after_cost_and_hurdle"],
    }))


def gate_checks(stage: str, result: dict[str, Any]) -> dict[str, bool]:
    main = result["summaries"]["primary_14d"]
    spread = main["spread"]
    proxy = main["single_leg_proxy"]
    exposure = main["market_exposure_mechanism"]
    return {
        "data_quality_pass": read_json(HERE / "data_quality.json")["status"] == "PASS",
        "all_action_weeks_present": main["weeks"] == EXPECTED_WEEKS[stage],
        "median_rankable_at_least_20": main["rankable"]["median"] >= int(CONFIG["minimum_rankable"]),
        "spread_mean_positive": spread["mean"] > 0,
        "spread_bootstrap_lower_positive": spread["block_bootstrap_95pct"][0] > 0,
        "spread_positive_fraction_at_least_55pct": spread["positive_fraction"] >= float(CONFIG["minimum_positive_spread_fraction"]),
        "spread_both_halves_positive": spread["first_half_mean"] > 0 and spread["second_half_mean"] > 0,
        "rank_ic_positive": main["rank_ic"]["mean"] > 0,
        "rank_ic_one_sided_hac_p_lt_10pct": main["rank_ic"]["hac_one_sided_p"] < 0.10,
        "controlled_slope_positive": main["controlled_rmom_slope"]["mean"] > 0,
        "controlled_slope_one_sided_hac_p_lt_10pct": main["controlled_rmom_slope"]["hac_one_sided_p"] < 0.10,
        "incremental_spread_exceeds_raw_momentum": main["ordinary_momentum_baseline"]["rmom_minus_raw_mean"] > 0,
        "common_market_exposure_reduced": exposure["rmom_tail_beta_spread_median_abs"] < exposure["raw_mom_tail_beta_spread_median_abs"],
        "proxy_mean_after_cost_hurdle_positive": proxy["mean_after_cost_and_hurdle"] > 0,
        "proxy_bootstrap_lower_positive": proxy["block_bootstrap_95pct"][0] > 0,
        "proxy_both_halves_positive": proxy["first_half_mean"] > 0 and proxy["second_half_mean"] > 0,
        "diagnostic_7d_spread_nonnegative": result["summaries"]["diagnostic_7d"]["spread"]["mean"] >= 0,
        "diagnostic_28d_spread_nonnegative": result["summaries"]["diagnostic_28d"]["spread"]["mean"] >= 0,
        "proxy_selected_symbol_breadth": proxy["selected_symbols"] >= int(CONFIG["minimum_selected_symbols"]),
        "proxy_positive_symbol_fraction": proxy["positive_symbol_fraction"] >= float(CONFIG["minimum_positive_symbol_fraction"]),
        "proxy_contribution_not_concentrated": proxy["maximum_positive_contribution_share"] <= float(CONFIG["maximum_positive_contribution_share"]),
        "score_not_control_duplicate": main["score_control_correlation"]["maximum_median_absolute"] < float(CONFIG["maximum_abs_score_control_correlation"]),
    }


ECONOMIC_CHECKS = {"spread_mean_positive", "proxy_mean_after_cost_hurdle_positive"}


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


def command_conclude(_args: argparse.Namespace) -> None:
    assert_checkpoint()
    available = [stage for stage in STAGES if (HERE / f"{stage}.json").exists()]
    gates = {stage: read_json(HERE / f"{stage}_gate.json") for stage in available}
    all_pass = len(gates) == 3 and all(gate["status"] == "PASS" for gate in gates.values())
    any_economic_failure = any(gate["economic_failed_checks"] for gate in gates.values())
    conclusion = "SUPPORTS_WITHIN_SCOPE" if all_pass else ("DOES_NOT_SUPPORT" if any_economic_failure else "INSUFFICIENT_EVIDENCE")
    payload = {
        "generated_at_utc": now_utc(),
        "conclusion": conclusion,
        "claim": "Predictive relationship only; no strategy qualification or long-term profitability claim",
        "available_stages": available,
        "stage_gate_status": {stage: gate["status"] for stage, gate in gates.items()},
        "stage_failed_checks": {stage: gate["failed_checks"] for stage, gate in gates.items()},
        "next_step": (
            "Open a separate actual-funding vectorbt strategy-candidate question"
            if conclusion == "SUPPORTS_WITHIN_SCOPE"
            else "No strategy conversion; residual-momentum family stop remains binding"
        ),
        "product_effects": "NONE",
    }
    write_json(HERE / "results.json", payload)
    print(json.dumps({"conclusion": conclusion, "available_stages": available}))


def command_validate(_args: argparse.Namespace) -> None:
    assert_checkpoint()
    checks: dict[str, bool] = {
        "data_quality_pass": read_json(HERE / "data_quality.json")["status"] == "PASS",
        "source_reuse_manifest_present": (HERE / "source_reuse_manifest.json").exists(),
        "parent_manifest_identity": digest_file(PARENT_MANIFEST) == PARENT_MANIFEST_SHA256,
    }
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
    root = argparse.ArgumentParser(description="Residual momentum and next-week return predictability")
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


if __name__ == "__main__":
    arguments = parser().parse_args()
    arguments.func(arguments)
