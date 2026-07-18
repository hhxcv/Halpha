from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json

import pytest

from tools.qualification.observe_b04_windows_soak import (
    WindowsSoakObservationError,
    _frozen_soak_identity,
    _normalize_checkpoint_task_times,
    _latest_runtime_ready,
    continuity_clock,
    normalize_task_time_local,
)


def test_continuity_clock_qualifies_only_seventy_two_awake_hours() -> None:
    started_at = datetime(2026, 7, 18, tzinfo=UTC)
    clock = continuity_clock(
        started_at=started_at,
        observed_at=started_at + timedelta(hours=72, seconds=1),
        started_unbiased_100ns=100,
        observed_unbiased_100ns=100 + (72 * 3600 + 1) * 10_000_000,
    )

    assert clock["minimum_72_awake_hours_observed"] is True
    assert clock["no_sleep_or_hibernate_over_60_seconds"] is True
    assert clock["sleep_or_hibernate_seconds"] == 0


def test_continuity_clock_rejects_wall_time_that_contains_sleep() -> None:
    started_at = datetime(2026, 7, 18, tzinfo=UTC)
    clock = continuity_clock(
        started_at=started_at,
        observed_at=started_at + timedelta(hours=72),
        started_unbiased_100ns=100,
        observed_unbiased_100ns=100 + 71 * 3600 * 10_000_000,
    )

    assert clock["minimum_72_awake_hours_observed"] is False
    assert clock["no_sleep_or_hibernate_over_60_seconds"] is False
    assert clock["sleep_or_hibernate_seconds"] == 3600


def test_latest_runtime_ready_streams_complete_lines_and_ignores_partial_tail(
    tmp_path,
) -> None:
    path = tmp_path / "executor.jsonl"
    first = {"event": "runtime_ready", "sequence": 1}
    latest = {"event": "runtime_ready", "sequence": 2}
    path.write_bytes(
        (json.dumps(first) + "\n" + json.dumps(latest) + "\n").encode("utf-8")
        + b'{"event":"runtime_ready"'
    )

    assert _latest_runtime_ready(path) == latest


def test_task_scheduler_local_wall_clock_discards_incorrect_com_timezone() -> None:
    raw = datetime(2026, 7, 18, 8, 20, 1, tzinfo=UTC)

    normalized = datetime.fromisoformat(normalize_task_time_local(raw))

    assert normalized.replace(tzinfo=None) == raw.replace(tzinfo=None)
    assert normalized.utcoffset() == raw.replace(tzinfo=None).astimezone().utcoffset()


def test_prior_checkpoint_task_time_labels_are_repaired_idempotently() -> None:
    checkpoints = [
        {
            "task_state": {
                "app": {"last_run_time_local": "2026-07-18 08:20:01+00:00"},
                "executor": {"last_run_time_local": "not-a-time"},
            }
        }
    ]

    _normalize_checkpoint_task_times(checkpoints)
    first = checkpoints[0]["task_state"]["app"]["last_run_time_local"]
    _normalize_checkpoint_task_times(checkpoints)

    parsed = datetime.fromisoformat(first)
    assert parsed.replace(tzinfo=None) == datetime(2026, 7, 18, 8, 20, 1)
    assert checkpoints[0]["task_state"]["app"]["last_run_time_local"] == first
    assert checkpoints[0]["task_state"]["executor"]["last_run_time_local"] == "not-a-time"


def test_soak_identity_freezes_source_and_configuration_on_reset() -> None:
    source = {"src/halpha/example.py": "1" * 64}

    baseline, digest, configuration, source_same, config_same = _frozen_soak_identity(
        None,
        current_source_sha256=source,
        current_configuration_digest="2" * 64,
    )

    assert baseline == source
    assert len(digest) == 64
    assert configuration == "2" * 64
    assert source_same is True
    assert config_same is True


def test_soak_identity_rejects_legacy_baseline_without_silent_migration() -> None:
    with pytest.raises(
        WindowsSoakObservationError,
        match="SOAK_SOURCE_IDENTITY_BASELINE_MISSING_RESET_REQUIRED",
    ):
        _frozen_soak_identity(
            {"schema_version": 2},
            current_source_sha256={"src/halpha/example.py": "1" * 64},
            current_configuration_digest="2" * 64,
        )


def test_soak_identity_preserves_baseline_and_detects_source_drift() -> None:
    original = {"src/halpha/example.py": "1" * 64}
    _, digest, _, _, _ = _frozen_soak_identity(
        None,
        current_source_sha256=original,
        current_configuration_digest="2" * 64,
    )
    prior = {
        "schema_version": 3,
        "source_sha256": original,
        "source_sha256_digest": digest,
        "configuration_digest": "2" * 64,
    }

    baseline, _, _, source_same, config_same = _frozen_soak_identity(
        prior,
        current_source_sha256={"src/halpha/example.py": "3" * 64},
        current_configuration_digest="2" * 64,
    )

    assert baseline == original
    assert source_same is False
    assert config_same is True
