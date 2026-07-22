from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import statsmodels.api as sm
import vectorbt as vbt
from statsmodels.stats.multitest import multipletests


STUDY_DIR = Path(__file__).resolve().parent
CHECKPOINT_PATH = STUDY_DIR / "checkpoint.json"
PARENT_DIR = STUDY_DIR.parent / "btc-shock-beta-gap-predictability"
PARENT_CODE = PARENT_DIR / "study.py"
PARENT_MANIFEST = PARENT_DIR / "source_manifest_development.json"
DATA_ROOT = Path(
    "D:/projects/Codex/CodexHome/research-data/halpha/"
    "btc-shock-beta-gap-predictability"
)
EXPECTED_PARENT_CODE_SHA = "3c2d83c79881c81fdc08e9ea0e55a568ecd677c3809b0a86a1f8905fdfff1ea6"
EXPECTED_PARENT_MANIFEST_SHA = "847588d0721c162374b794bc6720dced970c94095bebc1c0d9c965bc59737b81"


def load_parent_module():
    name = "halpha_btc_gap_parent"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, PARENT_CODE)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load parent study: {PARENT_CODE}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


parent = load_parent_module()
ANCHOR = parent.ANCHOR
ALTS = list(parent.ALTS)
SYMBOLS = list(parent.SYMBOLS)
HOURS_PER_DAY = 24
SCALE_WINDOW_HOURS = 30 * HOURS_PER_DAY
COOLDOWN_HOURS = 12

PHASES = parent.PHASES


@dataclass(frozen=True)
class Config:
    name: str
    beta_days: int = 30
    formation_hours: int = 6
    z_threshold: float = 2.5
    target_hours: int = 12
    entry_delay_hours: int = 1


CONFIGS = [
    Config("primary"),
    Config("beta_7d", beta_days=7),
    Config("beta_90d", beta_days=90),
    Config("formation_1h", formation_hours=1),
    Config("formation_12h", formation_hours=12),
    Config("z_2", z_threshold=2.0),
    Config("z_3", z_threshold=3.0),
    Config("target_4h", target_hours=4),
    Config("target_24h", target_hours=24),
    Config("extra_1h_latency", entry_delay_hours=2),
]


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def code_sha256() -> str:
    return sha256_path(Path(__file__))


def checkpoint() -> dict[str, Any]:
    return json.loads(CHECKPOINT_PATH.read_text(encoding="utf-8"))


def verify_plan() -> None:
    plan = checkpoint()
    actual = code_sha256()
    failures: list[str] = []
    if sha256_path(PARENT_CODE) != EXPECTED_PARENT_CODE_SHA:
        failures.append("parent study code changed")
    if sha256_path(PARENT_MANIFEST) != EXPECTED_PARENT_MANIFEST_SHA:
        failures.append("parent development manifest changed")
    if plan["parent_code_sha256"] != EXPECTED_PARENT_CODE_SHA:
        failures.append("checkpoint parent code hash differs")
    if plan["development_source_manifest_sha256"] != EXPECTED_PARENT_MANIFEST_SHA:
        failures.append("checkpoint parent manifest hash differs")
    if plan["anchor"] != ANCHOR or plan["symbols"] != ALTS:
        failures.append("fixed universe differs from checkpoint")
    expected = plan["study_code_sha256"]
    if expected == "PENDING_BEFORE_FIRST_RESULT":
        failures.append(f"checkpoint code hash is pending; actual is {actual}")
    elif expected != actual:
        failures.append(f"code hash mismatch: checkpoint={expected}, actual={actual}")
    if failures:
        raise RuntimeError("; ".join(failures))
    print(
        json.dumps(
            {
                "status": "PASS",
                "study_code_sha256": actual,
                "parent_code_sha256": EXPECTED_PARENT_CODE_SHA,
                "source_manifest_sha256": EXPECTED_PARENT_MANIFEST_SHA,
                "pandas": pd.__version__,
                "numpy": np.__version__,
                "statsmodels": sm.__version__,
                "vectorbt": vbt.__version__,
            },
            indent=2,
        )
    )


def prior_phase_allows(phase: str) -> bool:
    if phase == "development":
        return True
    prior = "development" if phase == "evaluation" else "evaluation"
    path = STUDY_DIR / f"{prior}.json"
    if not path.exists():
        return False
    return bool(json.loads(path.read_text(encoding="utf-8")).get("release_next_phase"))


def prepare(phase: str, workers: int) -> None:
    verify_plan()
    if phase == "development":
        raise RuntimeError("development reuses the parent manifest and requires no download")
    if not prior_phase_allows(phase):
        raise RuntimeError(f"{phase} remains sealed by the prior phase result")
    tasks = [
        (symbol, month)
        for symbol in SYMBOLS
        for month in parent.phase_prepare_months(phase)
    ]
    records: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    with ThreadPoolExecutor(max_workers=max(1, min(workers, 4))) as executor:
        futures = {
            executor.submit(parent.prepare_one, symbol, month): (symbol, month)
            for symbol, month in tasks
        }
        for future in as_completed(futures):
            symbol, month = futures[future]
            try:
                records.append(future.result())
            except Exception as exc:
                failures.append(
                    {
                        "symbol": symbol,
                        "month": month.strftime("%Y-%m"),
                        "error": repr(exc),
                    }
                )
    manifest = {
        "phase": phase,
        "generated_at_utc": pd.Timestamp.now(tz="UTC").isoformat(),
        "shared_cache": DATA_ROOT.as_posix(),
        "parent_downloader_sha256": EXPECTED_PARENT_CODE_SHA,
        "study_code_sha256": code_sha256(),
        "file_count": len(records),
        "total_bytes": sum(item["bytes"] for item in records),
        "failures": sorted(failures, key=lambda item: (item["symbol"], item["month"])),
        "files": sorted(records, key=lambda item: (item["symbol"], item["month"])),
    }
    path = STUDY_DIR / f"source_manifest_{phase}.json"
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    if failures:
        raise RuntimeError(f"{len(failures)} source failures; inspect {path.name}")
    print(json.dumps({"status": "PASS", "files": len(records), "manifest": str(path)}))


def validate_source_files(phase: str) -> dict[str, Any]:
    manifests = [PARENT_MANIFEST]
    if phase in {"evaluation", "confirmation"}:
        manifests.append(STUDY_DIR / "source_manifest_evaluation.json")
    if phase == "confirmation":
        manifests.append(STUDY_DIR / "source_manifest_confirmation.json")
    file_count = 0
    total_bytes = 0
    identities: list[dict[str, Any]] = []
    for manifest_path in manifests:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for item in manifest["files"]:
            local = DATA_ROOT / item["cache_relative_path"]
            actual = sha256_path(local)
            if actual != item["actual_sha256"] or actual != item["official_sha256"]:
                raise ValueError(f"source hash mismatch: {local}")
            if local.stat().st_size != item["bytes"]:
                raise ValueError(f"source byte count mismatch: {local}")
            file_count += 1
            total_bytes += item["bytes"]
        identities.append(
            {
                "path": str(manifest_path.relative_to(STUDY_DIR) if manifest_path.is_relative_to(STUDY_DIR) else manifest_path),
                "sha256": sha256_path(manifest_path),
                "file_count": len(manifest["files"]),
            }
        )
    result = {
        "phase": phase,
        "validated_at_utc": pd.Timestamp.now(tz="UTC").isoformat(),
        "shared_cache": DATA_ROOT.as_posix(),
        "manifests": identities,
        "validated_file_count": file_count,
        "validated_zip_bytes": total_bytes,
        "status": "PASS",
    }
    path = STUDY_DIR / f"source_reuse_manifest_{phase}.json"
    path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def aggregate_hourly(frame: pd.DataFrame) -> pd.DataFrame:
    counts = frame["open"].resample("1h").count()
    if not (counts == 12).all():
        bad = counts[counts != 12]
        raise ValueError(f"incomplete UTC hours: {bad.head().to_dict()}")
    result = frame.resample("1h").agg(
        {
            "open": "first",
            "close": "last",
            "quote_volume": "sum",
            "trade_count": "sum",
        }
    )
    if result.isna().any().any() or result.index.has_duplicates:
        raise ValueError("invalid hourly aggregation")
    return result


def load_hourly_matrices(phase: str) -> tuple[dict[str, pd.DataFrame], dict[str, Any]]:
    months = parent.required_months_for_run(phase)
    fields: dict[str, dict[str, pd.Series]] = {
        "open": {},
        "close": {},
        "quote_volume": {},
        "trade_count": {},
    }
    quality: dict[str, Any] = {"status": "PASS", "symbols": {}}
    reference: pd.DatetimeIndex | None = None
    for symbol in SYMBOLS:
        raw = pd.concat([parent.read_month(symbol, month) for month in months])
        hourly = aggregate_hourly(raw)
        if reference is None:
            reference = hourly.index
        elif not hourly.index.equals(reference):
            raise ValueError(f"hourly grid for {symbol} differs from {ANCHOR}")
        for field in fields:
            fields[field][symbol] = hourly[field]
        quality["symbols"][symbol] = {
            "hourly_rows": int(len(hourly)),
            "source_5m_rows": int(len(raw)),
            "first": hourly.index[0].isoformat(),
            "last": hourly.index[-1].isoformat(),
            "incomplete_hours": 0,
        }
    matrices = {name: pd.DataFrame(values) for name, values in fields.items()}
    quality["aligned_hourly_rows"] = int(len(matrices["close"]))
    return matrices, quality


def rolling_beta(alt_returns: pd.DataFrame, btc_returns: pd.Series, days: int) -> pd.DataFrame:
    window = days * HOURS_PER_DAY
    btc_var = btc_returns.rolling(window, min_periods=window).var().shift(1)
    return pd.DataFrame(
        {
            symbol: (
                alt_returns[symbol]
                .rolling(window, min_periods=window)
                .cov(btc_returns)
                .shift(1)
                / btc_var
            )
            for symbol in ALTS
        }
    )


def future_residual(
    opens: pd.DataFrame,
    closes: pd.DataFrame,
    beta: pd.DataFrame,
    target_hours: int,
    entry_delay_hours: int,
) -> pd.DataFrame:
    end_shift = entry_delay_hours + target_hours - 1
    alt_move = np.log(
        closes[ALTS].shift(-end_shift) / opens[ALTS].shift(-entry_delay_hours)
    )
    btc_move = np.log(
        closes[ANCHOR].shift(-end_shift) / opens[ANCHOR].shift(-entry_delay_hours)
    )
    return alt_move.subtract(beta.mul(btc_move, axis=0))


def cooldown_mask(condition: pd.DataFrame, cooldown: int) -> pd.DataFrame:
    selected = pd.DataFrame(False, index=condition.index, columns=condition.columns)
    for symbol in condition.columns:
        index = parent.select_events(condition[symbol], cooldown)
        selected.loc[index, symbol] = True
    return selected


def week_groups(index: pd.DatetimeIndex) -> np.ndarray:
    iso = index.isocalendar()
    return (iso["year"].astype(str) + "-W" + iso["week"].astype(str)).to_numpy()


def cluster_summary(series: pd.Series) -> dict[str, Any]:
    values = series.replace([np.inf, -np.inf], np.nan).dropna().astype(float)
    if values.empty:
        return {
            "n": 0,
            "mean_bps": None,
            "median_bps": None,
            "win_rate": None,
            "ci_low_bps": None,
            "ci_high_bps": None,
            "p_value_two_sided": None,
            "cluster_weeks": 0,
        }
    groups = week_groups(pd.DatetimeIndex(values.index))
    if len(np.unique(groups)) >= 2 and len(values) >= 3:
        fit = sm.OLS(values.to_numpy(), np.ones((len(values), 1))).fit(
            cov_type="cluster",
            cov_kwds={"groups": groups, "use_correction": True},
        )
        low, high = fit.conf_int(alpha=0.05)[0]
        p_value = float(fit.pvalues[0])
    else:
        low = high = p_value = math.nan
    return {
        "n": int(len(values)),
        "mean_bps": float(values.mean() * 10_000),
        "median_bps": float(values.median() * 10_000),
        "win_rate": float((values > 0).mean()),
        "ci_low_bps": None if math.isnan(low) else float(low * 10_000),
        "ci_high_bps": None if math.isnan(high) else float(high * 10_000),
        "p_value_two_sided": None if math.isnan(p_value) else p_value,
        "cluster_weeks": int(len(np.unique(groups))),
    }


def event_series(matrix: pd.DataFrame, event_mask: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    selected = matrix.where(event_mask)
    mean = selected.mean(axis=1, skipna=True).dropna()
    counts = selected.notna().sum(axis=1).reindex(mean.index)
    return mean, counts


def analyze_config(
    config: Config,
    matrices: dict[str, pd.DataFrame],
    phase: str,
    returns: pd.DataFrame,
    beta_cache: dict[int, pd.DataFrame],
) -> tuple[dict[str, Any], dict[str, Any]]:
    beta = beta_cache[config.beta_days]
    alt_formation = np.log(
        matrices["close"][ALTS] / matrices["close"][ALTS].shift(config.formation_hours)
    )
    btc_formation = np.log(
        matrices["close"][ANCHOR]
        / matrices["close"][ANCHOR].shift(config.formation_hours)
    )
    formation_residual = alt_formation.subtract(beta.mul(btc_formation, axis=0))
    scale = (
        formation_residual.rolling(
            SCALE_WINDOW_HOURS, min_periods=SCALE_WINDOW_HOURS
        )
        .std()
        .shift(1)
    )
    z_score = formation_residual / scale
    condition = z_score.abs() >= config.z_threshold
    event_mask = cooldown_mask(condition, COOLDOWN_HOURS)
    start = pd.Timestamp(PHASES[phase]["start"], tz="UTC")
    end = pd.Timestamp(PHASES[phase]["end"], tz="UTC")
    outside_phase = (event_mask.index < start) | (event_mask.index >= end)
    event_mask.loc[outside_phase, :] = False

    target = future_residual(
        matrices["open"],
        matrices["close"],
        beta,
        config.target_hours,
        config.entry_delay_hours,
    )
    valid_mask = event_mask & target.notna() & formation_residual.notna()
    response = -np.sign(formation_residual) * target
    primary_events, asset_counts = event_series(response, valid_mask)
    raw_reversal = -np.sign(alt_formation) * target
    baseline_events, _ = event_series(raw_reversal, valid_mask)

    favorable_cost = 12.0 * (1.0 + beta.abs())
    base_cost = 32.0 * (1.0 + beta.abs())
    stress_cost = 52.0 * (1.0 + beta.abs())
    favorable_events, _ = event_series(favorable_cost, valid_mask)
    base_events, _ = event_series(base_cost, valid_mask)
    stress_events, _ = event_series(stress_cost, valid_mask)

    result: dict[str, Any] = {
        "config": asdict(config),
        "event_hours": int(len(primary_events)),
        "asset_events": int(asset_counts.sum()),
        "mean_assets_per_event_hour": float(asset_counts.mean()) if len(asset_counts) else None,
        "primary": cluster_summary(primary_events),
        "same_event_raw_return_reversal_baseline": cluster_summary(baseline_events),
        "paired_round_trip_cost_floor_bps": {
            "favorable_mean": float(favorable_events.mean()) if len(favorable_events) else None,
            "base_mean": float(base_events.mean()) if len(base_events) else None,
            "stress_mean": float(stress_events.mean()) if len(stress_events) else None,
        },
        "subperiods": {},
        "residual_directions": {},
    }
    year = pd.Timestamp(PHASES[phase]["start"]).year
    split = min(start + pd.DateOffset(months=6), end)
    periods = [(f"{year}H1", start, split)]
    if split < end:
        periods.append((f"{year}H2", split, end))
    for label, left, right in periods:
        subset = primary_events[
            (primary_events.index >= left) & (primary_events.index < right)
        ]
        sub_mask = valid_mask.loc[left:right].copy()
        if right in sub_mask.index:
            sub_mask.loc[right] = False
        result["subperiods"][label] = {
            **cluster_summary(subset),
            "asset_events": int(sub_mask.sum().sum()),
        }
    for label, sign in [("positive_formation_residual", 1), ("negative_formation_residual", -1)]:
        signed_mask = valid_mask & np.sign(formation_residual).eq(sign)
        signed_events, _ = event_series(response, signed_mask)
        result["residual_directions"][label] = cluster_summary(signed_events)

    detail = {
        "valid_mask": valid_mask,
        "response": response,
        "formation_residual": formation_residual,
        "z_score": z_score,
        "beta": beta,
    }
    return result, detail


def per_asset(detail: dict[str, Any], matrices: dict[str, pd.DataFrame], phase: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    p_values: list[float] = []
    start = pd.Timestamp(PHASES[phase]["start"], tz="UTC")
    end = pd.Timestamp(PHASES[phase]["end"], tz="UTC")
    for symbol in ALTS:
        series = detail["response"][symbol].where(detail["valid_mask"][symbol]).dropna()
        stats = cluster_summary(series)
        p_values.append(
            1.0 if stats["p_value_two_sided"] is None else stats["p_value_two_sided"]
        )
        quote = matrices["quote_volume"].loc[
            (matrices["quote_volume"].index >= start)
            & (matrices["quote_volume"].index < end),
            symbol,
        ]
        rows.append(
            {
                "symbol": symbol,
                **stats,
                "median_hourly_quote_volume_usdt": float(quote.median()),
            }
        )
    rejected, q_values, _, _ = multipletests(p_values, alpha=0.05, method="fdr_by")
    for row, reject, q_value in zip(rows, rejected, q_values, strict=True):
        row["by_fdr_q_value"] = float(q_value)
        row["significant_by_fdr_0_05"] = bool(reject)
    return sorted(rows, key=lambda item: item["symbol"])


def gate(result: dict[str, Any]) -> dict[str, Any]:
    primary = result["primary"]
    baseline = result["same_event_raw_return_reversal_baseline"]
    halves = list(result["subperiods"].values())
    directions = list(result["residual_directions"].values())
    favorable = result["paired_round_trip_cost_floor_bps"]["favorable_mean"]
    checks = {
        "minimum_event_hours": result["event_hours"] >= 200,
        "minimum_asset_events": result["asset_events"] >= 500,
        "minimum_75_event_hours_each_half": all(item["n"] >= 75 for item in halves),
        "primary_mean_positive": primary["mean_bps"] is not None and primary["mean_bps"] > 0,
        "primary_ci_low_positive": primary["ci_low_bps"] is not None and primary["ci_low_bps"] > 0,
        "all_half_means_positive": all(
            item["mean_bps"] is not None and item["mean_bps"] > 0 for item in halves
        ),
        "beats_same_event_raw_reversal": (
            primary["mean_bps"] is not None
            and baseline["mean_bps"] is not None
            and primary["mean_bps"] > baseline["mean_bps"]
        ),
        "no_direction_significantly_negative": all(
            item["ci_high_bps"] is None or item["ci_high_bps"] >= 0
            for item in directions
        ),
        "reaches_average_favorable_paired_cost": (
            primary["mean_bps"] is not None
            and favorable is not None
            and primary["mean_bps"] >= favorable
        ),
    }
    return {"checks": checks, "pass": all(checks.values())}


def run(phase: str) -> None:
    verify_plan()
    if not prior_phase_allows(phase):
        raise RuntimeError(f"{phase} remains sealed by the prior phase result")
    source_identity = validate_source_files(phase)
    matrices, quality = load_hourly_matrices(phase)
    returns = np.log(matrices["close"]).diff()
    beta_cache = {
        days: rolling_beta(returns[ALTS], returns[ANCHOR], days)
        for days in [7, 30, 90]
    }
    results: list[dict[str, Any]] = []
    primary_detail: dict[str, Any] | None = None
    for config in CONFIGS:
        item, detail = analyze_config(config, matrices, phase, returns, beta_cache)
        results.append(item)
        if config.name == "primary":
            primary_detail = detail
    assert primary_detail is not None
    phase_gate = gate(results[0])
    release_next = bool(phase_gate["pass"] and phase != "confirmation")
    if not phase_gate["pass"]:
        conclusion = "DOES_NOT_SUPPORT"
    elif phase == "confirmation":
        conclusion = "SUPPORTS_WITHIN_SCOPE"
    else:
        conclusion = "INSUFFICIENT_EVIDENCE"
    output = {
        "phase": phase,
        "generated_at_utc": pd.Timestamp.now(tz="UTC").isoformat(),
        "study_code_sha256": code_sha256(),
        "parent_code_sha256": EXPECTED_PARENT_CODE_SHA,
        "environment": {
            "python": sys.version.split()[0],
            "pandas": pd.__version__,
            "numpy": np.__version__,
            "statsmodels": sm.__version__,
            "vectorbt": vbt.__version__,
        },
        "source_identity": source_identity,
        "data_quality": quality,
        "search_disclosure": checkpoint()["search_disclosure"],
        "configs": results,
        "per_asset_primary_exploratory": per_asset(primary_detail, matrices, phase),
        "gate": phase_gate,
        "release_next_phase": release_next,
        "conclusion": conclusion,
        "limitations": (
            "Predictive Kline result only; no spread/depth, funding, two-leg fill synchronization, "
            "mark price, margin, liquidation, capacity, tax, or causal participant identity."
        ),
    }
    path = STUDY_DIR / f"{phase}.json"
    path.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    latest = DATA_ROOT / f"btc-neutral-alt-residual-reversal-{phase}-latest.json"
    latest.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "phase": phase,
                "output": str(path),
                "conclusion": conclusion,
                "release_next_phase": release_next,
                "primary": results[0]["primary"],
                "cost_floor": results[0]["paired_round_trip_cost_floor_bps"],
                "gate": phase_gate,
            },
            indent=2,
        )
    )


def self_test() -> None:
    index = pd.date_range("2024-01-01", periods=48, freq="5min", tz="UTC")
    values = np.arange(48, dtype=float) + 100.0
    frame = pd.DataFrame(
        {
            "open": values,
            "close": values + 0.5,
            "quote_volume": np.ones(48),
            "trade_count": np.ones(48),
        },
        index=index,
    )
    hourly = aggregate_hourly(frame)
    if len(hourly) != 4 or hourly.iloc[0]["open"] != 100 or hourly.iloc[0]["close"] != 111.5:
        raise AssertionError("hourly aggregation failed")
    condition = pd.DataFrame(False, index=pd.date_range("2024-01-01", periods=40, freq="1h", tz="UTC"), columns=["A"])
    condition.iloc[[1, 5, 14, 26, 27], 0] = True
    selected = cooldown_mask(condition, 12)
    if list(np.flatnonzero(selected["A"].to_numpy())) != [1, 14, 27]:
        raise AssertionError("per-asset cooldown failed")
    rng = np.random.default_rng(20260721)
    sample_index = pd.date_range("2024-01-01", periods=1000, freq="1h", tz="UTC")
    stats = cluster_summary(pd.Series(rng.normal(0.001, 0.01, 1000), index=sample_index))
    if stats["n"] != 1000 or stats["cluster_weeks"] < 5:
        raise AssertionError("weekly cluster summary failed")
    print(json.dumps({"status": "PASS", "tests": ["hourly aggregation", "per-asset cooldown", "weekly cluster summary"]}, indent=2))


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    commands.add_parser("verify-plan")
    commands.add_parser("self-test")
    prepare_parser = commands.add_parser("prepare")
    prepare_parser.add_argument("--phase", choices=PHASES, required=True)
    prepare_parser.add_argument("--workers", type=int, default=4)
    run_parser = commands.add_parser("run")
    run_parser.add_argument("--phase", choices=PHASES, required=True)
    return result


def main() -> None:
    args = parser().parse_args()
    if args.command == "verify-plan":
        verify_plan()
    elif args.command == "self-test":
        self_test()
    elif args.command == "prepare":
        prepare(args.phase, args.workers)
    elif args.command == "run":
        run(args.phase)


if __name__ == "__main__":
    main()
