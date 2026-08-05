from __future__ import annotations

import asyncio
import json
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
from nautilus_trader.trading.config import ImportableControllerConfig
from nautilus_trader.trading.config import StrategyConfig

from tools.qualification.nautilus_fixtures import QualificationController
from tools.qualification.nautilus_fixtures import QualificationStrategy


async def _exercise_controller(
    node: TradingNode,
    controller: QualificationController,
    evidence: dict[str, object],
) -> None:
    try:
        for _ in range(200):
            if node.is_running():
                break
            await asyncio.sleep(0.01)
        if not node.is_running():
            raise RuntimeError("NODE_START_TIMEOUT")

        strategy = QualificationStrategy(
            config=StrategyConfig(
                strategy_id="DIRECTQUAL",
                order_id_tag="001",
                external_order_claims=None,
                manage_contingent_orders=False,
                manage_gtd_expiry=False,
                manage_stop=False,
            ),
        )
        controller.create_strategy(strategy, start=True)
        evidence["controller_add"] = strategy in node.trader.strategies()
        evidence["controller_start"] = bool(strategy.is_running)

        controller.stop_strategy(strategy)
        evidence["controller_stop"] = bool(strategy.is_stopped)
        controller.remove_strategy(strategy)
        evidence["controller_remove"] = strategy not in node.trader.strategies()
    finally:
        node.stop()


def main() -> int:
    evidence: dict[str, object] = {
        "operation": "INITIALIZING",
        "controller_add": False,
        "controller_start": False,
        "controller_stop": False,
        "controller_remove": False,
        "node_built": False,
        "node_started": False,
        "node_stopped": False,
        "node_disposed": False,
    }
    errors: list[str] = []
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    node: TradingNode | None = None
    try:
        evidence["operation"] = "CONFIGURING"
        config = TradingNodeConfig(
            environment=Environment.LIVE,
            trader_id=TraderId("DIRECT-QUAL-001"),
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
            controller=ImportableControllerConfig(
                controller_path="tools.qualification.nautilus_fixtures:QualificationController",
                config_path="nautilus_trader.live.config:ControllerConfig",
                config={},
            ),
            timeout_connection=2.0,
            timeout_reconciliation=2.0,
            timeout_portfolio=2.0,
            timeout_disconnection=2.0,
            timeout_post_stop=0.1,
            timeout_shutdown=2.0,
        )
        evidence["operation"] = "CONSTRUCTING_NODE"
        node = TradingNode(config=config, loop=loop)
        evidence["operation"] = "BUILDING_NODE"
        node.build()
        evidence["node_built"] = node.is_built()
        controllers = [actor for actor in node.trader.actors() if isinstance(actor, QualificationController)]
        if len(controllers) != 1:
            raise RuntimeError("CONTROLLER_COUNT_MISMATCH")
        evidence["operation"] = "RUNNING_NODE"
        controller_task = loop.create_task(_exercise_controller(node, controllers[0], evidence))
        node.run(raise_exception=True)
        if controller_task.done():
            controller_task.result()
        else:
            errors.append("CONTROLLER_TASK_NOT_COMPLETED")
        evidence["node_started"] = all(
            bool(evidence[key])
            for key in ("controller_add", "controller_start")
        )
        evidence["node_stopped"] = not node.is_running()
        node.dispose()
        evidence["node_disposed"] = True
        evidence["operation"] = "COMPLETED"
    except Exception as exc:  # pragma: no cover - evidence contains type only
        errors.append(f"NAUTILUS_LIFECYCLE_FAILED:{type(exc).__name__}")
        if node is not None:
            try:
                node.stop()
                node.dispose()
            except Exception:
                pass
    finally:
        asyncio.set_event_loop(None)
        if not loop.is_closed():
            loop.close()

    required = (
        "controller_add",
        "controller_start",
        "controller_stop",
        "controller_remove",
        "node_built",
        "node_started",
        "node_stopped",
        "node_disposed",
    )
    if not all(bool(evidence[key]) for key in required) and not errors:
        errors.append("NAUTILUS_LIFECYCLE_ASSERTION_FAILED")
    evidence["errors"] = errors
    evidence["status"] = "QUALIFIED" if not errors else "REJECTED"
    print(json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
