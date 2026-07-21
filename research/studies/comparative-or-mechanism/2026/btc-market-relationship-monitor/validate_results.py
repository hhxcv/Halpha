"""Independent result and data-quality checks for the BTC relationship monitor."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd


QUESTION_DIR = Path(__file__).resolve().parent
MONITOR_SPEC = importlib.util.spec_from_file_location("btc_relationship_monitor", QUESTION_DIR / "monitor.py")
assert MONITOR_SPEC and MONITOR_SPEC.loader
monitor = importlib.util.module_from_spec(MONITOR_SPEC)
sys.modules[MONITOR_SPEC.name] = monitor
MONITOR_SPEC.loader.exec_module(monitor)


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def analysis_identity_hash(results: pd.DataFrame) -> str:
    """Hash analytical content while excluding online/offline fetch provenance."""
    analytical = results.drop(columns=["fetch_status"]).sort_values("symbol").reset_index(drop=True)
    canonical = analytical.to_csv(index=False, lineterminator="\n").encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def independent_pair_metrics(symbol: str, cache_root: Path) -> dict[str, float | int]:
    def closes(name: str) -> pd.Series:
        frame = pd.read_csv(cache_root / "current" / "binance-spot-1d" / f"{name}.csv.gz")
        index = pd.to_datetime(frame["open_time_ms"], unit="ms", utc=True)
        return pd.Series(pd.to_numeric(frame["close"], errors="coerce").to_numpy(), index=index).dropna()

    prices = pd.concat({"asset": closes(symbol), "btc": closes("BTCUSDT")}, axis=1, join="inner").dropna()
    returns = np.log(prices).diff()
    returns = returns[prices.index.to_series().diff() == pd.Timedelta(days=1)].dropna().tail(365)
    covariance = np.cov(returns["asset"], returns["btc"], ddof=1)
    return {
        "n_obs": len(returns),
        "pearson": float(np.corrcoef(returns["asset"], returns["btc"])[0, 1]),
        "beta": float(covariance[0, 1] / covariance[1, 1]),
        "volatility_ratio": float(returns["asset"].std(ddof=1) / returns["btc"].std(ddof=1)),
    }


def validate(
    cache_root: Path = monitor.DEFAULT_CACHE_ROOT,
    *,
    write_report: bool = False,
) -> dict[str, object]:
    output = QUESTION_DIR / "evidence"
    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    results = pd.read_csv(output / "results.csv")
    significant = pd.read_csv(output / "significant-associations.csv")
    strong = pd.read_csv(output / "strong-associations.csv")
    not_analyzed = pd.read_csv(output / "not-analyzed.csv")
    errors: list[str] = []

    def check(condition: bool, message: str) -> None:
        if not condition:
            errors.append(message)

    check(results["symbol"].is_unique, "results symbols are not unique")
    check(len(results) == summary["counts"]["eligible_objects"], "result row count differs from eligible objects")
    check(int((results["status"] == "ANALYZED").sum()) == summary["counts"]["analyzed"], "analyzed count mismatch")
    check(len(significant) == summary["counts"]["statistically_significant"], "significant count mismatch")
    check(len(strong) == summary["counts"]["strong_association"], "strong count mismatch")
    check(len(not_analyzed) == summary["counts"]["insufficient_sample"], "not-analyzed count mismatch")
    check(set(strong["symbol"]).issubset(set(significant["symbol"])), "strong set is not a significant subset")
    check((significant["q_value_by"] <= 0.05 + 1e-12).all(), "significant file contains q>0.05")
    check((strong["pearson"].abs() >= 0.50 - 1e-12).all(), "strong file contains abs(Pearson)<0.50")
    check(strong["stable_sign"].astype(bool).all(), "strong file contains unstable sign")
    check(not set(summary["universe"]["excluded_bstock_symbols"]) & set(results["symbol"]), "excluded bStock leaked into results")
    check("DGBUSDT" in set(results["symbol"]), "DGB crypto exception is missing")
    check(results.loc[results["status"] == "ANALYZED", "last_return_utc"].nunique() == 1, "analyzed cutoffs are not aligned")
    check(summary["counts"]["fetch_failed"] == 0 and summary["counts"]["stale_cache"] == 0, "freshness failures remain")

    independent: dict[str, object] = {}
    by_symbol = results.set_index("symbol")
    for symbol in ("ETHUSDT", "SOLUSDT", "SUIUSDT", "DOGEUSDT"):
        recomputed = independent_pair_metrics(symbol, cache_root)
        saved = by_symbol.loc[symbol]
        deltas = {
            "pearson": abs(recomputed["pearson"] - float(saved["pearson"])),
            "beta": abs(recomputed["beta"] - float(saved["beta"])),
            "volatility_ratio": abs(recomputed["volatility_ratio"] - float(saved["volatility_ratio"])),
        }
        check(recomputed["n_obs"] == int(saved["n_obs"]), f"{symbol} independent n mismatch")
        check(all(delta < 1e-8 for delta in deltas.values()), f"{symbol} independent metric mismatch: {deltas}")
        independent[symbol] = {"recomputed": recomputed, "absolute_deltas": deltas}

    cutoff_ms = int(pd.Timestamp(summary["data_cutoff_utc"]).timestamp() * 1000)
    cache_checks = {"files_checked": 0, "duplicate_open_times": 0, "nonpositive_closes": 0, "bars_after_cutoff": 0}
    for symbol in ["BTCUSDT", *results["symbol"].tolist()]:
        path = cache_root / "current" / "binance-spot-1d" / f"{symbol}.csv.gz"
        check(path.exists(), f"cache missing: {symbol}")
        if not path.exists():
            continue
        frame = pd.read_csv(path)
        cache_checks["files_checked"] += 1
        cache_checks["duplicate_open_times"] += int(frame["open_time_ms"].duplicated().sum())
        cache_checks["nonpositive_closes"] += int((pd.to_numeric(frame["close"], errors="coerce") <= 0).sum())
        cache_checks["bars_after_cutoff"] += int((pd.to_numeric(frame["close_time_ms"], errors="coerce") > cutoff_ms).sum())
    check(cache_checks["duplicate_open_times"] == 0, "duplicate cached bars found")
    check(cache_checks["nonpositive_closes"] == 0, "nonpositive cached closes found")
    check(cache_checks["bars_after_cutoff"] == 0, "open/future cached bars found")

    crosschecks = summary.get("cross_source_checks", [])
    compared = [row for row in crosschecks if row.get("status") == "COMPARED"]
    check(all(row["direction_agreement"] for row in compared), "cross-source direction mismatch")
    check(all(row["pearson_delta"] < 0.02 for row in compared), "cross-source Pearson difference exceeds 0.02")

    report: dict[str, object] = {
        "validated_at_utc": monitor.iso_z(monitor.utc_now()),
        "assessment": "READY_TO_SHARE_WITH_CAVEATS" if not errors else "NEEDS_REVISION",
        "errors": errors,
        "counts_reconciled": {
            "results": len(results),
            "analyzed": int((results["status"] == "ANALYZED").sum()),
            "significant": len(significant),
            "strong": len(strong),
            "not_analyzed": len(not_analyzed),
        },
        "cache_quality": cache_checks,
        "independent_spot_checks": independent,
        "cross_source_compared": compared,
        "analysis_identity_sha256": analysis_identity_hash(results),
        "analysis_identity_note": "Excludes fetch_status so online and offline cache replays are comparable.",
        "artifact_hashes": {
            path.name: file_hash(path)
            for path in [
                output / "results.csv",
                output / "significant-associations.csv",
                output / "strong-associations.csv",
                output / "not-analyzed.csv",
                output / "summary.json",
                output / "data-manifest.json",
            ]
        },
        "required_caveats": summary["warnings"],
    }
    if write_report:
        (output / "validation.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-root", type=Path, default=monitor.DEFAULT_CACHE_ROOT)
    parser.add_argument(
        "--write-report",
        action="store_true",
        help="Replace evidence/validation.json after deliberately fixing a new evidence cutoff.",
    )
    args = parser.parse_args()
    result = validate(args.cache_root, write_report=args.write_report)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if not result["errors"] else 1)
