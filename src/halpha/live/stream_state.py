from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import sqlite3
from pathlib import Path
from typing import Any

from halpha.runtime.state_store import (
    apply_runtime_state_migrations,
    open_runtime_state_connection,
    runtime_state_transaction,
)


LIVE_STREAM_STATE_KEY = "live_stream_state"
LIVE_STREAM_ARTIFACT = "live_stream_state"


@dataclass(frozen=True)
class LiveStreamStateRepository:
    config_path: Path

    def list_states(self) -> list[dict[str, Any]]:
        state = self._read_state()
        streams = state.get("streams")
        if not isinstance(streams, dict):
            return []
        return [
            dict(item)
            for _, item in sorted(streams.items())
            if isinstance(item, dict)
        ]

    def get_state(self, target_key: str) -> dict[str, Any] | None:
        state = self._read_state()
        streams = state.get("streams")
        if not isinstance(streams, dict):
            return None
        item = streams.get(target_key)
        return dict(item) if isinstance(item, dict) else None

    def upsert_state(self, stream_state: dict[str, Any]) -> dict[str, Any]:
        target_key = _required_text(stream_state.get("target_key"), "target_key")
        state = self._read_state()
        streams = state.setdefault("streams", {})
        if not isinstance(streams, dict):
            streams = {}
            state["streams"] = streams
        normalized = _normalize_stream_state(stream_state)
        streams[target_key] = normalized
        self._write_state(state)
        return normalized

    def _read_state(self) -> dict[str, Any]:
        try:
            with closing(open_runtime_state_connection(config_path=self.config_path)) as connection:
                apply_runtime_state_migrations(connection)
                row = connection.execute(
                    "SELECT value FROM runtime_state_metadata WHERE key = ?",
                    (LIVE_STREAM_STATE_KEY,),
                ).fetchone()
        except sqlite3.Error:
            return _empty_state()
        if row is None:
            return _empty_state()
        try:
            loaded = json.loads(str(row[0]))
        except json.JSONDecodeError:
            return _empty_state()
        if not isinstance(loaded, dict):
            return _empty_state()
        loaded.setdefault("schema_version", 1)
        loaded.setdefault("artifact_type", LIVE_STREAM_ARTIFACT)
        if not isinstance(loaded.get("streams"), dict):
            loaded["streams"] = {}
        return loaded

    def _write_state(self, state: dict[str, Any]) -> None:
        now_text = _format_utc(datetime.now(timezone.utc))
        payload = {
            "schema_version": 1,
            "artifact_type": LIVE_STREAM_ARTIFACT,
            "updated_at": now_text,
            "streams": state.get("streams") if isinstance(state.get("streams"), dict) else {},
        }
        text = json.dumps(payload, ensure_ascii=True, sort_keys=True)
        with closing(open_runtime_state_connection(config_path=self.config_path)) as connection:
            apply_runtime_state_migrations(connection, now=now_text)
            with runtime_state_transaction(connection):
                connection.execute(
                    """
                    INSERT OR REPLACE INTO runtime_state_metadata (key, value, updated_at)
                    VALUES (?, ?, ?)
                    """,
                    (LIVE_STREAM_STATE_KEY, text, now_text),
                )


def _normalize_stream_state(stream_state: dict[str, Any]) -> dict[str, Any]:
    target_key = _required_text(stream_state.get("target_key"), "target_key")
    data_type = _required_text(stream_state.get("data_type"), "data_type")
    target = stream_state.get("target") if isinstance(stream_state.get("target"), dict) else {}
    status = _required_text(stream_state.get("status"), "status")
    normalized = {
        "target_key": target_key,
        "data_type": data_type,
        "source": _optional_text(target.get("source")),
        "symbol": _optional_text(target.get("symbol")),
        "timeframe": _optional_text(target.get("timeframe")),
        "target": target,
        "enabled": stream_state.get("enabled") is True,
        "transport": "websocket",
        "status": status,
        "stream_name": _optional_text(stream_state.get("stream_name")),
        "endpoint": _optional_text(stream_state.get("endpoint")),
        "connected_at": _optional_text(stream_state.get("connected_at")),
        "last_event_at": _optional_text(stream_state.get("last_event_at")),
        "last_closed_candle_at": _optional_text(stream_state.get("last_closed_candle_at")),
        "backfill_required": stream_state.get("backfill_required") is True,
        "backfill_since": _optional_text(stream_state.get("backfill_since")),
        "next_reconnect_at": _optional_text(stream_state.get("next_reconnect_at")),
        "reconnect_count": _non_negative_int(stream_state.get("reconnect_count")),
        "warnings": _strings(stream_state.get("warnings")),
        "errors": _strings(stream_state.get("errors")),
        "updated_at": _optional_text(stream_state.get("updated_at")) or _format_utc(datetime.now(timezone.utc)),
    }
    return normalized


def _empty_state() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "artifact_type": LIVE_STREAM_ARTIFACT,
        "updated_at": None,
        "streams": {},
    }


def _required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Live stream state requires {field}.")
    return value.strip()


def _optional_text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()][:20]


def _non_negative_int(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def _format_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
