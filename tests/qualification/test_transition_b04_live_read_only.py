from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from pathlib import Path

from halpha.domain_values import content_digest
from tools.qualification.transition_b04_live_read_only import (
    executor_arguments,
    latest_ready_event,
)


def _event(value: dict[str, object]) -> str:
    value["event_digest"] = content_digest(value)
    return json.dumps(value)


OBSERVATION_ID = "observation-1"
CONFIGURATION_DIGEST = "1" * 64
SOURCE_SHA256_DIGEST = "2" * 64


def _latest_ready(path: Path, *, not_before: datetime):
    return latest_ready_event(
        path,
        not_before=not_before,
        observation_id=OBSERVATION_ID,
        configuration_digest=CONFIGURATION_DIGEST,
        source_sha256_digest=SOURCE_SHA256_DIGEST,
    )


def test_executor_arguments_bind_only_read_only_observation_inputs(tmp_path: Path) -> None:
    config = tmp_path / "read-only.toml"
    spec = tmp_path / "spec.json"
    events = tmp_path / "events.jsonl"

    arguments = executor_arguments(config, spec, events)

    assert arguments.startswith("-m halpha.executor ")
    assert f'--config "{config.resolve()}"' in arguments
    assert f'--forward-observation-spec "{spec.resolve()}"' in arguments
    assert f'--forward-observation-evidence "{events.resolve()}"' in arguments
    assert "halpha.app" not in arguments
    assert "api_key" not in arguments
    assert "api_secret" not in arguments


def test_latest_ready_event_requires_trimmed_capabilities(tmp_path: Path) -> None:
    starts_at = datetime.now(UTC)
    path = tmp_path / "events.jsonl"
    rejected = {
        "event": "READ_ONLY_RUNTIME_READY",
        "observed_at": (starts_at + timedelta(seconds=1)).isoformat(),
        "observation_id": OBSERVATION_ID,
        "configuration_digest": CONFIGURATION_DIGEST,
        "source_sha256_digest": SOURCE_SHA256_DIGEST,
        "profile": "BINANCE_LIVE_READ_ONLY",
        "product_runtime_started": True,
        "strategy_adapter_started": True,
        "data_client_loaded": True,
        "binance_credentials_loaded": False,
        "instrument_commission_query_enabled": False,
        "execution_client_loaded": True,
        "database_connection_loaded": False,
        "execution_action_repository_loaded": False,
        "persisted_action_capability_loaded": False,
        "startup_execution_reconciliation": "NOT_APPLICABLE",
        "runtime_real_write_gate": "CLOSED",
    }
    qualified = {
        **rejected,
        "observed_at": (starts_at + timedelta(seconds=2)).isoformat(),
        "execution_client_loaded": False,
    }
    path.write_text(
        _event(rejected) + "\n" + _event(qualified) + "\n",
        encoding="utf-8",
    )

    assert _latest_ready(path, not_before=starts_at) == qualified


def test_latest_ready_event_rejects_prior_window(tmp_path: Path) -> None:
    starts_at = datetime.now(UTC)
    path = tmp_path / "events.jsonl"
    prior = {
        "event": "READ_ONLY_RUNTIME_READY",
        "observed_at": (starts_at - timedelta(seconds=1)).isoformat(),
        "observation_id": OBSERVATION_ID,
        "configuration_digest": CONFIGURATION_DIGEST,
        "source_sha256_digest": SOURCE_SHA256_DIGEST,
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
    path.write_text(_event(prior) + "\n", encoding="utf-8")

    assert _latest_ready(path, not_before=starts_at) is None


def test_latest_ready_event_rejects_invalid_digest_and_partial_tail(tmp_path: Path) -> None:
    starts_at = datetime.now(UTC)
    path = tmp_path / "events.jsonl"
    ready = {
        "event": "READ_ONLY_RUNTIME_READY",
        "observed_at": (starts_at + timedelta(seconds=1)).isoformat(),
        "observation_id": OBSERVATION_ID,
        "configuration_digest": CONFIGURATION_DIGEST,
        "source_sha256_digest": SOURCE_SHA256_DIGEST,
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
        "event_digest": "0" * 64,
    }
    path.write_bytes((json.dumps(ready) + "\n").encode("utf-8") + b'{"event":')

    assert _latest_ready(path, not_before=starts_at) is None


def test_latest_ready_event_rejects_another_observation_identity(tmp_path: Path) -> None:
    starts_at = datetime.now(UTC)
    path = tmp_path / "events.jsonl"
    wrong_identity = {
        "event": "READ_ONLY_RUNTIME_READY",
        "observed_at": (starts_at + timedelta(seconds=1)).isoformat(),
        "observation_id": "observation-2",
        "configuration_digest": "2" * 64,
        "source_sha256_digest": SOURCE_SHA256_DIGEST,
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
    path.write_text(_event(wrong_identity) + "\n", encoding="utf-8")

    assert _latest_ready(path, not_before=starts_at) is None


def test_latest_ready_event_rejects_another_source_identity(tmp_path: Path) -> None:
    starts_at = datetime.now(UTC)
    path = tmp_path / "events.jsonl"
    wrong_source = {
        "event": "READ_ONLY_RUNTIME_READY",
        "observed_at": (starts_at + timedelta(seconds=1)).isoformat(),
        "observation_id": OBSERVATION_ID,
        "configuration_digest": CONFIGURATION_DIGEST,
        "source_sha256_digest": "9" * 64,
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
    path.write_text(_event(wrong_source) + "\n", encoding="utf-8")

    assert _latest_ready(path, not_before=starts_at) is None
