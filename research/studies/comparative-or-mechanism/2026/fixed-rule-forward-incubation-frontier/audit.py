from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
EVIDENCE = {
    "ppc_checkpoint": (
        "research/studies/strategy-candidate/2026/price-path-continuity-weekly-winner-long/checkpoint.json",
        "bb92d5cf079117805d433fe93ddce38a6f1102bd25dfcb2c13949f0de44ec0f6",
    ),
    "ppc_results": (
        "research/studies/strategy-candidate/2026/price-path-continuity-weekly-winner-long/results.json",
        "823ba93c045d307aeb954832ead508333df8712bf32c7492dc95325dba7e89d0",
    ),
    "ppc_gate": (
        "research/studies/strategy-candidate/2026/price-path-continuity-weekly-winner-long/development_gate.json",
        "e7b85bd13fc524c3fe5610feae25e36c8b2a1c9aa3736ca0c502d9cc9d401616",
    ),
    "ctrend_checkpoint": (
        "research/studies/strategy-candidate/2026/ctrend-weekly-top-quintile-one-shot-long/checkpoint.json",
        "594370293434c77da46206fdf183c4dac1763b53ed1faab26bc87f0ba04f2724",
    ),
    "ctrend_results": (
        "research/studies/strategy-candidate/2026/ctrend-weekly-top-quintile-one-shot-long/results.json",
        "8d8b0a953f0a4a3a6fec36bf647bc5aeb3a5b7c78d2c4f38f5eb35b8a2b04a6b",
    ),
    "highvol_checkpoint": (
        "research/studies/strategy-candidate/2026/high-volatility-monthly-one-shot-short/checkpoint.json",
        "25753a41577b4ee5a2de48526a54d19b00d036ae0ed019076f1c5e87ad044730",
    ),
    "highvol_results": (
        "research/studies/strategy-candidate/2026/high-volatility-monthly-one-shot-short/results.json",
        "3f28b3ed2815c8e87c16a911e3500d6e54855bf254b4c81c61f7c3807de10e29",
    ),
    "ppc_power_checkpoint": (
        "research/studies/comparative-or-mechanism/2026/ppc-forward-gate-power/checkpoint.json",
        "2cabc1c65d44fc1b71c8a63130e9766796adef9c34f72af4bab577f59d72723e",
    ),
    "ppc_power_results": (
        "research/studies/comparative-or-mechanism/2026/ppc-forward-gate-power/results.json",
        "e4bb2fadde5e1011ce264bb5de0b119ce4bce98a72eda19a41fe10318792813b",
    ),
    "ppc_power_validation": (
        "research/studies/comparative-or-mechanism/2026/ppc-forward-gate-power/validation.json",
        "528f8c9760dd845895403478a770e7d1dad0c3b28309ac0ca1f00c29d2fdc05c",
    ),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def canonical(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(raw).hexdigest()


def write_json(path: Path, value: dict[str, Any]) -> None:
    payload = dict(value)
    payload["content_digest"] = canonical(payload)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def command_audit(_args: argparse.Namespace) -> None:
    identities: list[dict[str, str]] = []
    for name, (relative, expected) in EVIDENCE.items():
        path = ROOT / relative
        actual = sha256(path)
        if actual != expected:
            raise RuntimeError(f"evidence identity mismatch: {name}: {actual}")
        identities.append({"name": name, "path": relative, "sha256": actual})

    ppc_checkpoint = read_json(ROOT / EVIDENCE["ppc_checkpoint"][0])
    ppc_results = read_json(ROOT / EVIDENCE["ppc_results"][0])
    ctrend_results = read_json(ROOT / EVIDENCE["ctrend_results"][0])
    highvol_results = read_json(ROOT / EVIDENCE["highvol_results"][0])
    ppc_power = read_json(ROOT / EVIDENCE["ppc_power_results"][0])
    audit = {
        "as_of": "2026-07-22",
        "baseline_commit": "0bdfeffa616260cebd2d2188ddc8deb9e85c77f4",
        "research_kind": "COMPARATIVE_OR_MECHANISM",
        "question": "Which fixed positive-but-insufficient candidates merit genuinely forward incubation?",
        "conclusion": "INSUFFICIENT_EVIDENCE",
        "core_qualification_ready": 0,
        "active_forward_incubations": 1,
        "candidates": [
            {
                "id": ppc_checkpoint["configuration"]["strategy_id"],
                "status": "FORWARD_INCUBATE",
                "historical_conclusion": ppc_results["conclusion"],
                "rule_change_allowed": False,
                "first_eligible_entry_utc": "2026-07-27T00:00:00Z",
                "minimum_eligible_weeks": 26,
                "twenty_sixth_entry_utc": "2027-01-18T00:00:00Z",
                "first_checkpoint_complete_utc": "2027-01-25T00:00:00Z",
                "earliest_complete_decision_utc": None,
                "positive_gate_decision_possible_at_first_checkpoint": True,
                "power_calibration_conclusion": ppc_power["conclusion"],
                "power_if_true_net_edge_is_50bp_per_eligible_week": ppc_power["primary_26_weeks"]["joint_power"],
                "null_joint_false_positive": ppc_power["primary_26_weeks"]["null_joint_false_positive"],
                "maturity_caveat": "No-action or ineligible weeks delay the first checkpoint; at least two market states are also required. Exact power calibration shows a non-pass at 26 weeks is usually inconclusive rather than evidence of no edge.",
                "reason": "simple weekly mapping and positive-but-uncertain economics justify retaining unchanged observations, but 26-week exact joint power is only 5.92% for a true 50 bp weekly net edge; this is a first checkpoint, not a promised complete decision",
            },
            {
                "id": "RESEARCH_CTREND_TOP_QUINTILE_WEEKLY_LONG",
                "status": "RETAIN_NOT_ACTIVE",
                "historical_conclusion": ctrend_results["conclusion"],
                "reason": "19.2% model-failure rate and concentration make complexity, not elapsed time, the primary defect",
            },
            {
                "id": "RESEARCH_PERP_VOL90_TOP3_MONTHLY_ONE_SHOT_SHORT_0P25X_V1",
                "status": "RETAIN_NOT_ACTIVE",
                "historical_conclusion": highvol_results["conclusion"],
                "reason": "all three frozen neighbors negative; monthly sample is slow and exact-slice short risk is high",
            },
        ],
        "observation_policy": {
            "store_rows_before_maturity": True,
            "peek_or_change_rule": False,
            "raw_data": "official public Binance responses outside Git with manifest identities",
            "derived_data": "all eligible/no-action decisions and costs retained in Git at replay time",
            "scheduler_or_platform": False,
            "product_data_or_runtime": False,
        },
        "next_decision": "Collect the frozen PPC observations without peeking. Do not interpret them before the 26th eligible-week exit. At the first checkpoint a full positive gate may provide useful evidence, but a non-pass normally remains insufficient because exact 50 bp joint power is only 5.92%; no later decision date is currently justified by an exact power calculation. Continue historical work only for an independent mechanism.",
        "product_effects": "NONE",
        "evidence_identities": identities,
        "audit_py_sha256": sha256(Path(__file__)),
    }
    write_json(HERE / "audit.json", audit)
    output = read_json(HERE / "audit.json")
    validation = {
        "status": "PASS",
        "audit_content_digest_valid": output["content_digest"] == canonical({key: value for key, value in output.items() if key != "content_digest"}),
        "evidence_files_checked": len(identities),
        "active_forward_incubations": output["active_forward_incubations"],
        "core_qualification_ready": output["core_qualification_ready"],
    }
    if not validation["audit_content_digest_valid"]:
        raise RuntimeError("audit digest invalid")
    write_json(HERE / "validation.json", validation)
    print(json.dumps({
        "conclusion": output["conclusion"], "active": 1, "ready": 0,
        "evidence": len(identities), "validation": "PASS",
    }))


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Audit the fixed-rule forward-incubation frontier")
    sub = root.add_subparsers(dest="command", required=True)
    sub.add_parser("audit").set_defaults(func=command_audit)
    return root


if __name__ == "__main__":
    arguments = parser().parse_args()
    arguments.func(arguments)
