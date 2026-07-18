from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tools.qualification.probe_binance_demo_clients import _write_evidence
from tools.qualification.probe_reconnect_contract import _evaluate_reconnect_contract
from tools.qualification.probe_websocket_reconnect_blackbox import _evaluate_black_box


EXPECTED_INSTRUMENTS = {
    "BTCUSDT-PERP.BINANCE",
    "ETHUSDT-PERP.BINANCE",
}
STALE_PERMISSION_UNKNOWN = "API_KEY_WITHDRAWAL_PERMISSION_REQUIRES_SEPARATE_READ_ONLY_EVIDENCE"


def _callback_order_is_valid(sequence: list[str], instrument_id: str) -> bool:
    expected = [
        f"REGISTER_INDICATORS:{instrument_id}",
        f"REQUEST_HISTORY:{instrument_id}",
        f"CALLBACK_BEGIN:{instrument_id}",
        f"SUBSCRIBE_SOURCE:{instrument_id}",
        f"SUBSCRIBE_TARGET:{instrument_id}",
        f"SUBSCRIBE_MARK:{instrument_id}",
        f"SUBSCRIBE_QUOTE:{instrument_id}",
        f"CALLBACK_END:{instrument_id}",
    ]
    try:
        indexes = [sequence.index(value) for value in expected]
    except ValueError:
        return False
    return indexes == sorted(indexes) and len(set(indexes)) == len(indexes)


def _market_run_checks(evidence: dict[str, object], label: str) -> dict[str, bool]:
    market = evidence.get("market_data", {})
    request = market.get("request", {})
    subscriptions = market.get("subscriptions", {})
    instruments = market.get("instruments", {})
    sequence = market.get("callback_sequence", [])
    checks: dict[str, bool] = {
        f"{label}_no_errors": evidence.get("errors") == [],
        f"{label}_no_blockers": evidence.get("blockers") == [],
        f"{label}_only_stale_permission_unknown": set(evidence.get("unknowns", []))
        <= {STALE_PERMISSION_UNKNOWN},
        f"{label}_node_stopped": evidence.get("node_stopped") is True,
        f"{label}_node_disposed": evidence.get("node_disposed") is True,
        f"{label}_secret_clean": evidence.get("secret_scan", {}).get(
            "raw_credential_found",
        )
        is False,
        f"{label}_two_requests_completed": market.get("completed_request_count") == 2,
        f"{label}_instrument_set": set(instruments) == EXPECTED_INSTRUMENTS,
        f"{label}_request_72h_limit_1500": (
            request.get("duration_hours") == 72
            and request.get("limit") == 1500
            and request.get("include_external_data") is True
            and request.get("update_subscriptions") is True
            and request.get("update_catalog") is False
            and request.get("custom_time_range_segmentation") is False
        ),
        f"{label}_one_underlying_source": subscriptions.get(
            "one_underlying_source_bar_per_instrument",
        )
        is True,
        f"{label}_engine_has_source_and_target": len(
            subscriptions.get("data_engine_bars", []),
        )
        == 4,
        f"{label}_client_has_only_source": len(
            subscriptions.get("data_client_bars", []),
        )
        == 2,
    }
    for instrument_id in sorted(EXPECTED_INSTRUMENTS):
        item = instruments.get(instrument_id, {})
        prefix = f"{label}_{instrument_id.split('-')[0].lower()}"
        checks.update(
            {
                f"{prefix}_callback_order": _callback_order_is_valid(
                    sequence,
                    instrument_id,
                ),
                f"{prefix}_source_continuous": item.get(
                    "historical_source_recent_15_continuous",
                )
                is True,
                f"{prefix}_target_continuous": item.get(
                    "historical_target_recent_20_continuous",
                )
                is True,
                f"{prefix}_no_source_duplicates": item.get(
                    "historical_source_duplicate_timestamps",
                )
                == 0,
                f"{prefix}_no_target_duplicates": item.get(
                    "historical_target_duplicate_timestamps",
                )
                == 0,
                f"{prefix}_history_live_boundary": item.get(
                    "history_live_source_boundary",
                )
                in {"CONTIGUOUS_NEXT_BAR", "IDENTICAL_REPLAY"},
                f"{prefix}_mark_received": int(item.get("mark_price_count", 0)) > 0,
                f"{prefix}_quote_received": int(item.get("quote_tick_count", 0)) > 0,
                f"{prefix}_bid_ask_same_event": item.get("quote_bid_ask_same_event")
                is True,
                f"{prefix}_donchian_initialized": item.get("donchian_initialized")
                is True,
                f"{prefix}_atr_initialized": item.get("atr_initialized") is True,
            },
        )
    return checks


async def _evaluate(
    first: dict[str, object],
    restart: dict[str, object],
    official: dict[str, object],
    permission: dict[str, object],
) -> dict[str, object]:
    reconnect = await _evaluate_black_box()
    source_contract = _evaluate_reconnect_contract()
    checks = {
        **_market_run_checks(first, "first"),
        **_market_run_checks(restart, "restart"),
        "same_exact_config_digest": first.get("config_digest_sha256")
        == restart.get("config_digest_sha256"),
        "independent_restart_cycle_observed": (
            first.get("market_data", {}).get("request", {}).get("warmup_end")
            != restart.get("market_data", {}).get("request", {}).get("warmup_end")
        ),
        "official_15m_crosscheck_qualified": official.get("status") == "QUALIFIED",
        "official_15m_crosscheck_no_credentials": official.get("credentials_loaded")
        is False,
        "official_15m_crosscheck_not_runtime_source": official.get(
            "runtime_data_source_added",
        )
        is False,
        "demo_permission_evidence_qualified": permission.get("status") == "QUALIFIED",
        "demo_permission_evidence_no_unknowns": permission.get("unknowns") == [],
        "demo_profile_has_no_withdrawal_surface": permission.get(
            "api_permissions",
            {},
        ).get("withdrawal_capability_in_selected_profile")
        == "OUTSIDE_BINANCE_USDM_DEMO_PROFILE",
        "controlled_websocket_reconnect_qualified": reconnect.get("status")
        == "QUALIFIED",
        "fixed_reconnect_source_contract_qualified": source_contract.get("status")
        == "QUALIFIED_FIXED_SOURCE_CONTRACT",
    }
    errors = [name for name, passed in checks.items() if not passed]
    return {
        "stage": "B00_MARKET_DATA_COMBINED_EVIDENCE",
        "scope": "B00_ISOLATED_QUALIFICATION_ONLY",
        "source_runs": {
            "first_market_cycle": first.get("status"),
            "restart_market_cycle": restart.get("status"),
            "stale_source_unknown_superseded_by": permission.get("status"),
            "official_15m_crosscheck": official.get("status"),
            "controlled_websocket_reconnect": reconnect.get("status"),
            "fixed_reconnect_source_contract": source_contract.get("status"),
        },
        "checks": checks,
        "runtime_bar_sources_per_instrument": 1,
        "public_official_15m_sample_persisted_as_runtime_data": False,
        "system_proxy_modified": False,
        "proxy_address_or_port_persisted": False,
        "errors": errors,
        "status": "QUALIFIED" if not errors else "REJECTED",
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Combine B00 market-data, restart, reconnect, and official kline evidence.",
    )
    parser.add_argument("--first-evidence", type=Path, required=True)
    parser.add_argument("--restart-evidence", type=Path, required=True)
    parser.add_argument("--official-evidence", type=Path, required=True)
    parser.add_argument("--permission-evidence", type=Path, required=True)
    parser.add_argument("--evidence-path", type=Path)
    args = parser.parse_args()
    first = json.loads(args.first_evidence.read_text(encoding="utf-8"))
    restart = json.loads(args.restart_evidence.read_text(encoding="utf-8"))
    official = json.loads(args.official_evidence.read_text(encoding="utf-8"))
    permission = json.loads(args.permission_evidence.read_text(encoding="utf-8"))
    evidence = asyncio.run(_evaluate(first, restart, official, permission))
    _write_evidence(args.evidence_path, evidence)
    return 0 if evidence["status"] == "QUALIFIED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
