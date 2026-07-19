"""Small local-database helpers shared by direct product checks."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

import keyring
import psycopg

from halpha.capital.models import AuthorityClass, EnvironmentKind
from halpha.planning.models import RequestedLimits, TradePlanContent
from halpha.planning.service import PlanningApplicationService
from halpha.winvault import require_win_vault_backend


class NoExchangeClient:
    """Fail if a database-only check attempts an exchange request."""

    def submit_order(self, action: object) -> None:
        raise AssertionError("EXCHANGE_REQUEST_FORBIDDEN_IN_DATABASE_CHECK")

    def cancel_order(self, action: object) -> None:
        raise AssertionError("EXCHANGE_REQUEST_FORBIDDEN_IN_DATABASE_CHECK")

    def query_order(self, action: object) -> None:
        raise AssertionError("EXCHANGE_QUERY_UNUSED_IN_DATABASE_CHECK")


def _database_secret(role: str) -> str:
    backend = keyring.get_keyring()
    require_win_vault_backend(backend)
    secret = backend.get_password(
        f"Halpha/PostgreSQL/BINANCE_DEMO/{role}",
        "scram_password",
    )
    if not secret:
        raise RuntimeError(f"DEMO_{role.upper()}_DATABASE_REFERENCE_MISSING")
    return secret


def connect_app() -> psycopg.Connection[Any]:
    secret = _database_secret("App")
    try:
        return psycopg.connect(
            host="127.0.0.1",
            port=5432,
            dbname="halpha_demo",
            user="halpha_demo_app",
            password=secret,
        )
    finally:
        secret = ""


def connect_executor() -> psycopg.Connection[Any]:
    secret = _database_secret("Executor")
    try:
        return psycopg.connect(
            host="127.0.0.1",
            port=5432,
            dbname="halpha_demo",
            user="halpha_demo_executor",
            password=secret,
        )
    finally:
        secret = ""


def plan_content(
    *,
    environment_id: str,
    account_ref: str,
    instrument_ref: str,
    now: datetime,
    limits: tuple[str, str, str],
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
            max_margin=limits[0],
            max_notional=limits[1],
            max_allowed_loss=limits[2],
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


def create_and_activate(
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
        "activation_id": str(uuid4()),
    }
    service = PlanningApplicationService(connection, environment_id)
    service.create_draft(
        plan_id=ids["plan_id"],
        content=plan_content(
            environment_id=environment_id,
            account_ref=account_ref,
            instrument_ref=instrument_ref,
            now=now,
            limits=limits,
        ),
        observed_at=now,
    )
    service.fix_and_activate(
        plan_id=ids["plan_id"],
        expected_draft_version=1,
        plan_version_id=ids["plan_version_id"],
        activation_id=ids["activation_id"],
        environment_kind=EnvironmentKind.DEMO,
        authority_class=AuthorityClass.DEMO_VALIDATION,
        product_build_id="a" * 64,
        observed_at=now,
    )
    return ids


def cleanup_app(connection: psycopg.Connection[Any], environment_id: str) -> None:
    for table in (
        "stop_state_version",
        "receipt",
        "plan_event",
        "plan_activation",
        "command",
        "trade_plan_version",
        "trade_plan_draft",
    ):
        connection.execute(
            f"DELETE FROM halpha.{table} WHERE environment_id = %s",
            (environment_id,),
        )
