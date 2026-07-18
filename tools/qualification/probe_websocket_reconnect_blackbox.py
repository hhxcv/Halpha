from __future__ import annotations

import asyncio
import base64
import hashlib
import json
from dataclasses import dataclass
from dataclasses import field

from nautilus_trader.adapters.binance.websocket.client import BinanceWebSocketClient
from nautilus_trader.common.component import LiveClock


WEBSOCKET_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


@dataclass
class ServerEvidence:
    connection_count: int = 0
    request_paths: list[str] = field(default_factory=list)
    first_connection_messages: list[dict[str, object]] = field(default_factory=list)
    second_connection_messages: list[dict[str, object]] = field(default_factory=list)
    second_connection_streams: set[str] = field(default_factory=set)
    server_errors: list[str] = field(default_factory=list)
    resubscribe_seen: asyncio.Event = field(default_factory=asyncio.Event)


async def _websocket_handshake(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
) -> str:
    request = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=5.0)
    text = request.decode("ascii")
    lines = text.split("\r\n")
    request_parts = lines[0].split(" ")
    if len(request_parts) != 3 or request_parts[0] != "GET":
        raise RuntimeError("INVALID_WEBSOCKET_REQUEST_LINE")
    headers: dict[str, str] = {}
    for line in lines[1:]:
        if not line or ":" not in line:
            continue
        name, value = line.split(":", 1)
        headers[name.strip().lower()] = value.strip()
    key = headers.get("sec-websocket-key")
    if key is None:
        raise RuntimeError("WEBSOCKET_KEY_MISSING")
    accept = base64.b64encode(
        hashlib.sha1(f"{key}{WEBSOCKET_GUID}".encode("ascii")).digest(),
    ).decode("ascii")
    response = (
        "HTTP/1.1 101 Switching Protocols\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Accept: {accept}\r\n"
        "\r\n"
    )
    writer.write(response.encode("ascii"))
    await writer.drain()
    return request_parts[1]


async def _read_frame(
    reader: asyncio.StreamReader,
) -> tuple[int, bytes]:
    header = await reader.readexactly(2)
    opcode = header[0] & 0x0F
    masked = bool(header[1] & 0x80)
    length = header[1] & 0x7F
    if length == 126:
        length = int.from_bytes(await reader.readexactly(2), "big")
    elif length == 127:
        length = int.from_bytes(await reader.readexactly(8), "big")
    mask = await reader.readexactly(4) if masked else b""
    payload = await reader.readexactly(length)
    if masked:
        payload = bytes(value ^ mask[index % 4] for index, value in enumerate(payload))
    return opcode, payload


def _server_close_frame() -> bytes:
    payload = (1012).to_bytes(2, "big")
    return bytes((0x88, len(payload))) + payload


async def _run_black_box() -> dict[str, object]:
    server_evidence = ServerEvidence()
    reconnect_callback_seen = asyncio.Event()

    async def handle_connection(
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        server_evidence.connection_count += 1
        connection_number = server_evidence.connection_count
        try:
            path = await _websocket_handshake(reader, writer)
            server_evidence.request_paths.append(path)
            while True:
                opcode, payload = await _read_frame(reader)
                if opcode == 8:
                    writer.write(_server_close_frame())
                    await writer.drain()
                    break
                if opcode != 1:
                    continue
                decoded = json.loads(payload)
                if not isinstance(decoded, dict):
                    raise RuntimeError("CLIENT_MESSAGE_NOT_OBJECT")
                if connection_number == 1:
                    server_evidence.first_connection_messages.append(decoded)
                    writer.write(_server_close_frame())
                    await writer.drain()
                    writer.close()
                    await writer.wait_closed()
                    return
                server_evidence.second_connection_messages.append(decoded)
                params = decoded.get("params")
                if (
                    decoded.get("method") == "SUBSCRIBE"
                    and isinstance(params, list)
                ):
                    server_evidence.second_connection_streams.update(
                        value for value in params if isinstance(value, str)
                    )
                    if server_evidence.second_connection_streams == {
                        "btcusdt@kline_1m",
                        "btcusdt@bookTicker",
                        "btcusdt@markPrice@1s",
                    }:
                        server_evidence.resubscribe_seen.set()
        except asyncio.IncompleteReadError:
            pass
        except Exception as exc:
            server_evidence.server_errors.append(type(exc).__name__)
        finally:
            if not writer.is_closing():
                writer.close()
                await writer.wait_closed()

    server = await asyncio.start_server(handle_connection, "127.0.0.1", 0)
    socket = server.sockets[0]
    port = socket.getsockname()[1]

    async def on_reconnect() -> None:
        reconnect_callback_seen.set()

    client = BinanceWebSocketClient(
        clock=LiveClock(),
        base_url=f"ws://127.0.0.1:{port}",
        handler=lambda _raw: None,
        handler_reconnect=on_reconnect,
        loop=asyncio.get_running_loop(),
        proxy_url=None,
    )
    wait_timed_out = False
    try:
        await client.subscribe_bars("BTCUSDT", "1m")
        await client.subscribe_book_ticker("BTCUSDT")
        await asyncio.sleep(0.25)
        await client.subscribe_mark_price("BTCUSDT", speed=1000)
        try:
            await asyncio.wait_for(server_evidence.resubscribe_seen.wait(), timeout=20.0)
            await asyncio.wait_for(reconnect_callback_seen.wait(), timeout=5.0)
        except TimeoutError:
            wait_timed_out = True
    finally:
        await client.disconnect()
        server.close()
        await server.wait_closed()
        await asyncio.sleep(0.05)

    expected_streams = [
        "btcusdt@kline_1m",
        "btcusdt@bookTicker",
        "btcusdt@markPrice@1s",
    ]
    return {
        "connection_count": server_evidence.connection_count,
        "request_paths": server_evidence.request_paths,
        "first_connection_messages": server_evidence.first_connection_messages,
        "second_connection_messages": server_evidence.second_connection_messages,
        "second_connection_streams": sorted(server_evidence.second_connection_streams),
        "server_errors": server_evidence.server_errors,
        "client_subscriptions_after_reconnect": client.subscriptions,
        "expected_streams": expected_streams,
        "reconnect_callback_seen": reconnect_callback_seen.is_set(),
        "all_streams_present_after_reconnect": (
            sorted(server_evidence.second_connection_streams) == sorted(expected_streams)
        ),
        "wait_timed_out": wait_timed_out,
        "system_proxy_modified": False,
        "private_client_runtime_fields_accessed": False,
    }


async def _evaluate_black_box() -> dict[str, object]:
    errors: list[str] = []
    try:
        black_box = await _run_black_box()
    except Exception as exc:
        black_box = {"probe_exception_type": type(exc).__name__}
        errors.append(f"WEBSOCKET_RECONNECT_BLACK_BOX_FAILED:{type(exc).__name__}")
    if not errors:
        if black_box["connection_count"] < 2:
            errors.append("AUTOMATIC_RECONNECT_NOT_OBSERVED")
        if black_box["server_errors"]:
            errors.append("LOCAL_WEBSOCKET_SERVER_ERROR")
        if black_box["wait_timed_out"]:
            errors.append("RECONNECT_OBSERVATION_TIMEOUT")
        if not black_box["reconnect_callback_seen"]:
            errors.append("RECONNECT_CALLBACK_NOT_OBSERVED")
        if not black_box["all_streams_present_after_reconnect"]:
            errors.append("ALL_STREAMS_NOT_RESUBSCRIBED")
        if black_box["client_subscriptions_after_reconnect"] != black_box["expected_streams"]:
            errors.append("CLIENT_SUBSCRIPTION_STATE_CHANGED")
        if black_box["system_proxy_modified"]:
            errors.append("SYSTEM_PROXY_WAS_MODIFIED")
        if black_box["private_client_runtime_fields_accessed"]:
            errors.append("PRIVATE_RUNTIME_FIELDS_ACCESSED")
    return {
        "stage": "B00_CONTROLLED_WEBSOCKET_RECONNECT_BLACK_BOX",
        "black_box": black_box,
        "errors": errors,
        "status": "QUALIFIED" if not errors else "REJECTED",
    }


def main() -> int:
    evidence = asyncio.run(_evaluate_black_box())
    print(json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if evidence["status"] == "QUALIFIED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
