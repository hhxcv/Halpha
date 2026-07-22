from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
SOURCE = ROOT / "research/studies/strategy-candidate/2026/price-path-continuity-weekly-winner-long/development_main_trades.csv"
SOURCE_SHA256 = "8c3b0ce004fba8bf788c0b28a0b70d63475ffd2c1e3cfc1c6fc06a6930adbf3e"
BASELINE = "0bdfeffa616260cebd2d2188ddc8deb9e85c77f4"
CONFIG = {
    "candidate_id": "RESEARCH_PPC14_TOP_TERCILE_MOM14_TOP_TERCILE_WEEKLY_LONG_0P25X_V1",
    "annual_capital_hurdle": 0.04,
    "hold_days": 7,
    "expected_trades": 88,
    "expected_entry_dates": 40,
    "block_lengths": [1, 4, 8],
    "primary_block_length": 4,
    "sample_sizes": [26, 52, 78, 104, 156, 208, 260, 312, 416, 520],
    "effects": [0.0, 0.0025, 0.005, 0.0075, 0.01],
    "primary_effect": 0.005,
    "draws": 25000,
    "exact_outer_draws": 5000,
    "exact_inner_draws": 5000,
    "exact_inner_seed": 20260722,
    "seed": 2026072201,
    "power_target": 0.80,
    "false_positive_limit": 0.05,
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def write_json(path: Path, value: dict[str, Any]) -> None:
    payload = dict(value)
    payload["content_digest"] = canonical(payload)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def read_source() -> np.ndarray:
    if sha256(SOURCE) != SOURCE_SHA256:
        raise RuntimeError("PPC source identity mismatch")
    frame = pd.read_csv(SOURCE)
    if len(frame) != CONFIG["expected_trades"] or frame["entry_time"].nunique() != CONFIG["expected_entry_dates"]:
        raise RuntimeError("PPC source shape mismatch")
    required = {"entry_time", "stress_net_return"}
    if not required.issubset(frame.columns) or frame[list(required)].isna().any().any():
        raise RuntimeError("PPC source columns missing or null")
    date_returns = frame.groupby("entry_time", sort=True)["stress_net_return"].mean()
    adjusted = date_returns.to_numpy(float) - CONFIG["annual_capital_hurdle"] * CONFIG["hold_days"] / 365.0
    if not np.isfinite(adjusted).all():
        raise RuntimeError("non-finite PPC date return")
    return adjusted


def draw_statistics(values: np.ndarray, n: int, block: int, draws: int, seed: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    means = np.empty(draws)
    first = np.empty(draws)
    second = np.empty(draws)
    batch = 1000
    blocks = math.ceil(n / block)
    offsets = np.arange(block)
    for start in range(0, draws, batch):
        stop = min(start + batch, draws)
        starts = rng.integers(0, len(values), size=(stop - start, blocks))
        indexes = (starts[:, :, None] + offsets[None, None, :]) % len(values)
        sample = values[indexes.reshape(stop - start, -1)[:, :n]]
        midpoint = n // 2
        means[start:stop] = sample.mean(axis=1)
        first[start:stop] = sample[:, :midpoint].mean(axis=1)
        second[start:stop] = sample[:, midpoint:].mean(axis=1)
    return means, first, second


def wilson(successes: int, total: int) -> list[float]:
    z = 1.959963984540054
    p = successes / total
    denominator = 1.0 + z * z / total
    center = (p + z * z / (2.0 * total)) / denominator
    margin = z * math.sqrt(p * (1.0 - p) / total + z * z / (4.0 * total * total)) / denominator
    return [center - margin, center + margin]


def probability(mask: np.ndarray) -> dict[str, Any]:
    successes = int(mask.sum())
    return {"estimate": successes / len(mask), "wilson_95pct": wilson(successes, len(mask)), "successes": successes}


def circular_indexes(rng: np.random.Generator, population: int, n: int, block: int, draws: int) -> np.ndarray:
    blocks = math.ceil(n / block)
    starts = rng.integers(0, population, size=(draws, blocks))
    offsets = np.arange(block)
    return ((starts[:, :, None] + offsets[None, None, :]) % population).reshape(draws, -1)[:, :n]


def exact_nested_primary(centered: np.ndarray) -> dict[str, Any]:
    n = 26
    block = CONFIG["primary_block_length"]
    outer_draws = CONFIG["exact_outer_draws"]
    inner_draws = CONFIG["exact_inner_draws"]
    inner_indexes = circular_indexes(
        np.random.default_rng(CONFIG["exact_inner_seed"]), n, n, block, inner_draws
    )
    outer_rng = np.random.default_rng(CONFIG["seed"] + 900001)
    counters = {effect: {"mean": 0, "joint": 0} for effect in CONFIG["effects"]}
    batch = 20
    for start in range(0, outer_draws, batch):
        size = min(batch, outer_draws - start)
        outer_indexes = circular_indexes(outer_rng, len(centered), n, block, size)
        samples = centered[outer_indexes]
        nested_means = samples[:, inner_indexes].mean(axis=2)
        lower = np.quantile(nested_means, 0.025, axis=1)
        midpoint = n // 2
        first = samples[:, :midpoint].mean(axis=1)
        second = samples[:, midpoint:].mean(axis=1)
        for effect in CONFIG["effects"]:
            mean_pass = lower + effect > 0.0
            joint = mean_pass & (first + effect > 0.0) & (second + effect > 0.0)
            counters[effect]["mean"] += int(mean_pass.sum())
            counters[effect]["joint"] += int(joint.sum())
    output: dict[str, Any] = {}
    for effect in CONFIG["effects"]:
        mean_success = counters[effect]["mean"]
        joint_success = counters[effect]["joint"]
        output[f"{effect:.4f}"] = {
            "effect": effect,
            "mean_gate_power": mean_success / outer_draws,
            "mean_gate_wilson_95pct": wilson(mean_success, outer_draws),
            "joint_power": joint_success / outer_draws,
            "joint_wilson_95pct": wilson(joint_success, outer_draws),
            "outer_draws": outer_draws,
            "inner_draws": inner_draws,
        }
    return output


def calculate() -> tuple[dict[str, Any], pd.DataFrame]:
    raw = read_source()
    centered = raw - raw.mean()
    rows: list[dict[str, Any]] = []
    stream = 0
    for block in CONFIG["block_lengths"]:
        for n in CONFIG["sample_sizes"]:
            stream += 1
            calibration, _, _ = draw_statistics(
                centered, n, block, CONFIG["draws"], CONFIG["seed"] + stream * 10
            )
            critical = -float(np.quantile(calibration, 0.025))
            means, first, second = draw_statistics(
                centered, n, block, CONFIG["draws"], CONFIG["seed"] + stream * 10 + 1
            )
            for effect in CONFIG["effects"]:
                mean_pass = means + effect > critical
                halves_pass = (first + effect > 0.0) & (second + effect > 0.0)
                joint = mean_pass & halves_pass
                mean_result = probability(mean_pass)
                joint_result = probability(joint)
                rows.append({
                    "method": "REFERENCE_DISTRIBUTION_APPROXIMATION_NOT_GATE_EQUIVALENT",
                    "block_weeks": block,
                    "eligible_weeks": n,
                    "effect": effect,
                    "critical_mean": critical,
                    "mean_gate_power": mean_result["estimate"],
                    "mean_gate_wilson_low": mean_result["wilson_95pct"][0],
                    "mean_gate_wilson_high": mean_result["wilson_95pct"][1],
                    "joint_power": joint_result["estimate"],
                    "joint_wilson_low": joint_result["wilson_95pct"][0],
                    "joint_wilson_high": joint_result["wilson_95pct"][1],
                    "draws": CONFIG["draws"],
                })
    curve = pd.DataFrame(rows)
    exact = exact_nested_primary(centered)
    primary = curve[(curve["block_weeks"] == CONFIG["primary_block_length"]) & (curve["effect"] == CONFIG["primary_effect"])].copy()
    primary_26 = exact[f"{CONFIG['primary_effect']:.4f}"]
    null_26 = exact[f"{0.0:.4f}"]
    if primary_26["joint_power"] >= CONFIG["power_target"] and null_26["joint_power"] <= CONFIG["false_positive_limit"]:
        conclusion = "SUPPORTS_WITHIN_SCOPE"
    elif primary_26["joint_power"] < 0.50 or null_26["joint_power"] > CONFIG["false_positive_limit"]:
        conclusion = "DOES_NOT_SUPPORT"
    else:
        conclusion = "INSUFFICIENT_EVIDENCE"
    result = {
        "as_of": "2026-07-22",
        "baseline_commit": BASELINE,
        "research_kind": "COMPARATIVE_OR_MECHANISM",
        "question": "Can 26 eligible frozen PPC forward weeks reliably detect a 50 bp weekly net edge under the existing core evidence gate?",
        "conclusion": conclusion,
        "source": {"path": str(SOURCE.relative_to(ROOT)).replace("\\", "/"), "sha256": SOURCE_SHA256, "trades": len(pd.read_csv(SOURCE)), "entry_dates": len(raw)},
        "empirical_calibration": {
            "observed_mean_disclosed_not_used_as_effect": float(raw.mean()),
            "standard_deviation": float(raw.std(ddof=1)),
            "minimum": float(raw.min()),
            "maximum": float(raw.max()),
            "skew": float(pd.Series(raw).skew()),
            "excess_kurtosis": float(pd.Series(raw).kurt()),
            "centered_mean_used_in_simulation": float(centered.mean()),
        },
        "primary_26_weeks": {
            "effect": CONFIG["primary_effect"],
            "block_weeks": CONFIG["primary_block_length"],
            "method": "EXACT_NESTED_PERCENTILE_BOOTSTRAP",
            "mean_gate_power": primary_26["mean_gate_power"],
            "mean_gate_wilson_95pct": primary_26["mean_gate_wilson_95pct"],
            "joint_power": primary_26["joint_power"],
            "joint_wilson_95pct": primary_26["joint_wilson_95pct"],
            "null_joint_false_positive": null_26["joint_power"],
            "null_joint_false_positive_wilson_95pct": null_26["joint_wilson_95pct"],
        },
        "exact_26_week_effect_curve": exact,
        "first_horizon_reaching_80pct_joint_power_for_50bp": "NOT_DETERMINED; long-horizon curve is non-equivalent diagnostic only",
        "reference_threshold_curve_max_50bp_joint_power_not_gate_equivalent": float(primary["joint_power"].max()),
        "planning_interpretation": "26 eligible weeks remains the first checkpoint, not a decision-ready horizon" if conclusion == "DOES_NOT_SUPPORT" else "see primary power result",
        "strategy_rule_changed": False,
        "sealed_market_stage_opened": False,
        "product_effects": "NONE",
        "config": CONFIG,
        "study_py_sha256": sha256(Path(__file__)),
    }
    return result, curve


def command_checkpoint(_args: argparse.Namespace) -> None:
    raw = read_source()
    payload = {
        "as_of": "2026-07-22",
        "baseline_commit": BASELINE,
        "source_path": str(SOURCE.relative_to(ROOT)).replace("\\", "/"),
        "source_sha256": SOURCE_SHA256,
        "source_entry_dates": len(raw),
        "config": CONFIG,
        "study_py_sha256": sha256(Path(__file__)),
    }
    write_json(HERE / "checkpoint.json", payload)
    print(json.dumps({"checkpoint": "PASS", "entry_dates": len(raw)}))


def command_analyze(_args: argparse.Namespace) -> None:
    if not (HERE / "checkpoint.json").exists():
        raise RuntimeError("checkpoint required")
    result, curve = calculate()
    curve.to_csv(HERE / "power_curve.csv", index=False, float_format="%.12g")
    write_json(HERE / "results.json", result)
    print(json.dumps({
        "conclusion": result["conclusion"],
        "power_26": result["primary_26_weeks"]["joint_power"],
        "horizon_80pct": result["first_horizon_reaching_80pct_joint_power_for_50bp"],
    }))


def command_validate(_args: argparse.Namespace) -> None:
    stored = json.loads((HERE / "results.json").read_text(encoding="utf-8"))
    digest = stored.pop("content_digest")
    expected, curve = calculate()
    expected_digest = canonical(expected)
    actual_curve = pd.read_csv(HERE / "power_curve.csv")
    expected_curve = pd.read_csv(pd.io.common.StringIO(curve.to_csv(index=False, float_format="%.12g")))
    curve_match = actual_curve.shape == expected_curve.shape and np.allclose(
        actual_curve.select_dtypes(include=[np.number]), expected_curve.select_dtypes(include=[np.number]), rtol=0.0, atol=1e-12
    )
    text_columns = [c for c in actual_curve.columns if c not in actual_curve.select_dtypes(include=[np.number]).columns]
    curve_match = curve_match and all(actual_curve[c].equals(expected_curve[c]) for c in text_columns)
    validation = {
        "status": "PASS" if stored == expected and digest == expected_digest and curve_match else "FAIL",
        "source_identity_valid": sha256(SOURCE) == SOURCE_SHA256,
        "results_content_digest_valid": digest == expected_digest,
        "deterministic_recalculation_matches": stored == expected,
        "power_curve_matches": curve_match,
        "sealed_market_stage_opened": False,
        "product_effects": "NONE",
    }
    write_json(HERE / "validation.json", validation)
    if validation["status"] != "PASS":
        raise RuntimeError(json.dumps(validation))
    print(json.dumps(validation))


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Calibrate frozen PPC forward-gate power")
    sub = root.add_subparsers(dest="command", required=True)
    sub.add_parser("checkpoint").set_defaults(func=command_checkpoint)
    sub.add_parser("analyze").set_defaults(func=command_analyze)
    sub.add_parser("validate").set_defaults(func=command_validate)
    return root


if __name__ == "__main__":
    args = parser().parse_args()
    args.func(args)
