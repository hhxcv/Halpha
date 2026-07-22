from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any


STUDY_DIR = Path(__file__).resolve().parent
REPO_ROOT = STUDY_DIR.parents[4]
CHECKPOINT = STUDY_DIR / "checkpoint.json"
OUTPUT = STUDY_DIR / "audit.json"
DATA_ROOT = Path(
    "D:/projects/Codex/CodexHome/research-data/halpha/"
    "btc-shock-beta-gap-predictability"
)


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def read_baseline_file(commit: str, relative: str) -> bytes:
    try:
        return subprocess.check_output(
            ["git", "show", f"{commit}:{relative}"],
            cwd=REPO_ROOT,
        )
    except subprocess.CalledProcessError as exc:
        raise ValueError(
            f"cannot read pinned baseline input: {commit}:{relative}"
        ) from exc


def load_json(relative: str) -> dict[str, Any]:
    return json.loads((REPO_ROOT / relative).read_text(encoding="utf-8"))


def conclusion_of(document: dict[str, Any]) -> str:
    conclusion = document.get("conclusion")
    if conclusion not in {
        "SUPPORTS_WITHIN_SCOPE",
        "DOES_NOT_SUPPORT",
        "INSUFFICIENT_EVIDENCE",
        "CANNOT_DETERMINE",
    }:
        raise ValueError(f"invalid conclusion: {conclusion!r}")
    return str(conclusion)


def main() -> None:
    checkpoint = json.loads(CHECKPOINT.read_text(encoding="utf-8"))
    baseline_commit = checkpoint["baseline_commit"]
    actual_code_sha = sha256_path(Path(__file__))
    if actual_code_sha != checkpoint["audit_code_sha256"]:
        raise ValueError(
            "audit code changed: "
            f"checkpoint={checkpoint['audit_code_sha256']}, actual={actual_code_sha}"
        )
    validated: list[dict[str, Any]] = []
    product_input_drift: list[dict[str, Any]] = []
    for relative, expected in checkpoint["input_sha256"].items():
        if relative.startswith("docs/"):
            content = read_baseline_file(baseline_commit, relative)
            actual = sha256_bytes(content)
            source = f"git:{baseline_commit}"
            current_path = REPO_ROOT / relative
            current = sha256_path(current_path)
            product_input_drift.append(
                {
                    "path": relative,
                    "baseline_sha256": actual,
                    "working_tree_sha256": current,
                    "working_tree_matches_baseline": current == actual,
                }
            )
            size = len(content)
        else:
            path = REPO_ROOT / relative
            actual = sha256_path(path)
            source = "research_worktree"
            size = path.stat().st_size
        if actual != expected:
            raise ValueError(f"input changed: {relative}: expected={expected}, actual={actual}")
        validated.append(
            {"path": relative, "sha256": actual, "bytes": size, "source": source}
        )

    l4_text = read_baseline_file(
        baseline_commit, "docs/L4/HALPHA-PLAN-001-current-plan.yaml"
    ).decode("utf-8")
    strategy_id = re.search(r"^\s*strategy_id:\s*(\S+)", l4_text, re.MULTILINE)
    strategy_version = re.search(
        r"^\s*strategy_version:\s*(\S+)", l4_text, re.MULTILINE
    )
    if not strategy_id or not strategy_version:
        raise ValueError("cannot identify current L4 strategy")

    relation_text = (
        REPO_ROOT
        / "research/studies/comparative-or-mechanism/2026/"
        "btc-market-relationship-monitor/result.md"
    ).read_text(encoding="utf-8")
    if "`SUPPORTS_WITHIN_SCOPE`" not in relation_text or "不支持因果" not in relation_text:
        raise ValueError("BTC relationship result semantics changed")

    mature = load_json(
        "research/studies/predictive/2026/"
        "btc-shock-beta-gap-predictability/development.json"
    )
    residual = load_json(
        "research/studies/predictive/2026/"
        "btc-neutral-alt-residual-reversal/development.json"
    )
    mid = load_json(
        "research/studies/predictive/2026/"
        "btc-shock-mid-activity-beta-gap/development.json"
    )
    legacy = {
        "eth_2h_reversal": load_json(
            "research/studies/legacy/2026/ethusdt-2h-extreme-reversal/results.json"
        ),
        "alt_top2_momentum": load_json(
            "research/studies/legacy/2026/mature-alt-spot-top2-momentum/results.json"
        ),
        "btc_eth_momentum": load_json(
            "research/studies/legacy/2026/btc-eth-spot-dual-momentum/results.json"
        ),
        "conservative_perp_tsmom": load_json(
            "research/studies/legacy/2026/core-perp-conservative-volscaled-tsmom/results.json"
        ),
        "funding_carry_basket": load_json(
            "research/studies/legacy/2026/mature-alt-continuous-cash-carry-basket/results.json"
        ),
    }

    for document in [mature, residual, mid]:
        if conclusion_of(document) != "DOES_NOT_SUPPORT" or document["release_next_phase"]:
            raise ValueError("new predictive evidence no longer matches the frontier decision")

    manifest_paths = [
        "research/studies/predictive/2026/btc-shock-beta-gap-predictability/"
        "source_manifest_development.json",
        "research/studies/predictive/2026/btc-shock-mid-activity-beta-gap/"
        "source_manifest_development.json",
    ]
    unique_files: dict[str, int] = {}
    for relative in manifest_paths:
        manifest = load_json(relative)
        if manifest["failures"]:
            raise ValueError(f"source failures remain in {relative}")
        for item in manifest["files"]:
            unique_files[item["cache_relative_path"]] = int(item["bytes"])

    evidence = {
        "descriptive_relationship": {
            "conclusion": "SUPPORTS_WITHIN_SCOPE",
            "claim": "BTC is a common daily return reference for many currently observed coins; not causal, predictive or tradable evidence.",
        },
        "mature_alt_lead_lag": {
            "conclusion": mature["conclusion"],
            "mean_bps": mature["configs"][0]["primary"]["mean_bps"],
            "ci_bps": [
                mature["configs"][0]["primary"]["ci_low_bps"],
                mature["configs"][0]["primary"]["ci_high_bps"],
            ],
            "btc_sign_baseline_bps": mature["configs"][0]["baselines"]["btc_sign"]["mean_bps"],
            "own_sign_baseline_bps": mature["configs"][0]["baselines"]["own_return_sign"]["mean_bps"],
            "economic_release_floor_bps": 12,
        },
        "mid_activity_alt_lead_lag": {
            "conclusion": mid["conclusion"],
            "mean_bps": mid["configs"][0]["primary"]["mean_bps"],
            "ci_bps": [
                mid["configs"][0]["primary"]["ci_low_bps"],
                mid["configs"][0]["primary"]["ci_high_bps"],
            ],
            "own_sign_baseline_bps": mid["configs"][0]["baselines"]["own_return_sign"]["mean_bps"],
            "extra_5m_latency_bps": next(
                item for item in mid["configs"] if item["config"]["name"] == "extra_5m_latency"
            )["primary"]["mean_bps"],
            "economic_release_floor_bps": 12,
        },
        "slow_residual_reversal": {
            "conclusion": residual["conclusion"],
            "mean_bps": residual["configs"][0]["primary"]["mean_bps"],
            "median_bps": residual["configs"][0]["primary"]["median_bps"],
            "ci_bps": [
                residual["configs"][0]["primary"]["ci_low_bps"],
                residual["configs"][0]["primary"]["ci_high_bps"],
            ],
            "favorable_paired_cost_bps": residual["configs"][0]["paired_round_trip_cost_floor_bps"]["favorable_mean"],
            "base_paired_cost_bps": residual["configs"][0]["paired_round_trip_cost_floor_bps"]["base_mean"],
        },
        "legacy_strategy_context": {
            name: conclusion_of(document) for name, document in legacy.items()
        },
    }

    output = {
        "audit_date": "2026-07-21",
        "baseline_commit": baseline_commit,
        "formal_strategy": {
            "id": strategy_id.group(1),
            "version": strategy_version.group(1),
        },
        "validated_inputs": validated,
        "product_input_drift": product_input_drift,
        "data_reuse": {
            "unique_official_monthly_zip_files": len(unique_files),
            "unique_zip_bytes": sum(unique_files.values()),
            "large_data_root": DATA_ROOT.as_posix(),
        },
        "evidence": evidence,
        "frontier": [
            {
                "direction": "direct BTC-to-alt lead-lag on mature/high activity",
                "disposition": "CLOSED_DOES_NOT_SUPPORT",
                "reopen_only_with": "new period/venue or materially better verified latency/cost",
            },
            {
                "direction": "direct BTC-to-alt lead-lag on mid activity",
                "disposition": "CLOSED_DOES_NOT_SUPPORT",
                "reopen_only_with": "point-in-time historical spread/depth and a new untouched test",
            },
            {
                "direction": "lower-activity/new-coin 1m lead-lag",
                "disposition": "DO_NOT_START_UNDER_CURRENT_DATA_AND_RISK_BOUNDARY",
                "reopen_only_with": "L1/L2 execution evidence, delisting/integrity model and owner-approved scope",
            },
            {
                "direction": "BTC-neutral residual mean reversion",
                "disposition": "CLOSED_DOES_NOT_SUPPORT_FOR_FIXED_SIMPLE_RULE",
                "reopen_only_with": "independent structural relation rather than selected sign/symbol/window",
            },
            {
                "direction": "correlation/dispersion as sizing or risk state",
                "disposition": "DEFER_RISK_MODEL_NOT_STANDALONE_ALPHA",
                "reopen_only_with": "an owner-selected multi-asset strategy requiring the risk model",
            },
            {
                "direction": "causal buyer/order-flow identity",
                "disposition": "CANNOT_DETERMINE_FROM_OHLCV",
                "reopen_only_with": "trade/order-flow/cross-venue data and an identification design",
            },
            {
                "direction": "funding/cash-carry",
                "disposition": "SEPARATE_SUPPORTED_MECHANISM_NOT_BTC_CORRELATION_ALPHA",
                "reopen_only_with": "its own funding, execution and current-regime review",
            },
        ],
        "decision": {
            "new_btc_correlation_strategy_candidate": False,
            "continue_parameter_or_subgroup_search": False,
            "change_product_or_capital_state": False,
            "current_scope_substantially_covered": True,
        },
        "conclusion": "DOES_NOT_SUPPORT",
        "limitations": [
            "Does not rule out future regimes, lower-activity one-minute effects, cross-venue effects or order-flow alpha.",
            "The 2024 fixed-survivor Binance sample is not a historical point-in-time whole-market universe.",
            "OHLCV cannot identify who bought, causal motives, spread/depth, funding, fills, margin or liquidation.",
            "Supported carry evidence is a different economic mechanism and must not be counted as correlation alpha.",
        ],
    }
    OUTPUT.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS", "output": str(OUTPUT), "conclusion": output["conclusion"], "unique_files": len(unique_files), "unique_bytes": sum(unique_files.values())}, indent=2))


if __name__ == "__main__":
    main()
