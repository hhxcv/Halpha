from __future__ import annotations

import asyncio
import inspect
import json
import subprocess
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from nautilus_trader.common import Environment
from nautilus_trader.common.config import LoggingConfig
from nautilus_trader.live.config import LiveDataEngineConfig
from nautilus_trader.live.config import LiveExecEngineConfig
from nautilus_trader.live.config import TradingNodeConfig
from nautilus_trader.live.node import TradingNode
from nautilus_trader.model.identifiers import TraderId
from nautilus_trader.trading.config import StrategyConfig

from tools.qualification.nautilus_fixtures import LiveProposalQualificationStrategy


async def _observe_proposal(
    node: TradingNode,
    strategy: LiveProposalQualificationStrategy,
) -> None:
    try:
        for _ in range(200):
            if node.is_running() and strategy.proposals:
                return
            await asyncio.sleep(0.01)
        raise TimeoutError("LIVE_PROPOSAL_TIMEOUT")
    finally:
        node.stop()


def _live_harness_proposal() -> tuple[dict[str, object], list[str]]:
    errors: list[str] = []
    evidence: dict[str, object] = {
        "node_built": False,
        "node_stopped": False,
        "node_disposed": False,
        "proposal_count": 0,
    }
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    node: TradingNode | None = None
    strategy = LiveProposalQualificationStrategy(
        config=StrategyConfig(
            strategy_id="DIRECTLIVEPROPOSAL",
            order_id_tag="001",
            external_order_claims=None,
            manage_contingent_orders=False,
            manage_gtd_expiry=False,
            manage_stop=False,
        ),
    )
    try:
        node = TradingNode(
            config=TradingNodeConfig(
                environment=Environment.LIVE,
                trader_id=TraderId("DIRECT-PARITY-001"),
                cache=None,
                message_bus=None,
                emulator=None,
                streaming=None,
                catalogs=[],
                load_state=False,
                save_state=False,
                logging=LoggingConfig(log_level="ERROR", log_colors=False),
                data_engine=LiveDataEngineConfig(
                    time_bars_interval_type="left-open",
                    time_bars_timestamp_on_close=True,
                    time_bars_skip_first_non_full_bar=True,
                    time_bars_build_with_no_updates=False,
                    validate_data_sequence=True,
                ),
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
        node.trader.add_strategy(strategy)
        observer = loop.create_task(_observe_proposal(node, strategy))
        node.run(raise_exception=True)
        if observer.done():
            observer.result()
        else:
            errors.append("LIVE_PROPOSAL_OBSERVER_NOT_COMPLETED")
        evidence["proposal_count"] = len(strategy.proposals)
        evidence["proposal"] = strategy.proposals[0] if strategy.proposals else None
        evidence["node_stopped"] = not node.is_running()
        node.dispose()
        evidence["node_disposed"] = True
    except Exception as exc:
        errors.append(f"LIVE_PROPOSAL_HARNESS_FAILED:{type(exc).__name__}")
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


def _backtest_proposal() -> tuple[dict[str, object], list[str]]:
    completed = subprocess.run(
        [sys.executable, str(REPOSITORY_ROOT / "tools/qualification/probe_backtest_stack.py")],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return {}, ["BACKTEST_PROPOSAL_PROBE_FAILED"]
    try:
        evidence = json.loads(completed.stdout)
    except ValueError:
        return {}, ["BACKTEST_PROPOSAL_OUTPUT_NOT_JSON"]
    proposals = evidence.get("engine", {}).get("proposals", [])
    if evidence.get("status") != "QUALIFIED" or len(proposals) != 1:
        return {}, ["BACKTEST_PROPOSAL_NOT_QUALIFIED"]
    return {
        "proposal_count": len(proposals),
        "proposal": proposals[0],
        "product_runtime_or_records_created": evidence.get(
            "product_runtime_or_records_created",
        ),
    }, []


def main() -> int:
    live, live_errors = _live_harness_proposal()
    backtest, backtest_errors = _backtest_proposal()
    errors = [*live_errors, *backtest_errors]
    live_proposal = live.get("proposal") or {}
    backtest_proposal = backtest.get("proposal") or {}
    common_semantic_fields = (
        "strategy_id",
        "instrument_id",
        "direction",
        "action",
        "risk_direction",
    )
    source = inspect.getsource(LiveProposalQualificationStrategy)
    checks = {
        "live_one_proposal": live.get("proposal_count") == 1,
        "backtest_one_proposal": backtest.get("proposal_count") == 1,
        "same_structure": set(live_proposal) == set(backtest_proposal),
        "same_value_types": {
            key: type(value).__name__ for key, value in live_proposal.items()
        }
        == {key: type(value).__name__ for key, value in backtest_proposal.items()},
        "same_common_semantics": all(
            live_proposal.get(field) == backtest_proposal.get(field)
            for field in common_semantic_fields
        ),
        "reference_source_explicitly_differs": (
            live_proposal.get("reference_source") == "LIVE_HARNESS_REFERENCE_PROXY"
            and backtest_proposal.get("reference_source") == "BACKTEST_LAST_BAR_PROXY"
        ),
        "live_node_built": live.get("node_built") is True,
        "live_node_stopped": live.get("node_stopped") is True,
        "live_node_disposed": live.get("node_disposed") is True,
        "live_adapter_has_no_order_write_api": not any(
            token in source
            for token in (
                "submit_order",
                "cancel_order",
                "modify_order",
                "close_position",
                "market_exit",
            )
        ),
        "no_product_runtime_or_records": backtest.get("product_runtime_or_records_created")
        is False,
    }
    errors.extend(name for name, passed in checks.items() if not passed)
    evidence = {
        "operation": "DIRECT_STRATEGY_PROPOSAL_PARITY",
        "scope": "QUALIFICATION_FIXTURE_ONLY",
        "live_harness": live,
        "backtest_harness": backtest,
        "checks": checks,
        "errors": errors,
        "status": "QUALIFIED" if not errors else "REJECTED",
    }
    print(json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
