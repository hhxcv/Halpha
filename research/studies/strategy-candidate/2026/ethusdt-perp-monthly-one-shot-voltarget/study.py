from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import platform
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


HERE = Path(__file__).resolve().parent
ENGINE_PATH = HERE.parent / "trxusdt-perp-monthly-one-shot-voltarget" / "study.py"
SPEC = importlib.util.spec_from_file_location("halpha_trx_perp_voltarget_engine", ENGINE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"cannot load shared research engine: {ENGINE_PATH}")
engine = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(engine)

SYMBOL = "ETHUSDT"
DATA_START = "2020-10-01T00:00:00Z"
DATA_END_EXCLUSIVE = "2026-07-02T00:00:00Z"
RESEARCH_CUTOFF = "2026-07-01T00:00:00Z"
STAGES = {
    "development": ("2021-01-01T00:00:00Z", "2023-01-01T00:00:00Z"),
    "evaluation": ("2023-01-01T00:00:00Z", "2025-01-01T00:00:00Z"),
    "confirmation": ("2025-01-01T00:00:00Z", "2026-07-01T00:00:00Z"),
}
CONFIG = {
    "strategy_id": "RESEARCH_ETHUSDT_PERP_VOL60_TARGET8_CAP25_MONTHLY_ONE_SHOT_V1",
    "volatility_lookback_days": 60,
    "target_volatilities": [0.06, 0.08, 0.10],
    "primary_target_volatility": 0.08,
    "maximum_notional_fraction": 0.25,
    "annual_capital_hurdle": 0.04,
    "annual_research_program_haircut": 0.02,
    "costs": {
        "favorable": {"fee_per_side": 0.0006, "slippage_per_side": 0.0, "funding_stress": False},
        "base": {"fee_per_side": 0.0006, "slippage_per_side": 0.0010, "funding_stress": False},
        "stress": {"fee_per_side": 0.0006, "slippage_per_side": 0.0020, "funding_stress": True},
    },
    "funding_stress": {"positive_rate_multiplier": 1.5, "negative_rate_multiplier": 0.5},
    "stage_open_rule": "development -> evaluation on PASS -> confirmation on PASS",
}
CACHE_ROOT = Path(
    "D:/projects/Codex/CodexHome/research-data/halpha/"
    "ethusdt-perp-monthly-one-shot-voltarget/2026-07-22-v1"
)

# Bind the validated sibling engine to this registered question. The sibling file is
# never modified; generated data and outputs use only this study's HERE/cache roots.
engine.HERE = HERE
engine.CACHE_ROOT = CACHE_ROOT
engine.SYMBOL = SYMBOL
engine.DATA_START = DATA_START
engine.DATA_END_EXCLUSIVE = DATA_END_EXCLUSIVE
engine.RESEARCH_CUTOFF = RESEARCH_CUTOFF
engine.STAGES = STAGES
engine.CONFIG = CONFIG


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


def write_json(path: Path, value: Any) -> None:
    value = dict(value)
    value["content_digest"] = digest_value(value)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def combined_hurdle(total_return: float, stage: str) -> float:
    start, end = map(pd.Timestamp, STAGES[stage])
    years = (end - start).total_seconds() / (365.0 * 86400.0)
    hurdle = CONFIG["annual_capital_hurdle"] + CONFIG["annual_research_program_haircut"]
    return float((1.0 + total_return) / ((1.0 + hurdle) ** years) - 1.0)


def command_checkpoint(_args: argparse.Namespace) -> None:
    payload = {
        "created_at_utc": engine.iso_now(),
        "baseline_commit": "0bdfeffa616260cebd2d2188ddc8deb9e85c77f4",
        "formal_strategy": {"id": "ONE_SHOT_DONCHIAN_ATR_BREAKOUT", "version": "1.0.1"},
        "research_kind": "STRATEGY_CANDIDATE",
        "question": "Can fixed capped monthly ETH volatility targeting survive realistic one-shot perpetual economics?",
        "evidence_boundary": (
            "ETH market paths through 2026-06 were exposed by earlier Halpha research; "
            "the exact rule outputs are uncomputed and opened sequentially."
        ),
        "symbol": SYMBOL,
        "data_start": DATA_START,
        "data_end_exclusive": DATA_END_EXCLUSIVE,
        "research_cutoff": RESEARCH_CUTOFF,
        "stages": STAGES,
        "config": CONFIG,
        "study_py_sha256": digest_file(Path(__file__)),
        "engine_path": str(ENGINE_PATH.relative_to(HERE.parents[4])),
        "engine_sha256": digest_file(ENGINE_PATH),
        "preregistration_sha256": digest_file(HERE / "preregistration.md"),
        "sources_sha256": digest_file(HERE / "sources.md"),
        "environment": {
            "python": platform.python_version(),
            "vectorbt": engine.vbt.__version__,
            "pandas": pd.__version__,
            "numpy": np.__version__,
            "scipy": engine.scipy.__version__,
        },
        "cache_root": str(CACHE_ROOT),
    }
    write_json(HERE / "checkpoint.json", payload)
    print(json.dumps({"checkpoint": str(HERE / "checkpoint.json"), "digest": read_json(HERE / "checkpoint.json")["content_digest"]}))


def assert_checkpoint() -> None:
    checkpoint = engine.ensure_checkpoint()
    if checkpoint["study_py_sha256"] != digest_file(Path(__file__)):
        raise RuntimeError("study.py changed after checkpoint")
    if checkpoint["engine_sha256"] != digest_file(ENGINE_PATH):
        raise RuntimeError("shared research engine changed after checkpoint")


def command_fetch(args: argparse.Namespace) -> None:
    assert_checkpoint()
    engine.command_fetch(args)


def command_inspect(args: argparse.Namespace) -> None:
    assert_checkpoint()
    engine.command_inspect(args)


def stage_authorized(stage: str) -> None:
    if stage == "evaluation" and read_json(HERE / "development_gate.json")["status"] != "PASS":
        raise RuntimeError("evaluation remains sealed because development did not PASS")
    if stage == "confirmation" and read_json(HERE / "evaluation_gate.json")["status"] != "PASS":
        raise RuntimeError("confirmation remains sealed because evaluation did not PASS")


def fixed_weight_plans(stage: str, bars: pd.DataFrame, funding: pd.DataFrame) -> pd.DataFrame:
    plans = engine.build_plans(bars, funding, stage, 10.0)
    plans["weight"] = CONFIG["maximum_notional_fraction"]
    return engine.build_fixed_weight_plans(plans, funding)


def command_analyze(args: argparse.Namespace) -> None:
    assert_checkpoint()
    stage_authorized(args.stage)
    quality = read_json(HERE / "data_quality.json")
    if quality["status"] != "PASS":
        raise RuntimeError("data quality is not PASS")
    bars, funding, _symbol_info = engine.load_data()
    matrix: dict[str, Any] = {}
    primary_plans: pd.DataFrame | None = None
    for target in CONFIG["target_volatilities"]:
        plans = engine.attach_returns(engine.build_plans(bars, funding, args.stage, float(target)))
        summary = engine.summarize(plans, bars, funding, args.stage)
        for scenario in summary["scenarios"].values():
            scenario["return_after_6pct_combined_hurdle"] = combined_hurdle(scenario["total_return"], args.stage)
        matrix[f"{target:.2f}"] = summary
        if target == CONFIG["primary_target_volatility"]:
            primary_plans = plans
    benchmark_plans = engine.attach_returns(fixed_weight_plans(args.stage, bars, funding))
    benchmark = engine.summarize(benchmark_plans, bars, funding, args.stage)
    for scenario in benchmark["scenarios"].values():
        scenario["return_after_6pct_combined_hurdle"] = combined_hurdle(scenario["total_return"], args.stage)
    assert primary_plans is not None
    primary_path = HERE / f"{args.stage}_plans.csv"
    primary_plans.to_csv(primary_path, index=False, date_format="%Y-%m-%dT%H:%M:%SZ")
    payload = {
        "generated_at_utc": engine.iso_now(),
        "stage": args.stage,
        "period": {"start": STAGES[args.stage][0], "end_exclusive": STAGES[args.stage][1]},
        "data_quality_digest": quality["content_digest"],
        "matrix": matrix,
        "fixed_quarter_long_benchmark": benchmark,
        "primary_plan_csv_sha256": digest_file(primary_path),
        "search_disclosure": {
            "selectable_primary_configurations": 1,
            "diagnostic_neighbor_targets": [0.06, 0.10],
            "simple_benchmark": "forced-monthly fixed 0.25x ETHUSDT perpetual long",
            "prior_market_path_exposure": True,
        },
    }
    write_json(HERE / f"{args.stage}.json", payload)
    main = matrix["0.08"]["scenarios"]["base"]
    print(json.dumps({"stage": args.stage, "base_total": main["total_return"], "base_drawdown": main["daily_max_drawdown"]}))


def gate_checks(stage: str, result: dict[str, Any]) -> dict[str, bool]:
    primary_summary = result["matrix"]["0.08"]
    primary = primary_summary["scenarios"]
    benchmark = result["fixed_quarter_long_benchmark"]["scenarios"]["base"]
    checks = {
        "data_quality_pass": read_json(HERE / "data_quality.json")["status"] == "PASS",
        "all_plans_present": primary_summary["plans"] == (18 if stage == "confirmation" else 24),
        "vectorbt_reconciled": primary_summary["maximum_vectorbt_reconciliation_error"] <= 1e-10,
        "base_total_positive": primary["base"]["total_return"] > 0,
        "stress_after_4pct_hurdle_positive": primary["stress"]["return_after_4pct_annual_hurdle"] > 0,
        "base_after_6pct_combined_hurdle_positive": primary["base"]["return_after_6pct_combined_hurdle"] > 0,
        "base_drawdown_better_than_fixed_quarter": primary["base"]["daily_max_drawdown"] > benchmark["daily_max_drawdown"],
        "base_sharpe_better_than_fixed_quarter": primary["base"]["sharpe_zero_rf"] > benchmark["sharpe_zero_rf"],
        "neighbor_6pct_base_nonnegative": result["matrix"]["0.06"]["scenarios"]["base"]["total_return"] >= 0,
        "neighbor_10pct_base_nonnegative": result["matrix"]["0.10"]["scenarios"]["base"]["total_return"] >= 0,
        "worst_calendar_year_above_minus_10pct": min(
            values["base"] for values in primary_summary["by_year"].values()
        ) > -0.10,
    }
    if stage == "confirmation":
        checks["stress_total_positive"] = primary["stress"]["total_return"] > 0
        checks["base_drawdown_above_minus_10pct"] = primary["base"]["daily_max_drawdown"] > -0.10
    return checks


def command_gate(args: argparse.Namespace) -> None:
    result = read_json(HERE / f"{args.stage}.json")
    checks = gate_checks(args.stage, result)
    payload = {
        "generated_at_utc": engine.iso_now(),
        "stage": args.stage,
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "failed_checks": [name for name, passed in checks.items() if not passed],
        "result_digest": result["content_digest"],
    }
    write_json(HERE / f"{args.stage}_gate.json", payload)
    print(json.dumps({"stage": args.stage, "status": payload["status"], "failed": payload["failed_checks"]}))


def command_conclude(_args: argparse.Namespace) -> None:
    available = [stage for stage in STAGES if (HERE / f"{stage}.json").exists()]
    stages = {stage: read_json(HERE / f"{stage}.json") for stage in available}
    gates = {stage: read_json(HERE / f"{stage}_gate.json") for stage in available}
    all_pass = len(gates) == 3 and all(item["status"] == "PASS" for item in gates.values())
    latest = available[-1]
    latest_base = stages[latest]["matrix"]["0.08"]["scenarios"]["base"]["total_return"]
    if all_pass:
        conclusion = "SUPPORTS_WITHIN_SCOPE"
    elif latest_base <= 0 or gates.get("development", {}).get("status") == "FAIL":
        conclusion = "DOES_NOT_SUPPORT"
    else:
        conclusion = "INSUFFICIENT_EVIDENCE"
    payload = {
        "generated_at_utc": engine.iso_now(),
        "conclusion": conclusion,
        "claim": "ETH monthly capped volatility-target risk-premium plan, not Alpha proof",
        "available_stages": available,
        "stage_gate_status": {stage: gate["status"] for stage, gate in gates.items()},
        "stage_primary": {stage: result["matrix"]["0.08"] for stage, result in stages.items()},
        "stage_fixed_quarter_long": {stage: result["fixed_quarter_long_benchmark"] for stage, result in stages.items()},
        "evidence_limit": (
            "Earlier Halpha research exposed the ETH market paths. Sequential exact-rule evidence and "
            "program haircut reduce, but do not eliminate, research-program selection risk."
        ),
        "handoff_status": "RESEARCH_ONLY; product qualification required; no product object generated",
        "product_effects": "NONE",
    }
    write_json(HERE / "results.json", payload)
    print(json.dumps({"conclusion": conclusion, "available_stages": available, "all_gates_pass": all_pass}))


def command_validate(_args: argparse.Namespace) -> None:
    checkpoint = read_json(HERE / "checkpoint.json")
    checks = {
        "study_frozen": checkpoint["study_py_sha256"] == digest_file(Path(__file__)),
        "engine_frozen": checkpoint["engine_sha256"] == digest_file(ENGINE_PATH),
        "preregistration_frozen": checkpoint["preregistration_sha256"] == digest_file(HERE / "preregistration.md"),
        "sources_frozen": checkpoint["sources_sha256"] == digest_file(HERE / "sources.md"),
        "data_quality_pass": read_json(HERE / "data_quality.json")["status"] == "PASS",
    }
    for stage in STAGES:
        result_path = HERE / f"{stage}.json"
        if not result_path.exists():
            continue
        result = read_json(result_path)
        plan_path = HERE / f"{stage}_plans.csv"
        checks[f"{stage}_plans_identity"] = result["primary_plan_csv_sha256"] == digest_file(plan_path)
        checks[f"{stage}_gate_bound"] = read_json(HERE / f"{stage}_gate.json")["result_digest"] == result["content_digest"]
    payload = {
        "validated_at_utc": engine.iso_now(),
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
    root = argparse.ArgumentParser(description="ETH monthly capped perpetual volatility target")
    sub = root.add_subparsers(dest="command", required=True)
    sub.add_parser("checkpoint").set_defaults(func=command_checkpoint)
    sub.add_parser("fetch").set_defaults(func=command_fetch)
    sub.add_parser("inspect").set_defaults(func=command_inspect)
    for name, function in (("analyze", command_analyze), ("gate", command_gate)):
        item = sub.add_parser(name)
        item.add_argument("--stage", choices=tuple(STAGES), required=True)
        item.set_defaults(func=function)
    sub.add_parser("conclude").set_defaults(func=command_conclude)
    sub.add_parser("validate").set_defaults(func=command_validate)
    return root


if __name__ == "__main__":
    args = parser().parse_args()
    args.func(args)
