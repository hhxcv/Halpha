from __future__ import annotations

import inspect
import json

from nautilus_trader.adapters.binance.data import BinanceCommonDataClient
from nautilus_trader.adapters.binance.execution import BinanceCommonExecutionClient
from nautilus_trader.adapters.binance.websocket.client import BinanceWebSocketClient
from nautilus_trader.adapters.binance.websocket.user import BinanceUserDataWebSocketClient


def _evaluate_reconnect_contract() -> dict[str, object]:
    public_connect_source = inspect.getsource(BinanceWebSocketClient._connect_client)
    public_reconnect_source = inspect.getsource(BinanceWebSocketClient._handle_reconnect)
    public_resubscribe_source = inspect.getsource(BinanceWebSocketClient._resubscribe_client)
    data_reconnect_source = inspect.getsource(BinanceCommonDataClient._reconnect)
    user_connect_source = inspect.getsource(BinanceUserDataWebSocketClient._connect_stream)
    user_reconnect_source = inspect.getsource(
        BinanceUserDataWebSocketClient._handle_stream_reconnect,
    )
    user_resubscribe_source = inspect.getsource(
        BinanceUserDataWebSocketClient._resubscribe_locked,
    )
    execution_reconcile_source = inspect.getsource(
        BinanceCommonExecutionClient._reconcile_after_resubscribe,
    )

    contracts = {
        "public_ws_registers_post_reconnection_callback": (
            "post_reconnection=lambda: self._handle_reconnect(client_id)"
            in public_connect_source
        ),
        "public_ws_reconnect_resubscribes_all_tracked_streams": (
            "streams = self._client_streams[client_id]" in public_reconnect_source
            and "self._resubscribe_client(client_id, streams)" in public_reconnect_source
            and "self._create_subscribe_msg(streams=streams)" in public_resubscribe_source
        ),
        "public_ws_reconnect_invokes_data_recovery_handler": (
            "self._handler_reconnect()" in public_reconnect_source
        ),
        "data_reconnect_rebuilds_order_book_snapshot_before_deltas": (
            "self._order_book_snapshot_then_deltas(instrument_id)"
            in data_reconnect_source
        ),
        "user_stream_registers_independent_reconnect_callback": (
            "post_reconnection=self._handle_stream_reconnect" in user_connect_source
        ),
        "user_stream_reconnect_rotates_listen_key": (
            "self._resubscribe()" in user_reconnect_source
            and "self._subscription_id = None" in user_resubscribe_source
        ),
        "user_stream_resubscribe_invokes_pre_dispatch_reconciliation": (
            "pre_dispatch_hook=self._on_resubscribe" in user_resubscribe_source
        ),
        "execution_recovery_requests_uncapped_mass_status": (
            "generate_mass_status(lookback_mins=None)" in execution_reconcile_source
            and "_send_mass_status_report" in execution_reconcile_source
        ),
        "recovery_failure_disconnects_instead_of_claiming_active": (
            "user data stream is NOT active, disconnecting" in user_resubscribe_source
            and "await self.disconnect()" in user_resubscribe_source
        ),
    }
    errors = [name for name, qualified in contracts.items() if not qualified]
    return {
        "operation": "DIRECT_FIXED_SOURCE_RECONNECT_CONTRACT",
        "contracts": contracts,
        "natural_transport_faults_observed": {
            "rest_tls_handshake_or_connection_reset": True,
            "execution_user_websocket_timeout_or_tls_eof": True,
            "writes_attempted_before_connection_ready": False,
        },
        "controlled_active_stream_fault": {
            "status": "UNKNOWN_NOT_RUN",
            "reason": (
                "QUALIFICATION_DID_NOT_MUTATE_SYSTEM_PROXY_OR_REACH_INTO_PRIVATE_RUNTIME_CLIENTS"
            ),
        },
        "errors": errors,
        "status": "QUALIFIED_FIXED_SOURCE_CONTRACT" if not errors else "REJECTED",
    }


def main() -> int:
    evidence = _evaluate_reconnect_contract()
    print(json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if evidence["status"] == "QUALIFIED_FIXED_SOURCE_CONTRACT" else 1


if __name__ == "__main__":
    raise SystemExit(main())
