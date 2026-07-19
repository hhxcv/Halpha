"""Serve deterministic workbench states without exchange network access."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta
from pathlib import Path
import sys
from threading import Timer
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

import keyring
from pydantic import SecretStr
import uvicorn

from halpha.app.projection import PostgreSQLWorkbenchProjection
from halpha.app.secrets import AppSecrets
from halpha.app.web import create_app
from halpha.capital.models import (
    ActionCheckInput,
    AuthorityClass,
    CapDecision,
    EnvironmentKind,
    RiskClass,
    StopCategory,
)
from halpha.configuration import load_settings
from halpha.domain_values import content_digest
from halpha.executor.coordinator import HalphaCoordinator
from halpha.planning.strategies.one_shot import (
    EntryRiskContext,
    RiskDirection,
    StrategyProposal,
)
from halpha.planning.transitions import bar_source_identity
from halpha.venue_integration.gateway import PersistedActionGate
from halpha.venue_integration.repository import (
    PostgreSQLExecutionActionRepository,
    PostgreSQLVenueFactRepository,
)
from halpha.venue_integration.service import ExecutionApplicationService
from halpha.winvault import require_win_vault_backend
from tools.qualification.database_fixture import (
    NoExchangeClient,
    cleanup_app,
    connect_app,
    connect_executor,
    create_and_activate,
)


FIXTURE_ENVIRONMENT_ID = "trading-workbench-fixture"
FIXTURE_ACCOUNT_ID = "trading-workbench-account"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Serve deterministic workbench states without exchange-changing requests."
    )
    parser.add_argument(
        "--port",
        type=int,
        help="Override the configured local bind port for an isolated qualification run.",
    )
    parser.add_argument(
        "--max-runtime-seconds",
        type=int,
        help="Gracefully stop and clean the fixture after this many seconds.",
    )
    return parser.parse_args()


def _clean(app_connection: object, executor_connection: object) -> None:
    with executor_connection.transaction():
        executor_connection.execute(
            "DELETE FROM halpha.execution_action WHERE environment_id = %s",
            (FIXTURE_ENVIRONMENT_ID,),
        )
    with app_connection.transaction():
        app_connection.execute(
            "DELETE FROM halpha.review WHERE environment_id = %s",
            (FIXTURE_ENVIRONMENT_ID,),
        )
        cleanup_app(app_connection, FIXTURE_ENVIRONMENT_ID)


def _accepted_decision() -> CapDecision:
    fields = {
        "accepted": True,
        "reason_code": "ACCEPTED_RISK_INCREASING",
        "risk_class": RiskClass.RISK_INCREASING,
        "effective_leverage": "5",
        "action_notional": "500",
        "economic_action_notional": "500",
        "activation_notional_after": "500",
        "account_notional_after": "500",
        "activation_margin_after": "100",
        "stopped_categories": (),
        "input_digest": "c" * 64,
    }
    return CapDecision(**fields, decision_digest=content_digest(fields))


def _create_unknown_entry(
    executor_connection: object,
    *,
    activation_id: str,
    observed_at: datetime,
) -> None:
    action_repository = PostgreSQLExecutionActionRepository(
        executor_connection,
        FIXTURE_ENVIRONMENT_ID,
    )
    coordinator = HalphaCoordinator(
        executor_connection,
        PersistedActionGate(
            action_repository,
            NoExchangeClient(),
            environment_id=FIXTURE_ENVIRONMENT_ID,
            execution_profile_ref="BINANCE_DEMO",
            account_ref=FIXTURE_ACCOUNT_ID,
        ),
        environment_id=FIXTURE_ENVIRONMENT_ID,
        environment_kind="DEMO",
        authority_class="DEMO_VALIDATION",
        execution_profile_ref="BINANCE_DEMO",
        account_ref=FIXTURE_ACCOUNT_ID,
        runtime_real_write_gate="CLOSED",
    )
    source_ns = int(observed_at.timestamp() * 1_000_000_000)
    proposal_fields = {
        "strategy_id": "ONE_SHOT_DONCHIAN_ATR_BREAKOUT",
        "activation_id": activation_id,
        "rule_id": "ENTRY_BREAKOUT",
        "source_identity": bar_source_identity(
            activation_id=activation_id,
            rule_id="ENTRY_BREAKOUT",
            bar_type="BTCUSDT-PERP.BINANCE-15-MINUTE-LAST-INTERNAL",
            ts_event_ns=source_ns,
        ),
        "source_cutoff": observed_at,
        "input_digest": "7" * 64,
        "instrument_id": "BTCUSDT-PERP.BINANCE",
        "direction": "LONG",
        "action_profile": "ENTRY_MARKET",
        "risk_direction": RiskDirection.INCREASE,
        "quantity": "0.01",
        "reference_price": "50000",
        "reference_source": "TRADING_WORKBENCH_FIXTURE",
        "reason_code": "ENTRY_BREAKOUT_CONFIRMED",
        "valid_until": observed_at + timedelta(minutes=5),
        "entry_risk_context": EntryRiskContext(
            trigger_atr="500",
            initial_stop_atr_multiple="1.5",
            take_profit_1_r="1.5",
            take_profit_1_fraction="0.5",
            take_profit_2_r="3",
            max_hold_bars_15m=96,
            indicator_source_digest="8" * 64,
            indicator_source_cutoff_ns=source_ns,
            quantity_step="0.001",
            price_tick_size="0.1",
            entry_extension_boundary="51000",
            sizing_taker_fee_rate="0.0006",
            sizing_effective_leverage="5",
            instrument_rules_digest="9" * 64,
        ),
    }
    proposal = StrategyProposal(
        **proposal_fields,
        proposal_digest=content_digest(proposal_fields),
    )
    action_check = ActionCheckInput(
        environment_id=FIXTURE_ENVIRONMENT_ID,
        environment_kind=EnvironmentKind.DEMO,
        authority_class=AuthorityClass.DEMO_VALIDATION,
        activation_id=activation_id,
        account_ref=FIXTURE_ACCOUNT_ID,
        instrument_ref="BTCUSDT-PERP",
        action_profile="ENTRY_MARKET",
        control_category=StopCategory.NEW_RISK,
        risk_class=RiskClass.RISK_INCREASING,
        checked_at=observed_at,
        quantized_quantity="0.01",
        conservative_price="50000",
        account_dynamic_available_margin="500",
        actual_margin_mode="CROSSED",
        actual_leverage="20",
        post_action_abs_position="0.01",
        current_abs_position="0",
    )
    result = coordinator.consume_strategy_proposal(
        plan_event_id=str(uuid4()),
        execution_action_id=str(uuid4()),
        proposal=proposal,
        action_check=action_check,
        created_at=observed_at,
        client_order_id=uuid4().hex,
    )
    if result.execution_action is None:
        raise RuntimeError("WORKBENCH_UNKNOWN_ACTION_NOT_CREATED")
    execution = ExecutionApplicationService(
        action_repository,
        PostgreSQLVenueFactRepository(
            executor_connection,
            FIXTURE_ENVIRONMENT_ID,
        ),
        environment_id=FIXTURE_ENVIRONMENT_ID,
        environment_kind="DEMO",
        authority_class="DEMO_VALIDATION",
        execution_profile_ref="BINANCE_DEMO",
        account_ref=FIXTURE_ACCOUNT_ID,
    )
    execution.prepare_submission(
        result.execution_action.execution_action_id,
        capital_decision=_accepted_decision(),
        request_payload={"profile": "ENTRY_MARKET", "quantity": "0.01"},
        observed_at=observed_at + timedelta(seconds=1),
    )
    execution.record_submission_unknown(
        result.execution_action.execution_action_id,
        reason="WORKBENCH_UNKNOWN_RESULT",
        next_query_at=observed_at + timedelta(seconds=20),
        observed_at=observed_at + timedelta(seconds=2),
    )


def _prepare_states(app_connection: object, executor_connection: object) -> dict[str, str]:
    now = datetime.now(UTC)
    with app_connection.transaction():
        completed = create_and_activate(
            app_connection,
            environment_id=FIXTURE_ENVIRONMENT_ID,
            account_ref=FIXTURE_ACCOUNT_ID,
            now=now,
            instrument_ref="BTCUSDT-PERP",
            limits=("50", "250", "25"),
        )
    coordinator = HalphaCoordinator(
        executor_connection,
        PersistedActionGate(
            PostgreSQLExecutionActionRepository(
                executor_connection,
                FIXTURE_ENVIRONMENT_ID,
            ),
            NoExchangeClient(),
            environment_id=FIXTURE_ENVIRONMENT_ID,
            execution_profile_ref="BINANCE_DEMO",
            account_ref=FIXTURE_ACCOUNT_ID,
        ),
        environment_id=FIXTURE_ENVIRONMENT_ID,
        environment_kind="DEMO",
        authority_class="DEMO_VALIDATION",
        execution_profile_ref="BINANCE_DEMO",
        account_ref=FIXTURE_ACCOUNT_ID,
        runtime_real_write_gate="CLOSED",
    )
    coordinator.close_activation(
        activation_id=completed["activation_id"],
        cutoff=now,
        position_zero=True,
        open_order_refs=(),
        external_activity_conflict=False,
        fees_complete=True,
        funding_complete=True,
        user_takeover=False,
        handover_command_ref=None,
        fact_refs=(),
        result_ref="ignored-browser-fixture-ref",
        observed_at=now,
    )

    with app_connection.transaction():
        gap = create_and_activate(
            app_connection,
            environment_id=FIXTURE_ENVIRONMENT_ID,
            account_ref=FIXTURE_ACCOUNT_ID,
            now=now + timedelta(seconds=10),
            instrument_ref="BTCUSDT-PERP",
            limits=("100", "500", "50"),
        )
        exiting = create_and_activate(
            app_connection,
            environment_id=FIXTURE_ENVIRONMENT_ID,
            account_ref=FIXTURE_ACCOUNT_ID,
            now=now + timedelta(seconds=20),
            instrument_ref="ETHUSDT-PERP",
            limits=("80", "400", "40"),
        )
        takeover = create_and_activate(
            app_connection,
            environment_id=FIXTURE_ENVIRONMENT_ID,
            account_ref=FIXTURE_ACCOUNT_ID,
            now=now + timedelta(seconds=30),
            instrument_ref="SOLUSDT-PERP",
            limits=("60", "300", "30"),
        )
        stale_control = create_and_activate(
            app_connection,
            environment_id=FIXTURE_ENVIRONMENT_ID,
            account_ref=FIXTURE_ACCOUNT_ID,
            now=now + timedelta(seconds=35),
            instrument_ref="XRPUSDT-PERP",
            limits=("40", "200", "20"),
        )
        recovery = create_and_activate(
            app_connection,
            environment_id=FIXTURE_ENVIRONMENT_ID,
            account_ref=FIXTURE_ACCOUNT_ID,
            now=now + timedelta(seconds=37),
            instrument_ref="BNBUSDT-PERP",
            limits=("30", "150", "15"),
        )
        recovery_narrow = create_and_activate(
            app_connection,
            environment_id=FIXTURE_ENVIRONMENT_ID,
            account_ref=FIXTURE_ACCOUNT_ID,
            now=now + timedelta(seconds=38),
            instrument_ref="ADAUSDT-PERP",
            limits=("30", "150", "15"),
        )

    with executor_connection.transaction():
        _create_unknown_entry(
            executor_connection,
            activation_id=gap["activation_id"],
            observed_at=now + timedelta(seconds=43),
        )

    with app_connection.transaction():
        app_connection.execute(
            """
            UPDATE halpha.plan_activation
            SET has_entry_fill = true, protection_state = 'GAP',
                latest_venue_cutoff = %s, state_version = state_version + 1,
                updated_at = %s
            WHERE environment_id = %s AND activation_id = %s
            """,
            (now, now + timedelta(seconds=40), FIXTURE_ENVIRONMENT_ID, gap["activation_id"]),
        )
        app_connection.execute(
            """
            UPDATE halpha.plan_activation
            SET rule_state = jsonb_set(
                    jsonb_set(rule_state, '{capital,activation_loss}', '"50"', true),
                    '{capital,max_loss_reached}', 'true', true
                ),
                state_version = state_version + 1,
                updated_at = %s
            WHERE environment_id = %s AND activation_id = %s
            """,
            (now, FIXTURE_ENVIRONMENT_ID, gap["activation_id"]),
        )
        app_connection.execute(
            """
            UPDATE halpha.plan_activation
            SET lifecycle = 'EXITING', state_version = state_version + 1, updated_at = %s
            WHERE environment_id = %s AND activation_id = %s
            """,
            (now + timedelta(seconds=41), FIXTURE_ENVIRONMENT_ID, exiting["activation_id"]),
        )
        app_connection.execute(
            """
            UPDATE halpha.plan_activation
            SET lifecycle = 'USER_TAKEOVER', responsibility_owner = 'USER',
                entry_opportunity_consumed = true, takeover_scope = %s,
                state_version = state_version + 1, updated_at = %s
            WHERE environment_id = %s AND activation_id = %s
            """,
            (
                '{"source":"TRADING_WORKBENCH_FIXTURE","open_responsibility":"USER"}',
                now + timedelta(seconds=42),
                FIXTURE_ENVIRONMENT_ID,
                takeover["activation_id"],
            ),
        )
        app_connection.execute(
            """
            UPDATE halpha.plan_activation
            SET run_state = 'PAUSED', pause_reason = 'WRITER_CONTINUITY_LOST',
                paused_at = %s, state_version = state_version + 1, updated_at = %s
            WHERE environment_id = %s AND activation_id IN (%s, %s)
            """,
            (
                now + timedelta(seconds=44),
                now + timedelta(seconds=44),
                FIXTURE_ENVIRONMENT_ID,
                recovery["activation_id"],
                recovery_narrow["activation_id"],
            ),
        )
    return {
        "completed": completed["activation_id"],
        "gap": gap["activation_id"],
        "exiting": exiting["activation_id"],
        "takeover": takeover["activation_id"],
        "stale_control": stale_control["activation_id"],
        "recovery": recovery["activation_id"],
        "recovery_narrow": recovery_narrow["activation_id"],
    }


def main() -> int:
    args = _parse_args()
    settings = load_settings(ROOT / "config" / "halpha.example.toml")
    if args.port is not None:
        if not 1 <= args.port <= 65535:
            raise ValueError("WORKBENCH_FIXTURE_PORT_OUT_OF_RANGE")
        settings = settings.model_copy(
            update={"app": settings.app.model_copy(update={"port": args.port})}
        )
    if args.max_runtime_seconds is not None and args.max_runtime_seconds <= 0:
        raise ValueError("WORKBENCH_FIXTURE_MAX_RUNTIME_NOT_POSITIVE")
    settings = settings.model_copy(
        update={
            "release": settings.release.model_copy(
                update={
                    "environment_id": FIXTURE_ENVIRONMENT_ID,
                    "account_id": FIXTURE_ACCOUNT_ID,
                }
            )
        }
    )
    backend = keyring.get_keyring()
    require_win_vault_backend(backend)
    reference = settings.app.database_credential_reference
    database_password = backend.get_password(reference.service, reference.account)
    if not database_password:
        raise RuntimeError("WORKBENCH_FIXTURE_DATABASE_CREDENTIAL_MISSING")

    app_connection = connect_app()
    executor_connection = connect_executor()
    try:
        _clean(app_connection, executor_connection)
        _prepare_states(app_connection, executor_connection)
        app = create_app(
            settings,
            AppSecrets(
                database_password=SecretStr(database_password),
                csrf_signing_secret=SecretStr("workbench-fixture-csrf-signing-only"),
            ),
            repo_root=ROOT,
            projection=PostgreSQLWorkbenchProjection(
                settings.release.database_name,
                SecretStr(database_password),
                settings.release.environment_id,
            ),
            static_dist=ROOT / "frontend" / "dist",
        )
        server_config = {
            "host": settings.app.bind,
            "port": settings.app.port,
            "workers": 1,
            "reload": False,
            "proxy_headers": False,
            "server_header": False,
            "log_level": "warning",
        }
        if args.max_runtime_seconds is None:
            uvicorn.run(app, **server_config)
        else:
            server = uvicorn.Server(uvicorn.Config(app, **server_config))
            shutdown_timer = Timer(
                args.max_runtime_seconds,
                lambda: setattr(server, "should_exit", True),
            )
            shutdown_timer.daemon = True
            shutdown_timer.start()
            try:
                server.run()
            finally:
                shutdown_timer.cancel()
    finally:
        database_password = None
        try:
            _clean(app_connection, executor_connection)
        finally:
            executor_connection.close()
            app_connection.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
