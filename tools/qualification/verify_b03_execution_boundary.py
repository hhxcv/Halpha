"""Qualify the B03 environment action and append-only fact boundary."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import sys
from typing import Any
from uuid import uuid4

import keyring
import psycopg


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from halpha.capital.models import (
    ActionCheckInput,
    AuthorityClass,
    CapDecision,
    EnvironmentKind,
    RiskClass,
    StopCategory,
)
from halpha.domain_values import content_digest
from halpha.executor.coordinator import HalphaCoordinator
from halpha.planning.strategies.one_shot import (
    EntryRiskContext,
    RiskDirection,
    StrategyProposal,
)
from halpha.planning.transitions import bar_source_identity
from halpha.venue_integration.facts import build_venue_fact
from halpha.venue_integration.gateway import PersistedActionGate
from halpha.venue_integration.models import (
    ExecutionActionState,
    VenueFactKind,
    VenueFactSourceClass,
)
from halpha.venue_integration.repository import (
    PostgreSQLExecutionActionRepository,
    PostgreSQLVenueFactRepository,
)
from halpha.venue_integration.service import ExecutionApplicationService
from tools.qualification.verify_b02_database_boundary import (
    _cleanup,
    _connect,
    _create_and_activate,
    _insert_limit,
)


DEFAULT_OUTPUT = ROOT / "build/qualification/b03-execution-boundary.json"


class _NoWriteClient:
    def submit_order(self, action: object) -> None:
        raise AssertionError("VENUE_WRITE_FORBIDDEN_IN_DATABASE_QUALIFICATION")

    def cancel_order(self, action: object) -> None:
        raise AssertionError("VENUE_WRITE_FORBIDDEN_IN_DATABASE_QUALIFICATION")

    def query_order(self, action: object) -> None:
        raise AssertionError("VENUE_QUERY_UNUSED_IN_DATABASE_QUALIFICATION")


class _RollbackEvidence(Exception):
    pass


def _executor_connect() -> psycopg.Connection[Any]:
    secret = keyring.get_password(
        "Halpha/PostgreSQL/BINANCE_DEMO/Executor",
        "scram_password",
    )
    if not secret:
        raise RuntimeError("DEMO_EXECUTOR_DATABASE_REFERENCE_MISSING")
    try:
        return psycopg.connect(
            host="127.0.0.1",
            port=5432,
            dbname="halpha_demo",
            user="halpha_demo_executor",
            password=secret,
        )
    finally:
        secret = None


def _cap_decision(risk_class: RiskClass = RiskClass.RISK_INCREASING) -> CapDecision:
    fields = {
        "accepted": True,
        "reason_code": f"ACCEPTED_{risk_class.value}",
        "risk_class": risk_class,
        "effective_leverage": "5" if risk_class is RiskClass.RISK_INCREASING else None,
        "action_notional": "500",
        "economic_action_notional": "500",
        "activation_notional_after": "500",
        "account_notional_after": "500",
        "activation_margin_after": "100",
        "stopped_categories": (),
        "input_digest": "c" * 64,
    }
    return CapDecision(**fields, decision_digest=content_digest(fields))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    now = datetime.now(UTC)
    environment_id = f"qualification-b03-{uuid4()}"
    account_ref = f"qualification-account-{uuid4()}"
    checks: dict[str, bool] = {}
    observations: dict[str, Any] = {}
    errors: list[str] = []
    app_connection = _connect()
    executor_connection: psycopg.Connection[Any] | None = None
    try:
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
            closure_ids = _create_and_activate(
                app_connection,
                environment_id=environment_id,
                account_ref=account_ref,
                limit_id=limit_id,
                now=now,
                instrument_ref="ETHUSDT-PERP",
                limits=("50", "250", "25"),
            )

        executor_connection = _executor_connect()
        action_repository = PostgreSQLExecutionActionRepository(
            executor_connection,
            environment_id,
        )
        fact_repository = PostgreSQLVenueFactRepository(
            executor_connection,
            environment_id,
        )
        gate = PersistedActionGate(
            action_repository,
            _NoWriteClient(),
            environment_id=environment_id,
            execution_profile_ref="BINANCE_DEMO",
            account_ref=account_ref,
        )
        coordinator = HalphaCoordinator(
            executor_connection,
            gate,
            environment_id=environment_id,
            environment_kind="DEMO",
            authority_class="DEMO_VALIDATION",
            execution_profile_ref="BINANCE_DEMO",
            account_ref=account_ref,
            runtime_real_write_gate="CLOSED",
        )
        proposal_fields = {
            "strategy_id": "ONE_SHOT_DONCHIAN_ATR_BREAKOUT",
            "activation_id": ids["activation_id"],
            "rule_id": "ENTRY_BREAKOUT",
            "source_identity": bar_source_identity(
                activation_id=ids["activation_id"],
                rule_id="ENTRY_BREAKOUT",
                bar_type="BTCUSDT-PERP.BINANCE-15-MINUTE-LAST-INTERNAL",
                ts_event_ns=1_773_910_800_000_000_000,
            ),
            "source_cutoff": now,
            "input_digest": "7" * 64,
            "instrument_id": "BTCUSDT-PERP.BINANCE",
            "direction": "LONG",
            "action_profile": "ENTRY_MARKET",
            "risk_direction": RiskDirection.INCREASE,
            "quantity": "0.1",
            "reference_price": "5000",
            "reference_source": "B03_DATABASE_QUALIFICATION",
            "reason_code": "ENTRY_BREAKOUT_CONFIRMED",
            "valid_until": now + timedelta(seconds=30),
            "entry_risk_context": EntryRiskContext(
                trigger_atr="100",
                initial_stop_atr_multiple="1.5",
                take_profit_1_r="1.5",
                take_profit_1_fraction="0.5",
                take_profit_2_r="3",
                max_hold_bars_15m=96,
                indicator_source_digest="8" * 64,
                indicator_source_cutoff_ns=1_773_910_800_000_000_000,
                quantity_step="0.001",
                price_tick_size="0.1",
            ),
        }
        proposal = StrategyProposal(
            **proposal_fields,
            proposal_digest=content_digest(proposal_fields),
        )
        first_check = ActionCheckInput(
            environment_id=environment_id,
            environment_kind=EnvironmentKind.DEMO,
            authority_class=AuthorityClass.DEMO_VALIDATION,
            activation_id=ids["activation_id"],
            account_ref=account_ref,
            instrument_ref="BTCUSDT-PERP",
            action_profile="ENTRY_MARKET",
            control_category=StopCategory.NEW_FUNDING,
            risk_class=RiskClass.RISK_INCREASING,
            checked_at=now,
            quantized_quantity="0.1",
            conservative_price="5000",
            account_dynamic_available_margin="500",
            actual_margin_mode="CROSSED",
            actual_leverage="20",
            post_action_abs_position="0.1",
            current_abs_position="0",
        )
        try:
            with executor_connection.transaction():
                result = coordinator.consume_strategy_proposal(
                    plan_event_id=str(uuid4()),
                    execution_action_id=str(uuid4()),
                    proposal=proposal,
                    action_check=first_check,
                    created_at=now,
                    client_order_id=uuid4().hex,
                )
                action = result.execution_action
                if action is None:
                    raise RuntimeError("EXECUTION_ACTION_NOT_CREATED")
                replay = coordinator.consume_strategy_proposal(
                    plan_event_id=str(uuid4()),
                    execution_action_id=str(uuid4()),
                    proposal=proposal,
                    action_check=first_check,
                    created_at=now,
                    client_order_id=uuid4().hex,
                )
                checks["plan_cap_action_atomic_and_replay_stable"] = (
                    replay.plan_event.plan_event_id == result.plan_event.plan_event_id
                    and replay.execution_action is not None
                    and replay.execution_action.execution_action_id
                    == action.execution_action_id
                    and int(
                        executor_connection.execute(
                            "SELECT count(*) FROM halpha.execution_action WHERE environment_id = %s",
                            (environment_id,),
                        ).fetchone()[0]
                    )
                    == 1
                )
                execution = ExecutionApplicationService(
                    action_repository,
                    fact_repository,
                    environment_id=environment_id,
                    environment_kind="DEMO",
                    authority_class="DEMO_VALIDATION",
                    execution_profile_ref="BINANCE_DEMO",
                    account_ref=account_ref,
                )
                prepared = execution.prepare_submission(
                    action.execution_action_id,
                    capital_decision=_cap_decision(),
                    request_payload={"profile": "ENTRY_MARKET", "quantity": "0.1"},
                    observed_at=now + timedelta(seconds=1),
                )
                unknown = execution.record_submission_unknown(
                    action.execution_action_id,
                    reason="QUALIFIED_CRASH_WINDOW",
                    next_query_at=now + timedelta(seconds=10),
                    observed_at=now + timedelta(seconds=2),
                )
                checks["submitting_crash_is_query_only_unknown"] = (
                    prepared.state is ExecutionActionState.SUBMITTING
                    and unknown.state is ExecutionActionState.SUBMITTED_UNKNOWN
                    and unknown.client_order_id == action.client_order_id
                    and unknown.request_digest == prepared.request_digest
                )
                fact_time = now + timedelta(seconds=3)
                fact = build_venue_fact(
                    venue_fact_id=str(uuid4()),
                    environment_id=environment_id,
                    venue_ref="BINANCE",
                    account_ref=account_ref,
                    instrument_ref="BTCUSDT-PERP",
                    kind=VenueFactKind.ORDER_STATE,
                    source_class=VenueFactSourceClass.VENUE_QUERY,
                    source_object_id=unknown.client_order_id or "",
                    source_sequence="qualification-ack-1",
                    source_time=fact_time,
                    received_at=fact_time,
                    cutoff=fact_time,
                    payload={"status": "ACKNOWLEDGED", "venue_order_ref": "qualification"},
                    action=unknown,
                )
                acknowledged = execution.apply_venue_fact(
                    fact=fact,
                    observed_at=fact_time,
                )
                checks["authoritative_fact_advances_original_action"] = (
                    acknowledged is not None
                    and acknowledged.state is ExecutionActionState.ACKNOWLEDGED
                    and acknowledged.execution_action_id == action.execution_action_id
                    and acknowledged.venue_fact_refs == (fact.venue_fact_id,)
                )
                fill_time = now + timedelta(seconds=4)
                fill_fact = build_venue_fact(
                    venue_fact_id=str(uuid4()),
                    environment_id=environment_id,
                    venue_ref="BINANCE",
                    account_ref=account_ref,
                    instrument_ref="BTCUSDT-PERP",
                    kind=VenueFactKind.FILL,
                    source_class=VenueFactSourceClass.VENUE_STREAM,
                    source_object_id="qualification-trade-1",
                    source_sequence="1",
                    source_time=fill_time,
                    received_at=fill_time,
                    cutoff=fill_time,
                    payload={
                        "last_price": "5000",
                        "last_quantity": "0.1",
                        "leaves_quantity": "0",
                        "venue_order_ref": "qualification",
                    },
                    action=acknowledged,
                )
                protection_check = ActionCheckInput(
                    environment_id=environment_id,
                    environment_kind=EnvironmentKind.DEMO,
                    authority_class=AuthorityClass.DEMO_VALIDATION,
                    activation_id=ids["activation_id"],
                    account_ref=account_ref,
                    instrument_ref="BTCUSDT-PERP",
                    action_profile="PROTECTIVE_STOP_REDUCE_ONLY",
                    control_category=StopCategory.PROTECTION,
                    risk_class=RiskClass.RISK_REDUCING,
                    checked_at=fill_time,
                    quantized_quantity="0.1",
                    conservative_price="5000",
                    account_dynamic_available_margin="500",
                    actual_margin_mode="CROSSED",
                    actual_leverage="20",
                    post_action_abs_position="0",
                    current_abs_position="0.1",
                )
                protection_result = coordinator.create_protection_for_fill(
                    fill_fact=fill_fact,
                    plan_event_id=str(uuid4()),
                    execution_action_id=str(uuid4()),
                    action_check=protection_check,
                    observed_at=fill_time,
                    client_order_id=uuid4().hex,
                )
                protection = protection_result.execution_action
                protection_activation = coordinator.get_activation_snapshot(
                    ids["activation_id"]
                )
                checks["fill_atomically_freezes_r_and_creates_explicit_protection"] = (
                    protection is not None
                    and protection.action_terms["trigger_price"] == "4850"
                    and protection.action_terms["quantity"] == "0.1"
                    and protection_activation.protection_state.value == "UNKNOWN"
                    and protection_activation.rule_state["first_fill"]["R"] == "150"
                )
                if protection is None:
                    raise RuntimeError("PROTECTION_ACTION_NOT_CREATED")
                prepared_protection = execution.prepare_submission(
                    protection.execution_action_id,
                    capital_decision=_cap_decision(RiskClass.RISK_REDUCING),
                    request_payload={
                        "profile": "PROTECTIVE_STOP_REDUCE_ONLY",
                        "quantity": "0.1",
                        "trigger_price": "4850",
                    },
                    observed_at=fill_time + timedelta(seconds=1),
                )
                protection_working_time = fill_time + timedelta(seconds=2)
                protection_fact = build_venue_fact(
                    venue_fact_id=str(uuid4()),
                    environment_id=environment_id,
                    venue_ref="BINANCE",
                    account_ref=account_ref,
                    instrument_ref="BTCUSDT-PERP",
                    kind=VenueFactKind.ORDER_STATE,
                    source_class=VenueFactSourceClass.VENUE_QUERY,
                    source_object_id=prepared_protection.client_order_id or "",
                    source_sequence="qualification-protection-working-1",
                    source_time=protection_working_time,
                    received_at=protection_working_time,
                    cutoff=protection_working_time,
                    payload={
                        "status": "WORKING",
                        "venue_order_ref": "qualification-protection",
                    },
                    action=prepared_protection,
                )
                working_protection = coordinator.apply_venue_fact(
                    protection_fact,
                    observed_at=protection_working_time,
                )
                working_activation = coordinator.get_activation_snapshot(
                    ids["activation_id"]
                )
                checks["protection_working_precedes_take_profit_responsibilities"] = (
                    working_protection is not None
                    and working_protection.state is ExecutionActionState.WORKING
                    and working_activation.protection_state.value == "WORKING"
                )
                tp_checks = tuple(
                    ActionCheckInput(
                        environment_id=environment_id,
                        environment_kind=EnvironmentKind.DEMO,
                        authority_class=AuthorityClass.DEMO_VALIDATION,
                        activation_id=ids["activation_id"],
                        account_ref=account_ref,
                        instrument_ref="BTCUSDT-PERP",
                        action_profile=f"TAKE_PROFIT_{index}",
                        control_category=StopCategory.RISK_REDUCTION_OR_ORDER_MANAGEMENT,
                        risk_class=RiskClass.RISK_REDUCING,
                        checked_at=protection_working_time,
                        quantized_quantity="0.05",
                        conservative_price="5000",
                        account_dynamic_available_margin="500",
                        actual_margin_mode="CROSSED",
                        actual_leverage="20",
                        post_action_abs_position="0.05",
                        current_abs_position="0.1",
                    )
                    for index in (1, 2)
                )
                tp_results = coordinator.create_take_profits_for_protected_fill(
                    protection_action_id=protection.execution_action_id,
                    fill_fact_ref=fill_fact.venue_fact_id,
                    fill_source_identity="qualification-trade-1:1",
                    fill_quantity="0.1",
                    plan_event_ids=(str(uuid4()), str(uuid4())),
                    execution_action_ids=(str(uuid4()), str(uuid4())),
                    action_checks=tp_checks,
                    observed_at=protection_working_time,
                    client_order_ids=(uuid4().hex, uuid4().hex),
                )
                checks["two_take_profits_use_same_execution_action_flow"] = (
                    all(item.execution_action is not None for item in tp_results)
                    and tuple(
                        item.execution_action.action_terms["trigger_price"]
                        for item in tp_results
                        if item.execution_action is not None
                    )
                    == ("5225", "5450")
                    and tuple(
                        item.execution_action.action_terms["quantity"]
                        for item in tp_results
                        if item.execution_action is not None
                    )
                    == ("0.05", "0.05")
                )
                first_tp = tp_results[0].execution_action
                if first_tp is None:
                    raise RuntimeError("TAKE_PROFIT_ACTION_NOT_CREATED")
                cancel_time = protection_working_time + timedelta(seconds=1)
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
                    conservative_price="5000",
                    account_dynamic_available_margin="500",
                    actual_margin_mode="CROSSED",
                    actual_leverage="20",
                    post_action_abs_position="0.1",
                    current_abs_position="0.1",
                )
                cancel_result = coordinator.create_cancel_for_action(
                    target_action_id=first_tp.execution_action_id,
                    target_endpoint="ALGO",
                    plan_event_id=str(uuid4()),
                    execution_action_id=str(uuid4()),
                    action_check=cancel_check,
                    reason_ref="qualification-deadline-cancel",
                    observed_at=cancel_time,
                )
                cancel_action = cancel_result.execution_action
                checks["cancel_is_a_distinct_persisted_action_for_original_identity"] = (
                    cancel_action is not None
                    and cancel_action.action_kind.value == "CANCEL"
                    and cancel_action.cancel_target is not None
                    and cancel_action.cancel_target["client_order_id"]
                    == first_tp.client_order_id
                    and cancel_action.client_order_id is None
                )

                exit_time = cancel_time + timedelta(seconds=1)
                exit_check = ActionCheckInput(
                    environment_id=environment_id,
                    environment_kind=EnvironmentKind.DEMO,
                    authority_class=AuthorityClass.DEMO_VALIDATION,
                    activation_id=ids["activation_id"],
                    account_ref=account_ref,
                    instrument_ref="BTCUSDT-PERP",
                    action_profile="REDUCE_OR_CLOSE_MARKET",
                    control_category=StopCategory.RISK_REDUCTION_OR_ORDER_MANAGEMENT,
                    risk_class=RiskClass.RISK_REDUCING,
                    checked_at=exit_time,
                    quantized_quantity="0.1",
                    conservative_price="5000",
                    account_dynamic_available_margin="500",
                    actual_margin_mode="CROSSED",
                    actual_leverage="20",
                    post_action_abs_position="0",
                    current_abs_position="0.1",
                )
                exit_result = coordinator.create_position_exit(
                    activation_id=ids["activation_id"],
                    position_quantity="0.1",
                    position_fact_ref="qualification-position-1",
                    reason_ref="qualification-user-exit",
                    plan_event_id=str(uuid4()),
                    execution_action_id=str(uuid4()),
                    action_check=exit_check,
                    observed_at=exit_time,
                    client_order_id=uuid4().hex,
                )
                exit_action = exit_result.execution_action
                checks["exit_uses_explicit_quantity_reduce_only_execution_action"] = (
                    exit_action is not None
                    and exit_action.action_kind.value == "EXIT"
                    and exit_action.action_terms["quantity"] == "0.1"
                    and exit_action.action_terms["reduce_only"] is True
                    and exit_action.action_terms["close_position"] is False
                )

                closure_digest = coordinator.close_activation(
                    activation_id=closure_ids["activation_id"],
                    cutoff=exit_time,
                    position_zero=True,
                    open_order_refs=(),
                    external_activity_conflict=False,
                    fees_complete=True,
                    funding_complete=True,
                    user_takeover=False,
                    handover_command_ref=None,
                    fact_refs=(),
                    result_ref="qualification-review-empty-activation",
                    observed_at=exit_time,
                )
                closed_activation = coordinator.get_activation_snapshot(
                    closure_ids["activation_id"]
                )
                closed_allocation = executor_connection.execute(
                    """
                    SELECT status, closure_digest
                    FROM halpha.plan_allocation
                    WHERE environment_id = %s AND activation_id = %s
                    """,
                    (environment_id, closure_ids["activation_id"]),
                ).fetchone()
                checks["closure_atomically_completes_plan_and_releases_allocation"] = (
                    closed_activation.lifecycle.value == "COMPLETED"
                    and closed_activation.closure_digest == closure_digest
                    and closed_allocation == ("RELEASED", closure_digest)
                )
                try:
                    with executor_connection.transaction():
                        executor_connection.execute(
                            "UPDATE halpha.execution_action SET environment_id = 'forbidden' "
                            "WHERE execution_action_id = %s",
                            (action.execution_action_id,),
                        )
                except Exception as exc:
                    checks["database_rejects_action_identity_mutation"] = (
                        getattr(exc, "sqlstate", None) == "23514"
                    )
                try:
                    with executor_connection.transaction():
                        executor_connection.execute(
                            "UPDATE halpha.venue_fact SET payload = '{}'::jsonb "
                            "WHERE venue_fact_id = %s",
                            (fact.venue_fact_id,),
                        )
                except Exception as exc:
                    checks["executor_cannot_update_append_only_fact"] = (
                        getattr(exc, "sqlstate", None) == "42501"
                    )
                privilege_row = executor_connection.execute(
                    """
                    SELECT has_table_privilege(current_user, 'halpha.venue_fact', 'INSERT'),
                           has_table_privilege(current_user, 'halpha.venue_fact', 'UPDATE'),
                           has_table_privilege(current_user, 'halpha.venue_fact', 'DELETE')
                    """
                ).fetchone()
                checks["executor_fact_privilege_is_insert_only"] = privilege_row == (
                    True,
                    False,
                    False,
                )
                observations["schema_boundary_object_count"] = int(
                    executor_connection.execute(
                        """
                        SELECT
                          (SELECT count(*) FROM pg_trigger
                           WHERE tgrelid = 'halpha.execution_action'::regclass
                             AND tgname = 'trg_execution_action_identity_immutable'
                             AND NOT tgisinternal)
                          +
                          (SELECT count(*) FROM pg_trigger
                           WHERE tgrelid = 'halpha.venue_fact'::regclass
                             AND tgname = 'trg_venue_fact_append_only'
                             AND NOT tgisinternal)
                          +
                          (SELECT count(*) FROM pg_constraint
                           WHERE connamespace = 'halpha'::regnamespace
                             AND conname IN (
                               'ck_execution_action_order_identity',
                               'ck_execution_action_unknown_evidence',
                               'ck_execution_action_closure_evidence',
                               'ck_execution_action_time_order',
                               'ck_venue_fact_source_identity',
                               'ck_venue_fact_time_order'
                             ))
                          +
                          (SELECT count(*) FROM pg_indexes
                           WHERE schemaname = 'halpha'
                             AND indexname = 'uq_execution_action_client_order_identity')
                        """
                    ).fetchone()[0]
                )
                observations["action_state_path"] = [
                    action.state.value,
                    prepared.state.value,
                    unknown.state.value,
                    acknowledged.state.value if acknowledged is not None else None,
                ]
                raise _RollbackEvidence
        except _RollbackEvidence:
            pass
        checks["qualification_records_rolled_back"] = (
            int(
                executor_connection.execute(
                    "SELECT count(*) FROM halpha.execution_action WHERE environment_id = %s",
                    (environment_id,),
                ).fetchone()[0]
            )
            == 0
            and int(
                executor_connection.execute(
                    "SELECT count(*) FROM halpha.venue_fact WHERE environment_id = %s",
                    (environment_id,),
                ).fetchone()[0]
            )
            == 0
        )
        checks["database_b03_boundary_objects_present"] = (
            observations["schema_boundary_object_count"] == 9
        )
    except Exception as exc:
        errors.append(f"B03_EXECUTION_BOUNDARY_FAILED:{type(exc).__name__}:{exc}")
    finally:
        if executor_connection is not None:
            executor_connection.close()
        try:
            with app_connection.transaction():
                _cleanup(app_connection, environment_id)
        except Exception as exc:
            errors.append(f"B03_SETUP_CLEANUP_FAILED:{type(exc).__name__}")
        app_connection.close()

    errors.extend(name for name, passed in checks.items() if not passed)
    report: dict[str, Any] = {
        "stage": "B03_EXECUTION_AND_FACT_BOUNDARY",
        "observed_at": now.isoformat(),
        "environment_kind": "DEMO",
        "authority_class": "DEMO_VALIDATION",
        "venue_write_performed": False,
        "checks": checks,
        "observations": observations,
        "errors": errors,
        "status": "QUALIFIED" if not errors else "REJECTED",
    }
    report["evidence_digest"] = content_digest(report)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
