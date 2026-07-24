"""Sequential Binance Spot adaptation of the fixed daily Donchian candidate."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import io
import json
import sys
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
import pandas as pd
import vectorbt as vbt


STUDY_DIR = Path(__file__).resolve().parent
BASE_STUDY_PATH = STUDY_DIR.parent / "btcusdt-daily-donchian-ensemble" / "study.py"
DONCHIAN_RETURNS_PATH = (
    STUDY_DIR.parent / "btcusdt-daily-donchian-ensemble" / "development_daily_returns.csv"
)
CARRY_RETURNS_PATH = (
    STUDY_DIR.parent
    / "btcusdt-daily-donchian-carry-conditioned"
    / "development_daily_returns.csv"
)
PERIODS = {
    "development": ("2021-01-01T00:00:00Z", "2024-01-01T00:00:00Z"),
    "evaluation": ("2024-01-01T00:00:00Z", "2026-01-01T00:00:00Z"),
    "confirmation": ("2026-01-01T00:00:00Z", "2026-07-01T00:00:00Z"),
}
LOOKBACKS = (20, 30, 60, 90)
SCENARIOS = {
    "favorable": {"fee": 0.0010, "slippage": 0.0002},
    "base": {"fee": 0.0010, "slippage": 0.0005},
    "stress": {"fee": 0.0010, "slippage": 0.0010},
}
RELATED_TRIAL_COUNT = 10


def _load_base() -> ModuleType:
    spec = importlib.util.spec_from_file_location("halpha_daily_donchian_spot_base", BASE_STUDY_PATH)
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


def _utc_ms(value: str) -> int:
    return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1000)


def _normalize_epoch(values: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(values, errors="raise").astype("int64")
    return numeric.where(numeric < 100_000_000_000_000, numeric // 1000)


def _load_spot_data(cache_root: Path, manifest_path: Path) -> Any:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    frames: list[pd.DataFrame] = []
    verified: list[dict[str, Any]] = []
    for item in manifest["archives"]:
        path = cache_root / item["cache_relative_path"]
        actual = _sha256(path)
        if actual != item["sha256"]:
            raise ValueError(f"ARCHIVE_SHA256_MISMATCH:{path.name}")
        with zipfile.ZipFile(path) as archive:
            csv_names = [name for name in archive.namelist() if name.endswith(".csv")]
            if len(csv_names) != 1:
                raise ValueError(f"ARCHIVE_CSV_COUNT:{path.name}")
            frame = pd.read_csv(
                io.BytesIO(archive.read(csv_names[0])),
                header=None,
                names=BASE.CSV_COLUMNS,
            )
        frame["open_time"] = _normalize_epoch(frame["open_time"])
        frame["close_time"] = _normalize_epoch(frame["close_time"])
        frames.append(frame)
        verified.append(
            {
                "cache_relative_path": item["cache_relative_path"],
                "sha256": actual,
                "bytes": path.stat().st_size,
            }
        )
    bars = pd.concat(frames, ignore_index=True).sort_values("open_time")
    duplicate_count = int(bars["open_time"].duplicated().sum())
    if duplicate_count:
        raise ValueError("DUPLICATE_BARS")
    numeric_columns = ("open", "high", "low", "close")
    for column in numeric_columns:
        bars[column] = pd.to_numeric(bars[column], errors="raise")
    open_time = bars["open_time"].to_numpy(dtype=np.int64)
    if len(open_time) < 2 or np.any(np.diff(open_time) != 86_400_000):
        raise ValueError("NON_CONTINUOUS_DAILY_BARS")
    open_price = bars["open"].to_numpy(dtype=np.float64)
    high = bars["high"].to_numpy(dtype=np.float64)
    low = bars["low"].to_numpy(dtype=np.float64)
    close = bars["close"].to_numpy(dtype=np.float64)
    valid = (
        np.isfinite(open_price)
        & np.isfinite(high)
        & np.isfinite(low)
        & np.isfinite(close)
        & (low > 0)
        & (low <= np.minimum(open_price, close))
        & (high >= np.maximum(open_price, close))
    )
    if not np.all(valid):
        raise ValueError("INVALID_OHLC")
    identity = hashlib.sha256(
        json.dumps(
            {
                "manifest_sha256": _sha256(manifest_path),
                "manifest_content_identity": manifest["content_identity"],
                "verified": verified,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return BASE.MarketData(
        open_time=open_time,
        open=open_price,
        high=high,
        low=low,
        close=close,
        funding_boundary_value=np.zeros(len(bars), dtype=np.float64),
        funding_intraday_value=np.zeros(len(bars), dtype=np.float64),
        manifest_identity=identity,
        quality={
            "bars": int(len(bars)),
            "first_open_time": datetime.fromtimestamp(open_time[0] / 1000, tz=UTC).isoformat(),
            "last_open_time": datetime.fromtimestamp(open_time[-1] / 1000, tz=UTC).isoformat(),
            "continuous_daily": True,
            "valid_ohlc": True,
            "duplicate_bars": duplicate_count,
            "archives_verified": len(verified),
            "archive_bytes": int(sum(item["bytes"] for item in verified)),
            "timestamp_units_normalized": ["milliseconds", "microseconds_to_milliseconds"],
        },
    )


def _weights(data: Any) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    candidate = BASE.Candidate("SPOT_LONG_BALANCED_4", "LONG_ONLY", LOOKBACKS)
    desired, _ = BASE._desired_weight(
        data.close,
        candidate,
        {},
        target_vol=BASE.TARGET_VOL,
        cap=BASE.MAX_WEIGHT,
    )
    continuous = BASE._continuous_long_weight(data.close)
    half_buy_hold = np.full(len(data.close), 0.5, dtype=np.float64)
    return desired, continuous, half_buy_hold


def _simulate_scenarios(
    data: Any, weight: np.ndarray, start_ms: int, end_ms: int
) -> tuple[dict[str, Any], np.ndarray, pd.DatetimeIndex]:
    scenarios: dict[str, Any] = {}
    base_returns: np.ndarray | None = None
    dates: pd.DatetimeIndex | None = None
    for name, costs in SCENARIOS.items():
        simulation = BASE._simulate(
            data,
            weight,
            start_ms=start_ms,
            end_ms=end_ms,
            fee_rate=costs["fee"],
            slippage_rate=costs["slippage"],
        )
        scenarios[name] = simulation.metrics
        if name == "base":
            base_returns = simulation.returns
            dates = simulation.dates
    if base_returns is None or dates is None:
        raise RuntimeError("BASE_SCENARIO_MISSING")
    return scenarios, base_returns, dates


def _development_dsr(
    spot_returns: np.ndarray, dates: pd.DatetimeIndex
) -> tuple[float, dict[str, str]]:
    donchian = pd.read_csv(DONCHIAN_RETURNS_PATH, index_col="date", parse_dates=True)
    carry = pd.read_csv(CARRY_RETURNS_PATH, index_col="date", parse_dates=True)
    spot = pd.DataFrame({"SPOT_LONG_BALANCED_4": spot_returns}, index=dates)
    frame = pd.concat([donchian, carry, spot], axis=1, join="inner")
    if len(frame) != len(spot) or frame.shape[1] != RELATED_TRIAL_COUNT:
        raise ValueError(
            f"RELATED_TRIAL_MATRIX_INVALID:{frame.shape[0]}x{frame.shape[1]}"
        )
    dsr = frame.vbt.returns.deflated_sharpe_ratio(nb_trials=RELATED_TRIAL_COUNT)
    return float(dsr["SPOT_LONG_BALANCED_4"]), {
        "donchian_returns_sha256": _sha256(DONCHIAN_RETURNS_PATH),
        "carry_returns_sha256": _sha256(CARRY_RETURNS_PATH),
    }


def _authorization(phase: str, path: str | None) -> None:
    if phase == "development":
        return
    if path is None:
        raise ValueError("AUTHORIZATION_REQUIRED")
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    required = "evaluation_authorized" if phase == "evaluation" else "confirmation_authorized"
    if not payload.get(required):
        raise ValueError(f"{phase.upper()}_NOT_AUTHORIZED")


def analyze(args: argparse.Namespace) -> None:
    _authorization(args.phase, args.authorization)
    start_ms, end_ms = map(_utc_ms, PERIODS[args.phase])
    data = _load_spot_data(
        Path(args.cache_root).resolve(), Path(args.manifest).resolve()
    )
    desired, continuous, half_buy_hold = _weights(data)
    candidate, base_returns, dates = _simulate_scenarios(
        data, desired, start_ms, end_ms
    )
    continuous_result, _, _ = _simulate_scenarios(
        data, continuous, start_ms, end_ms
    )
    buy_hold_result, _, _ = _simulate_scenarios(
        data, half_buy_hold, start_ms, end_ms
    )
    dsr = None
    trial_identity = None
    if args.phase == "development":
        dsr, trial_identity = _development_dsr(base_returns, dates)
    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "phase": args.phase,
        "period": list(PERIODS[args.phase]),
        "framework_versions": {
            "vectorbt": vbt.__version__,
            "pandas": pd.__version__,
            "numpy": np.__version__,
        },
        "method_identity": {
            "study_sha256": _sha256(Path(__file__).resolve()),
            "base_study_sha256": _sha256(BASE_STUDY_PATH),
            "data_identity": data.manifest_identity,
            "related_trial_inputs": trial_identity,
        },
        "data_quality": data.quality,
        "rules": {
            "market": "BINANCE_SPOT",
            "instrument": "BTCUSDT",
            "direction": "LONG_ONLY",
            "lookbacks_days": list(LOOKBACKS),
            "target_volatility": BASE.TARGET_VOL,
            "max_weight": BASE.MAX_WEIGHT,
            "volatility_window_days": BASE.VOL_WINDOW,
            "rebalance_threshold": BASE.REBALANCE_THRESHOLD,
            "action_time": "next UTC day open",
        },
        "costs_per_unit_turnover": SCENARIOS,
        "candidate": {
            "candidate_id": "SPOT_LONG_BALANCED_4",
            "scenarios": candidate,
            "deflated_sharpe_probability": dsr,
            "related_trial_count": RELATED_TRIAL_COUNT,
        },
        "benchmarks": {
            "continuous_vol_target_long": continuous_result,
            "half_buy_hold": buy_hold_result,
        },
        "product_effects": "NONE",
    }
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / f"{args.phase}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    rows: list[dict[str, Any]] = []
    for scenario, metrics in candidate.items():
        row: dict[str, Any] = {
            "candidate_id": "SPOT_LONG_BALANCED_4",
            "scenario": scenario,
            "deflated_sharpe_probability": dsr,
        }
        for key, value in metrics.items():
            if key == "annual_returns":
                for year, annual_return in value.items():
                    row[f"return_{year}"] = annual_return
            elif not isinstance(value, (dict, list)):
                row[key] = value
        rows.append(row)
    pd.DataFrame(rows).to_csv(output_dir / f"{args.phase}.csv", index=False)
    pd.DataFrame(
        {"SPOT_LONG_BALANCED_4": base_returns}, index=dates
    ).to_csv(output_dir / f"{args.phase}_daily_returns.csv", index_label="date")
    print(json.dumps({"phase": args.phase, "candidate": "SPOT_LONG_BALANCED_4"}))


def select_development(args: argparse.Namespace) -> None:
    source = Path(args.input)
    payload = json.loads(source.read_text(encoding="utf-8"))
    if payload.get("phase") != "development":
        raise ValueError("NOT_DEVELOPMENT_RESULT")
    candidate = payload["candidate"]
    base = candidate["scenarios"]["base"]
    stress = candidate["scenarios"]["stress"]
    continuous = payload["benchmarks"]["continuous_vol_target_long"]["base"]
    buy_hold = payload["benchmarks"]["half_buy_hold"]["base"]
    annual = base["annual_returns"]
    checks = {
        "base_total_positive": base["total_return"] > 0,
        "stress_total_positive": stress["total_return"] > 0,
        "stress_cagr_above_4pct": stress["cagr"] > 0.04,
        "base_sharpe_at_least_0p60": base["sharpe"] >= 0.60,
        "ten_trial_dsr_at_least_0p80": candidate[
            "deflated_sharpe_probability"
        ]
        >= 0.80,
        "drawdown_above_minus_15pct": base["max_drawdown"] > -0.15,
        "two_of_three_years_positive": sum(
            annual.get(year, -1.0) > 0 for year in ("2021", "2022", "2023")
        )
        >= 2,
        "worst_year_at_least_minus_5pct": min(annual.values()) >= -0.05,
        "active_days_at_least_180": base["active_days"] >= 180,
        "calmar_exceeds_continuous_long": base["calmar"] > continuous["calmar"],
        "drawdown_25pct_shallower_than_half_buy_hold": abs(base["max_drawdown"])
        <= 0.75 * abs(buy_hold["max_drawdown"]),
    }
    passed = all(checks.values())
    result = {
        "schema_version": 1,
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "phase": "development_selection",
        "source_sha256": _sha256(source),
        "candidate_id": candidate["candidate_id"],
        "checks": checks,
        "failed_checks": [name for name, value in checks.items() if not value],
        "evaluation_authorized": passed,
    }
    Path(args.output).write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False))


def qualify_evaluation(args: argparse.Namespace) -> None:
    source = Path(args.input)
    payload = json.loads(source.read_text(encoding="utf-8"))
    selection = json.loads(Path(args.selection).read_text(encoding="utf-8"))
    if payload.get("phase") != "evaluation" or not selection.get(
        "evaluation_authorized"
    ):
        raise ValueError("EVALUATION_INPUT_INVALID")
    base = payload["candidate"]["scenarios"]["base"]
    stress = payload["candidate"]["scenarios"]["stress"]
    continuous = payload["benchmarks"]["continuous_vol_target_long"]["base"]
    checks = {
        "base_total_positive": base["total_return"] > 0,
        "stress_total_positive": stress["total_return"] > 0,
        "stress_cagr_above_4pct": stress["cagr"] > 0.04,
        "2024_positive": base["annual_returns"].get("2024", -1.0) > 0,
        "2025_positive": base["annual_returns"].get("2025", -1.0) > 0,
        "base_sharpe_at_least_0p60": base["sharpe"] >= 0.60,
        "drawdown_above_minus_12pct": base["max_drawdown"] > -0.12,
        "active_days_at_least_120": base["active_days"] >= 120,
        "calmar_exceeds_continuous_long": base["calmar"] > continuous["calmar"],
    }
    passed = all(checks.values())
    result = {
        "schema_version": 1,
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "phase": "evaluation_gate",
        "source_sha256": _sha256(source),
        "candidate_id": payload["candidate"]["candidate_id"],
        "checks": checks,
        "failed_checks": [name for name, value in checks.items() if not value],
        "confirmation_authorized": passed,
    }
    Path(args.output).write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False))


def qualify_confirmation(args: argparse.Namespace) -> None:
    source = Path(args.input)
    confirmation = json.loads(source.read_text(encoding="utf-8"))
    evaluation = json.loads(Path(args.evaluation).read_text(encoding="utf-8"))
    gate = json.loads(Path(args.authorization).read_text(encoding="utf-8"))
    if confirmation.get("phase") != "confirmation" or not gate.get(
        "confirmation_authorized"
    ):
        raise ValueError("CONFIRMATION_INPUT_INVALID")
    base = confirmation["candidate"]["scenarios"]["base"]
    stress = confirmation["candidate"]["scenarios"]["stress"]
    combined: dict[str, dict[str, float]] = {}
    total_days = 0
    for scenario in ("base", "stress"):
        evaluation_metrics = evaluation["candidate"]["scenarios"][scenario]
        confirmation_metrics = confirmation["candidate"]["scenarios"][scenario]
        total_return = (
            (1.0 + evaluation_metrics["total_return"])
            * (1.0 + confirmation_metrics["total_return"])
            - 1.0
        )
        total_days = evaluation_metrics["days"] + confirmation_metrics["days"]
        years = total_days / 365.25
        cagr = (1.0 + total_return) ** (1.0 / years) - 1.0
        combined[scenario] = {"total_return": total_return, "cagr": cagr}
    checks = {
        "base_non_negative": base["total_return"] >= 0,
        "stress_non_negative": stress["total_return"] >= 0,
        "drawdown_above_minus_8pct": base["max_drawdown"] > -0.08,
        "active_days_at_least_15": base["active_days"] >= 15,
        "combined_base_cagr_above_4pct": combined["base"]["cagr"] > 0.04,
        "combined_stress_cagr_above_4pct": combined["stress"]["cagr"] > 0.04,
    }
    passed = all(checks.values())
    result = {
        "schema_version": 1,
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "phase": "confirmation_gate",
        "source_sha256": _sha256(source),
        "candidate_id": confirmation["candidate"]["candidate_id"],
        "checks": checks,
        "failed_checks": [name for name, value in checks.items() if not value],
        "combined_evaluation_confirmation": combined,
        "passed": passed,
        "conclusion": "SUPPORTS_WITHIN_SCOPE" if passed else "DOES_NOT_SUPPORT",
    }
    Path(args.output).write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(required=True)

    analyze_parser = subparsers.add_parser("analyze")
    analyze_parser.add_argument("--phase", choices=tuple(PERIODS), required=True)
    analyze_parser.add_argument("--cache-root", required=True)
    analyze_parser.add_argument("--manifest", required=True)
    analyze_parser.add_argument("--output-dir", required=True)
    analyze_parser.add_argument("--authorization")
    analyze_parser.set_defaults(func=analyze)

    select_parser = subparsers.add_parser("select-development")
    select_parser.add_argument("--input", required=True)
    select_parser.add_argument("--output", required=True)
    select_parser.set_defaults(func=select_development)

    evaluation_parser = subparsers.add_parser("qualify-evaluation")
    evaluation_parser.add_argument("--input", required=True)
    evaluation_parser.add_argument("--selection", required=True)
    evaluation_parser.add_argument("--output", required=True)
    evaluation_parser.set_defaults(func=qualify_evaluation)

    confirmation_parser = subparsers.add_parser("qualify-confirmation")
    confirmation_parser.add_argument("--input", required=True)
    confirmation_parser.add_argument("--evaluation", required=True)
    confirmation_parser.add_argument("--authorization", required=True)
    confirmation_parser.add_argument("--output", required=True)
    confirmation_parser.set_defaults(func=qualify_confirmation)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
