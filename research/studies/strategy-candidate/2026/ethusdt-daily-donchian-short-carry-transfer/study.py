"""Sequential ETHUSDT transfer of the fixed short-side carry-conditioned Donchian rule."""

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
CARRY_STUDY_PATH = STUDY_DIR.parent / "btcusdt-daily-donchian-carry-conditioned" / "study.py"
DONCHIAN_RETURNS_PATH = STUDY_DIR.parent / "btcusdt-daily-donchian-ensemble" / "development_daily_returns.csv"
CARRY_RETURNS_PATH = STUDY_DIR.parent / "btcusdt-daily-donchian-carry-conditioned" / "development_daily_returns.csv"
SPOT_RETURNS_PATH = STUDY_DIR.parent / "btcusdt-spot-daily-donchian" / "development_daily_returns.csv"
PERIODS = {
    "development": ("2021-01-01T00:00:00Z", "2024-01-01T00:00:00Z"),
    "evaluation": ("2024-01-01T00:00:00Z", "2026-01-01T00:00:00Z"),
    "confirmation": ("2026-01-01T00:00:00Z", "2026-07-01T00:00:00Z"),
}
RELATED_TRIAL_COUNT = 11


def _load_carry() -> ModuleType:
    spec = importlib.util.spec_from_file_location("halpha_eth_carry_base", CARRY_STUDY_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("CARRY_STUDY_IMPORT_UNAVAILABLE")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


CARRY = _load_carry()
BASE = CARRY.BASE


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _utc_ms(value: str) -> int:
    return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1000)


def _weights(data: Any) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    pure_long_short, pure_long = CARRY._pure_weights(data)
    candidate = CARRY.CarryCandidate("ETH_SHORT_CARRY_ONLY", False, True)
    daily_funding_value = data.funding_boundary_value + data.funding_intraday_value
    desired = CARRY._carry_condition(pure_long_short, daily_funding_value, candidate)
    continuous = BASE._continuous_long_weight(data.close)
    return desired, pure_long_short, pure_long, continuous


def _development_dsr(
    eth_returns: np.ndarray, dates: pd.DatetimeIndex
) -> tuple[float, dict[str, str]]:
    frames = [
        pd.read_csv(DONCHIAN_RETURNS_PATH, index_col="date", parse_dates=True),
        pd.read_csv(CARRY_RETURNS_PATH, index_col="date", parse_dates=True),
        pd.read_csv(SPOT_RETURNS_PATH, index_col="date", parse_dates=True),
        pd.DataFrame({"ETH_SHORT_CARRY_ONLY": eth_returns}, index=dates),
    ]
    matrix = pd.concat(frames, axis=1, join="inner")
    if len(matrix) != len(dates) or matrix.shape[1] != RELATED_TRIAL_COUNT:
        raise ValueError(f"RELATED_TRIAL_MATRIX_INVALID:{matrix.shape}")
    dsr = matrix.vbt.returns.deflated_sharpe_ratio(nb_trials=RELATED_TRIAL_COUNT)
    return float(dsr["ETH_SHORT_CARRY_ONLY"]), {
        "donchian_returns_sha256": _sha256(DONCHIAN_RETURNS_PATH),
        "carry_returns_sha256": _sha256(CARRY_RETURNS_PATH),
        "spot_returns_sha256": _sha256(SPOT_RETURNS_PATH),
    }


def _authorization(phase: str, path: str | None) -> None:
    if phase == "development":
        return
    if path is None:
        raise ValueError("AUTHORIZATION_REQUIRED")
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    key = "evaluation_authorized" if phase == "evaluation" else "confirmation_authorized"
    if not payload.get(key):
        raise ValueError(f"{phase.upper()}_NOT_AUTHORIZED")


def analyze(args: argparse.Namespace) -> None:
    _authorization(args.phase, args.authorization)
    start_ms, end_ms = map(_utc_ms, PERIODS[args.phase])
    data = BASE._load_market_data(
        Path(args.cache_root).resolve(), Path(args.manifest).resolve()
    )
    desired, pure_long_short, pure_long, continuous = _weights(data)
    candidate, base_returns, dates = CARRY._simulate_scenarios(
        data, desired, start_ms, end_ms
    )
    benchmarks: dict[str, Any] = {}
    for name, weight in {
        "pure_long_short": pure_long_short,
        "pure_long_only": pure_long,
        "continuous_vol_target_long": continuous,
    }.items():
        scenarios, _, _ = CARRY._simulate_scenarios(data, weight, start_ms, end_ms)
        benchmarks[name] = scenarios
    dsr = None
    trial_inputs = None
    if args.phase == "development":
        dsr, trial_inputs = _development_dsr(base_returns, dates)
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
            "carry_study_sha256": _sha256(CARRY_STUDY_PATH),
            "data_identity": data.manifest_identity,
            "related_trial_inputs": trial_inputs,
        },
        "data_quality": data.quality,
        "rules": {
            "instrument": "ETHUSDT USD-M perpetual",
            "lookbacks_days": list(CARRY.LOOKBACKS),
            "condition_long": False,
            "condition_short": True,
            "carry_signal": "prior completed UTC day actual funding net cashflow sign",
            "target_volatility": BASE.TARGET_VOL,
            "max_absolute_weight": BASE.MAX_WEIGHT,
            "rebalance_threshold": BASE.REBALANCE_THRESHOLD,
        },
        "costs_per_unit_turnover": BASE.SCENARIOS,
        "candidate": {
            "candidate_id": "ETH_SHORT_CARRY_ONLY",
            "scenarios": candidate,
            "deflated_sharpe_probability": dsr,
            "related_trial_count": RELATED_TRIAL_COUNT,
        },
        "benchmarks": benchmarks,
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
            "candidate_id": "ETH_SHORT_CARRY_ONLY",
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
    pd.DataFrame({"ETH_SHORT_CARRY_ONLY": base_returns}, index=dates).to_csv(
        output_dir / f"{args.phase}_daily_returns.csv", index_label="date"
    )
    print(json.dumps({"phase": args.phase, "candidate": "ETH_SHORT_CARRY_ONLY"}))


def _best_benchmarks(payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    return (
        payload["benchmarks"]["pure_long_short"]["base"],
        payload["benchmarks"]["pure_long_only"]["base"],
    )


def select_development(args: argparse.Namespace) -> None:
    source = Path(args.input)
    payload = json.loads(source.read_text(encoding="utf-8"))
    if payload.get("phase") != "development":
        raise ValueError("NOT_DEVELOPMENT_RESULT")
    candidate = payload["candidate"]
    base = candidate["scenarios"]["base"]
    stress = candidate["scenarios"]["stress"]
    pure_long_short, pure_long = _best_benchmarks(payload)
    annual = base["annual_returns"]
    checks = {
        "base_total_positive": base["total_return"] > 0,
        "stress_total_positive": stress["total_return"] > 0,
        "stress_cagr_above_4pct": stress["cagr"] > 0.04,
        "base_sharpe_at_least_0p60": base["sharpe"] >= 0.60,
        "eleven_trial_dsr_at_least_0p80": candidate[
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
        "sharpe_exceeds_both_pure_trends": base["sharpe"]
        > max(pure_long_short["sharpe"], pure_long["sharpe"]),
        "calmar_exceeds_both_pure_trends": base["calmar"]
        > max(pure_long_short["calmar"], pure_long["calmar"]),
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
    pure_long_short, pure_long = _best_benchmarks(payload)
    checks = {
        "base_total_positive": base["total_return"] > 0,
        "stress_total_positive": stress["total_return"] > 0,
        "stress_cagr_above_4pct": stress["cagr"] > 0.04,
        "2024_positive": base["annual_returns"].get("2024", -1.0) > 0,
        "2025_positive": base["annual_returns"].get("2025", -1.0) > 0,
        "base_sharpe_at_least_0p60": base["sharpe"] >= 0.60,
        "drawdown_above_minus_15pct": base["max_drawdown"] > -0.15,
        "active_days_at_least_120": base["active_days"] >= 120,
        "sharpe_exceeds_both_pure_trends": base["sharpe"]
        > max(pure_long_short["sharpe"], pure_long["sharpe"]),
        "calmar_exceeds_both_pure_trends": base["calmar"]
        > max(pure_long_short["calmar"], pure_long["calmar"]),
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
    for scenario in ("base", "stress"):
        evaluation_metrics = evaluation["candidate"]["scenarios"][scenario]
        confirmation_metrics = confirmation["candidate"]["scenarios"][scenario]
        total_return = (
            (1.0 + evaluation_metrics["total_return"])
            * (1.0 + confirmation_metrics["total_return"])
            - 1.0
        )
        years = (evaluation_metrics["days"] + confirmation_metrics["days"]) / 365.25
        combined[scenario] = {
            "total_return": total_return,
            "cagr": (1.0 + total_return) ** (1.0 / years) - 1.0,
        }
    checks = {
        "base_non_negative": base["total_return"] >= 0,
        "stress_non_negative": stress["total_return"] >= 0,
        "drawdown_above_minus_10pct": base["max_drawdown"] > -0.10,
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
