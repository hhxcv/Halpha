from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from tools.provisioning.provision_b04_transition_task import (
    REPETITION_DURATION,
    REPETITION_INTERVAL,
    FINALIZE_REPETITION_DURATION,
    FINALIZE_REPETITION_INTERVAL,
    RESTART_REPETITION_INTERVAL,
    SOAK_CHECKPOINT_REPETITION_DURATION,
    SOAK_CHECKPOINT_REPETITION_INTERVAL,
    TransitionTaskProvisioningError,
    parse_local_start,
    finalize_action_arguments,
    restart_action_arguments,
    soak_checkpoint_action_arguments,
    transition_action_arguments,
)


def test_transition_task_has_bounded_retry_and_explicit_apply() -> None:
    assert REPETITION_INTERVAL == "PT5M"
    assert RESTART_REPETITION_INTERVAL == "PT30M"
    assert FINALIZE_REPETITION_INTERVAL == "PT30M"
    assert FINALIZE_REPETITION_DURATION == "P8D"
    assert SOAK_CHECKPOINT_REPETITION_INTERVAL == "PT1H"
    assert SOAK_CHECKPOINT_REPETITION_DURATION == "P3D"
    assert REPETITION_DURATION == "P1D"
    assert transition_action_arguments() == (
        "tools/qualification/transition_b04_live_read_only.py --apply"
    )
    assert "proxy" not in transition_action_arguments().lower()
    assert restart_action_arguments() == (
        "tools/qualification/restart_b04_live_read_only_observation.py --apply"
    )
    assert "proxy" not in restart_action_arguments().lower()
    assert finalize_action_arguments() == (
        "tools/qualification/finalize_b04_live_read_only_observation.py --apply"
    )
    assert "proxy" not in finalize_action_arguments().lower()
    assert soak_checkpoint_action_arguments() == (
        "tools/qualification/observe_b04_windows_soak.py --config config/halpha.toml"
    )
    assert "proxy" not in soak_checkpoint_action_arguments().lower()


def test_transition_start_must_be_future_local_time() -> None:
    now = datetime(2026, 7, 18, 6, 0, 0)
    future = now + timedelta(days=3)
    assert parse_local_start(future.isoformat(), now=now) == future
    with pytest.raises(
        TransitionTaskProvisioningError,
        match="TRANSITION_START_TIME_MUST_BE_FUTURE",
    ):
        parse_local_start(now.isoformat(), now=now)
