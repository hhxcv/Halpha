from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tools.qualification.probe_binance_demo_clients import _write_evidence


EXPECTED_FULL_NON_MATRIX_ERRORS = {"TP_PARTIAL_POSITION_EXIT_NOT_OBSERVED"}


def _emergency_unused(evidence: dict[str, object]) -> bool:
    emergency = evidence.get("emergency_cleanup")
    return isinstance(emergency, dict) and not any(bool(value) for value in emergency.values())


def _evaluate(
    full: dict[str, object],
    partial: dict[str, object],
) -> dict[str, object]:
    errors: list[str] = []
    full_errors = set(full.get("errors", []))
    stable = full.get("simultaneous_topology", {})
    explicit_exit = full.get("explicit_market_exit", {})
    no_reverse = full.get("post_exit_no_reverse", {})
    sibling_cleanup = full.get("sibling_cleanup", {})
    race = full.get("stop_tp_race", {})
    partial_exit = partial.get("tp_partial_position_exit", {})
    remainder_exit = partial.get("partial_episode_remainder_exit", {})
    partial_cleanup = partial.get("partial_episode_sibling_cleanup", {})

    stable_checks = {
        "full_responsibility_cleared": full.get("responsibility_cleared") is True,
        "full_only_unrelated_price_timeout_error": (
            full_errors == EXPECTED_FULL_NON_MATRIX_ERRORS
        ),
        "stable_four_profiles_open": stable.get("open_profile_count") == 4,
        "stable_protection_covers_position": (
            stable.get("position_quantity") in {"0.004", "0.0040"}
            and stable.get("protection_quantity") == "0.004"
        ),
        "stable_tp_covers_position": stable.get("take_profit_quantity") == "0.004",
        "stable_combined_quantity_accepted": (
            stable.get("combined_reduce_only_quantity_exceeds_position_without_rejection")
            is True
        ),
        "stable_close_position_unused": stable.get("close_position_used") is False,
        "stable_explicit_exit_flat": explicit_exit.get("position_after_exit") == "0",
        "stable_no_reverse": no_reverse.get("all_flat") is True,
        "stable_siblings_cleared": sibling_cleanup.get("remaining_owned_algo_profiles") == [],
        "full_emergency_unused": _emergency_unused(full),
        "full_secret_clean": full.get("secret_scan", {}).get("raw_credential_found") is False,
    }
    race_checks = {
        "race_both_open_before_trigger": race.get("both_orders_open_before_trigger") is True,
        "race_trigger_observed": race.get("trigger_timeout") is False,
        "race_exactly_one_finished": race.get("finished_profile_count") == 1,
        "race_flat": race.get("position_after_race") == "0",
        "race_no_reverse": race.get("all_no_reverse_samples_flat") is True,
        "race_sibling_cleared": race.get("sibling_cleanup_remaining_profiles") == [],
        "race_write_not_retried": race.get("write_retried") is False,
    }
    partial_checks = {
        "partial_probe_qualified": partial.get("status") == "QUALIFIED",
        "partial_responsibility_cleared": partial.get("responsibility_cleared") is True,
        "partial_all_profiles_open": (
            partial_exit.get("all_stop_and_tp_profiles_open_before_trigger") is True
        ),
        "partial_exact_half_exit": (
            partial_exit.get("starting_position") == "0.004"
            and partial_exit.get("tp_explicit_quantity") == "0.002"
            and partial_exit.get("position_after_tp") in {"0.002", "0.0020"}
        ),
        "partial_siblings_remain_open": (
            partial_exit.get("stop_and_tp2_still_open_after_partial_exit") is True
        ),
        "partial_tp_finished": partial_exit.get("tp_terminal_status") == "FINISHED",
        "partial_same_identity_read_retry": (
            partial_exit.get("same_uuid32_read_retry_only") is True
            and partial_exit.get("write_retried") is False
        ),
        "partial_remainder_flat_without_reverse": remainder_exit.get("all_flat") is True,
        "partial_siblings_cleared": (
            partial_cleanup.get("remaining_owned_algo_profiles") == []
        ),
        "partial_emergency_unused": _emergency_unused(partial),
        "partial_secret_clean": partial.get("secret_scan", {}).get("raw_credential_found")
        is False,
    }
    checks = {**stable_checks, **partial_checks, **race_checks}
    errors.extend(name for name, passed in checks.items() if not passed)
    return {
        "stage": "B00_REDUCE_ONLY_COMBINED_EVIDENCE",
        "scope": "B00_ISOLATED_QUALIFICATION_ONLY",
        "source_runs": {
            "stable_and_race": "RESPONSIBILITY_CLEARED_WITH_UNRELATED_TP_PRICE_TIMEOUT",
            "partial_tp": partial.get("status"),
        },
        "checks": checks,
        "normal_write_path": "ONE_NAUTILUS_STRATEGY_PER_RUN",
        "automatic_write_retry": "DISABLED",
        "close_position_used": False,
        "private_patch_used": False,
        "second_binance_write_adapter_used": False,
        "actual_client_order_ids_persisted": False,
        "errors": errors,
        "status": "QUALIFIED" if not errors else "REJECTED",
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Combine independent B00 reduce-only Demo matrix evidence.",
    )
    parser.add_argument("--full-evidence", type=Path, required=True)
    parser.add_argument("--partial-evidence", type=Path, required=True)
    parser.add_argument("--evidence-path", type=Path)
    args = parser.parse_args()
    full = json.loads(args.full_evidence.read_text(encoding="utf-8"))
    partial = json.loads(args.partial_evidence.read_text(encoding="utf-8"))
    evidence = _evaluate(full, partial)
    _write_evidence(args.evidence_path, evidence)
    return 0 if evidence["status"] == "QUALIFIED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
