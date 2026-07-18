"""Exercise one complete persisted Halpha product cycle on Binance Demo.

All venue writes use ProductExecutorRuntime -> HalphaCoordinator -> the private
persisted-action gate. The supplemental Binance HTTP client is read-only and is
used only for preflight, account configuration, position, order, and funding
evidence.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal, ROUND_DOWN
import json
import os
from pathlib import Path
import re
import sys
from threading import Event
from typing import Any
from uuid import uuid4

import keyring
from nautilus_trader.adapters.binance import (
    BINANCE_VENUE,
    BinanceAccountType,
    get_cached_binance_http_client,
)
from nautilus_trader.adapters.binance.common.enums import (
    BinanceEnvironment,
    BinanceKeyType,
)
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
from halpha.executor.product_entry import instrument_rules_payload
from halpha.executor.runtime import ProductExecutorRuntime
from halpha.outcomes.models import EvidencePurpose, PrimaryResult
from halpha.outcomes.service import OutcomeApplicationService, review_id_for_activation
from halpha.planning.control_service import ActivationControlService
from halpha.planning.models import ProtectionState
from halpha.planning.repository import PostgreSQLPlanningRepository
from halpha.planning.strategies.one_shot import (
    EntryRiskContext,
    RiskDirection,
    StrategyProposal,
)
from halpha.planning.registry import Direction, ONE_SHOT_STRATEGY_ID
from halpha.planning.transitions import ControlIntent, venue_source_identity
from halpha.user_workbench.commands import ReceiptState, build_command
from halpha.venue_integration.binance_algo_orders import (
    working_fact_from_open_algo_orders,
)
from halpha.venue_integration.binance_commissions import (
    commission_facts_from_user_trades,
)
from halpha.venue_integration.facts import build_venue_fact
from halpha.venue_integration.models import (
    ExecutionAction,
    ExecutionActionState,
    VenueFact,
    VenueFactKind,
    VenueFactSourceClass,
)
from halpha.venue_integration.repository import PostgreSQLVenueFactRepository
from halpha.venue_integration.repository import VenueIntegrationConflict
from halpha.winvault import executor_secret_resolver
from tools.qualification.probe_binance_demo_clients import (
    _effective_leverage,
    _query_funding_income_window,
    _query_single_asset_mode,
)
from tools.qualification.probe_binance_demo_order_roundtrip import (
    _all_clear,
    _responsibility_snapshot,
)
from tools.qualification.probe_binance_demo_reduce_only_topology import _account_api
from tools.qualification.source_binding import (
    SourceBindingError,
    capture_source_sha256,
)
from tools.qualification.verify_b02_database_boundary import (
    _connect,
    _create_and_activate,
    _insert_limit,
)


DEFAULT_OUTPUT = ROOT / "build/qualification/b04-product-demo-cycle.json"
CONFIG = ROOT / "config/halpha.toml"
LOG_DIRECTORY = ROOT / "build/qualification/runtime/b04-product-demo-cycle"
INSTRUMENT_ID = InstrumentId.from_str("BTCUSDT-PERP.BINANCE")
INSTRUMENT_REF = "BTCUSDT-PERP"
SYMBOL = "BTCUSDT"
PRODUCT_SOURCE_PATTERNS = (
    "config/halpha.toml",
    "migrations/versions/*.py",
    "requirements/runtime.txt",
    "src/halpha/capital/**/*.py",
    "src/halpha/configuration.py",
    "src/halpha/database/**/*.py",
    "src/halpha/domain_values.py",
    "src/halpha/executor/**/*.py",
    "src/halpha/outcomes/**/*.py",
    "src/halpha/planning/**/*.py",
    "src/halpha/runtime_identity.py",
    "src/halpha/user_workbench/**/*.py",
    "src/halpha/venue_integration/**/*.py",
    "src/halpha/winvault.py",
    "tools/qualification/probe_b04_product_demo_cycle.py",
    "tools/qualification/probe_binance_demo_clients.py",
    "tools/qualification/probe_binance_demo_order_roundtrip.py",
    "tools/qualification/probe_binance_demo_reduce_only_topology.py",
    "tools/qualification/source_binding.py",
    "src/halpha/source_identity.py",
    "tools/qualification/verify_b02_database_boundary.py",
)


async def _wait_for_action(
    runtime: ProductExecutorRuntime,
    action_id: str,
    states: frozenset[ExecutionActionState],
    *,
    timeout_seconds: float = 45.0,
) -> ExecutionAction:
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    while asyncio.get_running_loop().time() < deadline:
        try:
            action = runtime.coordinator.get_execution_action(action_id)
        except VenueIntegrationConflict as exc:
            if str(exc) != "EXECUTION_ACTION_NOT_FOUND":
                raise
            await asyncio.sleep(0.05)
            continue
        if action.state in states:
            return action
        await asyncio.sleep(0.25)
    raise RuntimeError("PRODUCT_ACTION_STATE_TIMEOUT")


async def _wait_for_reference_facts(
    runtime: ProductExecutorRuntime,
) -> tuple[Any, Any, Any]:
    quote = None
    account = None
    instrument = None
    for _ in range(240):
        quote = runtime.node.cache.quote_tick(INSTRUMENT_ID)
        account = runtime.node.cache.account_for_venue(BINANCE_VENUE)
        instrument = runtime.node.cache.instrument(INSTRUMENT_ID)
        if quote is not None and account is not None and instrument is not None:
            return quote, account, instrument
        await asyncio.sleep(0.25)
    raise RuntimeError("PRODUCT_REFERENCE_FACT_TIMEOUT")


async def _position_amount(account_api: Any) -> Decimal:
    positions = await account_api.query_futures_position_risk(
        symbol=SYMBOL,
        recv_window="5000",
    )
    return sum(
        (Decimal(str(position.positionAmt)) for position in positions),
        start=Decimal("0"),
    )


async def _wait_for_position(
    account_api: Any,
    expected: Decimal,
    *,
    timeout_seconds: float = 45.0,
) -> Decimal:
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    actual = await _position_amount(account_api)
    while asyncio.get_running_loop().time() < deadline:
        if actual == expected:
            return actual
        await asyncio.sleep(0.25)
        actual = await _position_amount(account_api)
    return actual


def _shared_http_client(
    runtime: ProductExecutorRuntime,
    api_key: str,
    api_secret: str,
    proxy_url: str | None,
):
    return get_cached_binance_http_client(
        clock=runtime.node.kernel.clock,
        account_type=BinanceAccountType.USDT_FUTURES,
        api_key=api_key,
        api_secret=api_secret,
        key_type=BinanceKeyType.HMAC,
        base_url=None,
        environment=BinanceEnvironment.DEMO,
        is_us=False,
        proxy_url=proxy_url,
    )


async def _account_policy(
    runtime: ProductExecutorRuntime,
    account_api: Any,
    shared_http_client: Any,
) -> tuple[dict[str, object], str, str]:
    account_info = await account_api.query_futures_account_info(recv_window="5000")
    hedge_mode = await account_api.query_futures_hedge_mode(recv_window="5000")
    symbol_configs = await account_api.query_futures_symbol_config(
        recv_window="5000"
    )
    by_symbol = {item.symbol: item for item in symbol_configs}
    symbol_config = by_symbol.get(SYMBOL)
    if symbol_config is None:
        raise RuntimeError("PRODUCT_SYMBOL_CONFIGURATION_MISSING")
    margin_mode = str(symbol_config.marginType).upper()
    leverage = str(symbol_config.leverage)
    if margin_mode not in {"CROSSED", "ISOLATED"} or Decimal(leverage) <= 0:
        raise RuntimeError("PRODUCT_ACCOUNT_CONFIGURATION_UNKNOWN")
    single_asset = await _query_single_asset_mode(
        shared_http_client,
        runtime.node.kernel.clock,
    )
    return (
        {
            "can_trade": bool(account_info.canTrade),
            "position_mode": (
                "HEDGE" if bool(hedge_mode.dualSidePosition) else "ONE_WAY"
            ),
            "asset_mode": "SINGLE_ASSET" if single_asset else "MULTI_ASSET",
            "actual_margin_mode": margin_mode,
            "actual_leverage": leverage,
            "effective_leverage": str(
                _effective_leverage(int(symbol_config.leverage))
            ),
            "account_configuration_modified": False,
            "position_mode_enforced_as_p0_precondition": False,
            "asset_mode_enforced_as_p0_precondition": False,
            "margin_mode_or_leverage_enforced_as_p0_precondition": False,
        },
        margin_mode,
        leverage,
    )


def _qualification_quantity(
    rules: dict[str, str],
    reference_price: Decimal,
) -> str:
    step = Decimal(rules["step_size"])
    maximum = min(Decimal("0.004"), Decimal("800") / reference_price)
    units = int((maximum / step).to_integral_value(rounding=ROUND_DOWN))
    if units % 2:
        units -= 1
    if units < 2:
        raise RuntimeError("PRODUCT_QUALIFICATION_QUANTITY_TOO_SMALL")
    return canonical_decimal(step * units)


def _action_check(
    *,
    environment_id: str,
    account_ref: str,
    activation_id: str,
    profile: str,
    category: StopCategory,
    risk_class: RiskClass,
    checked_at: datetime,
    quantity: str,
    conservative_price: str,
    available_margin: str,
    margin_mode: str,
    leverage: str,
    current_position: str,
    post_position: str,
) -> ActionCheckInput:
    current_notional = Decimal(current_position) * Decimal(conservative_price)
    effective = _effective_leverage(int(Decimal(leverage)))
    return ActionCheckInput(
        environment_id=environment_id,
        environment_kind=EnvironmentKind.DEMO,
        authority_class=AuthorityClass.DEMO_VALIDATION,
        activation_id=activation_id,
        account_ref=account_ref,
        instrument_ref=INSTRUMENT_REF,
        action_profile=profile,
        control_category=category,
        risk_class=risk_class,
        checked_at=checked_at,
        quantized_quantity=quantity,
        conservative_price=conservative_price,
        activation_current_notional=canonical_decimal(current_notional),
        account_current_notional=canonical_decimal(current_notional),
        activation_current_margin=canonical_decimal(current_notional / effective),
        account_dynamic_available_margin=available_margin,
        actual_margin_mode=margin_mode,
        actual_leverage=leverage,
        post_action_abs_position=post_position,
        current_abs_position=current_position,
    )


def _facts_for_action(
    connection: Any,
    environment_id: str,
    action_id: str,
) -> tuple[VenueFact, ...]:
    return PostgreSQLVenueFactRepository(
        connection,
        environment_id,
    ).list_for_action(action_id)


def _fee_evidence(facts: tuple[VenueFact, ...]) -> dict[str, object]:
    fills = tuple(fact for fact in facts if fact.kind is VenueFactKind.FILL)
    commissions = tuple(
        fact for fact in facts if fact.kind is VenueFactKind.COMMISSION
    )
    commission_trade_ids = {fact.source_object_id for fact in commissions}
    complete = bool(fills) and all(
        fact.source_object_id in commission_trade_ids for fact in fills
    )
    return {
        "fill_count": len(fills),
        "commission_count": len(commissions),
        "all_fills_have_actual_commission": complete,
        "facts": facts,
        "fills": fills,
    }


async def _complete_fee_evidence(
    runtime: ProductExecutorRuntime,
    account_api: Any,
    connection: Any,
    *,
    environment_id: str,
    action_id: str,
    timeout_seconds: float = 10.0,
) -> dict[str, object]:
    """Converge stream facts with the qualified read-only user-trades supplement."""

    deadline = asyncio.get_running_loop().time() + timeout_seconds
    query_count = 0
    supplement_fact_count = 0
    evidence = _fee_evidence(
        _facts_for_action(connection, environment_id, action_id)
    )
    while asyncio.get_running_loop().time() < deadline:
        if bool(evidence["all_fills_have_actual_commission"]):
            return {
                **evidence,
                "supplement_query_count": query_count,
                "supplement_fact_count": supplement_fact_count,
            }
        action = runtime.coordinator.get_execution_action(action_id)
        user_trades: list[Any] = []
        for venue_order_ref in action.venue_order_refs:
            try:
                order_id = int(venue_order_ref)
            except ValueError:
                raise RuntimeError("PRODUCT_COMMISSION_ORDER_ID_INVALID") from None
            user_trades.extend(
                await account_api.query_user_trades(
                    symbol=SYMBOL,
                    order_id=order_id,
                    recv_window="5000",
                )
            )
            query_count += 1
        observed_at = datetime.now(UTC)
        supplemental = commission_facts_from_user_trades(
            action=action,
            facts=tuple(evidence["facts"]),
            user_trades=user_trades,
            expected_symbol=SYMBOL,
            observed_at=observed_at,
        )
        for fact in supplemental:
            runtime.coordinator.apply_venue_fact(
                fact,
                observed_at=observed_at,
            )
        supplement_fact_count += len(supplemental)
        if supplemental:
            evidence = _fee_evidence(
                _facts_for_action(connection, environment_id, action_id)
            )
            continue
        await asyncio.sleep(0.25)
        evidence = _fee_evidence(
            _facts_for_action(connection, environment_id, action_id)
        )
    return {
        **evidence,
        "supplement_query_count": query_count,
        "supplement_fact_count": supplement_fact_count,
    }


async def _wait_for_algo_working(
    runtime: ProductExecutorRuntime,
    account_api: Any,
    action_id: str,
    *,
    timeout_seconds: float = 12.0,
) -> tuple[ExecutionAction, int]:
    """Project one exact open-algo query as WORKING when no stream update exists."""

    deadline = asyncio.get_running_loop().time() + timeout_seconds
    query_count = 0
    while asyncio.get_running_loop().time() < deadline:
        action = runtime.coordinator.get_execution_action(action_id)
        if action.state is ExecutionActionState.WORKING:
            return action, query_count
        if action.state in {
            ExecutionActionState.CANCELLED,
            ExecutionActionState.REJECTED,
            ExecutionActionState.EXPIRED,
            ExecutionActionState.FILLED,
            ExecutionActionState.RECONCILED,
        }:
            raise RuntimeError("PRODUCT_ALGO_TERMINATED_BEFORE_WORKING")
        open_orders = await account_api.query_open_algo_orders(
            symbol=SYMBOL,
            recv_window="5000",
        )
        query_count += 1
        observed_at = datetime.now(UTC)
        fact = working_fact_from_open_algo_orders(
            action=action,
            open_algo_orders=open_orders,
            expected_symbol=SYMBOL,
            observed_at=observed_at,
        )
        if fact is not None:
            updated = runtime.coordinator.apply_venue_fact(
                fact,
                observed_at=observed_at,
            )
            if updated is not None and updated.state is ExecutionActionState.WORKING:
                return updated, query_count
        await asyncio.sleep(0.25)
    raise RuntimeError("PRODUCT_ALGO_WORKING_TIMEOUT")


def _retained_product_records(environment_id: str) -> dict[str, int]:
    connection = _connect()
    connection.autocommit = True
    try:
        row = connection.execute(
            """
            SELECT
                (SELECT count(*) FROM halpha.plan_activation WHERE environment_id = %s),
                (SELECT count(*) FROM halpha.execution_action WHERE environment_id = %s),
                (SELECT count(*) FROM halpha.venue_fact WHERE environment_id = %s),
                (SELECT count(*) FROM halpha.review WHERE environment_id = %s)
            """,
            (environment_id, environment_id, environment_id, environment_id),
        ).fetchone()
        if row is None:
            raise RuntimeError("PRODUCT_RETENTION_QUERY_EMPTY")
        return {
            "activation_count": int(row[0]),
            "execution_action_count": int(row[1]),
            "venue_fact_count": int(row[2]),
            "review_version_count": int(row[3]),
        }
    finally:
        connection.close()


def _safe_error_reason(exc: Exception) -> str:
    reason = str(exc)
    if re.fullmatch(r"[A-Z][A-Z0-9_:-]{0,159}", reason):
        return reason
    return type(exc).__name__


def _persist_position_fact(
    runtime: ProductExecutorRuntime,
    *,
    action: ExecutionAction,
    quantity: Decimal,
    observation: str,
    observed_at: datetime,
) -> VenueFact:
    fact = build_venue_fact(
        venue_fact_id=str(uuid4()),
        environment_id=action.environment_id,
        venue_ref="BINANCE",
        account_ref=action.account_ref,
        instrument_ref=INSTRUMENT_REF,
        kind=VenueFactKind.POSITION_STATE,
        source_class=VenueFactSourceClass.VENUE_QUERY,
        source_object_id=f"{SYMBOL}:POSITION",
        source_sequence=f"{observation}:{int(observed_at.timestamp() * 1_000_000)}",
        source_time=None,
        received_at=observed_at,
        cutoff=observed_at,
        payload={
            "symbol": SYMBOL,
            "quantity": canonical_decimal(quantity),
            "query_path": "/fapi/v2/positionRisk",
            "read_only": True,
            "observation": observation,
        },
        action=action,
    )
    runtime.coordinator.apply_venue_fact(fact, observed_at=observed_at)
    return fact


def _reconcile_terminal_action(
    runtime: ProductExecutorRuntime,
    connection: Any,
    environment_id: str,
    action_id: str,
    *,
    closure_evidence: dict[str, object],
) -> ExecutionAction:
    facts = _facts_for_action(connection, environment_id, action_id)
    return runtime.coordinator.reconcile_execution_action(
        action_id,
        closure_evidence=closure_evidence,
        venue_fact_refs=tuple(fact.venue_fact_id for fact in facts),
        observed_at=datetime.now(UTC),
    )


async def _cancel_target(
    runtime: ProductExecutorRuntime,
    *,
    environment_id: str,
    account_ref: str,
    activation_id: str,
    target_action_id: str,
    target_endpoint: str,
    conservative_price: str,
    available_margin: str,
    margin_mode: str,
    leverage: str,
    current_position: str,
    reason_ref: str,
) -> tuple[ExecutionAction, ExecutionAction]:
    now = datetime.now(UTC)
    check = _action_check(
        environment_id=environment_id,
        account_ref=account_ref,
        activation_id=activation_id,
        profile="CANCEL_ORDER",
        category=StopCategory.RISK_REDUCTION_OR_ORDER_MANAGEMENT,
        risk_class=RiskClass.RISK_NEUTRAL,
        checked_at=now,
        quantity="0",
        conservative_price=conservative_price,
        available_margin=available_margin,
        margin_mode=margin_mode,
        leverage=leverage,
        current_position=current_position,
        post_position=current_position,
    )
    coordinated = runtime.coordinator.create_cancel_for_action(
        target_action_id=target_action_id,
        target_endpoint=target_endpoint,
        plan_event_id=str(uuid4()),
        execution_action_id=str(uuid4()),
        action_check=check,
        reason_ref=reason_ref,
        observed_at=now,
    )
    cancel = coordinated.execution_action
    if cancel is None:
        raise RuntimeError("PRODUCT_CANCEL_ACTION_NOT_CREATED")
    runtime.coordinator.process_execution_action(
        cancel.execution_action_id,
        action_check=check,
        request_payload={
            "profile": "CANCEL_ORDER",
            "target_action_id": target_action_id,
            "target_endpoint": target_endpoint,
        },
        observed_at=datetime.now(UTC),
    )
    target = await _wait_for_action(
        runtime,
        target_action_id,
        frozenset({ExecutionActionState.CANCELLED}),
    )
    cancel = await _wait_for_action(
        runtime,
        cancel.execution_action_id,
        frozenset({ExecutionActionState.RECONCILED}),
    )
    return target, cancel


async def _attempt_recovery_to_clear(
    runtime: ProductExecutorRuntime,
    account_api: Any,
    *,
    environment_id: str,
    account_ref: str,
    activation_id: str,
    tracked_target_actions: list[str],
    anchor_action_id: str | None,
    conservative_price: str | None,
    available_margin: str | None,
    margin_mode: str | None,
    leverage: str | None,
) -> bool:
    if not all(
        value is not None
        for value in (
            conservative_price,
            available_margin,
            margin_mode,
            leverage,
        )
    ):
        return _all_clear(await _responsibility_snapshot(account_api))
    position = await _position_amount(account_api)
    for index, target_action_id in enumerate(reversed(tracked_target_actions)):
        action = runtime.coordinator.get_execution_action(target_action_id)
        if action.state not in {
            ExecutionActionState.ACKNOWLEDGED,
            ExecutionActionState.WORKING,
            ExecutionActionState.PARTIALLY_FILLED,
            ExecutionActionState.SUBMITTED_UNKNOWN,
        }:
            continue
        try:
            await _cancel_target(
                runtime,
                environment_id=environment_id,
                account_ref=account_ref,
                activation_id=activation_id,
                target_action_id=target_action_id,
                target_endpoint="ALGO",
                conservative_price=str(conservative_price),
                available_margin=str(available_margin),
                margin_mode=str(margin_mode),
                leverage=str(leverage),
                current_position=canonical_decimal(abs(position)),
                reason_ref=f"B04_RECOVERY_CANCEL_{index}",
            )
        except Exception:
            continue
    position = await _position_amount(account_api)
    if position > 0 and anchor_action_id is not None:
        anchor = runtime.coordinator.get_execution_action(anchor_action_id)
        observed_at = datetime.now(UTC)
        position_fact = _persist_position_fact(
            runtime,
            action=anchor,
            quantity=position,
            observation="RECOVERY_PRE_EXIT",
            observed_at=observed_at,
        )
        check = _action_check(
            environment_id=environment_id,
            account_ref=account_ref,
            activation_id=activation_id,
            profile="REDUCE_OR_CLOSE_MARKET",
            category=StopCategory.RISK_REDUCTION_OR_ORDER_MANAGEMENT,
            risk_class=RiskClass.RISK_REDUCING,
            checked_at=observed_at,
            quantity=canonical_decimal(position),
            conservative_price=str(conservative_price),
            available_margin=str(available_margin),
            margin_mode=str(margin_mode),
            leverage=str(leverage),
            current_position=canonical_decimal(position),
            post_position="0",
        )
        coordinated = runtime.coordinator.create_position_exit(
            activation_id=activation_id,
            position_quantity=canonical_decimal(position),
            position_fact_ref=position_fact.venue_fact_id,
            reason_ref="B04_PRODUCT_RECOVERY_EXIT",
            plan_event_id=str(uuid4()),
            execution_action_id=str(uuid4()),
            action_check=check,
            observed_at=observed_at,
            client_order_id=uuid4().hex,
        )
        if coordinated.execution_action is not None:
            runtime.coordinator.process_execution_action(
                coordinated.execution_action.execution_action_id,
                action_check=check,
                request_payload={
                    "profile": "REDUCE_OR_CLOSE_MARKET",
                    "quantity": canonical_decimal(position),
                    "recovery": True,
                },
                observed_at=datetime.now(UTC),
            )
            await _wait_for_action(
                runtime,
                coordinated.execution_action.execution_action_id,
                frozenset({ExecutionActionState.FILLED}),
            )
            await _wait_for_position(account_api, Decimal("0"))
    return _all_clear(await _responsibility_snapshot(account_api))


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
    source_sha256_at_start = capture_source_sha256(ROOT, PRODUCT_SOURCE_PATTERNS)
    started_at = datetime.now(UTC)
    environment_id = f"qualification-b04-product-{uuid4()}"
    account_ref = f"qualification-demo-account-{uuid4()}"
    proxy_url = os.environ.get("HALPHA_RUNTIME_PROXY_URL")
    evidence: dict[str, Any] = {
        "stage": "INITIALIZING",
        "environment_kind": "DEMO",
        "authority_class": "DEMO_VALIDATION",
        "profile": "BINANCE_DEMO",
        "evidence_purpose": "SYSTEM_MECHANISM_EVIDENCE",
        "venue_write_performed": False,
        "proxy_supplied": bool(proxy_url),
        "proxy_value_persisted": False,
        "account_configuration_modified": False,
        "qualification_environment_ref": environment_id,
        "checks": {},
        "errors": [],
    }
    checks: dict[str, bool] = evidence["checks"]
    errors: list[str] = evidence["errors"]
    app_connection = _connect()
    app_connection.autocommit = True
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
        database_password = resolver.resolve(
            view.executor.database_credential_reference
        )
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
                now=started_at,
            )
            ids = _create_and_activate(
                app_connection,
                environment_id=environment_id,
                account_ref=account_ref,
                limit_id=limit_id,
                now=started_at,
                instrument_ref=INSTRUMENT_REF,
                limits=("500", "1000", "100"),
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
            proxy_url=proxy_url,
        )
        evidence["stage"] = "BUILDING_PRODUCT_RUNTIME"
        runtime.build()

        async def product_flow() -> None:
            nonlocal terminal_proven
            flow_stage = "REFERENCE_FACTS"
            account_api = None
            tracked_target_actions: list[str] = []
            entry_action_id: str | None = None
            conservative_price: str | None = None
            available_margin: str | None = None
            margin_mode: str | None = None
            leverage: str | None = None
            try:
                quote, account, instrument = await _wait_for_reference_facts(runtime)
                flow_stage = "ACCOUNT_POLICY"
                account_api = _account_api(
                    runtime.node,
                    api_key_value,
                    api_secret_value,
                    proxy_url,
                )
                shared_http_client = _shared_http_client(
                    runtime,
                    api_key_value,
                    api_secret_value,
                    proxy_url,
                )
                policy, margin_mode, leverage = await _account_policy(
                    runtime,
                    account_api,
                    shared_http_client,
                )
                evidence["account_policy"] = policy
                checks["account_configuration_read_only_and_nonblocking"] = (
                    policy["account_configuration_modified"] is False
                    and policy["position_mode_enforced_as_p0_precondition"] is False
                    and policy["asset_mode_enforced_as_p0_precondition"] is False
                    and policy["margin_mode_or_leverage_enforced_as_p0_precondition"]
                    is False
                )
                if not bool(policy["can_trade"]):
                    raise RuntimeError("PRODUCT_DEMO_TRADING_PERMISSION_MISSING")

                flow_stage = "PREFLIGHT"
                preflight = await _responsibility_snapshot(account_api)
                evidence["preflight"] = preflight
                checks["read_only_preflight_clear_before_resume_or_write"] = _all_clear(
                    preflight
                )
                if not _all_clear(preflight):
                    raise RuntimeError("PREFLIGHT_EXTERNAL_OR_UNKNOWN_RESPONSIBILITY")

                flow_stage = "MANUAL_RESUME"
                resume_at = datetime.now(UTC)
                with app_connection.transaction():
                    activation = PostgreSQLPlanningRepository(
                        app_connection,
                        environment_id,
                    ).get_activation(ids["activation_id"], for_update=True)
                    reconciliation_digest = content_digest(
                        {
                            "environment_id": environment_id,
                            "activation_id": activation.activation_id,
                            "startup_reconciliation_completed": True,
                            "unresolved_action_count": runtime.recovered_action_count,
                            "read_only_preflight_digest": content_digest(preflight),
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
                        scope={"reason": "B04_PRODUCT_DEMO_COMPLETE_CYCLE"},
                        parameters={},
                        submitted_at=resume_at,
                    )
                    receipt = ActivationControlService(
                        app_connection,
                        environment_id,
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

                flow_stage = "ENTRY"
                reference = Decimal(str(quote.ask_price))
                conservative_price = canonical_decimal(reference)
                available_margin = canonical_decimal(
                    account.balance_free(Currency.from_str("USDT")).as_decimal()
                )
                execution_rules = instrument_rules_payload(instrument)
                quantity = _qualification_quantity(execution_rules, reference)
                quantity_decimal = Decimal(quantity)
                tick = Decimal(execution_rules["price_tick_size"])
                step = Decimal(execution_rules["step_size"])
                trigger_atr = (reference * Decimal("0.20") / tick).to_integral_value(
                    rounding=ROUND_DOWN
                ) * tick
                entry_context = EntryRiskContext(
                    trigger_atr=canonical_decimal(trigger_atr),
                    initial_stop_atr_multiple="1",
                    take_profit_1_r="1",
                    take_profit_1_fraction="0.5",
                    take_profit_2_r="2",
                    max_hold_bars_15m=8,
                    indicator_source_digest=content_digest(
                        {
                            "source": "B04_PRODUCT_DEMO_QUALIFICATION",
                            "quote_ts": quote.ts_event,
                        }
                    ),
                    indicator_source_cutoff_ns=int(quote.ts_event),
                    quantity_step=canonical_decimal(step),
                    price_tick_size=canonical_decimal(tick),
                    entry_extension_boundary=canonical_decimal(
                        reference + trigger_atr
                    ),
                    sizing_taker_fee_rate=canonical_decimal(instrument.taker_fee),
                    sizing_effective_leverage=str(
                        _effective_leverage(int(Decimal(leverage)))
                    ),
                    instrument_rules_digest=content_digest(execution_rules),
                )
                entry_at = datetime.now(UTC)
                proposal_basis = {
                    "strategy_id": ONE_SHOT_STRATEGY_ID,
                    "activation_id": ids["activation_id"],
                    "rule_id": "ENTRY_BREAKOUT",
                    "source_identity": (
                        f"{ids['activation_id']}:B04_PRODUCT_ENTRY:{quote.ts_event}"
                    ),
                    "source_cutoff": entry_at,
                    "input_digest": content_digest(
                        {
                            "quote_ts": quote.ts_event,
                            "reference_price": conservative_price,
                            "quantity": quantity,
                        }
                    ),
                    "instrument_id": str(INSTRUMENT_ID),
                    "direction": Direction.LONG,
                    "action_profile": "ENTRY_MARKET",
                    "risk_direction": RiskDirection.INCREASE,
                    "quantity": quantity,
                    "reference_price": conservative_price,
                    "reference_source": "BINANCE_DEMO_TOP_OF_BOOK",
                    "reason_code": "B04_PRODUCT_DEMO_QUALIFICATION",
                    "valid_until": entry_at + timedelta(seconds=60),
                    "entry_risk_context": entry_context,
                }
                proposal = StrategyProposal(
                    **proposal_basis,
                    proposal_digest=content_digest(proposal_basis),
                )
                entry_action_id = runtime.submit_strategy_proposal(proposal)
                submitted = await _wait_for_action(
                    runtime,
                    entry_action_id,
                    frozenset(
                        {
                            ExecutionActionState.SUBMITTED_UNKNOWN,
                            ExecutionActionState.ACKNOWLEDGED,
                            ExecutionActionState.WORKING,
                            ExecutionActionState.PARTIALLY_FILLED,
                            ExecutionActionState.FILLED,
                            ExecutionActionState.NOT_SUBMITTED,
                        }
                    ),
                )
                if submitted.state is ExecutionActionState.NOT_SUBMITTED:
                    raise RuntimeError(
                        "PRODUCT_ENTRY_NOT_SUBMITTED:"
                        f"{submitted.not_submitted_reason or 'UNKNOWN'}"
                    )
                evidence["venue_write_performed"] = True
                checks["entry_uses_persisted_product_gate"] = (
                    submitted.state
                    in {
                        ExecutionActionState.SUBMITTED_UNKNOWN,
                        ExecutionActionState.ACKNOWLEDGED,
                        ExecutionActionState.WORKING,
                        ExecutionActionState.PARTIALLY_FILLED,
                        ExecutionActionState.FILLED,
                    }
                )
                checks["entry_uses_production_proposal_processor"] = True
                entry = await _wait_for_action(
                    runtime,
                    entry_action_id,
                    frozenset({ExecutionActionState.FILLED}),
                )
                position = await _wait_for_position(account_api, quantity_decimal)
                checks["entry_fill_and_position_observed"] = (
                    entry.state is ExecutionActionState.FILLED
                    and position == quantity_decimal
                )
                if position != quantity_decimal:
                    raise RuntimeError("PRODUCT_ENTRY_POSITION_MISMATCH")

                entry_fees = await _complete_fee_evidence(
                    runtime,
                    account_api,
                    app_connection,
                    environment_id=environment_id,
                    action_id=entry_action_id,
                )
                entry_fills = entry_fees["fills"]
                checks["entry_actual_commission_complete"] = bool(
                    entry_fees["all_fills_have_actual_commission"]
                )
                if not entry_fees["all_fills_have_actual_commission"]:
                    raise RuntimeError("PRODUCT_ENTRY_COMMISSION_INCOMPLETE")
                fill_total = sum(
                    (Decimal(str(fact.payload["last_quantity"])) for fact in entry_fills),
                    start=Decimal("0"),
                )
                if fill_total != quantity_decimal:
                    raise RuntimeError("PRODUCT_ENTRY_FILL_TOTAL_MISMATCH")

                flow_stage = "PROTECTION_AND_TAKE_PROFIT"
                protection_ids: list[str] = []
                take_profit_ids: list[str] = []
                algo_working_query_count = 0
                for fill_index, fill_fact in enumerate(entry_fills, start=1):
                    fill_quantity = str(fill_fact.payload["last_quantity"])
                    fill_decimal = Decimal(fill_quantity)
                    protection_at = datetime.now(UTC)
                    protection_check = _action_check(
                        environment_id=environment_id,
                        account_ref=account_ref,
                        activation_id=ids["activation_id"],
                        profile="PROTECTIVE_STOP_REDUCE_ONLY",
                        category=StopCategory.PROTECTION,
                        risk_class=RiskClass.RISK_REDUCING,
                        checked_at=protection_at,
                        quantity=fill_quantity,
                        conservative_price=conservative_price,
                        available_margin=available_margin,
                        margin_mode=margin_mode,
                        leverage=leverage,
                        current_position=quantity,
                        post_position=canonical_decimal(quantity_decimal - fill_decimal),
                    )
                    protection_id = str(uuid4())
                    protection_result = runtime.coordinator.create_protection_for_fill(
                        fill_fact=fill_fact,
                        plan_event_id=str(uuid4()),
                        execution_action_id=protection_id,
                        action_check=protection_check,
                        observed_at=protection_at,
                        client_order_id=uuid4().hex,
                    )
                    if protection_result.execution_action is None:
                        raise RuntimeError("PRODUCT_PROTECTION_ACTION_NOT_CREATED")
                    runtime.coordinator.process_execution_action(
                        protection_id,
                        action_check=protection_check,
                        request_payload={
                            "profile": "PROTECTIVE_STOP_REDUCE_ONLY",
                            "quantity": fill_quantity,
                            "trigger_price": protection_result.execution_action.action_terms[
                                "trigger_price"
                            ],
                        },
                        observed_at=datetime.now(UTC),
                    )
                    protection_ids.append(protection_id)
                    tracked_target_actions.append(protection_id)
                    _protection, working_queries = await _wait_for_algo_working(
                        runtime,
                        account_api,
                        protection_id,
                    )
                    algo_working_query_count += working_queries

                    fill_source_identity = venue_source_identity(
                        activation_id=ids["activation_id"],
                        rule_id="PROTECTION_AFTER_FILL",
                        source_class=fill_fact.source_class.value,
                        source_object_id=fill_fact.source_object_id,
                        source_sequence_or_version=fill_fact.source_sequence,
                    )
                    tp_at = datetime.now(UTC)
                    tp_quantities = (
                        canonical_decimal(
                            (fill_decimal * Decimal("0.5") / step).to_integral_value(
                                rounding=ROUND_DOWN
                            )
                            * step
                        ),
                        canonical_decimal(
                            fill_decimal
                            - (
                                fill_decimal
                                * Decimal("0.5")
                                / step
                            ).to_integral_value(rounding=ROUND_DOWN)
                            * step
                        ),
                    )
                    if any(Decimal(value) <= 0 for value in tp_quantities):
                        raise RuntimeError("PRODUCT_TAKE_PROFIT_SPLIT_TOO_SMALL")
                    tp_checks = tuple(
                        _action_check(
                            environment_id=environment_id,
                            account_ref=account_ref,
                            activation_id=ids["activation_id"],
                            profile=profile,
                            category=StopCategory.RISK_REDUCTION_OR_ORDER_MANAGEMENT,
                            risk_class=RiskClass.RISK_REDUCING,
                            checked_at=tp_at,
                            quantity=tp_quantity,
                            conservative_price=conservative_price,
                            available_margin=available_margin,
                            margin_mode=margin_mode,
                            leverage=leverage,
                            current_position=quantity,
                            post_position=canonical_decimal(
                                quantity_decimal - Decimal(tp_quantity)
                            ),
                        )
                        for profile, tp_quantity in zip(
                            ("TAKE_PROFIT_1", "TAKE_PROFIT_2"),
                            tp_quantities,
                            strict=True,
                        )
                    )
                    tp_action_ids = (str(uuid4()), str(uuid4()))
                    tp_results = runtime.coordinator.create_take_profits_for_protected_fill(
                        protection_action_id=protection_id,
                        fill_fact_ref=fill_fact.venue_fact_id,
                        fill_source_identity=fill_source_identity,
                        fill_quantity=fill_quantity,
                        plan_event_ids=(str(uuid4()), str(uuid4())),
                        execution_action_ids=tp_action_ids,
                        action_checks=tp_checks,
                        observed_at=tp_at,
                        client_order_ids=(uuid4().hex, uuid4().hex),
                    )
                    for tp_result, tp_check in zip(tp_results, tp_checks, strict=True):
                        tp_action = tp_result.execution_action
                        if tp_action is None:
                            raise RuntimeError("PRODUCT_TAKE_PROFIT_ACTION_NOT_CREATED")
                        runtime.coordinator.process_execution_action(
                            tp_action.execution_action_id,
                            action_check=tp_check,
                            request_payload={
                                "profile": tp_action.action_terms["action_profile"],
                                "quantity": tp_action.action_terms["quantity"],
                                "trigger_price": tp_action.action_terms["trigger_price"],
                            },
                            observed_at=datetime.now(UTC),
                        )
                        take_profit_ids.append(tp_action.execution_action_id)
                        tracked_target_actions.append(tp_action.execution_action_id)
                        _take_profit, working_queries = await _wait_for_algo_working(
                            runtime,
                            account_api,
                            tp_action.execution_action_id,
                        )
                        algo_working_query_count += working_queries

                protected_activation = runtime.coordinator.get_activation_snapshot(
                    ids["activation_id"]
                )
                mid_snapshot = await _responsibility_snapshot(account_api)
                evidence["protected_position"] = {
                    "entry_fill_count": len(entry_fills),
                    "protection_action_count": len(protection_ids),
                    "take_profit_action_count": len(take_profit_ids),
                    "open_algo_order_count": mid_snapshot[SYMBOL][
                        "open_algo_order_count"
                    ],
                    "position_quantity": canonical_decimal(position),
                }
                checks["protection_and_two_tps_working_per_fill"] = (
                    protected_activation.protection_state is ProtectionState.WORKING
                    and len(protection_ids) == len(entry_fills)
                    and len(take_profit_ids) == 2 * len(entry_fills)
                    and mid_snapshot[SYMBOL]["open_algo_order_count"]
                    == len(tracked_target_actions)
                )
                if not checks["protection_and_two_tps_working_per_fill"]:
                    raise RuntimeError("PRODUCT_PROTECTION_TOPOLOGY_MISMATCH")

                flow_stage = "ENTRY_RECONCILIATION"
                entry = _reconcile_terminal_action(
                    runtime,
                    app_connection,
                    environment_id,
                    entry_action_id,
                    closure_evidence={
                        "order_terminal": True,
                        "fills_complete": True,
                        "fees_complete": True,
                        "position_effect_known": True,
                        "protection_actions_working": len(protection_ids),
                    },
                )
                checks["entry_reconciled_after_protection"] = (
                    entry.state is ExecutionActionState.RECONCILED
                )

                flow_stage = "ALGO_CANCELLATION"
                cancel_action_count = 0
                for index, target_id in enumerate(reversed(tracked_target_actions), start=1):
                    target, cancel = await _cancel_target(
                        runtime,
                        environment_id=environment_id,
                        account_ref=account_ref,
                        activation_id=ids["activation_id"],
                        target_action_id=target_id,
                        target_endpoint="ALGO",
                        conservative_price=conservative_price,
                        available_margin=available_margin,
                        margin_mode=margin_mode,
                        leverage=leverage,
                        current_position=quantity,
                        reason_ref=f"B04_PRODUCT_PRE_EXIT_CANCEL_{index}",
                    )
                    _reconcile_terminal_action(
                        runtime,
                        app_connection,
                        environment_id,
                        target.execution_action_id,
                        closure_evidence={
                            "order_terminal": True,
                            "fills_complete": True,
                            "fees_complete": True,
                            "position_effect_known": True,
                            "cancel_action_ref": cancel.execution_action_id,
                        },
                    )
                    cancel_action_count += 1
                gap_activation = runtime.coordinator.get_activation_snapshot(
                    ids["activation_id"]
                )
                before_exit_snapshot = await _responsibility_snapshot(account_api)
                checks["algo_cleanup_is_persisted_and_projects_protection_gap"] = (
                    cancel_action_count == len(tracked_target_actions)
                    and before_exit_snapshot[SYMBOL]["open_algo_order_count"] == 0
                    and gap_activation.protection_state is ProtectionState.GAP
                )
                if not checks[
                    "algo_cleanup_is_persisted_and_projects_protection_gap"
                ]:
                    raise RuntimeError("PRODUCT_PRE_EXIT_CLEANUP_INCOMPLETE")

                flow_stage = "CONTROLLED_EXIT"
                position = await _position_amount(account_api)
                pre_exit_at = datetime.now(UTC)
                position_fact = _persist_position_fact(
                    runtime,
                    action=entry,
                    quantity=position,
                    observation="PRE_EXIT",
                    observed_at=pre_exit_at,
                )
                exit_check = _action_check(
                    environment_id=environment_id,
                    account_ref=account_ref,
                    activation_id=ids["activation_id"],
                    profile="REDUCE_OR_CLOSE_MARKET",
                    category=StopCategory.RISK_REDUCTION_OR_ORDER_MANAGEMENT,
                    risk_class=RiskClass.RISK_REDUCING,
                    checked_at=pre_exit_at,
                    quantity=canonical_decimal(position),
                    conservative_price=conservative_price,
                    available_margin=available_margin,
                    margin_mode=margin_mode,
                    leverage=leverage,
                    current_position=canonical_decimal(position),
                    post_position="0",
                )
                exit_action_id = str(uuid4())
                exit_result = runtime.coordinator.create_position_exit(
                    activation_id=ids["activation_id"],
                    position_quantity=canonical_decimal(position),
                    position_fact_ref=position_fact.venue_fact_id,
                    reason_ref="B04_PRODUCT_CONTROLLED_EXIT",
                    plan_event_id=str(uuid4()),
                    execution_action_id=exit_action_id,
                    action_check=exit_check,
                    observed_at=pre_exit_at,
                    client_order_id=uuid4().hex,
                )
                if exit_result.execution_action is None:
                    raise RuntimeError("PRODUCT_EXIT_ACTION_NOT_CREATED")
                runtime.coordinator.process_execution_action(
                    exit_action_id,
                    action_check=exit_check,
                    request_payload={
                        "profile": "REDUCE_OR_CLOSE_MARKET",
                        "quantity": canonical_decimal(position),
                        "position_fact_ref": position_fact.venue_fact_id,
                    },
                    observed_at=datetime.now(UTC),
                )
                exit_action = await _wait_for_action(
                    runtime,
                    exit_action_id,
                    frozenset({ExecutionActionState.FILLED}),
                )
                flat = await _wait_for_position(account_api, Decimal("0"))
                if flat != 0:
                    raise RuntimeError("PRODUCT_EXIT_POSITION_NOT_FLAT")
                flat_at = datetime.now(UTC)
                flat_fact = _persist_position_fact(
                    runtime,
                    action=exit_action,
                    quantity=flat,
                    observation="POST_EXIT",
                    observed_at=flat_at,
                )
                exit_fees = await _complete_fee_evidence(
                    runtime,
                    account_api,
                    app_connection,
                    environment_id=environment_id,
                    action_id=exit_action_id,
                )
                checks["exit_actual_commission_complete"] = bool(
                    exit_fees["all_fills_have_actual_commission"]
                )
                if not exit_fees["all_fills_have_actual_commission"]:
                    raise RuntimeError("PRODUCT_EXIT_COMMISSION_INCOMPLETE")
                exit_action = _reconcile_terminal_action(
                    runtime,
                    app_connection,
                    environment_id,
                    exit_action_id,
                    closure_evidence={
                        "order_terminal": True,
                        "fills_complete": True,
                        "fees_complete": True,
                        "position_effect_known": True,
                        "position_zero_fact_ref": flat_fact.venue_fact_id,
                    },
                )
                checks["controlled_exit_reconciled_and_flat"] = (
                    exit_action.state is ExecutionActionState.RECONCILED and flat == 0
                )

                flow_stage = "FUNDING_QUERY"
                funding_end_ms = runtime.node.kernel.clock.timestamp_ms()
                funding_start_ms = int(started_at.timestamp() * 1000) - 1000
                funding_records, funding_window = await _query_funding_income_window(
                    shared_http_client,
                    runtime.node.kernel.clock,
                    symbol=SYMBOL,
                    start_time_ms=funding_start_ms,
                    end_time_ms=funding_end_ms,
                )
                funding_fact_refs: list[str] = []
                for record in funding_records:
                    identity = record["identity"]
                    source_time = datetime.fromtimestamp(
                        int(record["time_ms"]) / 1000,
                        tz=UTC,
                    )
                    funding_fact = build_venue_fact(
                        venue_fact_id=str(uuid4()),
                        environment_id=environment_id,
                        venue_ref="BINANCE",
                        account_ref=account_ref,
                        instrument_ref=INSTRUMENT_REF,
                        kind=VenueFactKind.FUNDING,
                        source_class=VenueFactSourceClass.VENUE_QUERY,
                        source_object_id=str(identity[1]),
                        source_sequence=f"{identity[0]}:{identity[1]}",
                        source_time=source_time,
                        received_at=flat_at,
                        cutoff=flat_at,
                        payload={
                            "income_type": identity[0],
                            "transaction_id": identity[1],
                            "symbol": record["symbol"],
                            "income": record["income"],
                            "asset": record["asset"],
                            "query_start_ms": funding_start_ms,
                            "query_end_ms": funding_end_ms,
                        },
                        action=entry,
                    )
                    runtime.coordinator.apply_venue_fact(
                        funding_fact,
                        observed_at=flat_at,
                    )
                    funding_fact_refs.append(funding_fact.venue_fact_id)
                evidence["funding_query"] = {
                    **funding_window,
                    "window_start_ms": funding_start_ms,
                    "window_end_ms": funding_end_ms,
                    "funding_fact_count": len(funding_fact_refs),
                    "total_income": canonical_decimal(
                        sum(
                            (Decimal(str(item["income"])) for item in funding_records),
                            start=Decimal("0"),
                        )
                    ),
                    "read_only": True,
                }
                checks["funding_window_queried_and_persisted_if_present"] = (
                    funding_window["unique_record_count"] == len(funding_fact_refs)
                )

                postflight = await _responsibility_snapshot(account_api)
                evidence["postflight"] = postflight
                checks["postflight_position_and_orders_clear"] = _all_clear(postflight)
                if not _all_clear(postflight):
                    raise RuntimeError("PRODUCT_POSTFLIGHT_RESPONSIBILITY_OPEN")

                flow_stage = "CLOSURE_AND_REVIEW"
                fact_rows = app_connection.execute(
                    """
                    SELECT venue_fact_id
                    FROM halpha.venue_fact
                    WHERE environment_id = %s AND activation_ref = %s
                    ORDER BY cutoff, venue_fact_id
                    """,
                    (environment_id, ids["activation_id"]),
                ).fetchall()
                fact_refs = tuple(str(row[0]) for row in fact_rows)
                cutoff = datetime.now(UTC)
                closure = runtime.coordinator.close_activation(
                    activation_id=ids["activation_id"],
                    cutoff=cutoff,
                    position_zero=True,
                    open_order_refs=(),
                    external_activity_conflict=False,
                    fees_complete=True,
                    funding_complete=True,
                    user_takeover=False,
                    handover_command_ref=None,
                    fact_refs=fact_refs,
                    result_ref="B04_PRODUCT_DEMO_REVIEW",
                    observed_at=cutoff,
                )
                completed_activation = runtime.coordinator.get_activation_snapshot(
                    ids["activation_id"]
                )
                outcome = OutcomeApplicationService(app_connection, environment_id)
                review_id = review_id_for_activation(
                    environment_id,
                    ids["activation_id"],
                )
                first_review = outcome.read_review(review_id)["review"]
                with app_connection.transaction():
                    replay_review = outcome.update_activation_review(
                        ids["activation_id"],
                        fact_cutoff=cutoff,
                        observed_at=datetime.now(UTC),
                    )
                checks["closure_releases_and_creates_idempotent_demo_review"] = (
                    len(closure) == 64
                    and completed_activation.lifecycle.value == "COMPLETED"
                    and completed_activation.protection_state is ProtectionState.CLOSED
                    and first_review["primary_result"] == PrimaryResult.COMPLETED.value
                    and first_review["evidence_purpose"]
                    == EvidencePurpose.SYSTEM_MECHANISM_EVIDENCE.value
                    and first_review["review_version"] == replay_review.review_version
                    and first_review["content_digest"] == replay_review.content_digest
                )
                if not checks[
                    "closure_releases_and_creates_idempotent_demo_review"
                ]:
                    raise RuntimeError("PRODUCT_REVIEW_OR_CLOSURE_MISMATCH")

                action_rows = app_connection.execute(
                    """
                    SELECT action_kind, state, count(*)
                    FROM halpha.execution_action
                    WHERE environment_id = %s AND activation_id = %s
                    GROUP BY action_kind, state
                    ORDER BY action_kind, state
                    """,
                    (environment_id, ids["activation_id"]),
                ).fetchall()
                evidence["product_cycle"] = {
                    "quantity": quantity,
                    "entry_fill_count": len(entry_fills),
                    "entry_commission_count": entry_fees["commission_count"],
                    "entry_commission_supplement_query_count": entry_fees[
                        "supplement_query_count"
                    ],
                    "entry_commission_supplement_fact_count": entry_fees[
                        "supplement_fact_count"
                    ],
                    "exit_fill_count": exit_fees["fill_count"],
                    "exit_commission_count": exit_fees["commission_count"],
                    "exit_commission_supplement_query_count": exit_fees[
                        "supplement_query_count"
                    ],
                    "exit_commission_supplement_fact_count": exit_fees[
                        "supplement_fact_count"
                    ],
                    "protection_action_count": len(protection_ids),
                    "take_profit_action_count": len(take_profit_ids),
                    "cancel_action_count": cancel_action_count,
                    "algo_working_query_count": algo_working_query_count,
                    "venue_fact_count": len(fact_refs),
                    "terminal_action_summary": [
                        {"kind": str(row[0]), "state": str(row[1]), "count": int(row[2])}
                        for row in action_rows
                    ],
                    "review_primary_result": first_review["primary_result"],
                    "review_evidence_purpose": first_review["evidence_purpose"],
                    "records_retained_as_append_only_product_evidence": True,
                }
                terminal_proven = True
                evidence["flow_stage"] = "COMPLETED"
                evidence["stage"] = "COMPLETED"
            except Exception as exc:
                evidence["flow_stage"] = flow_stage
                errors.append(
                    f"PRODUCT_DEMO_FLOW_FAILED:{flow_stage}:{_safe_error_reason(exc)}"
                )
                if account_api is not None:
                    try:
                        terminal_proven = await _attempt_recovery_to_clear(
                            runtime,
                            account_api,
                            environment_id=environment_id,
                            account_ref=account_ref,
                            activation_id=ids["activation_id"],
                            tracked_target_actions=tracked_target_actions,
                            anchor_action_id=entry_action_id,
                            conservative_price=conservative_price,
                            available_margin=available_margin,
                            margin_mode=margin_mode,
                            leverage=leverage,
                        )
                        checks["failure_recovery_uses_product_gate_and_clears_venue"] = (
                            terminal_proven
                        )
                    except Exception as recovery_exc:
                        errors.append(
                            "PRODUCT_DEMO_RECOVERY_FAILED:"
                            f"{_safe_error_reason(recovery_exc)}"
                        )
                        terminal_proven = False
            finally:
                stop.set()

        def on_ready(_runtime_evidence: dict[str, object]) -> None:
            nonlocal flow_task
            checks["product_runtime_reconciliation_precedes_ready"] = (
                runtime is not None and runtime.recovery_complete
            )
            checks["live_history_warmup_precedes_product_ready"] = (
                runtime is not None and runtime.strategy_history_warmup_complete
            )
            flow_task = runtime.node.get_event_loop().create_task(product_flow())

        evidence["stage"] = "RUNNING_PRODUCT_DEMO"
        runtime.run_until_stop(stop.wait, on_ready=on_ready)
        if flow_task is not None and not flow_task.cancelled():
            flow_task.result()
    except Exception as exc:
        errors.append(f"PRODUCT_DEMO_PROBE_FAILED:{_safe_error_reason(exc)}")
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
        if not terminal_proven and bool(evidence["venue_write_performed"]):
            evidence["recovery_environment_ref"] = environment_id
        evidence["venue_terminal_clear_proven"] = terminal_proven
        app_connection.close()
        try:
            retained = _retained_product_records(environment_id)
            evidence["retained_product_records"] = retained
            product_cycle = evidence.get("product_cycle")
            if isinstance(product_cycle, dict):
                expected_actions = sum(
                    int(item["count"])
                    for item in product_cycle["terminal_action_summary"]
                )
                expected_facts = int(product_cycle["venue_fact_count"])
                retained_matches = (
                    retained["execution_action_count"] == expected_actions
                    and retained["venue_fact_count"] == expected_facts
                    and retained["review_version_count"] >= 1
                )
            else:
                retained_matches = (
                    retained["activation_count"] >= 1
                    and (
                        not bool(evidence["venue_write_performed"])
                        or (
                            retained["execution_action_count"] >= 1
                            and retained["venue_fact_count"] >= 1
                        )
                    )
                )
            checks["product_evidence_records_retained_not_archived"] = (
                retained_matches
            )
        except Exception as exc:
            checks["product_evidence_records_retained_not_archived"] = False
            errors.append(
                f"PRODUCT_RETENTION_CHECK_FAILED:{_safe_error_reason(exc)}"
            )
        api_key_value = ""
        api_secret_value = ""

    if not all(checks.values()) and not errors:
        errors.append("PRODUCT_DEMO_REQUIRED_CHECK_FAILED")
    evidence["source_sha256"] = source_sha256_at_start
    try:
        checks["source_stable_during_qualification"] = (
            capture_source_sha256(ROOT, PRODUCT_SOURCE_PATTERNS)
            == source_sha256_at_start
        )
    except SourceBindingError as exc:
        checks["source_stable_during_qualification"] = False
        errors.append(f"PRODUCT_SOURCE_BINDING_FAILED:{exc}")
    evidence["observed_at"] = datetime.now(UTC).isoformat()
    evidence["status"] = (
        "QUALIFIED"
        if not errors and all(checks.values()) and terminal_proven
        else "REJECTED"
    )
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
        newline="\n",
    )
    print(json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if evidence["status"] == "QUALIFIED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
