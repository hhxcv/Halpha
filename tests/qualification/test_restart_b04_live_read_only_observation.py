from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from pathlib import Path

from halpha.domain_values import content_digest
from tools.qualification.restart_b04_live_read_only_observation import (
    MINIMUM_GAP_SECONDS,
    process_start_count,
    restart_completed,
)


def _event(value: dict[str, object]) -> str:
    value["event_digest"] = content_digest(value)
    return json.dumps(value)


def test_restart_requires_a_gap_longer_than_ninety_seconds() -> None:
    assert MINIMUM_GAP_SECONDS >= 100


def test_restart_completion_requires_new_start_and_trimmed_ready(tmp_path: Path) -> None:
    gap_started_at = datetime.now(UTC)
    events = tmp_path / "events.jsonl"
    start = {
        "event": "OBSERVATION_PROCESS_STARTED",
        "observed_at": (gap_started_at + timedelta(seconds=101)).isoformat(),
        "observation_id": "observation-1",
        "configuration_digest": "1" * 64,
    }
    ready = {
        "event": "READ_ONLY_RUNTIME_READY",
        "observed_at": (gap_started_at + timedelta(seconds=102)).isoformat(),
        "observation_id": "observation-1",
        "configuration_digest": "1" * 64,
        "profile": "BINANCE_LIVE_READ_ONLY",
        "product_runtime_started": True,
        "strategy_adapter_started": True,
        "data_client_loaded": True,
        "binance_credentials_loaded": False,
        "instrument_commission_query_enabled": False,
        "execution_client_loaded": False,
        "database_connection_loaded": False,
        "execution_action_repository_loaded": False,
        "persisted_action_capability_loaded": False,
        "startup_execution_reconciliation": "NOT_APPLICABLE",
        "runtime_real_write_gate": "CLOSED",
    }
    events.write_text(_event(start) + "\n" + _event(ready) + "\n", encoding="utf-8")

    assert process_start_count(events) == 1
    assert restart_completed(
        events,
        prior_start_count=1,
        gap_started_at=gap_started_at,
        observation_id="observation-1",
        configuration_digest="1" * 64,
    )
    assert not restart_completed(
        events,
        prior_start_count=1,
        gap_started_at=gap_started_at,
        observation_id="observation-1",
        configuration_digest="2" * 64,
    )
    assert not restart_completed(
        events,
        prior_start_count=1,
        gap_started_at=gap_started_at,
        prior_event_offset=events.stat().st_size,
    )


def test_restart_completion_rejects_ready_from_another_observation(tmp_path: Path) -> None:
    gap_started_at = datetime.now(UTC)
    events = tmp_path / "events.jsonl"
    start = {
        "event": "OBSERVATION_PROCESS_STARTED",
        "observed_at": (gap_started_at + timedelta(seconds=101)).isoformat(),
        "observation_id": "observation-1",
        "configuration_digest": "1" * 64,
    }
    wrong_ready = {
        "event": "READ_ONLY_RUNTIME_READY",
        "observed_at": (gap_started_at + timedelta(seconds=102)).isoformat(),
        "observation_id": "observation-2",
        "configuration_digest": "2" * 64,
        "profile": "BINANCE_LIVE_READ_ONLY",
        "product_runtime_started": True,
        "strategy_adapter_started": True,
        "data_client_loaded": True,
        "binance_credentials_loaded": False,
        "instrument_commission_query_enabled": False,
        "execution_client_loaded": False,
        "database_connection_loaded": False,
        "execution_action_repository_loaded": False,
        "persisted_action_capability_loaded": False,
        "startup_execution_reconciliation": "NOT_APPLICABLE",
        "runtime_real_write_gate": "CLOSED",
    }
    events.write_text(
        _event(start) + "\n" + _event(wrong_ready) + "\n",
        encoding="utf-8",
    )

    assert not restart_completed(
        events,
        prior_start_count=1,
        gap_started_at=gap_started_at,
        observation_id="observation-1",
        configuration_digest="1" * 64,
    )


def test_restart_completion_rejects_digest_invalid_start(tmp_path: Path) -> None:
    gap_started_at = datetime.now(UTC)
    events = tmp_path / "events.jsonl"
    invalid_start = {
        "event": "OBSERVATION_PROCESS_STARTED",
        "observed_at": (gap_started_at + timedelta(seconds=101)).isoformat(),
        "event_digest": "0" * 64,
    }
    ready = {
        "event": "READ_ONLY_RUNTIME_READY",
        "observed_at": (gap_started_at + timedelta(seconds=102)).isoformat(),
        "observation_id": "observation-1",
        "configuration_digest": "1" * 64,
        "profile": "BINANCE_LIVE_READ_ONLY",
        "product_runtime_started": True,
        "strategy_adapter_started": True,
        "data_client_loaded": True,
        "binance_credentials_loaded": False,
        "instrument_commission_query_enabled": False,
        "execution_client_loaded": False,
        "database_connection_loaded": False,
        "execution_action_repository_loaded": False,
        "persisted_action_capability_loaded": False,
        "startup_execution_reconciliation": "NOT_APPLICABLE",
        "runtime_real_write_gate": "CLOSED",
    }
    events.write_text(
        json.dumps(invalid_start) + "\n" + _event(ready) + "\n",
        encoding="utf-8",
    )

    assert not restart_completed(
        events,
        prior_start_count=1,
        gap_started_at=gap_started_at,
        observation_id="observation-1",
        configuration_digest="1" * 64,
    )
