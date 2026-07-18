"""Qualify the production Halpha strategy adapter in live and backtest runtimes."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import inspect
import json
from pathlib import Path
from typing import Any

from nautilus_trader.backtest.config import BacktestEngineConfig
from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.common import Environment
from nautilus_trader.common.config import LoggingConfig
from nautilus_trader.live.config import LiveDataEngineConfig, LiveExecEngineConfig
from nautilus_trader.live.config import TradingNodeConfig
from nautilus_trader.live.node import TradingNode
from nautilus_trader.model.identifiers import TraderId

from halpha.capital.models import AuthorityClass, EnvironmentKind
from halpha.domain_values import content_digest
from halpha.planning.adapter import HalphaStrategyAdapter
from halpha.planning.models import PlanActivation, ProtectionState
from halpha.planning.registry import OneShotParameters
from halpha.planning.strategies.one_shot import (
    ActivationStrategyState,
    EntryEvaluationInput,
    InstrumentQuantityRules,
    NativeIndicatorSnapshot,
    OneShotDonchianAtrLogic,
    StrategyProposal,
)
from halpha.planning.transitions import (
    bar_source_identity,
    proposed_action_from_strategy_proposal,
)


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / "build/qualification/b02-strategy-adapter-parity.json"
ACTIVATION_ID = "b02-production-adapter-parity"


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _evaluation() -> EntryEvaluationInput:
    decision_at = datetime(2026, 7, 17, 9, tzinfo=UTC)
    source_cutoff = decision_at - timedelta(minutes=1)
    source_cutoff_ns = int(source_cutoff.timestamp() * 1_000_000_000)
    source_basis = {
        "instrument_id": "BTCUSDT-PERP.BINANCE",
        "source_identity": bar_source_identity(
            activation_id=ACTIVATION_ID,
            rule_id="ENTRY_BREAKOUT",
            bar_type="BTCUSDT-PERP.BINANCE-15-MINUTE-LAST-INTERNAL",
            ts_event_ns=source_cutoff_ns,
        ),
        "source_cutoff": source_cutoff,
        "confirmation_closes": ["101", "101.5"],
        "indicator_digest": "a" * 64,
        "reference_price": "101.5",
        "reference_source": "QUALIFICATION_NORMALIZED_INPUT",
    }
    return EntryEvaluationInput(
        activation_id=ACTIVATION_ID,
        instrument_id=source_basis["instrument_id"],
        source_identity=source_basis["source_identity"],
        source_cutoff=source_cutoff,
        input_digest=content_digest(source_basis),
        decision_at=decision_at,
        valid_until=decision_at + timedelta(seconds=30),
        confirmation_closes=tuple(source_basis["confirmation_closes"]),
        indicators=NativeIndicatorSnapshot(
            upper="100",
            lower="90",
            atr="5",
            initialized=True,
            source_digest=source_basis["indicator_digest"],
            source_cutoff_ns=source_cutoff_ns,
        ),
        reference_price=source_basis["reference_price"],
        reference_source=source_basis["reference_source"],
        max_allowed_loss="100",
        max_notional="1000",
        max_margin="200",
        effective_leverage="5",
        taker_fee_rate="0.0006",
        rules=InstrumentQuantityRules(
            step_size="0.001",
            price_tick_size="0.1",
            min_quantity="0.001",
            max_market_quantity="100",
            min_notional="5",
        ),
    )


def _activation() -> PlanActivation:
    observed_at = datetime(2026, 7, 17, 8, tzinfo=UTC)
    return PlanActivation(
        activation_id=ACTIVATION_ID,
        environment_id="b02-demo",
        environment_kind=EnvironmentKind.DEMO,
        authority_class=AuthorityClass.DEMO_VALIDATION,
        plan_version_ref="b02-plan-version",
        authorization_version_ref="b02-authorization",
        allocation_ref="b02-allocation",
        account_ref="b02-account",
        instrument_ref="BTCUSDT-PERP",
        direction="LONG",
        strategy_id="ONE_SHOT_DONCHIAN_ATR_BREAKOUT",
        framework_strategy_id="HALPHA-B02-PARITY",
        target_exposure="0.01",
        rule_state={},
        protection_state=ProtectionState.NONE,
        created_at=observed_at,
        updated_at=observed_at,
    )


def _adapter(proposals: list[dict[str, Any]]) -> HalphaStrategyAdapter:
    def capture(proposal: StrategyProposal) -> None:
        proposals.append(proposal.model_dump(mode="json"))

    return HalphaStrategyAdapter(
        activation_id=ACTIVATION_ID,
        logic=OneShotDonchianAtrLogic(OneShotParameters(direction="LONG")),
        state_provider=ActivationStrategyState,
        proposal_sink=capture,
    )


async def _evaluate_while_live(
    node: TradingNode,
    adapter: HalphaStrategyAdapter,
    proposals: list[dict[str, Any]],
) -> None:
    try:
        for _ in range(200):
            if node.is_running():
                adapter.evaluate_normalized_entry(_evaluation())
                break
            await asyncio.sleep(0.01)
        for _ in range(200):
            if proposals:
                return
            await asyncio.sleep(0.01)
        raise TimeoutError("LIVE_PRODUCTION_ADAPTER_PROPOSAL_TIMEOUT")
    finally:
        node.stop()


def _live_path() -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    proposals: list[dict[str, Any]] = []
    adapter = _adapter(proposals)
    evidence: dict[str, Any] = {
        "adapter_class": f"{type(adapter).__module__}.{type(adapter).__qualname__}",
        "logic_class": f"{type(adapter._logic).__module__}.{type(adapter._logic).__qualname__}",
        "strategy_id": str(adapter.id),
        "node_built": False,
        "node_stopped": False,
        "node_disposed": False,
    }
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    node: TradingNode | None = None
    try:
        node = TradingNode(
            config=TradingNodeConfig(
                environment=Environment.LIVE,
                trader_id=TraderId("B02-PARITY-001"),
                cache=None,
                message_bus=None,
                emulator=None,
                streaming=None,
                catalogs=[],
                load_state=False,
                save_state=False,
                logging=LoggingConfig(log_level="ERROR", log_colors=False),
                data_engine=LiveDataEngineConfig(validate_data_sequence=True),
                exec_engine=LiveExecEngineConfig(
                    reconciliation=True,
                    inflight_check_interval_ms=0,
                    open_check_interval_secs=10.0,
                    open_check_open_only=True,
                    generate_missing_orders=True,
                ),
                data_clients={},
                exec_clients={},
                timeout_connection=2.0,
                timeout_reconciliation=2.0,
                timeout_portfolio=2.0,
                timeout_disconnection=2.0,
                timeout_post_stop=0.1,
                timeout_shutdown=2.0,
            ),
            loop=loop,
        )
        node.build()
        evidence["node_built"] = node.is_built()
        node.trader.add_strategy(adapter)
        observer = loop.create_task(_evaluate_while_live(node, adapter, proposals))
        node.run(raise_exception=True)
        observer.result()
        evidence["registered_adapter_classes"] = [
            f"{type(strategy).__module__}.{type(strategy).__qualname__}"
            for strategy in node.trader.strategies()
        ]
        evidence["proposal_count"] = len(proposals)
        evidence["proposal"] = proposals[0] if proposals else None
        evidence["proposed_action"] = (
            proposed_action_from_strategy_proposal(
                _activation(),
                StrategyProposal.model_validate(proposals[0]),
            ).model_dump(mode="json")
            if proposals
            else None
        )
        evidence["node_stopped"] = not node.is_running()
        pending = tuple(task for task in asyncio.all_tasks(loop) if not task.done())
        for task in pending:
            task.cancel()
        if pending:
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        evidence["pending_loop_tasks_before_dispose"] = len(
            tuple(task for task in asyncio.all_tasks(loop) if not task.done())
        )
        node.dispose()
        evidence["node_disposed"] = True
    except Exception as exc:
        errors.append(f"LIVE_PRODUCTION_ADAPTER_FAILED:{type(exc).__name__}")
        if node is not None:
            try:
                node.stop()
                node.dispose()
                evidence["node_stopped"] = not node.is_running()
                evidence["node_disposed"] = True
            except Exception:
                pass
    finally:
        asyncio.set_event_loop(None)
        if not loop.is_closed():
            loop.close()
    return evidence, errors


def _backtest_path() -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    proposals: list[dict[str, Any]] = []
    adapter = _adapter(proposals)
    evidence: dict[str, Any] = {
        "adapter_class": f"{type(adapter).__module__}.{type(adapter).__qualname__}",
        "logic_class": f"{type(adapter._logic).__module__}.{type(adapter._logic).__qualname__}",
        "strategy_id": str(adapter.id),
        "engine_disposed": False,
    }
    engine: BacktestEngine | None = None
    try:
        engine = BacktestEngine(
            BacktestEngineConfig(
                logging=LoggingConfig(log_level="ERROR", bypass_logging=True),
                run_analysis=False,
            )
        )
        engine.add_strategy(adapter)
        evidence["registered_adapter_classes"] = [
            f"{type(strategy).__module__}.{type(strategy).__qualname__}"
            for strategy in engine.trader.strategies()
        ]
        adapter.evaluate_normalized_entry(_evaluation())
        engine.run()
        evidence["proposal_count"] = len(proposals)
        evidence["proposal"] = proposals[0] if proposals else None
        evidence["proposed_action"] = (
            proposed_action_from_strategy_proposal(
                _activation(),
                StrategyProposal.model_validate(proposals[0]),
            ).model_dump(mode="json")
            if proposals
            else None
        )
    except Exception as exc:
        errors.append(f"BACKTEST_PRODUCTION_ADAPTER_FAILED:{type(exc).__name__}")
    finally:
        if engine is not None:
            try:
                engine.dispose()
                evidence["engine_disposed"] = True
            except Exception as exc:
                errors.append(f"BACKTEST_PRODUCTION_ADAPTER_DISPOSE_FAILED:{type(exc).__name__}")
    return evidence, errors


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    live, live_errors = _live_path()
    backtest, backtest_errors = _backtest_path()
    adapter_source = inspect.getsource(HalphaStrategyAdapter)
    logic_source = inspect.getsource(OneShotDonchianAtrLogic)
    class_name = "halpha.planning.adapter.HalphaStrategyAdapter"
    logic_name = "halpha.planning.strategies.one_shot.OneShotDonchianAtrLogic"
    checks = {
        "live_loaded_production_adapter": live.get("registered_adapter_classes") == [class_name],
        "backtest_loaded_production_adapter": backtest.get("registered_adapter_classes") == [class_name],
        "same_production_adapter_class": live.get("adapter_class") == backtest.get("adapter_class") == class_name,
        "same_production_logic_class": live.get("logic_class") == backtest.get("logic_class") == logic_name,
        "same_activation_strategy_id": live.get("strategy_id") == backtest.get("strategy_id"),
        "one_proposal_per_runtime": live.get("proposal_count") == backtest.get("proposal_count") == 1,
        "same_normalized_input_same_exact_proposal": live.get("proposal") == backtest.get("proposal"),
        "same_proposal_maps_to_same_proposed_action": (
            live.get("proposed_action") == backtest.get("proposed_action")
            and live.get("proposed_action") is not None
        ),
        "live_node_lifecycle_closed": all(
            live.get(field) is True for field in ("node_built", "node_stopped", "node_disposed")
        )
        and live.get("pending_loop_tasks_before_dispose") == 0,
        "backtest_engine_disposed": backtest.get("engine_disposed") is True,
        "adapter_b02_has_no_venue_write_calls": not any(
            token in adapter_source
            for token in ("submit_order(", "cancel_order(", "modify_order(", "close_position(")
        ),
        "pure_logic_has_no_framework_or_venue_write_calls": not any(
            token in logic_source
            for token in (
                "nautilus_trader",
                "submit_order",
                "cancel_order",
                "modify_order",
                "close_position",
                "TradingNode",
                "ExecutionClient",
            )
        ),
    }
    errors = [*live_errors, *backtest_errors]
    errors.extend(name for name, passed in checks.items() if not passed)
    report: dict[str, Any] = {
        "stage": "B02_PRODUCTION_STRATEGY_ADAPTER_PARITY",
        "scope": "NO_VENUE_CLIENTS_NO_PRODUCT_RECORDS",
        "normalized_input_digest": _evaluation().input_digest,
        "adapter_source_digest": sha256(adapter_source.encode("utf-8")).hexdigest(),
        "logic_source_digest": sha256(logic_source.encode("utf-8")).hexdigest(),
        "live": live,
        "backtest": backtest,
        "checks": checks,
        "errors": errors,
        "status": "QUALIFIED" if not errors else "REJECTED",
    }
    report["evidence_digest"] = sha256(_canonical(report)).hexdigest()
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
