from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime
from datetime import timezone
from pathlib import Path

import yaml


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tools.qualification.probe_binance_demo_clients import _write_evidence


DEMO_EVIDENCE_ROOT = REPOSITORY_ROOT / "build" / "qualification" / "binance-demo"
DEFAULT_EVIDENCE_PATH = (
    REPOSITORY_ROOT / "build" / "qualification" / "b00-qualification-latest.json"
)
WHEEL_PATH = (
    REPOSITORY_ROOT
    / "build"
    / "qualification"
    / "wheels"
    / "nautilus_trader-1.230.0-cp313-cp313-win_amd64.whl"
)
EXPECTED_PROFILES = {
    "BINANCE_DEMO",
    "BINANCE_LIVE_READ_ONLY",
    "BINANCE_LIVE_WRITE",
}
EXPECTED_INSTRUMENTS = {
    "BTCUSDT-PERP.BINANCE",
    "ETHUSDT-PERP.BINANCE",
}
ONLINE_EVIDENCE_FILES = {
    "funding": "funding-income-latest.json",
    "market": "market-data-combined-latest.json",
    "official_15m": "official-15m-crosscheck-latest.json",
    "order_read": "order-read-matrix-latest.json",
    "order_roundtrip": "order-roundtrip-latest.json",
    "restart": "restart-recovery-latest.json",
    "missing_position": "missing-position-recovery-latest.json",
    "reduce_only": "reduce-only-combined-latest.json",
    "algo_query": "algo-query-matrix-direct.evidence.json",
}


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        check=False,
        encoding="utf-8",
        errors="replace",
        text=True,
    )


def _run_json_probe(*arguments: str) -> dict[str, object]:
    result = _run([sys.executable, *arguments])
    try:
        evidence = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        return {
            "status": "PROBE_OUTPUT_INVALID",
            "returncode": result.returncode,
            "error": type(exc).__name__,
        }
    evidence["returncode"] = result.returncode
    return evidence


def _load_evidence(filename: str) -> dict[str, object]:
    path = DEMO_EVIDENCE_ROOT / filename
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "status": "EVIDENCE_UNAVAILABLE",
            "error": type(exc).__name__,
        }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _file_evidence(path: Path, status: object = None) -> dict[str, object]:
    try:
        stat = path.stat()
        relative_path = path.relative_to(REPOSITORY_ROOT).as_posix()
        return {
            "path": relative_path,
            "sha256": _sha256(path),
            "size_bytes": stat.st_size,
            "modified_at_utc": datetime.fromtimestamp(
                stat.st_mtime,
                tz=timezone.utc,
            ).isoformat(),
            "status": status,
        }
    except OSError as exc:
        return {
            "path": str(path),
            "available": False,
            "error": type(exc).__name__,
            "status": status,
        }


def _group(**checks: bool) -> dict[str, object]:
    failed = [name for name, passed in checks.items() if not passed]
    return {
        "checks": checks,
        "failed_checks": failed,
        "status": "QUALIFIED" if not failed else "REJECTED",
    }


def _status_is(evidence: dict[str, object], *expected: str) -> bool:
    return evidence.get("returncode", 0) == 0 and evidence.get("status") in expected


def _actual_account_check(funding: dict[str, object]) -> tuple[bool, dict[str, object]]:
    policy = funding.get("margin_leverage_policy", {})
    symbols = funding.get("symbol_configuration", {})
    symbol_checks: dict[str, bool] = {}
    observed: dict[str, object] = {}
    if isinstance(symbols, dict):
        for symbol, item in symbols.items():
            if not isinstance(item, dict):
                symbol_checks[str(symbol)] = False
                continue
            actual = item.get("actual_leverage")
            effective = item.get("effective_leverage")
            margin_type = item.get("margin_type")
            try:
                expected_effective = min(int(actual), 5)
            except (TypeError, ValueError):
                expected_effective = None
            symbol_checks[str(symbol)] = (
                margin_type in {"CROSSED", "ISOLATED"}
                and expected_effective is not None
                and expected_effective > 0
                and effective == expected_effective
            )
            observed[str(symbol)] = {
                "actual_margin_mode": margin_type,
                "actual_leverage": actual,
                "effective_leverage": effective,
            }
    accepted = (
        funding.get("position_mode") == "ONE_WAY"
        and funding.get("single_asset_mode") == "SINGLE_ASSET"
        and policy.get("effective_leverage_formula") == "min(actual_leverage, 5)"
        and policy.get("actual_leverage_is_observed_not_modified") is True
        and policy.get("actual_margin_mode_is_observed_not_modified") is True
        and policy.get("crossed_or_actual_leverage_above_5_is_not_a_blocker") is True
        and set(symbol_checks) == {"BTCUSDT", "ETHUSDT"}
        and all(symbol_checks.values())
    )
    return accepted, {
        "observed": observed,
        "accepted_actual_modes": ["CROSSED", "ISOLATED"],
        "effective_leverage_formula": "min(actual_leverage, 5)",
        "account_setting_mutation": False,
        "blocks_b00": not accepted,
    }


def _evaluate() -> dict[str, object]:
    plan_path = (
        REPOSITORY_ROOT
        / "docs"
        / "L4"
        / "HALPHA-PLAN-001-current-construction-plan.yaml"
    )
    plan = yaml.safe_load(
        plan_path.read_text(encoding="utf-8"),
    )
    accepted_b00_status = plan.get("dependency_qualification_gate", {}).get(
        "status",
        "UNKNOWN",
    )
    accepted_d00_status = plan.get("design_formalization_gate", {}).get(
        "status",
        "UNKNOWN",
    )
    offline = {
        "venv": _run_json_probe("tools/qualification/verify_venv.py"),
        "components": _run_json_probe("tools/qualification/verify_components.py"),
        "artifact": _run_json_probe(
            "tools/qualification/verify_nautilus_artifact.py",
            "--wheel",
            str(WHEEL_PATH),
        ),
        "windows": _run_json_probe("tools/qualification/probe_windows_primitives.py"),
        "lifecycle": _run_json_probe("tools/qualification/probe_nautilus_lifecycle.py"),
        "profiles": _run_json_probe(
            "tools/qualification/probe_binance_demo_clients.py",
            "--config-only",
        ),
        "bars": _run_json_probe("tools/qualification/probe_bar_semantics.py"),
        "backtest": _run_json_probe("tools/qualification/probe_backtest_stack.py"),
        "proposal_parity": _run_json_probe(
            "tools/qualification/probe_strategy_proposal_parity.py",
        ),
        "order_profiles": _run_json_probe(
            "tools/qualification/probe_order_profiles.py",
        ),
        "order_failure": _run_json_probe(
            "tools/qualification/probe_order_failure_semantics.py",
        ),
    }
    online = {
        name: _load_evidence(filename)
        for name, filename in ONLINE_EVIDENCE_FILES.items()
    }

    pip_check = _run([sys.executable, "-m", "pip", "check"])
    ignored_venv = _run(["git", "check-ignore", "-q", ".venv/pyvenv.cfg"])
    tracked_venv = _run(["git", "ls-files", ".venv"])
    lock_text = (REPOSITORY_ROOT / "requirements" / "b00.txt").read_text(
        encoding="utf-8",
    )
    input_text = (REPOSITORY_ROOT / "requirements" / "b00.in").read_text(
        encoding="utf-8",
    )

    funding = online["funding"]
    account_accepted, account_evaluation = _actual_account_check(funding)
    profile_isolation = offline["profiles"].get("profile_isolation", {})
    profiles = profile_isolation.get("profiles", {})
    config = offline["profiles"].get("configuration", {})
    provider = config.get("instrument_provider", {})
    topology = config.get("topology", {})
    execution_engine = config.get("execution_engine", {})
    failure_semantics = offline["order_failure"].get(
        "required_halpha_interpretation",
        {},
    )
    funding_read = funding.get("funding_income_read", {})
    funding_contract = funding_read.get("field_contract_qualification", {})
    commission = funding.get("commission_rate_read", {})
    api_permissions = funding.get("api_permissions", {})
    order_read = online["order_read"]
    missing = online["missing_position"]
    reduce_only = online["reduce_only"]
    backtest = offline["backtest"]

    required_outputs = {
        "01_environment_and_venv": _group(
            exact_venv=_status_is(offline["venv"], "QUALIFIED"),
            pinned_components=_status_is(offline["components"], "QUALIFIED"),
            dependency_integrity=pip_check.returncode == 0,
            venv_ignored=ignored_venv.returncode == 0,
            venv_untracked=not tracked_venv.stdout.strip(),
        ),
        "02_artifact_lock_and_license": _group(
            artifact=_status_is(offline["artifact"], "QUALIFIED"),
            official_index_only=(
                "--index-url=https://pypi.org/simple" in lock_text
                and "--extra-index-url" not in lock_text
                and "--trusted-host" not in lock_text
            ),
            complete_hash_lock="--hash=sha256:" in lock_text,
            exact_direct_dependencies=all(
                requirement in input_text
                for requirement in (
                    "nautilus-trader==1.230.0",
                    "pandas==2.3.3",
                    "pywin32==312",
                )
            ),
        ),
        "03_windows_and_lifecycle": _group(
            windows_primitives=_status_is(offline["windows"], "QUALIFIED"),
            node_and_controller_lifecycle=_status_is(
                offline["lifecycle"],
                "QUALIFIED",
            ),
        ),
        "04_profile_isolation_and_exact_node_config": _group(
            config_probe=_status_is(offline["profiles"], "QUALIFIED"),
            exact_profiles=set(profiles) == EXPECTED_PROFILES,
            profiles_distinct=profile_isolation.get(
                "providers_distinct_across_profiles",
            )
            is True,
            no_live_write=(
                profiles.get("BINANCE_LIVE_READ_ONLY", {}).get(
                    "write_authorization",
                )
                == "DISABLED_READ_ONLY_PROFILE"
                and profiles.get("BINANCE_LIVE_WRITE", {}).get(
                    "write_authorization",
                )
                == "DISABLED_UNTIL_B05"
            ),
            demo_load_ids=set(provider.get("load_ids", [])) == EXPECTED_INSTRUMENTS,
            provider_shared=provider.get("shared_by_data_and_execution") is True,
            one_node_one_client_pair=(
                topology.get("trading_nodes") == 1
                and topology.get("data_clients") == 1
                and topology.get("execution_clients") == 1
            ),
            no_parallel_infrastructure=all(
                topology.get(name) is None
                for name in ("event_store", "order_emulator", "persistent_cache", "redis")
            ),
            actual_account_configuration_accepted=account_accepted,
        ),
        "05_market_data_and_reconnect": _group(
            combined_market_evidence=_status_is(online["market"], "QUALIFIED"),
            official_15m_crosscheck=_status_is(
                online["official_15m"],
                "QUALIFIED",
            ),
            one_runtime_bar_source=online["market"].get(
                "runtime_bar_sources_per_instrument",
            )
            == 1,
        ),
        "06_order_unknown_and_restart": _group(
            fixed_failure_semantics=_status_is(
                offline["order_failure"],
                "QUALIFIED_COMPONENT_SEMANTICS",
            ),
            algo_identity_read_matrix=_status_is(
                online["algo_query"],
                "QUALIFIED_READ_MATRIX",
            ),
            restart_query_cancel_terminal=_status_is(
                online["restart"],
                "QUALIFIED",
            ),
        ),
        "07_execution_config_and_no_synthetic_terminal": _group(
            exact_check_intervals=(
                execution_engine.get("inflight_check_interval_ms") == 0
                and execution_engine.get("open_check_interval_secs") == 10.0
                and execution_engine.get("open_check_open_only") is True
            ),
            submitted_unknown_preserved=(
                failure_semantics.get("write_timeout_or_crash") == "SUBMITTED_UNKNOWN"
                and failure_semantics.get("next_action")
                == "QUERY_ORIGINAL_UUID32_ONLY"
                and failure_semantics.get(
                    "technical_synthetic_rejected_is_product_terminal",
                )
                is False
            ),
            no_automatic_resubmit=failure_semantics.get(
                "automatic_resubmit_same_identity",
            )
            is False,
        ),
        "08_missing_position_recovery": _group(
            recovery_probe=_status_is(missing, "QUALIFIED"),
            generated_projection_not_product_fact=missing.get(
                "generated_technical_cache",
                {},
            ).get("projection_is_product_fact")
            is False,
            reduce_only_exit_bounded=missing.get(
                "risk_engine_reduce_only_exit",
                {},
            ).get("request_not_above_recovered_position")
            is True,
            no_write_retry=missing.get("risk_engine_reduce_only_exit", {}).get(
                "write_retried",
            )
            is False,
        ),
        "09_bars_indicators_and_backtest": _group(
            bars_and_indicators=_status_is(offline["bars"], "QUALIFIED"),
            backtest_actual_fill=_status_is(backtest, "QUALIFIED"),
            no_product_runtime_or_records=backtest.get(
                "product_runtime_or_records_created",
            )
            is False,
        ),
        "10_backtest_stack_and_funding_disclosure": _group(
            exact_public_stack=_status_is(backtest, "QUALIFIED"),
            funding_not_modeled=backtest.get("funding_model") == "NOT_MODELED",
            funding_not_injected=backtest.get("funding_data_injected") is False,
        ),
        "11_strategy_proposal_parity": _group(
            live_backtest_parity=_status_is(
                offline["proposal_parity"],
                "QUALIFIED",
            ),
            no_product_runtime_or_records=offline["proposal_parity"].get(
                "checks",
                {},
            ).get("no_product_runtime_or_records")
            is True,
        ),
        "12_order_profiles_and_roundtrip": _group(
            eight_profiles=_status_is(offline["order_profiles"], "QUALIFIED")
            and offline["order_profiles"].get("profile_count") == 8,
            actual_demo_roundtrip=_status_is(
                online["order_roundtrip"],
                "QUALIFIED",
            ),
            identities_not_persisted=online["order_roundtrip"].get(
                "actual_client_order_ids_persisted",
            )
            is False,
        ),
        "13_reduce_only_topology": _group(
            combined_demo_matrix=_status_is(reduce_only, "QUALIFIED"),
            all_matrix_checks=all(reduce_only.get("checks", {}).values()),
            no_close_position=reduce_only.get("close_position_used") is False,
            no_private_patch=reduce_only.get("private_patch_used") is False,
            no_second_write_adapter=reduce_only.get(
                "second_binance_write_adapter_used",
            )
            is False,
        ),
        "14_read_only_get_supplement": _group(
            funding_and_commission=_status_is(funding, "QUALIFIED"),
            order_history=_status_is(order_read, "QUALIFIED"),
            get_only=(
                funding.get("read_only_get_supplement", {}).get("method") == "GET"
                and commission.get("method") == "GET"
                and commission.get("write_methods_exposed") is False
                and order_read.get("read_only") is True
                and order_read.get("write_method_called") is False
            ),
            funding_contract=(
                funding_read.get("identity") == "(incomeType,tranId)"
                and funding_contract.get("nonempty_decimal_golden_vector") is True
                and funding_contract.get("malformed_payload_rejected") is True
                and funding_contract.get("synthetic_record_emitted_as_venue_fact")
                is False
            ),
            short_page_pagination=all(
                details.get(kind, {}).get("short_page_terminates") is True
                for details in order_read.get("instruments", {}).values()
                for kind in ("ordinary", "algorithm")
            ),
            demo_withdrawal_surface_absent=(
                api_permissions.get("api_key_withdrawal_permission_readback")
                == "NOT_EXPOSED_BY_USDM_API"
                and api_permissions.get("b00_get_whitelist_exposes_withdrawal_route")
                is False
                and api_permissions.get("withdrawal_capability_in_selected_profile")
                == "OUTSIDE_BINANCE_USDM_DEMO_PROFILE"
            ),
            no_unknowns=funding.get("unknowns") == [],
        ),
    }
    failed_outputs = [
        output_id
        for output_id, result in required_outputs.items()
        if result["status"] != "QUALIFIED"
    ]

    source_statuses = {
        "offline": {name: item.get("status") for name, item in offline.items()},
        "online": {name: item.get("status") for name, item in online.items()},
    }
    source_files = {
        name: _file_evidence(
            DEMO_EVIDENCE_ROOT / filename,
            online[name].get("status"),
        )
        for name, filename in ONLINE_EVIDENCE_FILES.items()
    }
    return {
        "stage": "B00_QUALIFICATION_SUMMARY",
        "scope": "B00_ISOLATED_QUALIFICATION_ONLY",
        "normative": False,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "authorized_package": "B00",
        "required_output_count": len(required_outputs),
        "required_outputs": required_outputs,
        "account_configuration_evaluation": account_evaluation,
        "accepted_plan_state": {
            "B00": accepted_b00_status,
            "D00": accepted_d00_status,
            "source": _file_evidence(plan_path),
        },
        "source_evidence_statuses": source_statuses,
        "source_evidence_files": source_files,
        "qualified_artifact": {
            "wheel_filename": offline["artifact"].get("wheel_filename"),
            "wheel_sha256": offline["artifact"].get("wheel_sha256"),
            "wheel_tag": offline["artifact"].get("wheel_tag"),
            "source_tag_object_sha": offline["artifact"].get(
                "source_tag_object_sha",
            ),
            "source_commit_sha": offline["artifact"].get("source_commit_sha"),
        },
        "constraints": {
            "product_runtime_or_records_created": False,
            "live_connection_attempted": False,
            "live_write_enabled": False,
            "automatic_write_retry": "DISABLED",
            "second_binance_write_adapter_used": False,
            "private_patch_used": False,
            "close_position_used": False,
            "proxy_address_or_port_persisted": False,
        },
        "construction_after_b00": (
            "BLOCKED_BY_D00_UPSTREAM_CONFLICT"
            if accepted_d00_status != "ALIGNED"
            else "GOVERNED_BY_ACCEPTED_CONSTRUCTION_PLAN"
        ),
        "normative_plan_update_required": accepted_b00_status != "QUALIFIED",
        "normative_handoff": {
            "target": (
                "docs/L4/HALPHA-PLAN-001-current-construction-plan.yaml"
            ),
            "recommended_b00_status_from_local_evidence": "QUALIFIED",
            "recommended_qualification_progress": (
                "QUALIFIED_ALL_REQUIRED_OUTPUTS"
            ),
            "preserve_d00_status": accepted_d00_status,
            "preserve_runtime_real_write_gate": "CLOSED",
            "do_not_authorize_b01_until_d00_aligned": True,
            "document_owner_review_required": True,
        },
        "errors": failed_outputs,
        "status": "QUALIFIED" if not failed_outputs else "REJECTED",
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Summarize all accepted L4 B00 qualification outputs.",
    )
    parser.add_argument("--evidence-path", type=Path, default=DEFAULT_EVIDENCE_PATH)
    args = parser.parse_args()
    evidence = _evaluate()
    _write_evidence(args.evidence_path, evidence)
    return 0 if evidence["status"] == "QUALIFIED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
