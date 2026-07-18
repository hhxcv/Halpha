"""Exercise one persisted product ENTRY_LIMIT -> CANCEL round trip on Binance Demo."""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import json
import os
from pathlib import Path
import sys
from threading import Event
from typing import Any
from uuid import uuid4

import keyring
from nautilus_trader.adapters.binance import BINANCE_VENUE
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.objects import Currency


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from halpha.capital.models import (
    ActionCheckInput,
    AuthorityClass,
    EnvironmentKind,
    RiskClass,
    StopCategory,
)
from halpha.configuration import executor_settings, load_settings
from halpha.domain_values import canonical_decimal, content_digest
from halpha.executor.continuity import PostgreSQLExecutorContinuityGuard
from halpha.executor.runtime import ProductExecutorRuntime
from halpha.planning.control_service import ActivationControlService
from halpha.planning.models import ProposedAction, ProposedActionKind
from halpha.planning.repository import PostgreSQLPlanningRepository
from halpha.planning.transitions import ControlIntent
from halpha.user_workbench.commands import ReceiptState, build_command
from halpha.venue_integration.models import ExecutionActionState
from halpha.winvault import executor_secret_resolver
from tools.qualification.verify_b02_database_boundary import (
    _cleanup,
    _connect,
    _create_and_activate,
    _insert_limit,
)


DEFAULT_OUTPUT = ROOT / "build/qualification/b03-product-demo-roundtrip.json"
CONFIG = ROOT / "config/halpha.toml"
LOG_DIRECTORY = ROOT / "build/qualification/runtime/b03-product-demo"


async def _wait_for_action(
    runtime: ProductExecutorRuntime,
    action_id: str,
    states: frozenset[ExecutionActionState],
    *,
    timeout_seconds: float,
) -> Any:
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    while asyncio.get_running_loop().time() < deadline:
        action = runtime.coordinator.get_execution_action(action_id)
        if action.state in states:
            return action
        await asyncio.sleep(0.25)
    raise RuntimeError("PRODUCT_ACTION_STATE_TIMEOUT")


def _scan_logs(api_key: str, api_secret: str) -> tuple[int, bool]:
    scanned = 0
    found = False
    for path in LOG_DIRECTORY.rglob("*") if LOG_DIRECTORY.exists() else ():
        if not path.is_file():
            continue
        scanned += 1
        payload = path.read_bytes()
        found = found or (
            bool(api_key) and api_key.encode() in payload
        ) or (
            bool(api_secret) and api_secret.encode() in payload
        )
    return scanned, found


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    now = datetime.now(UTC)
    environment_id = f"qualification-b03-product-{uuid4()}"
    account_ref = f"qualification-demo-account-{uuid4()}"
    evidence: dict[str, Any] = {
        "stage": "INITIALIZING",
        "environment_kind": "DEMO",
        "authority_class": "DEMO_VALIDATION",
        "profile": "BINANCE_DEMO",
        "venue_write_performed": False,
        "proxy_supplied": bool(os.environ.get("HALPHA_RUNTIME_PROXY_URL")),
        "proxy_value_persisted": False,
        "checks": {},
        "errors": [],
    }
    checks: dict[str, bool] = evidence["checks"]
    errors: list[str] = evidence["errors"]
    app_connection = _connect()
    runtime: ProductExecutorRuntime | None = None
    stop = Event()
    flow_task: asyncio.Task[None] | None = None
    terminal_proven = False
    api_key_value = ""
    api_secret_value = ""
    try:
        settings = load_settings(CONFIG)
        base_view = executor_settings(settings)
        release = base_view.release.model_copy(
            update={"environment_id": environment_id, "account_id": account_ref}
        )
        view = base_view.model_copy(update={"release": release})
        resolver = executor_secret_resolver(keyring.get_keyring(), view)
        database_password = resolver.resolve(view.executor.database_credential_reference)
        api_key = resolver.resolve(view.executor.binance_api_key_reference)
        api_secret = resolver.resolve(view.executor.binance_api_secret_reference)
        api_key_value = api_key.get_secret_value()
        api_secret_value = api_secret.get_secret_value()

        limit_id = str(uuid4())
        with app_connection.transaction():
            _insert_limit(
                app_connection,
                environment_id=environment_id,
                account_ref=account_ref,
                limit_id=limit_id,
                now=now,
            )
            ids = _create_and_activate(
                app_connection,
                environment_id=environment_id,
                account_ref=account_ref,
                limit_id=limit_id,
                now=now,
                instrument_ref="BTCUSDT-PERP",
                limits=("200", "1000", "100"),
            )

        paused = PostgreSQLExecutorContinuityGuard(
            database_name="halpha_demo",
            password=database_password,
            environment_id=environment_id,
        ).pause_open_activations(datetime.now(UTC))
        checks["continuity_pause_precedes_node_start"] = paused == 1
        runtime = ProductExecutorRuntime(
            settings=view,
            database_password=database_password,
            api_key=api_key,
            api_secret=api_secret,
            log_directory=LOG_DIRECTORY,
            proxy_url=os.environ.get("HALPHA_RUNTIME_PROXY_URL"),
        )
        evidence["stage"] = "BUILDING_PRODUCT_RUNTIME"
        runtime.build()

        async def product_flow() -> None:
            nonlocal terminal_proven
            entry_action_id: str | None = None
            try:
                flow_now = datetime.now(UTC)
                with app_connection.transaction():
                    activation = PostgreSQLPlanningRepository(
                        app_connection, environment_id
                    ).get_activation(ids["activation_id"], for_update=True)
                    reconciliation_digest = content_digest(
                        {
                            "environment_id": environment_id,
                            "activation_id": activation.activation_id,
                            "startup_reconciliation_completed": True,
                            "unresolved_action_count": runtime.recovered_action_count,
                        }
                    )
                    command = build_command(
                        command_id=str(uuid4()),
                        environment_id=environment_id,
                        owner_scope="owner-primary",
                        idempotency_key=str(uuid4()),
                        activation_id=activation.activation_id,
                        expected_version=activation.state_version,
                        intent=ControlIntent.RESUME_ACTIVATION,
                        scope={"reason": "B03_PRODUCT_DEMO_QUALIFICATION"},
                        parameters={},
                        submitted_at=flow_now,
                    )
                    receipt = ActivationControlService(
                        app_connection, environment_id
                    ).submit(
                        command,
                        receipt_id=str(uuid4()),
                        stop_state_version_id=str(uuid4()),
                        reconciliation_digest=reconciliation_digest,
                        authorization_current=True,
                        facts_known=True,
                    )
                checks["manual_resume_uses_stable_command"] = (
                    receipt.state is ReceiptState.EFFECTIVE
                )
                if receipt.state is not ReceiptState.EFFECTIVE:
                    raise RuntimeError("PRODUCT_ACTIVATION_RESUME_REJECTED")

                instrument_id = InstrumentId.from_str("BTCUSDT-PERP.BINANCE")
                quote = None
                account = None
                for _ in range(120):
                    quote = runtime.node.cache.quote_tick(instrument_id)
                    account = runtime.node.cache.account_for_venue(BINANCE_VENUE)
                    if quote is not None and account is not None:
                        break
                    await asyncio.sleep(0.25)
                if quote is None or account is None:
                    raise RuntimeError("PRODUCT_REFERENCE_FACT_TIMEOUT")
                instrument = runtime.node.cache.instrument(instrument_id)
                if instrument is None:
                    raise RuntimeError("PRODUCT_INSTRUMENT_NOT_LOADED")
                quantity = str(instrument.make_qty("0.002"))
                limit_price = str(instrument.make_price(float(quote.bid_price) * 0.8))
                conservative_price = str(quote.ask_price)
                available_margin = canonical_decimal(
                    account.balance_free(Currency.from_str("USDT")).as_decimal()
                )
                action_time = datetime.now(UTC)
                causation = content_digest(
                    {
                        "activation_id": ids["activation_id"],
                        "profile": "ENTRY_LIMIT",
                        "quantity": quantity,
                        "price": limit_price,
                        "quote_ts": quote.ts_event,
                    }
                )
                proposed = ProposedAction(
                    environment_id=environment_id,
                    action_kind=ProposedActionKind.ENTRY,
                    action_profile="ENTRY_LIMIT",
                    instrument_ref="BTCUSDT-PERP",
                    direction="LONG",
                    quantity=quantity,
                    close_position=False,
                    order_type="LIMIT",
                    price=limit_price,
                    reduce_only=False,
                    source_responsibility="HALPHA_MONITORED",
                    causation_ref=causation,
                )
                entry_check = ActionCheckInput(
                    environment_id=environment_id,
                    environment_kind=EnvironmentKind.DEMO,
                    authority_class=AuthorityClass.DEMO_VALIDATION,
                    activation_id=ids["activation_id"],
                    account_ref=account_ref,
                    instrument_ref="BTCUSDT-PERP",
                    action_profile="ENTRY_LIMIT",
                    control_category=StopCategory.NEW_FUNDING,
                    risk_class=RiskClass.RISK_INCREASING,
                    checked_at=action_time,
                    quantized_quantity=quantity,
                    conservative_price=conservative_price,
                    account_dynamic_available_margin=available_margin,
                    actual_margin_mode="CROSSED",
                    actual_leverage="20",
                    post_action_abs_position=quantity,
                    current_abs_position="0",
                )
                entry_action_id = str(uuid4())
                coordinated = runtime.coordinator.consume_proposed_action(
                    plan_event_id=str(uuid4()),
                    execution_action_id=entry_action_id,
                    activation_id=ids["activation_id"],
                    rule_id="B03_PRODUCT_ENTRY_LIMIT",
                    source_identity=f"{ids['activation_id']}:B03_PRODUCT_ENTRY_LIMIT:1",
                    source_cutoff=action_time,
                    input_digest=causation,
                    proposed_action=proposed,
                    action_check=entry_check,
                    observed_at=action_time,
                    client_order_id=uuid4().hex,
                )
                if coordinated.execution_action is None:
                    raise RuntimeError("PRODUCT_EXECUTION_ACTION_NOT_CREATED")
                result = runtime.coordinator.process_execution_action(
                    entry_action_id,
                    action_check=entry_check,
                    request_payload={
                        "profile": "ENTRY_LIMIT",
                        "quantity": quantity,
                        "price": limit_price,
                    },
                    observed_at=datetime.now(UTC),
                )
                evidence["venue_write_performed"] = result.venue_called
                checks["product_plan_cap_action_precedes_venue_call"] = (
                    result.venue_called
                    and result.execution_action.state
                    is ExecutionActionState.SUBMITTED_UNKNOWN
                )
                opened = await _wait_for_action(
                    runtime,
                    entry_action_id,
                    frozenset(
                        {
                            ExecutionActionState.ACKNOWLEDGED,
                            ExecutionActionState.WORKING,
                        }
                    ),
                    timeout_seconds=30,
                )
                checks["demo_ack_returns_to_original_uuid"] = (
                    opened.client_order_id == coordinated.execution_action.client_order_id
                )

                cancel_time = datetime.now(UTC)
                cancel_check = ActionCheckInput(
                    environment_id=environment_id,
                    environment_kind=EnvironmentKind.DEMO,
                    authority_class=AuthorityClass.DEMO_VALIDATION,
                    activation_id=ids["activation_id"],
                    account_ref=account_ref,
                    instrument_ref="BTCUSDT-PERP",
                    action_profile="CANCEL_ORDER",
                    control_category=StopCategory.RISK_REDUCTION_OR_ORDER_MANAGEMENT,
                    risk_class=RiskClass.RISK_NEUTRAL,
                    checked_at=cancel_time,
                    quantized_quantity="0",
                    conservative_price=conservative_price,
                    account_dynamic_available_margin=available_margin,
                    actual_margin_mode="CROSSED",
                    actual_leverage="20",
                    post_action_abs_position="0",
                    current_abs_position="0",
                )
                cancel_result = runtime.coordinator.create_cancel_for_action(
                    target_action_id=entry_action_id,
                    target_endpoint="ORDINARY",
                    plan_event_id=str(uuid4()),
                    execution_action_id=str(uuid4()),
                    action_check=cancel_check,
                    reason_ref="B03_PRODUCT_DEMO_CLEANUP",
                    observed_at=cancel_time,
                )
                cancel = cancel_result.execution_action
                if cancel is None:
                    raise RuntimeError("PRODUCT_CANCEL_ACTION_NOT_CREATED")
                runtime.coordinator.process_execution_action(
                    cancel.execution_action_id,
                    action_check=cancel_check,
                    request_payload={
                        "profile": "CANCEL_ORDER",
                        "target_client_order_id": opened.client_order_id,
                    },
                    observed_at=datetime.now(UTC),
                )
                terminal = await _wait_for_action(
                    runtime,
                    entry_action_id,
                    frozenset({ExecutionActionState.CANCELLED}),
                    timeout_seconds=30,
                )
                cancel_closed = await _wait_for_action(
                    runtime,
                    cancel.execution_action_id,
                    frozenset({ExecutionActionState.RECONCILED}),
                    timeout_seconds=30,
                )
                reconciled = runtime.coordinator.reconcile_execution_action(
                    entry_action_id,
                    closure_evidence={
                        "order_terminal": True,
                        "fills_complete": True,
                        "fees_complete": True,
                        "position_effect_known": True,
                    },
                    venue_fact_refs=terminal.venue_fact_refs,
                    observed_at=datetime.now(UTC),
                )
                fact_refs = tuple(
                    dict.fromkeys((*reconciled.venue_fact_refs, *cancel_closed.venue_fact_refs))
                )
                closure = runtime.coordinator.close_activation(
                    activation_id=ids["activation_id"],
                    cutoff=datetime.now(UTC),
                    position_zero=True,
                    open_order_refs=(),
                    external_activity_conflict=False,
                    fees_complete=True,
                    funding_complete=True,
                    user_takeover=False,
                    handover_command_ref=None,
                    fact_refs=fact_refs,
                    result_ref="b03-product-demo-no-fill-review",
                    observed_at=datetime.now(UTC),
                )
                checks["product_cancel_and_closure_complete"] = (
                    terminal.state is ExecutionActionState.CANCELLED
                    and cancel_closed.state is ExecutionActionState.RECONCILED
                    and len(closure) == 64
                )
                terminal_proven = True
            except Exception as exc:
                errors.append(f"PRODUCT_DEMO_FLOW_FAILED:{type(exc).__name__}")
            finally:
                stop.set()

        def on_ready(_runtime_evidence: dict[str, object]) -> None:
            nonlocal flow_task
            checks["product_runtime_reconciliation_precedes_ready"] = (
                runtime is not None and runtime.recovery_complete
            )
            flow_task = runtime.node.get_event_loop().create_task(product_flow())

        evidence["stage"] = "RUNNING_PRODUCT_DEMO"
        runtime.run_until_stop(stop.wait, on_ready=on_ready)
        if flow_task is not None and not flow_task.cancelled():
            flow_task.result()
        evidence["stage"] = "COMPLETED"
    except Exception as exc:
        errors.append(f"PRODUCT_DEMO_PROBE_FAILED:{type(exc).__name__}")
        stop.set()
    finally:
        if runtime is not None:
            runtime.close()
        scanned, secret_found = _scan_logs(api_key_value, api_secret_value)
        evidence["secret_scan"] = {
            "files_scanned": scanned,
            "raw_credential_found": secret_found,
        }
        checks["secrets_absent_from_runtime_logs"] = not secret_found
        if terminal_proven or not bool(evidence["venue_write_performed"]):
            try:
                with app_connection.transaction():
                    app_connection.execute(
                        "DELETE FROM halpha.improvement_handoff WHERE environment_id = %s",
                        (environment_id,),
                    )
                    app_connection.execute(
                        "DELETE FROM halpha.review WHERE environment_id = %s",
                        (environment_id,),
                    )
                    _cleanup(app_connection, environment_id)
                checks["qualification_records_cleaned_after_terminal"] = True
            except Exception as exc:
                errors.append(f"PRODUCT_DEMO_CLEANUP_FAILED:{type(exc).__name__}")
        else:
            checks["qualification_records_cleaned_after_terminal"] = False
            evidence["recovery_environment_ref"] = environment_id
        app_connection.close()
        api_key_value = ""
        api_secret_value = ""

    if not all(checks.values()) and not errors:
        errors.append("PRODUCT_DEMO_REQUIRED_CHECK_FAILED")
    evidence["observed_at"] = datetime.now(UTC).isoformat()
    evidence["status"] = "QUALIFIED" if not errors and all(checks.values()) else "REJECTED"
    evidence["evidence_digest"] = content_digest(
        {
            key: value
            for key, value in evidence.items()
            if key not in {"evidence_digest", "observed_at"}
        }
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if evidence["status"] == "QUALIFIED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
