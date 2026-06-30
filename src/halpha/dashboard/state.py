from __future__ import annotations

from contextlib import closing, suppress
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any

from halpha.dashboard.settings import dashboard_config_ref
from halpha.runtime.state_store import (
    RUNTIME_STATE_MIGRATIONS,
    StateStoreMigration,
    apply_runtime_state_migrations,
    open_runtime_state_connection,
    runtime_state_transaction,
)


DASHBOARD_UI_PREFERENCES_MIGRATION_VERSION = 8
DASHBOARD_UI_PREFERENCES_SCHEMA_VERSION = 1
DASHBOARD_SELECTED_CONFIG_KEY = "selected_config"
DASHBOARD_CONFIG_HISTORY_LIMIT = 12


DASHBOARD_UI_PREFERENCE_MIGRATIONS = (
    StateStoreMigration(
        version=DASHBOARD_UI_PREFERENCES_MIGRATION_VERSION,
        name="dashboard_ui_preferences",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS dashboard_ui_preferences (
              preference_key TEXT PRIMARY KEY,
              value_json TEXT NOT NULL,
              updated_at TEXT NOT NULL
            )
            """,
        ),
    ),
)


def apply_dashboard_ui_preference_migrations(
    connection: sqlite3.Connection,
    *,
    now: datetime | str | None = None,
) -> None:
    apply_runtime_state_migrations(
        connection,
        migrations=RUNTIME_STATE_MIGRATIONS + DASHBOARD_UI_PREFERENCE_MIGRATIONS,
        now=now,
    )


def write_dashboard_selected_config_state(
    config_path: Path,
    *,
    runtime_root: Path | None = None,
    now: datetime | str | None = None,
) -> dict[str, Any]:
    timestamp = _format_utc(now)
    with closing(open_runtime_state_connection(runtime_root=runtime_root, config_path=config_path)) as connection:
        apply_dashboard_ui_preference_migrations(connection, now=timestamp)
        row = connection.execute(
            """
            SELECT value_json
            FROM dashboard_ui_preferences
            WHERE preference_key = ?
            """,
            (DASHBOARD_SELECTED_CONFIG_KEY,),
        ).fetchone()
        existing = _loads(row[0]) if row is not None else {}
        state = {
            "schema_version": DASHBOARD_UI_PREFERENCES_SCHEMA_VERSION,
            "artifact_type": "dashboard_selected_config_state",
            "status": "selected",
            "config_path": str(config_path),
            "config": {"loaded": True, "ref": dashboard_config_ref(config_path)},
            "history": _updated_config_history(existing.get("history"), config_path),
            "updated_at": timestamp,
        }
        with runtime_state_transaction(connection):
            connection.execute(
                """
                INSERT OR REPLACE INTO dashboard_ui_preferences (
                  preference_key,
                  value_json,
                  updated_at
                )
                VALUES (?, ?, ?)
                """,
                (DASHBOARD_SELECTED_CONFIG_KEY, _dumps(state), timestamp),
            )
    return state


def read_dashboard_selected_config_state(*, runtime_root: Path | None = None) -> tuple[dict[str, Any], str | None]:
    with closing(open_runtime_state_connection(runtime_root=runtime_root)) as connection:
        apply_dashboard_ui_preference_migrations(connection)
        row = connection.execute(
            """
            SELECT value_json
            FROM dashboard_ui_preferences
            WHERE preference_key = ?
            """,
            (DASHBOARD_SELECTED_CONFIG_KEY,),
        ).fetchone()
    if row is None:
        return {}, "selected dashboard config was not found."
    state = _loads(row[0])
    if not state:
        return {}, "selected dashboard config preference is not valid JSON."
    return state, None


def read_dashboard_config_history(*, runtime_root: Path | None = None) -> list[str]:
    state, error = read_dashboard_selected_config_state(runtime_root=runtime_root)
    if error:
        return []
    return _string_list(state.get("history"))


def _format_utc(value: datetime | str | None) -> str:
    if value is None:
        timestamp = datetime.now(timezone.utc).replace(microsecond=0)
    elif isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError("dashboard preference timestamp must include a UTC offset.")
        timestamp = value.astimezone(timezone.utc).replace(microsecond=0)
    elif isinstance(value, str):
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            raise ValueError("dashboard preference timestamp must include a UTC offset.")
        timestamp = timestamp.astimezone(timezone.utc).replace(microsecond=0)
    else:
        raise ValueError("dashboard preference timestamp must be a datetime or ISO 8601 string.")
    return timestamp.isoformat().replace("+00:00", "Z")


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _loads(value: Any) -> dict[str, Any]:
    if not isinstance(value, str) or not value:
        return {}
    with suppress(json.JSONDecodeError):
        loaded = json.loads(value)
        if isinstance(loaded, dict):
            return loaded
    return {}


def _updated_config_history(existing: Any, config_path: Path) -> list[str]:
    selected = str(config_path)
    history = [selected]
    for item in _string_list(existing):
        if item != selected:
            history.append(item)
        if len(history) >= DASHBOARD_CONFIG_HISTORY_LIMIT:
            break
    return history


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in (str(item).strip() for item in value) if item]
