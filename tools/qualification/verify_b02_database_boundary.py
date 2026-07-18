"""Qualify B02 PostgreSQL transactions and five control commands on the target host."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import json
from pathlib import Path
from threading import Barrier, Lock, Thread
from typing import Any
from uuid import uuid4

import keyring
import psycopg
from pydantic import SecretStr

from halpha.app.projection import PostgreSQLWorkbenchProjection
from halpha.app.planning_api import ActivationPayload, PostgreSQLPlanningApi
from halpha.capital.models import (
    AccountCapitalLimitVersion,
    ActionCheckInput,
    AuthorityClass,
    EnvironmentKind,
    RiskClass,
    StopCategory,
)
from halpha.capital.repository import PostgreSQLCapitalRepository
from halpha.domain_values import content_digest
from halpha.planning.control_service import ActivationControlService
from halpha.planning.models import RequestedLimits, TradePlanContent
from halpha.planning.repository import PostgreSQLPlanningRepository
from halpha.planning.service import PlanningApplicationService
from halpha.planning.strategies.one_shot import RiskDirection, StrategyProposal
from halpha.planning.transitions import ControlIntent, EventConflict, bar_source_identity
from halpha.user_workbench.commands import build_command
from halpha.user_workbench.repository import CommandConflict
from halpha.winvault import require_win_vault_backend


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / "build/qualification/b02-database-boundary.json"


def _connect() -> psycopg.Connection[Any]:
    backend = keyring.get_keyring()
    require_win_vault_backend(backend)
    secret = keyring.get_password(
        "Halpha/PostgreSQL/BINANCE_DEMO/App",
        "scram_password",
    )
    if not secret:
        raise RuntimeError("DEMO_APP_DATABASE_REFERENCE_MISSING")
    try:
        return psycopg.connect(
            host="127.0.0.1",
            port=5432,
            dbname="halpha_demo",
            user="halpha_demo_app",
            password=secret,
        )
    finally:
        secret = None


def _planning_api(*, environment_id: str, account_ref: str) -> PostgreSQLPlanningApi:
    secret = keyring.get_password(
        "Halpha/PostgreSQL/BINANCE_DEMO/App",
        "scram_password",
    )
    if not secret:
        raise RuntimeError("DEMO_APP_DATABASE_REFERENCE_MISSING")
    try:
        return PostgreSQLPlanningApi(
            database_name="halpha_demo",
            password=SecretStr(secret),
            environment_id=environment_id,
            environment_kind="DEMO",
            authority_class="DEMO_VALIDATION",
            account_ref=account_ref,
            build_digest="a" * 64,
        )
    finally:
        secret = None


def _operations_projection(environment_id: str) -> dict[str, Any]:
    secret = keyring.get_password(
        "Halpha/PostgreSQL/BINANCE_DEMO/App",
        "scram_password",
    )
    if not secret:
        raise RuntimeError("DEMO_APP_DATABASE_REFERENCE_MISSING")
    try:
        return PostgreSQLWorkbenchProjection(
            database_name="halpha_demo",
            password=SecretStr(secret),
            environment_id=environment_id,
        ).operations()
    finally:
        secret = None


def _plan_content(
    *,
    environment_id: str,
    account_ref: str,
    instrument_ref: str,
    now: datetime,
    max_margin: str,
    max_notional: str,
    max_allowed_loss: str,
) -> TradePlanContent:
    return TradePlanContent(
        strategy_id="ONE_SHOT_DONCHIAN_ATR_BREAKOUT",
        parameters={"direction": "LONG"},
        environment_id=environment_id,
        environment_kind=EnvironmentKind.DEMO,
        authority_class=AuthorityClass.DEMO_VALIDATION,
        account_ref=account_ref,
        venue_ref="BINANCE_USDM_DEMO",
        instrument_ref=instrument_ref,
        direction="LONG",
        target_exposure="0.01",
        requested_limits=RequestedLimits(
            max_margin=max_margin,
            max_notional=max_notional,
            max_allowed_loss=max_allowed_loss,
        ),
        valid_from=now - timedelta(minutes=1),
        valid_until=now + timedelta(days=1),
        allowed_actions=frozenset(
            {
                "ENTRY_MARKET",
                "ENTRY_LIMIT",
                "ENTRY_STOP_MARKET",
                "CANCEL_ORDER",
                "PROTECTIVE_STOP_REDUCE_ONLY",
                "TAKE_PROFIT_1",
                "TAKE_PROFIT_2",
                "REDUCE_OR_CLOSE_MARKET",
            }
        ),
        terms={"one_entry_cycle": True, "resume_policy": "MANUAL_PLAN_RESUME"},
    )


def _insert_limit(
    connection: psycopg.Connection[Any],
    *,
    environment_id: str,
    account_ref: str,
    limit_id: str,
    now: datetime,
    instruments: tuple[str, ...] = (
        "BTCUSDT-PERP",
        "ETHUSDT-PERP",
        "SOLUSDT-PERP",
    ),
) -> None:
    fields = {
        "capital_limit_version_id": limit_id,
        "environment_id": environment_id,
        "environment_kind": EnvironmentKind.DEMO,
        "authority_class": AuthorityClass.DEMO_VALIDATION,
        "account_ref": account_ref,
        "quote_asset": "USDT",
        "version": 1,
        "effective_at": now,
        "max_margin": "1000",
        "max_notional": "5000",
        "max_allowed_loss": "500",
        "max_action_notional": "1000",
        "scope": {
            "instruments": list(instruments),
            "actions": ["PLAN_ACTIVATION"],
        },
    }
    limit = AccountCapitalLimitVersion(**fields, content_digest=content_digest(fields))
    PostgreSQLCapitalRepository(connection, environment_id).insert_account_limit(limit)


def _create_and_activate(
    connection: psycopg.Connection[Any],
    *,
    environment_id: str,
    account_ref: str,
    limit_id: str,
    now: datetime,
    instrument_ref: str,
    limits: tuple[str, str, str],
) -> dict[str, str]:
    ids = {
        "plan_id": str(uuid4()),
        "plan_version_id": str(uuid4()),
        "activation_id": str(uuid4()),
        "authorization_id": str(uuid4()),
        "allocation_id": str(uuid4()),
    }
    service = PlanningApplicationService(connection, environment_id)
    service.create_draft(
        plan_id=ids["plan_id"],
        content=_plan_content(
            environment_id=environment_id,
            account_ref=account_ref,
            instrument_ref=instrument_ref,
            now=now,
            max_margin=limits[0],
            max_notional=limits[1],
            max_allowed_loss=limits[2],
        ),
        observed_at=now,
    )
    service.fix_and_activate(
        plan_id=ids["plan_id"],
        expected_draft_version=1,
        plan_version_id=ids["plan_version_id"],
        activation_id=ids["activation_id"],
        authorization_version_id=ids["authorization_id"],
        allocation_id=ids["allocation_id"],
        capital_limit_version_id=limit_id,
        quote_asset="USDT",
        build_digest="a" * 64,
        evidence_digest="b" * 64,
        evidence_scope={"environment": "DEMO", "instrument": instrument_ref},
        observed_at=now,
    )
    return ids


def _create_fixed_plan(
    connection: psycopg.Connection[Any],
    *,
    environment_id: str,
    account_ref: str,
    now: datetime,
    instrument_ref: str,
    limits: tuple[str, str, str],
) -> dict[str, str]:
    ids = {
        "plan_id": str(uuid4()),
        "plan_version_id": str(uuid4()),
    }
    service = PlanningApplicationService(connection, environment_id)
    service.create_draft(
        plan_id=ids["plan_id"],
        content=_plan_content(
            environment_id=environment_id,
            account_ref=account_ref,
            instrument_ref=instrument_ref,
            now=now,
            max_margin=limits[0],
            max_notional=limits[1],
            max_allowed_loss=limits[2],
        ),
        observed_at=now,
    )
    service.fix_draft(
        plan_id=ids["plan_id"],
        expected_draft_version=1,
        plan_version_id=ids["plan_version_id"],
        build_digest="a" * 64,
        evidence_digest="b" * 64,
        evidence_scope={"environment": "DEMO", "instrument": instrument_ref},
        fixed_at=now,
    )
    return ids


def _concurrent_allocation_outcomes(
    *,
    environment_id: str,
    account_ref: str,
    now: datetime,
) -> list[str]:
    setup = _connect()
    limit_ids = (str(uuid4()), str(uuid4()))
    try:
        with setup.transaction():
            for limit_id in limit_ids:
                _insert_limit(
                    setup,
                    environment_id=environment_id,
                    account_ref=account_ref,
                    limit_id=limit_id,
                    now=now,
                )
        fixed: list[dict[str, str]] = []
        for instrument in ("BTCUSDT-PERP", "ETHUSDT-PERP"):
            with setup.transaction():
                fixed.append(
                    _create_fixed_plan(
                        setup,
                        environment_id=environment_id,
                        account_ref=account_ref,
                        now=now,
                        instrument_ref=instrument,
                        limits=("800", "4000", "400"),
                    )
                )
    finally:
        setup.close()

    barrier = Barrier(2)
    result_lock = Lock()
    outcomes: list[str] = []

    def activate(index: int) -> None:
        connection = _connect()
        try:
            barrier.wait(timeout=10)
            with connection.transaction():
                PlanningApplicationService(connection, environment_id).activate_version(
                    plan_version_id=fixed[index]["plan_version_id"],
                    activation_id=str(uuid4()),
                    authorization_version_id=str(uuid4()),
                    allocation_id=str(uuid4()),
                    capital_limit_version_id=limit_ids[index],
                    quote_asset="USDT",
                    observed_at=now,
                )
            outcome = "ACCEPTED"
        except ValueError as exc:
            outcome = str(exc)
        except Exception as exc:
            outcome = f"UNEXPECTED:{type(exc).__name__}:{exc}"
        finally:
            connection.close()
        with result_lock:
            outcomes.append(outcome)

    threads = [Thread(target=activate, args=(index,), daemon=True) for index in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)
    if any(thread.is_alive() for thread in threads):
        return ["UNEXPECTED:CONCURRENCY_TIMEOUT"]
    return sorted(outcomes)


def _submit_control(
    connection: psycopg.Connection[Any],
    *,
    environment_id: str,
    activation_id: str,
    expected_version: int,
    intent: ControlIntent,
    now: datetime,
    sequence: int,
    reconciliation_digest: str | None = None,
) -> tuple[object, object]:
    command = build_command(
        command_id=str(uuid4()),
        environment_id=environment_id,
        owner_scope="local-owner",
        idempotency_key=f"b02-{sequence}-{uuid4()}",
        activation_id=activation_id,
        expected_version=expected_version,
        intent=intent,
        scope={
            "activation_id": activation_id,
            "cutoff": now.isoformat(),
            "known_open_orders": [],
            "known_position": "0",
        },
        parameters={},
        submitted_at=now + timedelta(seconds=sequence),
    )
    receipt = ActivationControlService(connection, environment_id).submit(
        command,
        receipt_id=str(uuid4()),
        stop_state_version_id=str(uuid4()),
        reconciliation_digest=reconciliation_digest,
    )
    return command, receipt


def _counts(connection: psycopg.Connection[Any], environment_id: str) -> dict[str, int]:
    tables = (
        "trade_plan_draft",
        "trade_plan_version",
        "plan_activation",
        "plan_event",
        "account_capital_limit_version",
        "machine_authorization_version",
        "plan_allocation",
        "stop_state_version",
        "execution_action",
        "venue_fact",
        "command",
        "receipt",
    )
    return {
        table: int(
            connection.execute(
                f"SELECT count(*) FROM halpha.{table} WHERE environment_id = %s",
                (environment_id,),
            ).fetchone()[0]
        )
        for table in tables
    }


def _cleanup(connection: psycopg.Connection[Any], environment_id: str) -> None:
    for table in (
        "stop_state_version",
        "receipt",
        "plan_event",
        "plan_allocation",
        "machine_authorization_version",
        "plan_activation",
        "command",
        "trade_plan_version",
        "trade_plan_draft",
        "account_capital_limit_version",
    ):
        connection.execute(
            f"DELETE FROM halpha.{table} WHERE environment_id = %s",
            (environment_id,),
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    now = datetime.now(UTC)
    environment_id = f"qualification-b02-{uuid4()}"
    account_ref = f"qualification-account-{uuid4()}"
    concurrency_environment_id = f"qualification-b02-concurrent-{uuid4()}"
    concurrency_account_ref = f"qualification-concurrent-account-{uuid4()}"
    limit_id = str(uuid4())
    checks: dict[str, bool] = {}
    observations: dict[str, Any] = {}
    errors: list[str] = []
    connection = _connect()
    try:
        with connection.transaction():
            _insert_limit(
                connection,
                environment_id=environment_id,
                account_ref=account_ref,
                limit_id=limit_id,
                now=now,
            )
        with connection.transaction():
            primary = _create_and_activate(
                connection,
                environment_id=environment_id,
                account_ref=account_ref,
                limit_id=limit_id,
                now=now,
                instrument_ref="BTCUSDT-PERP",
                limits=("200", "1000", "100"),
            )
        checks["draft_fix_activation_committed_atomically"] = True

        with connection.transaction():
            secondary = _create_and_activate(
                connection,
                environment_id=environment_id,
                account_ref=account_ref,
                limit_id=limit_id,
                now=now,
                instrument_ref="ETHUSDT-PERP",
                limits=("100", "500", "50"),
            )
        checks["different_instrument_with_remaining_allocation_accepted"] = True

        failed_plan_id: str | None = None
        try:
            with connection.transaction():
                failed = _create_and_activate(
                    connection,
                    environment_id=environment_id,
                    account_ref=account_ref,
                    limit_id=limit_id,
                    now=now,
                    instrument_ref="SOLUSDT-PERP",
                    limits=("800", "4000", "400"),
                )
                failed_plan_id = failed["plan_id"]
        except ValueError as exc:
            checks["multi_instrument_allocation_overrun_rejected"] = str(exc) == "ACCOUNT_LIMIT_EXCEEDED"
        if failed_plan_id is not None:
            errors.append("ALLOCATION_OVERRUN_UNEXPECTEDLY_COMMITTED")

        duplicate_plan_id: str | None = None
        try:
            with connection.transaction():
                duplicate = _create_and_activate(
                    connection,
                    environment_id=environment_id,
                    account_ref=account_ref,
                    limit_id=limit_id,
                    now=now,
                    instrument_ref="BTCUSDT-PERP",
                    limits=("50", "200", "25"),
                )
                duplicate_plan_id = duplicate["plan_id"]
        except psycopg.errors.UniqueViolation:
            checks["same_instrument_attribution_ambiguity_rejected"] = True
        if duplicate_plan_id is not None:
            errors.append("DUPLICATE_INSTRUMENT_UNEXPECTEDLY_COMMITTED")

        with connection.transaction():
            api_conflict = _create_fixed_plan(
                connection,
                environment_id=environment_id,
                account_ref=account_ref,
                now=now,
                instrument_ref="BTCUSDT-PERP",
                limits=("50", "200", "25"),
            )
        try:
            _planning_api(
                environment_id=environment_id,
                account_ref=account_ref,
            ).activate(
                ActivationPayload(
                    plan_version_id=api_conflict["plan_version_id"],
                    capital_limit_version_id=limit_id,
                    quote_asset="USDT",
                    owner_password="qualification-only-not-verified-at-domain-boundary",
                ),
                idempotency_key=f"b02-open-scope-{uuid4()}",
                observed_at=now,
            )
        except ValueError as exc:
            checks["api_open_scope_conflict_maps_to_stable_code"] = (
                str(exc) == "ATTRIBUTION_AMBIGUOUS"
            )

        event_id = str(uuid4())
        source_identity = (
            f"{primary['activation_id']}:BAR:ENTRY:1-MINUTE-LAST:1770000000000000000"
        )
        with connection.transaction():
            event = PlanningApplicationService(
                connection, environment_id
            ).record_plan_event(
                plan_event_id=event_id,
                activation_id=primary["activation_id"],
                rule_id="ENTRY",
                source_identity=source_identity,
                source_cutoff=now,
                input_digest="d" * 64,
                reason_code="ENTRY_CONDITION_FALSE",
                proposed_action=None,
                no_action_reason="CONDITION_FALSE",
                condition_judgement=None,
                capital_decision={"accepted": False, "reason_code": "NO_ACTION"},
                created_at=now,
            )
        with connection.transaction():
            replayed_event = PlanningApplicationService(
                connection, environment_id
            ).record_plan_event(
                plan_event_id=str(uuid4()),
                activation_id=primary["activation_id"],
                rule_id="ENTRY",
                source_identity=source_identity,
                source_cutoff=now,
                input_digest="d" * 64,
                reason_code="ENTRY_CONDITION_FALSE",
                proposed_action=None,
                no_action_reason="CONDITION_FALSE",
                condition_judgement=None,
                capital_decision={"accepted": False, "reason_code": "NO_ACTION"},
                created_at=now,
            )
        checks["plan_event_same_source_replays_original"] = (
            replayed_event.plan_event_id == event.plan_event_id == event_id
        )
        try:
            with connection.transaction():
                PlanningApplicationService(connection, environment_id).record_plan_event(
                    plan_event_id=str(uuid4()),
                    activation_id=primary["activation_id"],
                    rule_id="ENTRY",
                    source_identity=source_identity,
                    source_cutoff=now,
                    input_digest="e" * 64,
                    reason_code="ENTRY_CONDITION_FALSE",
                    proposed_action=None,
                    no_action_reason="CONDITION_FALSE",
                    condition_judgement=None,
                    capital_decision={"accepted": False, "reason_code": "NO_ACTION"},
                    created_at=now,
                )
        except EventConflict as exc:
            checks["plan_event_same_source_different_digest_conflicts"] = (
                str(exc) == "FACT_CONFLICT"
            )

        proposal_source = bar_source_identity(
            activation_id=primary["activation_id"],
            rule_id="ENTRY_BREAKOUT",
            bar_type="BTCUSDT-PERP.BINANCE-15-MINUTE-LAST-INTERNAL",
            ts_event_ns=1_773_910_800_000_000_000,
        )
        proposal_fields = {
            "strategy_id": "ONE_SHOT_DONCHIAN_ATR_BREAKOUT",
            "activation_id": primary["activation_id"],
            "rule_id": "ENTRY_BREAKOUT",
            "source_identity": proposal_source,
            "source_cutoff": now,
            "input_digest": "7" * 64,
            "instrument_id": "BTCUSDT-PERP.BINANCE",
            "direction": "LONG",
            "action_profile": "ENTRY_MARKET",
            "risk_direction": RiskDirection.INCREASE,
            "quantity": "0.1",
            "reference_price": "5000",
            "reference_source": "B02_DATABASE_QUALIFICATION",
            "reason_code": "ENTRY_BREAKOUT_CONFIRMED",
            "valid_until": now + timedelta(seconds=30),
        }
        proposal = StrategyProposal(
            **proposal_fields,
            proposal_digest=content_digest(proposal_fields),
        )
        with connection.transaction():
            proposal_event = PlanningApplicationService(
                connection, environment_id
            ).consume_strategy_proposal(
                plan_event_id=str(uuid4()),
                proposal=proposal,
                action_check=ActionCheckInput(
                    environment_id=environment_id,
                    environment_kind=EnvironmentKind.DEMO,
                    authority_class=AuthorityClass.DEMO_VALIDATION,
                    activation_id=primary["activation_id"],
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
                ),
                created_at=now,
            )
        checks["proposal_is_normalized_cap_checked_and_persisted_atomically"] = (
            proposal_event.proposed_action is not None
            and proposal_event.proposed_action.environment_id == environment_id
            and proposal_event.proposed_action.instrument_ref == "BTCUSDT-PERP"
            and proposal_event.proposed_action.causation_ref == proposal.proposal_digest
            and proposal_event.capital_decision["accepted"] is True
            and proposal_event.capital_decision["reason_code"]
            == "ACCEPTED_RISK_INCREASING"
        )

        concurrent_outcomes = _concurrent_allocation_outcomes(
            environment_id=concurrency_environment_id,
            account_ref=concurrency_account_ref,
            now=now,
        )
        checks["concurrent_cross_version_allocations_are_serialized"] = (
            concurrent_outcomes == ["ACCEPTED", "ACCOUNT_LIMIT_EXCEEDED"]
        )

        with connection.transaction():
            command_stop, receipt_stop = _submit_control(
                connection,
                environment_id=environment_id,
                activation_id=primary["activation_id"],
                expected_version=1,
                intent=ControlIntent.STOP_NEW_RISK,
                now=now,
                sequence=1,
            )
        with connection.transaction():
            _, receipt_resume_risk = _submit_control(
                connection,
                environment_id=environment_id,
                activation_id=primary["activation_id"],
                expected_version=1,
                intent=ControlIntent.RESUME_NEW_RISK,
                now=now,
                sequence=2,
            )
        with connection.transaction():
            paused_count = PlanningApplicationService(
                connection, environment_id
            ).pause_for_writer_continuity_loss(now + timedelta(seconds=3))
        paused_proposal_fields = {
            **proposal_fields,
            "source_identity": bar_source_identity(
                activation_id=primary["activation_id"],
                rule_id="ENTRY_BREAKOUT",
                bar_type="BTCUSDT-PERP.BINANCE-15-MINUTE-LAST-INTERNAL",
                ts_event_ns=1_773_910_860_000_000_000,
            ),
            "source_cutoff": now + timedelta(seconds=3),
            "input_digest": "6" * 64,
        }
        paused_proposal = StrategyProposal(
            **paused_proposal_fields,
            proposal_digest=content_digest(paused_proposal_fields),
        )
        with connection.transaction():
            paused_proposal_event = PlanningApplicationService(
                connection, environment_id
            ).consume_strategy_proposal(
                plan_event_id=str(uuid4()),
                proposal=paused_proposal,
                action_check=ActionCheckInput(
                    environment_id=environment_id,
                    environment_kind=EnvironmentKind.DEMO,
                    authority_class=AuthorityClass.DEMO_VALIDATION,
                    activation_id=primary["activation_id"],
                    account_ref=account_ref,
                    instrument_ref="BTCUSDT-PERP",
                    action_profile="ENTRY_MARKET",
                    control_category=StopCategory.NEW_FUNDING,
                    risk_class=RiskClass.RISK_INCREASING,
                    checked_at=now + timedelta(seconds=3),
                    quantized_quantity="0.1",
                    conservative_price="5000",
                    account_dynamic_available_margin="500",
                    actual_margin_mode="CROSSED",
                    actual_leverage="20",
                    post_action_abs_position="0.1",
                    current_abs_position="0",
                ),
                created_at=now + timedelta(seconds=3),
            )
        checks["paused_activation_drops_racing_proposal_before_cap_or_write"] = (
            paused_proposal_event.proposed_action is None
            and paused_proposal_event.no_action_reason == "NEW_RISK_STOPPED"
            and paused_proposal_event.capital_decision["reason_code"]
            == "NOT_EVALUATED_NEW_RISK_STOPPED"
        )
        resume_preview = _planning_api(
            environment_id=environment_id,
            account_ref=account_ref,
        ).control_preview(
            primary["activation_id"],
            ControlIntent.RESUME_ACTIVATION,
        )
        checks["user_resume_requires_future_authoritative_exe_evidence"] = (
            resume_preview["resume_eligible"] is False
            and resume_preview["reconciliation_digest"] is None
            and resume_preview["resume_denial_reasons"]
            == ["B03_AUTHORITATIVE_RECONCILIATION_NOT_AVAILABLE"]
        )
        with connection.transaction():
            _, receipt_resume_activation = _submit_control(
                connection,
                environment_id=environment_id,
                activation_id=primary["activation_id"],
                expected_version=2,
                intent=ControlIntent.RESUME_ACTIVATION,
                now=now,
                sequence=4,
                reconciliation_digest="c" * 64,
            )
        with connection.transaction():
            _, receipt_exit = _submit_control(
                connection,
                environment_id=environment_id,
                activation_id=primary["activation_id"],
                expected_version=3,
                intent=ControlIntent.EXIT_STRATEGY,
                now=now,
                sequence=5,
            )
        with connection.transaction():
            _, receipt_takeover = _submit_control(
                connection,
                environment_id=environment_id,
                activation_id=primary["activation_id"],
                expected_version=4,
                intent=ControlIntent.USER_TAKEOVER,
                now=now,
                sequence=6,
            )
        with connection.transaction():
            replay = ActivationControlService(connection, environment_id).submit(
                command_stop,
                receipt_id=str(uuid4()),
                stop_state_version_id=str(uuid4()),
            )
        checks["five_control_commands_persisted"] = all(
            receipt.state.value in {"EFFECTIVE", "PROCESSING"}
            for receipt in (
                receipt_stop,
                receipt_resume_risk,
                receipt_resume_activation,
                receipt_exit,
                receipt_takeover,
            )
        )
        checks["writer_continuity_loss_paused_all_open_activations"] = paused_count == 2
        checks["idempotent_command_returns_original_receipt"] = replay.receipt_id == receipt_stop.receipt_id
        conflict = command_stop.model_copy(
            update={"command_id": str(uuid4()), "content_digest": "f" * 64}
        )
        try:
            with connection.transaction():
                ActivationControlService(connection, environment_id).submit(
                    conflict,
                    receipt_id=str(uuid4()),
                    stop_state_version_id=str(uuid4()),
                )
        except (CommandConflict, ValueError):
            checks["idempotency_key_content_conflict_rejected"] = True

        deadline_observed_at = now + timedelta(days=1, seconds=1)
        deadline_event_id = str(uuid4())
        with connection.transaction():
            expired_activation, deadline_event = PlanningApplicationService(
                connection, environment_id
            ).expire_entry_deadline(
                activation_id=secondary["activation_id"],
                plan_event_id=deadline_event_id,
                observed_at=deadline_observed_at,
            )
        with connection.transaction():
            replay_expired_activation, replay_deadline_event = (
                PlanningApplicationService(
                    connection, environment_id
                ).expire_entry_deadline(
                    activation_id=secondary["activation_id"],
                    plan_event_id=str(uuid4()),
                    observed_at=deadline_observed_at + timedelta(seconds=1),
                )
            )
        checks["deadline_is_idempotent_and_missed_window_never_backfills_entry"] = (
            expired_activation.entry_opportunity_consumed
            and replay_expired_activation.entry_opportunity_consumed
            and deadline_event.plan_event_id == deadline_event_id
            and replay_deadline_event.plan_event_id == deadline_event_id
            and deadline_event.no_action_reason == "ENTRY_WINDOW_EXPIRED"
            and deadline_event.proposed_action is None
        )

        max_loss_stop_id = str(uuid4())
        max_loss_fact_cutoff = deadline_observed_at + timedelta(seconds=2)
        max_loss_funding_cutoff = deadline_observed_at + timedelta(seconds=1)
        below_loss_fact_cutoff = deadline_observed_at + timedelta(milliseconds=1500)
        with connection.transaction():
            below_loss_activation, below_loss_allocation, below_loss_stop = (
                PlanningApplicationService(
                    connection, environment_id
                ).update_activation_loss(
                    activation_id=secondary["activation_id"],
                    activation_loss=Decimal("49"),
                    loss_fact_cutoff=below_loss_fact_cutoff,
                    funding_query_cutoff=max_loss_funding_cutoff,
                    fact_digest="8" * 64,
                    stop_state_version_id=str(uuid4()),
                    observed_at=below_loss_fact_cutoff,
                )
            )
        checks["loss_revision_below_threshold_persists_without_exit"] = (
            below_loss_activation.lifecycle.value == "RUNNING"
            and below_loss_allocation.activation_loss == "49"
            and below_loss_allocation.status.value == "HELD"
            and below_loss_allocation.max_loss_reached is False
            and below_loss_stop is None
        )
        with connection.transaction():
            loss_activation, loss_allocation, loss_stop = PlanningApplicationService(
                connection, environment_id
            ).update_activation_loss(
                activation_id=secondary["activation_id"],
                activation_loss=Decimal("50"),
                loss_fact_cutoff=max_loss_fact_cutoff,
                funding_query_cutoff=max_loss_funding_cutoff,
                fact_digest="9" * 64,
                stop_state_version_id=max_loss_stop_id,
                observed_at=max_loss_fact_cutoff,
            )
        with connection.transaction():
            replay_loss_activation, replay_loss_allocation, replay_loss_stop = (
                PlanningApplicationService(
                    connection, environment_id
                ).update_activation_loss(
                    activation_id=secondary["activation_id"],
                    activation_loss=Decimal("50"),
                    loss_fact_cutoff=max_loss_fact_cutoff,
                    funding_query_cutoff=max_loss_funding_cutoff,
                    fact_digest="9" * 64,
                    stop_state_version_id=str(uuid4()),
                    observed_at=max_loss_fact_cutoff,
                )
            )
        checks["max_loss_atomically_latches_stop_and_full_exit"] = (
            loss_activation.lifecycle.value == "EXITING"
            and loss_activation.entry_opportunity_consumed
            and loss_allocation.status.value == "EXIT_ONLY"
            and loss_allocation.max_loss_reached
            and loss_allocation.loss_fact_cutoff == max_loss_fact_cutoff
            and loss_allocation.funding_query_cutoff == max_loss_funding_cutoff
            and loss_stop is not None
            and loss_stop.reason == "MAX_LOSS_REACHED"
            and loss_stop.source == "SYSTEM_MAX_LOSS"
            and loss_stop.loss_latch_digest == loss_allocation.loss_latch_digest
            and replay_loss_activation == loss_activation
            and replay_loss_allocation == loss_allocation
            and replay_loss_stop is not None
            and replay_loss_stop.stop_state_version_id == max_loss_stop_id
        )

        with connection.transaction():
            final_activation = PostgreSQLPlanningRepository(
                connection, environment_id
            ).get_activation(primary["activation_id"])
            primary_allocation = PostgreSQLCapitalRepository(
                connection, environment_id
            ).get_allocation(primary["activation_id"])
            counts = _counts(connection, environment_id)
        checks["resume_did_not_clear_later_exit_or_takeover"] = (
            final_activation.lifecycle.value == "USER_TAKEOVER"
            and final_activation.entry_opportunity_consumed
        )
        checks["no_b02_venue_or_execution_write"] = (
            counts["execution_action"] == 0 and counts["venue_fact"] == 0
        )
        checks["secondary_loss_does_not_change_primary_allocation"] = (
            primary_allocation.activation_loss == "0"
            and primary_allocation.max_loss_reached is False
            and primary_allocation.status.value == "TAKEOVER_HELD"
        )
        checks["failed_atomic_attempts_left_no_partial_records"] = (
            counts["trade_plan_draft"] == 3
            and counts["trade_plan_version"] == 3
            and counts["plan_activation"] == 2
            and counts["machine_authorization_version"] == 2
            and counts["plan_allocation"] == 2
        )
        checks["plan_event_conflicts_and_deadline_replays_add_no_duplicates"] = (
            counts["plan_event"] == 4
        )
        operations = _operations_projection(environment_id)
        projected = {
            item["activation_id"]: item for item in operations["activations"]
        }
        checks["operations_projection_is_environment_scoped_and_authoritative"] = (
            operations["database_available"] is True
            and set(projected) == {primary["activation_id"], secondary["activation_id"]}
            and projected[primary["activation_id"]]["lifecycle"] == "USER_TAKEOVER"
            and projected[secondary["activation_id"]]["lifecycle"] == "EXITING"
            and projected[secondary["activation_id"]]["run_state"] == "PAUSED"
            and projected[secondary["activation_id"]]["pause_reason"]
            == "WRITER_CONTINUITY_LOST"
            and len(projected[primary["activation_id"]]["receipts"]) == 5
            and projected[primary["activation_id"]]["execution_actions"] == []
            and projected[primary["activation_id"]]["venue_facts"] == []
            and bool(projected[primary["activation_id"]]["authorization_valid_until"])
            and "NEW_FUNDING"
            in projected[secondary["activation_id"]]["stopped_categories"]
        )
        observations = {
            "database_revision_expected": "20260717_0003",
            "database_revision_app_read": "NOT_AUTHORIZED_BY_LEAST_PRIVILEGE_BOUNDARY",
            "record_counts_before_cleanup": counts,
            "primary_activation_final_lifecycle": final_activation.lifecycle.value,
            "primary_activation_final_state_version": final_activation.state_version,
            "secondary_max_loss_latch_digest": loss_allocation.loss_latch_digest,
            "secondary_activation_id": secondary["activation_id"],
            "concurrent_allocation_outcomes": concurrent_outcomes,
            "operations_server_fact_cutoff": operations["server_fact_cutoff"],
            "control_receipt_states": {
                "STOP_NEW_RISK": receipt_stop.state.value,
                "RESUME_NEW_RISK": receipt_resume_risk.state.value,
                "RESUME_ACTIVATION": receipt_resume_activation.state.value,
                "EXIT_STRATEGY": receipt_exit.state.value,
                "USER_TAKEOVER": receipt_takeover.state.value,
            },
        }
    except Exception as exc:
        errors.append(f"B02_DATABASE_QUALIFICATION_FAILED:{type(exc).__name__}:{exc}")
    finally:
        try:
            with connection.transaction():
                _cleanup(connection, environment_id)
                _cleanup(connection, concurrency_environment_id)
        except Exception as exc:
            errors.append(f"B02_DATABASE_CLEANUP_FAILED:{type(exc).__name__}")
        connection.close()

    errors.extend(name for name, passed in checks.items() if not passed)
    report: dict[str, Any] = {
        "stage": "B02_DATABASE_AND_CONTROL_BOUNDARY",
        "observed_at": now.isoformat(),
        "environment_kind": "DEMO",
        "authority_class": "DEMO_VALIDATION",
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
