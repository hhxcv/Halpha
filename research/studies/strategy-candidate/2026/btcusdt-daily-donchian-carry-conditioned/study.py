"""Sequential carry-conditioned daily Donchian study.

This study reuses the audited market-data loader and simulation proxy from the
preceding daily Donchian question. It does not import product code, read product
state, or call exchange-changing endpoints.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
import pandas as pd
import vectorbt as vbt


STUDY_DIR = Path(__file__).resolve().parent
BASE_STUDY_PATH = STUDY_DIR.parent / "btcusdt-daily-donchian-ensemble" / "study.py"
PERIODS = {
    "development": ("2021-01-01T00:00:00Z", "2024-01-01T00:00:00Z"),
    "evaluation": ("2024-01-01T00:00:00Z", "2026-01-01T00:00:00Z"),
    "confirmation": ("2026-01-01T00:00:00Z", "2026-07-01T00:00:00Z"),
}
LOOKBACKS = (20, 30, 60, 90)


@dataclass(frozen=True)
class CarryCandidate:
    candidate_id: str
    condition_long: bool
    condition_short: bool


CANDIDATES = (
    CarryCandidate("CARRY_BOTH_SIDES", True, True),
    CarryCandidate("CARRY_LONG_SIDE_ONLY", True, False),
    CarryCandidate("CARRY_SHORT_SIDE_ONLY", False, True),
)


def _load_base() -> ModuleType:
    spec = importlib.util.spec_from_file_location("halpha_daily_donchian_base", BASE_STUDY_PATH)
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


def _json_digest(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _utc_ms(value: str) -> int:
    return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1000)


def _pure_weights(data: Any) -> tuple[np.ndarray, np.ndarray]:
    component_cache: dict[tuple[int, str], np.ndarray] = {}
    long_short = BASE.Candidate("PURE_LONG_SHORT", "LONG_SHORT", LOOKBACKS)
    long_only = BASE.Candidate("PURE_LONG_ONLY", "LONG_ONLY", LOOKBACKS)
    long_short_weight, _ = BASE._desired_weight(
        data.close,
        long_short,
        component_cache,
        target_vol=BASE.TARGET_VOL,
        cap=BASE.MAX_WEIGHT,
    )
    long_only_weight, _ = BASE._desired_weight(
        data.close,
        long_only,
        component_cache,
        target_vol=BASE.TARGET_VOL,
        cap=BASE.MAX_WEIGHT,
    )
    return long_short_weight, long_only_weight


def _carry_condition(
    pure_weight: np.ndarray, daily_funding_value: np.ndarray, candidate: CarryCandidate
) -> np.ndarray:
    result = pure_weight.copy()
    if candidate.condition_long:
        result[(result > 0) & (daily_funding_value > 0)] = 0.0
    if candidate.condition_short:
        result[(result < 0) & (daily_funding_value < 0)] = 0.0
    return result


def _simulate_scenarios(
    data: Any, desired_weight: np.ndarray, start_ms: int, end_ms: int
) -> tuple[dict[str, Any], np.ndarray, pd.DatetimeIndex]:
    scenarios: dict[str, Any] = {}
    base_returns: np.ndarray | None = None
    dates: pd.DatetimeIndex | None = None
    for scenario, costs in BASE.SCENARIOS.items():
        simulation = BASE._simulate(
            data,
            desired_weight,
            start_ms=start_ms,
            end_ms=end_ms,
            fee_rate=costs["fee"],
            slippage_rate=costs["slippage"],
        )
        scenarios[scenario] = simulation.metrics
        if scenario == "base":
            base_returns = simulation.returns
            dates = simulation.dates
    if base_returns is None or dates is None:
        raise RuntimeError("BASE_SCENARIO_MISSING")
    return scenarios, base_returns, dates


def _authorized_candidates(phase: str, authorization_path: str | None) -> tuple[CarryCandidate, ...]:
    if phase == "development":
        return CANDIDATES
    if authorization_path is None:
        raise ValueError("AUTHORIZATION_REQUIRED")
    authorization = json.loads(Path(authorization_path).read_text(encoding="utf-8"))
    if phase == "evaluation":
        if not authorization.get("evaluation_authorized"):
            raise ValueError("EVALUATION_NOT_AUTHORIZED")
        candidate_id = authorization["selected_candidate"]["candidate_id"]
    else:
        if not authorization.get("confirmation_authorized"):
            raise ValueError("CONFIRMATION_NOT_AUTHORIZED")
        candidate_id = authorization["confirmation_candidate"]["candidate_id"]
    by_id = {candidate.candidate_id: candidate for candidate in CANDIDATES}
    if candidate_id not in by_id:
        raise ValueError("AUTHORIZED_CANDIDATE_INVALID")
    return (by_id[candidate_id],)


def _carry_diagnostics(
    data: Any, start_ms: int, end_ms: int, daily_funding_value: np.ndarray
) -> dict[str, Any]:
    start = int(np.searchsorted(data.open_time, start_ms, side="left"))
    end = int(np.searchsorted(data.open_time, end_ms, side="left"))
    values = daily_funding_value[start:end]
    signs = np.sign(values)
    comparable = (signs[:-1] != 0) & (signs[1:] != 0)
    persistence = (
        float(np.mean(signs[:-1][comparable] == signs[1:][comparable]))
        if np.any(comparable)
        else None
    )
    return {
        "days": int(len(values)),
        "positive_day_fraction": float(np.mean(values > 0)),
        "negative_day_fraction": float(np.mean(values < 0)),
        "zero_day_fraction": float(np.mean(values == 0)),
        "next_day_sign_persistence_nonzero": persistence,
        "nonzero_sign_comparisons": int(np.count_nonzero(comparable)),
    }


def analyze(args: argparse.Namespace) -> None:
    phase = args.phase
    candidates = _authorized_candidates(phase, args.authorization)
    start_ms, end_ms = map(_utc_ms, PERIODS[phase])
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    data = BASE._load_market_data(
        Path(args.cache_root).resolve(), Path(args.manifest).resolve()
    )
    pure_long_short, pure_long = _pure_weights(data)
    continuous_long = BASE._continuous_long_weight(data.close)
    daily_funding_value = data.funding_boundary_value + data.funding_intraday_value

    benchmark_weights = {
        "pure_long_short": pure_long_short,
        "pure_long_only": pure_long,
        "continuous_vol_target_long": continuous_long,
    }
    benchmarks: dict[str, dict[str, Any]] = {}
    for name, weight in benchmark_weights.items():
        scenarios, _, _ = _simulate_scenarios(data, weight, start_ms, end_ms)
        benchmarks[name] = scenarios

    results: list[dict[str, Any]] = []
    return_columns: dict[str, np.ndarray] = {}
    return_index: pd.DatetimeIndex | None = None
    for candidate in candidates:
        desired = _carry_condition(pure_long_short, daily_funding_value, candidate)
        scenarios, base_returns, dates = _simulate_scenarios(
            data, desired, start_ms, end_ms
        )
        return_columns[candidate.candidate_id] = base_returns
        return_index = dates
        results.append(
            {
                "candidate_id": candidate.candidate_id,
                "condition_long": candidate.condition_long,
                "condition_short": candidate.condition_short,
                "scenarios": scenarios,
            }
        )
    if return_index is None:
        raise RuntimeError("NO_CANDIDATE_RETURNS")
    returns = pd.DataFrame(return_columns, index=return_index)
    dsr = returns.vbt.returns.deflated_sharpe_ratio(nb_trials=len(CANDIDATES))
    for candidate in results:
        candidate["deflated_sharpe_probability"] = float(
            dsr[candidate["candidate_id"]]
        )

    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "phase": phase,
        "period": list(PERIODS[phase]),
        "framework_versions": {
            "vectorbt": vbt.__version__,
            "pandas": pd.__version__,
            "numpy": np.__version__,
        },
        "method_identity": {
            "study_sha256": _sha256(Path(__file__).resolve()),
            "base_study_sha256": _sha256(BASE_STUDY_PATH),
            "data_identity": data.manifest_identity,
        },
        "data_quality": data.quality,
        "carry_definition": "sign of prior completed UTC day's realized funding cashflow per unit; positive means long pays",
        "carry_diagnostics": _carry_diagnostics(
            data, start_ms, end_ms, daily_funding_value
        ),
        "lookbacks_days": list(LOOKBACKS),
        "costs_per_unit_turnover": BASE.SCENARIOS,
        "target_volatility": BASE.TARGET_VOL,
        "max_absolute_weight": BASE.MAX_WEIGHT,
        "rebalance_threshold": BASE.REBALANCE_THRESHOLD,
        "benchmarks": benchmarks,
        "candidates": results,
        "candidate_distribution_digest": _json_digest(results),
        "product_effects": "NONE",
    }
    output_json = output_dir / f"{phase}.json"
    output_json.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    rows: list[dict[str, Any]] = []
    for candidate in results:
        for scenario, metrics in candidate["scenarios"].items():
            row = {
                "candidate_id": candidate["candidate_id"],
                "scenario": scenario,
                "deflated_sharpe_probability": candidate[
                    "deflated_sharpe_probability"
                ],
            }
            for key, value in metrics.items():
                if key == "annual_returns":
                    for year, annual_return in value.items():
                        row[f"return_{year}"] = annual_return
                elif not isinstance(value, (dict, list)):
                    row[key] = value
            rows.append(row)
    pd.DataFrame(rows).to_csv(output_dir / f"{phase}.csv", index=False)
    returns.to_csv(output_dir / f"{phase}_daily_returns.csv", index_label="date")
    print(json.dumps({"phase": phase, "candidates": len(results)}, ensure_ascii=False))


def _best_trend_benchmarks(payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    pure_long_short = payload["benchmarks"]["pure_long_short"]["base"]
    pure_long = payload["benchmarks"]["pure_long_only"]["base"]
    return pure_long_short, pure_long


def _development_checks(
    candidate: dict[str, Any], payload: dict[str, Any]
) -> dict[str, bool]:
    base = candidate["scenarios"]["base"]
    stress = candidate["scenarios"]["stress"]
    pure_long_short, pure_long = _best_trend_benchmarks(payload)
    best_sharpe = max(pure_long_short["sharpe"], pure_long["sharpe"])
    best_calmar = max(pure_long_short["calmar"], pure_long["calmar"])
    return {
        "base_total_positive": base["total_return"] > 0,
        "stress_total_positive": stress["total_return"] > 0,
        "base_sharpe_at_least_0p50": base["sharpe"] is not None
        and base["sharpe"] >= 0.50,
        "drawdown_above_minus_15pct": base["max_drawdown"] > -0.15,
        "two_of_three_years_positive": sum(
            base["annual_returns"].get(year, -1.0) > 0
            for year in ("2021", "2022", "2023")
        )
        >= 2,
        "active_days_at_least_180": base["active_days"] >= 180,
        "sharpe_exceeds_both_pure_trends": base["sharpe"] is not None
        and base["sharpe"] > best_sharpe,
        "calmar_exceeds_both_pure_trends": base["calmar"] is not None
        and base["calmar"] > best_calmar,
        "funding_pnl_improves_pure_long_short": base[
            "funding_pnl_on_initial_equity"
        ]
        > pure_long_short["funding_pnl_on_initial_equity"],
        "dsr_at_least_0p80": candidate["deflated_sharpe_probability"] >= 0.80,
    }


def select_development(args: argparse.Namespace) -> None:
    source = Path(args.input)
    payload = json.loads(source.read_text(encoding="utf-8"))
    if payload.get("phase") != "development":
        raise ValueError("NOT_DEVELOPMENT_RESULT")
    assessed: list[dict[str, Any]] = []
    passers: list[dict[str, Any]] = []
    for candidate in payload["candidates"]:
        checks = _development_checks(candidate, payload)
        base = candidate["scenarios"]["base"]
        stress = candidate["scenarios"]["stress"]
        record = {
            "candidate_id": candidate["candidate_id"],
            "passed": all(checks.values()),
            "checks": checks,
            "failed_checks": [name for name, passed in checks.items() if not passed],
            "worst_annual_base_return": min(base["annual_returns"].values()),
            "stress_sharpe": stress["sharpe"],
            "base_sharpe": base["sharpe"],
        }
        assessed.append(record)
        if record["passed"]:
            passers.append(record)
    passers.sort(
        key=lambda item: (
            -item["worst_annual_base_return"],
            -item["stress_sharpe"],
            -item["base_sharpe"],
            item["candidate_id"],
        )
    )
    selected = passers[0] if passers else None
    result = {
        "schema_version": 1,
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "phase": "development_selection",
        "source_sha256": _sha256(source),
        "assessed_candidates": assessed,
        "selected_candidate": selected,
        "evaluation_authorized": selected is not None,
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
    candidate_id = selection["selected_candidate"]["candidate_id"]
    candidate = next(
        item for item in payload["candidates"] if item["candidate_id"] == candidate_id
    )
    base = candidate["scenarios"]["base"]
    stress = candidate["scenarios"]["stress"]
    pure_long_short, pure_long = _best_trend_benchmarks(payload)
    checks = {
        "base_total_positive": base["total_return"] > 0,
        "stress_total_positive": stress["total_return"] > 0,
        "2024_positive": base["annual_returns"].get("2024", -1.0) > 0,
        "2025_positive": base["annual_returns"].get("2025", -1.0) > 0,
        "base_sharpe_at_least_0p50": base["sharpe"] is not None
        and base["sharpe"] >= 0.50,
        "drawdown_above_minus_15pct": base["max_drawdown"] > -0.15,
        "active_days_at_least_120": base["active_days"] >= 120,
        "sharpe_exceeds_both_pure_trends": base["sharpe"]
        > max(pure_long_short["sharpe"], pure_long["sharpe"]),
        "calmar_exceeds_both_pure_trends": base["calmar"]
        > max(pure_long_short["calmar"], pure_long["calmar"]),
        "funding_pnl_improves_pure_long_short": base[
            "funding_pnl_on_initial_equity"
        ]
        > pure_long_short["funding_pnl_on_initial_equity"],
    }
    passed = all(checks.values())
    result = {
        "schema_version": 1,
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "phase": "evaluation_gate",
        "source_sha256": _sha256(source),
        "candidate_id": candidate_id,
        "checks": checks,
        "failed_checks": [name for name, value in checks.items() if not value],
        "confirmation_candidate": {"candidate_id": candidate_id} if passed else None,
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
    candidate_id = gate["confirmation_candidate"]["candidate_id"]
    candidate = next(
        item
        for item in confirmation["candidates"]
        if item["candidate_id"] == candidate_id
    )
    evaluation_candidate = next(
        item for item in evaluation["candidates"] if item["candidate_id"] == candidate_id
    )
    base = candidate["scenarios"]["base"]
    stress = candidate["scenarios"]["stress"]
    pure_long_short = confirmation["benchmarks"]["pure_long_short"]["base"]
    combined: dict[str, float] = {}
    for scenario in ("base", "stress"):
        evaluation_return = evaluation_candidate["scenarios"][scenario]["total_return"]
        confirmation_return = candidate["scenarios"][scenario]["total_return"]
        combined[scenario] = (
            (1.0 + evaluation_return) * (1.0 + confirmation_return) - 1.0
        )
    checks = {
        "base_non_negative": base["total_return"] >= 0,
        "stress_non_negative": stress["total_return"] >= 0,
        "drawdown_above_minus_10pct": base["max_drawdown"] > -0.10,
        "active_days_at_least_15": base["active_days"] >= 15,
        "funding_pnl_not_worse_than_pure_long_short": base[
            "funding_pnl_on_initial_equity"
        ]
        >= pure_long_short["funding_pnl_on_initial_equity"],
        "combined_base_positive": combined["base"] > 0,
        "combined_stress_positive": combined["stress"] > 0,
    }
    passed = all(checks.values())
    result = {
        "schema_version": 1,
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "phase": "confirmation_gate",
        "candidate_id": candidate_id,
        "checks": checks,
        "failed_checks": [name for name, value in checks.items() if not value],
        "combined_evaluation_confirmation_returns": combined,
        "passed": passed,
        "conclusion": "SUPPORTS_WITHIN_SCOPE" if passed else "DOES_NOT_SUPPORT",
        "source_sha256": _sha256(source),
    }
    Path(args.output).write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(required=True)

    analyze_parser = subparsers.add_parser("analyze")
    analyze_parser.add_argument(
        "--phase", choices=tuple(PERIODS), required=True
    )
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
