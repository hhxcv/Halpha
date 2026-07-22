from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import platform
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import scipy
import statsmodels
import statsmodels.api as sm


HERE = Path(__file__).resolve().parent
ENGINE_PATH = HERE.parent / "trxusdt-perp-monthly-one-shot-voltarget" / "study.py"
SPEC = importlib.util.spec_from_file_location("halpha_tom_perp_engine", ENGINE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"cannot load shared research engine: {ENGINE_PATH}")
engine = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(engine)

SYMBOL = "BTCUSDT"
DATA_START = "2021-12-01T00:00:00Z"
DATA_END_EXCLUSIVE = "2026-07-05T00:00:00Z"
RESEARCH_CUTOFF = "2026-07-04T00:00:00Z"
STAGES = {
    "development": ("2022-01-01T00:00:00Z", "2024-01-01T00:00:00Z"),
    "evaluation": ("2024-01-01T00:00:00Z", "2025-01-01T00:00:00Z"),
    "confirmation": ("2025-01-01T00:00:00Z", "2026-07-01T00:00:00Z"),
}
EXPECTED_PLANS = {"development": 24, "evaluation": 12, "confirmation": 18}
CONFIG = {
    "strategy_id": "RESEARCH_BTCUSDT_TOM_LAST_TO_DAY4_LONG_0P5X_V1",
    "weight": 0.5,
    "annual_capital_hurdle": 0.04,
    "annual_research_program_haircut": 0.02,
    "costs": {
        "favorable": {"fee_per_side": 0.0006, "slippage_per_side": 0.0, "funding_stress": False},
        "base": {"fee_per_side": 0.0006, "slippage_per_side": 0.0010, "funding_stress": False},
        "stress": {"fee_per_side": 0.0006, "slippage_per_side": 0.0020, "funding_stress": True},
    },
    "funding_stress": {"positive_rate_multiplier": 1.5, "negative_rate_multiplier": 0.5},
    "bootstrap": {"block_months": 3, "repetitions": 5000, "seed": 20260722},
    "hac_maxlags": 7,
    "stage_open_rule": "development -> evaluation on PASS -> confirmation on PASS",
}
VARIANTS = {
    "primary": {"schedule": "tom", "entry_offset": 0, "exit_offset": 4},
    "tom3": {"schedule": "tom", "entry_offset": 0, "exit_offset": 3},
    "tom5": {"schedule": "tom", "entry_offset": 1, "exit_offset": 4},
    "midmonth": {"schedule": "midmonth"},
    "month_long": {"schedule": "month_long"},
}
CACHE_ROOT = Path(
    "D:/projects/Codex/CodexHome/research-data/halpha/"
    "btcusdt-perp-turn-of-month-one-shot-long/2026-07-22-v1"
)

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


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def digest_value(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(raw).hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: dict[str, Any]) -> None:
    payload = dict(value)
    payload["content_digest"] = digest_value(payload)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def csv_bytes(frame: pd.DataFrame) -> bytes:
    return frame.to_csv(index=False, date_format="%Y-%m-%dT%H:%M:%SZ").encode("utf-8")


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
        "question": "Can the conventional BTC turn-of-month window qualify as a realistic monthly one-shot perpetual plan?",
        "evidence_boundary": (
            "Primary published samples end in 2021, so development is post-publication; "
            "broad BTC paths were exposed by earlier Halpha work, but this exact rule was not calculated."
        ),
        "symbol": SYMBOL,
        "data_start": DATA_START,
        "data_end_exclusive": DATA_END_EXCLUSIVE,
        "research_cutoff": RESEARCH_CUTOFF,
        "stages": STAGES,
        "expected_plans": EXPECTED_PLANS,
        "variants": VARIANTS,
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
            "scipy": scipy.__version__,
            "statsmodels": statsmodels.__version__,
        },
        "cache_root": str(CACHE_ROOT),
    }
    write_json(HERE / "checkpoint.json", payload)
    print(json.dumps({"checkpoint": str(HERE / "checkpoint.json"), "digest": read_json(HERE / "checkpoint.json")["content_digest"]}))


def assert_checkpoint() -> None:
    checkpoint = read_json(HERE / "checkpoint.json")
    checks = {
        "study": checkpoint["study_py_sha256"] == digest_file(Path(__file__)),
        "engine": checkpoint["engine_sha256"] == digest_file(ENGINE_PATH),
        "preregistration": checkpoint["preregistration_sha256"] == digest_file(HERE / "preregistration.md"),
        "sources": checkpoint["sources_sha256"] == digest_file(HERE / "sources.md"),
    }
    if not all(checks.values()):
        raise RuntimeError(f"checkpoint identity mismatch: {checks}")


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


def schedule_times(month_end: pd.Timestamp, variant: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    spec = VARIANTS[variant]
    month_start = month_end.replace(day=1)
    if spec["schedule"] == "tom":
        return (
            month_end - pd.Timedelta(days=int(spec["entry_offset"])),
            month_end + pd.Timedelta(days=int(spec["exit_offset"])),
        )
    if spec["schedule"] == "midmonth":
        return month_start + pd.Timedelta(days=13), month_start + pd.Timedelta(days=17)
    if spec["schedule"] == "month_long":
        return month_start, month_end + pd.Timedelta(days=1)
    raise ValueError(f"unknown schedule: {variant}")


def build_plans(bars: pd.DataFrame, funding: pd.DataFrame, stage: str, variant: str) -> pd.DataFrame:
    start, end = map(pd.Timestamp, STAGES[stage])
    month_ends = pd.date_range(start, end, freq="ME", inclusive="left")
    rows: list[dict[str, Any]] = []
    weight = float(CONFIG["weight"])
    for month_end in month_ends:
        entry, exit_time = schedule_times(month_end, variant)
        if entry not in bars.index or exit_time not in bars.index:
            raise RuntimeError(f"missing scheduled bar for {variant}: {entry} -> {exit_time}")
        rates = funding[(funding.index > entry) & (funding.index <= exit_time)]
        if rates.empty or rates["markPrice"].isna().any():
            raise RuntimeError(f"incomplete funding for {variant}: {entry} -> {exit_time}")
        entry_price = float(bars.at[entry, "open"])
        exit_price = float(bars.at[exit_time, "open"])
        quantity = weight / entry_price
        stressed = rates["fundingRate"].map(engine.adverse_funding_rate)
        rows.append({
            "plan_id": f"{stage}-{variant}-{month_end.strftime('%Y%m')}",
            "stage": stage,
            "variant": variant,
            "month_end": month_end,
            "decision_time": entry - pd.Timedelta(seconds=1),
            "entry_time": entry,
            "exit_time": exit_time,
            "holding_days": float((exit_time - entry).total_seconds() / 86400.0),
            "weight": weight,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "quantity_per_unit_plan_capital": quantity,
            "funding_events": int(len(rates)),
            "funding_rate_sum": float(rates["fundingRate"].sum()),
            "actual_funding_return": float((-quantity * rates["markPrice"] * rates["fundingRate"]).sum()),
            "stress_funding_return": float((-quantity * rates["markPrice"] * stressed).sum()),
        })
    return pd.DataFrame(rows)


def block_ci(values: np.ndarray) -> list[float]:
    return engine.block_bootstrap_mean_ci(
        np.asarray(values, dtype=float),
        block=int(CONFIG["bootstrap"]["block_months"]),
        reps=int(CONFIG["bootstrap"]["repetitions"]),
        seed=int(CONFIG["bootstrap"]["seed"]),
    )


def daily_tom_test(bars: pd.DataFrame, stage: str) -> dict[str, Any]:
    start, end = map(pd.Timestamp, STAGES[stage])
    selected = bars[(bars.index >= start) & (bars.index <= end)].copy()
    selected["next_open"] = selected["open"].shift(-1)
    selected = selected[(selected.index < end) & selected["next_open"].notna()].copy()
    selected["log_return"] = np.log(selected["next_open"] / selected["open"])
    selected["tom"] = np.asarray([item.is_month_end or item.day <= 3 for item in selected.index], dtype=int)
    design = sm.add_constant(selected["tom"].to_numpy(float))
    fitted = sm.OLS(selected["log_return"].to_numpy(float), design).fit(
        cov_type="HAC", cov_kwds={"maxlags": int(CONFIG["hac_maxlags"])}
    )
    coefficient = float(fitted.params[1])
    two_sided = float(fitted.pvalues[1])
    one_sided = two_sided / 2.0 if coefficient >= 0 else 1.0 - two_sided / 2.0
    confidence = fitted.conf_int(alpha=0.05)[1]
    tom = selected.loc[selected["tom"] == 1, "log_return"]
    other = selected.loc[selected["tom"] == 0, "log_return"]
    return {
        "daily_rows": int(len(selected)),
        "tom_days": int(len(tom)),
        "non_tom_days": int(len(other)),
        "tom_mean_log_return": float(tom.mean()),
        "non_tom_mean_log_return": float(other.mean()),
        "tom_minus_non_tom_hac_coefficient": coefficient,
        "hac_95pct": [float(confidence[0]), float(confidence[1])],
        "hac_two_sided_p": two_sided,
        "hac_one_sided_positive_p": one_sided,
        "hac_maxlags": int(CONFIG["hac_maxlags"]),
    }


def analysis_core(stage: str) -> tuple[dict[str, Any], dict[str, pd.DataFrame]]:
    bars, funding, _symbol_info = engine.load_data()
    frames: dict[str, pd.DataFrame] = {}
    summaries: dict[str, Any] = {}
    csv_hashes: dict[str, str] = {}
    for variant in VARIANTS:
        frame = engine.attach_returns(build_plans(bars, funding, stage, variant))
        frames[variant] = frame
        summary = engine.summarize(frame, bars, funding, stage)
        for scenario in summary["scenarios"].values():
            scenario["return_after_6pct_combined_hurdle"] = combined_hurdle(scenario["total_return"], stage)
        summary["stress_positive_month_fraction"] = float((frame["stress_net_return"] > 0).mean())
        summaries[variant] = summary
        csv_hashes[f"{stage}_{variant}_plans.csv"] = digest_bytes(csv_bytes(frame))
    paired = frames["primary"]["base_net_return"].to_numpy(float) - frames["midmonth"]["base_net_return"].to_numpy(float)
    comparison = {
        "primary_minus_midmonth_base_mean": float(paired.mean()),
        "primary_minus_midmonth_base_block_bootstrap_95pct": block_ci(paired),
        "primary_positive_fraction_of_pairs": float((paired > 0).mean()),
    }
    core = {
        "stage": stage,
        "period": {"start": STAGES[stage][0], "end_exclusive": STAGES[stage][1]},
        "data_quality_digest": read_json(HERE / "data_quality.json")["content_digest"],
        "summaries": summaries,
        "paired_comparison": comparison,
        "daily_tom_replication": daily_tom_test(bars, stage),
        "plan_csv_sha256": csv_hashes,
        "search_disclosure": {
            "selectable_primary_configurations": 1,
            "primary": "last UTC calendar day open through next month day 4 open; 0.5x long",
            "diagnostics_only": ["TOM3", "TOM5", "midmonth", "month_long"],
            "post_publication_stage": True,
            "prior_broad_btc_path_exposure": True,
        },
    }
    return core, frames


def command_analyze(args: argparse.Namespace) -> None:
    assert_checkpoint()
    stage_authorized(args.stage)
    quality = read_json(HERE / "data_quality.json")
    if quality["status"] != "PASS":
        raise RuntimeError("data quality is not PASS")
    core, frames = analysis_core(args.stage)
    for variant, frame in frames.items():
        (HERE / f"{args.stage}_{variant}_plans.csv").write_bytes(csv_bytes(frame))
    payload = {"generated_at_utc": engine.iso_now(), **core}
    write_json(HERE / f"{args.stage}.json", payload)
    base = core["summaries"]["primary"]["scenarios"]["base"]
    print(json.dumps({
        "stage": args.stage,
        "base_total": base["total_return"],
        "daily_tom_coefficient": core["daily_tom_replication"]["tom_minus_non_tom_hac_coefficient"],
    }))


def gate_checks(stage: str, result: dict[str, Any]) -> dict[str, bool]:
    primary_summary = result["summaries"]["primary"]
    primary = primary_summary["scenarios"]
    checks = {
        "data_quality_pass": read_json(HERE / "data_quality.json")["status"] == "PASS",
        "all_plans_present": primary_summary["plans"] == EXPECTED_PLANS[stage],
        "vectorbt_reconciled": primary_summary["maximum_vectorbt_reconciliation_error"] <= 1e-10,
        "base_total_positive": primary["base"]["total_return"] > 0,
        "stress_total_positive": primary["stress"]["total_return"] > 0,
        "stress_after_4pct_hurdle_positive": primary["stress"]["return_after_4pct_annual_hurdle"] > 0,
        "base_after_6pct_combined_hurdle_positive": primary["base"]["return_after_6pct_combined_hurdle"] > 0,
        "paired_midmonth_improvement_positive": result["paired_comparison"]["primary_minus_midmonth_base_mean"] > 0,
        "daily_tom_hac_coefficient_positive": result["daily_tom_replication"]["tom_minus_non_tom_hac_coefficient"] > 0,
        "tom3_base_nonnegative": result["summaries"]["tom3"]["scenarios"]["base"]["total_return"] >= 0,
        "tom5_base_nonnegative": result["summaries"]["tom5"]["scenarios"]["base"]["total_return"] >= 0,
        "base_drawdown_above_minus_15pct": primary["base"]["daily_max_drawdown"] > -0.15,
        "stress_positive_month_fraction_at_least_half": primary_summary["stress_positive_month_fraction"] >= 0.5,
        "each_calendar_year_base_positive": all(item["base"] > 0 for item in primary_summary["by_year"].values()),
    }
    if stage == "development":
        checks["stress_monthly_bootstrap_lower_positive"] = primary["stress"]["monthly_mean_bootstrap_95pct"][0] > 0
        checks["daily_tom_one_sided_hac_p_lt_10pct"] = result["daily_tom_replication"]["hac_one_sided_positive_p"] < 0.10
    return checks


ECONOMIC_CHECKS = {
    "base_total_positive",
    "stress_total_positive",
    "stress_after_4pct_hurdle_positive",
    "base_after_6pct_combined_hurdle_positive",
    "paired_midmonth_improvement_positive",
    "daily_tom_hac_coefficient_positive",
}


def command_gate(args: argparse.Namespace) -> None:
    result = read_json(HERE / f"{args.stage}.json")
    checks = gate_checks(args.stage, result)
    payload = {
        "generated_at_utc": engine.iso_now(),
        "stage": args.stage,
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "failed_checks": [name for name, passed in checks.items() if not passed],
        "economic_failed_checks": [name for name in ECONOMIC_CHECKS if not checks.get(name, True)],
        "result_digest": result["content_digest"],
    }
    write_json(HERE / f"{args.stage}_gate.json", payload)
    print(json.dumps({"stage": args.stage, "status": payload["status"], "failed": payload["failed_checks"]}))


def pooled_checks() -> dict[str, Any]:
    stage_frames: dict[str, list[pd.DataFrame]] = {"primary": [], "midmonth": []}
    for stage in STAGES:
        for variant in stage_frames:
            frame = pd.read_csv(HERE / f"{stage}_{variant}_plans.csv")
            stage_frames[variant].append(frame)
    primary = pd.concat(stage_frames["primary"], ignore_index=True)
    midmonth = pd.concat(stage_frames["midmonth"], ignore_index=True)
    stress = primary["stress_net_return"].to_numpy(float)
    paired = primary["base_net_return"].to_numpy(float) - midmonth["base_net_return"].to_numpy(float)
    details = {
        "plans": int(len(primary)),
        "stress_mean": float(stress.mean()),
        "stress_block_bootstrap_95pct": block_ci(stress),
        "paired_base_mean": float(paired.mean()),
        "paired_base_block_bootstrap_95pct": block_ci(paired),
    }
    details["checks"] = {
        "all_54_plans_present": len(primary) == 54,
        "pooled_stress_bootstrap_lower_positive": details["stress_block_bootstrap_95pct"][0] > 0,
        "pooled_paired_base_bootstrap_lower_positive": details["paired_base_block_bootstrap_95pct"][0] > 0,
    }
    details["status"] = "PASS" if all(details["checks"].values()) else "FAIL"
    return details


def command_conclude(_args: argparse.Namespace) -> None:
    assert_checkpoint()
    available = [stage for stage in STAGES if (HERE / f"{stage}.json").exists()]
    gates = {stage: read_json(HERE / f"{stage}_gate.json") for stage in available}
    all_stage_pass = len(gates) == 3 and all(item["status"] == "PASS" for item in gates.values())
    pooled = pooled_checks() if all_stage_pass else {"status": "NOT_OPENED"}
    any_economic_failure = any(item["economic_failed_checks"] for item in gates.values())
    if all_stage_pass and pooled["status"] == "PASS":
        conclusion = "SUPPORTS_WITHIN_SCOPE"
    elif any_economic_failure:
        conclusion = "DOES_NOT_SUPPORT"
    else:
        conclusion = "INSUFFICIENT_EVIDENCE"
    payload = {
        "generated_at_utc": engine.iso_now(),
        "conclusion": conclusion,
        "claim": "BTC turn-of-month monthly timing candidate; not Alpha proof or a profitability guarantee",
        "available_stages": available,
        "stage_gate_status": {stage: gate["status"] for stage, gate in gates.items()},
        "stage_failed_checks": {stage: gate["failed_checks"] for stage, gate in gates.items()},
        "pooled": pooled,
        "evidence_limit": (
            "Stages are post-publication but broad BTC paths were already visible to the research program; "
            "daily-bar execution and funding stress cannot reproduce live fills or all perpetual risks."
        ),
        "handoff_status": (
            "ELIGIBLE_FOR_LATER_CORE_QUALIFICATION" if conclusion == "SUPPORTS_WITHIN_SCOPE" else
            "NO_HANDOFF; later stages remain sealed after FAIL"
        ),
        "product_effects": "NONE",
    }
    write_json(HERE / "results.json", payload)
    print(json.dumps({"conclusion": conclusion, "available_stages": available, "pooled": pooled["status"]}))


def command_validate(_args: argparse.Namespace) -> None:
    assert_checkpoint()
    checks: dict[str, bool] = {
        "data_quality_pass": read_json(HERE / "data_quality.json")["status"] == "PASS",
        "source_manifest_present": (HERE / "source_manifest.json").exists(),
    }
    for stage in STAGES:
        path = HERE / f"{stage}.json"
        if not path.exists():
            continue
        stored = read_json(path)
        recomputed, _frames = analysis_core(stage)
        stored_core = {key: value for key, value in stored.items() if key not in {"generated_at_utc", "content_digest"}}
        checks[f"{stage}_economics_recomputed"] = digest_value(stored_core) == digest_value(recomputed)
        checks[f"{stage}_gate_bound"] = read_json(HERE / f"{stage}_gate.json")["result_digest"] == stored["content_digest"]
        for name, identity in stored["plan_csv_sha256"].items():
            checks[f"{name}_identity"] = digest_file(HERE / name) == identity
    if (HERE / "results.json").exists():
        result = read_json(HERE / "results.json")
        checks["valid_conclusion"] = result["conclusion"] in {
            "SUPPORTS_WITHIN_SCOPE", "DOES_NOT_SUPPORT", "INSUFFICIENT_EVIDENCE", "CANNOT_DETERMINE"
        }
        checks["no_handoff_without_support"] = (
            result["conclusion"] == "SUPPORTS_WITHIN_SCOPE" or result["handoff_status"].startswith("NO_HANDOFF")
        )
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
    root = argparse.ArgumentParser(description="BTCUSDT conventional turn-of-month one-shot long")
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
    arguments = parser().parse_args()
    arguments.func(arguments)

