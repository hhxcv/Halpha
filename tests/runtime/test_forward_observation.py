from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

import halpha.executor.forward_observation as forward_observation_module
from halpha.domain_values import content_digest
from halpha.executor.forward_observation import (
    ForwardObservationEvidence,
    ForwardObservationError,
    ForwardObservationSpec,
    percentile_five,
    require_forward_observation_source_identity,
)
from halpha.planning.registry import OneShotParameters
from halpha.source_identity import source_file_sha256


def _spec() -> ForwardObservationSpec:
    starts_at = datetime(2026, 7, 18, tzinfo=UTC)
    parameters = OneShotParameters(direction="LONG")
    source_sha256 = {"src/halpha/example.py": "3" * 64}
    return ForwardObservationSpec(
        observation_id="read-only-check-20260718",
        activation_id="read-only-check-btcusdt",
        strategy_evidence_ref="build/evidence/reports/strategy-evidence.json",
        strategy_evidence_digest="1" * 64,
        configuration_digest="2" * 64,
        source_sha256=source_sha256,
        source_sha256_digest=content_digest(source_sha256),
        parameters=parameters,
        parameter_digest=content_digest(parameters.model_dump(mode="json")),
        starts_at=starts_at,
        max_allowed_loss="50",
        max_notional="500",
        max_margin="100",
        effective_leverage="5",
    )


def test_forward_observation_spec_binds_start_inputs_and_parameters() -> None:
    spec = _spec()

    assert spec.schema_version == 4
    assert spec.entry_valid_until == spec.starts_at + timedelta(days=1)
    with pytest.raises(ValidationError, match="PARAMETER_DIGEST_MISMATCH"):
        ForwardObservationSpec.model_validate(
            {
                **spec.model_dump(mode="json"),
                "parameter_digest": "0" * 64,
            }
        )
    with pytest.raises(ValidationError, match="SOURCE_DIGEST_MISMATCH"):
        ForwardObservationSpec.model_validate(
            {
                **spec.model_dump(mode="json"),
                "source_sha256_digest": "0" * 64,
            }
        )


def test_forward_observation_evidence_is_append_only_and_sanitized(tmp_path) -> None:
    path = tmp_path / "observation.jsonl"
    evidence = ForwardObservationEvidence(_spec(), path)
    evidence.record_process_started()
    evidence.record_quote_tick(
        SimpleNamespace(
            ts_event=1_000_000_000,
            ask_price="100",
            ask_size="3",
            bid_price="99",
            bid_size="4",
        )
    )
    evidence.record_quote_tick(
        SimpleNamespace(
            ts_event=1_500_000_000,
            ask_price="100",
            ask_size="2",
            bid_price="99",
            bid_size="4",
        )
    )
    evidence.record_quote_tick(
        SimpleNamespace(
            ts_event=2_000_000_000,
            ask_price="101",
            ask_size="4",
            bid_price="100",
            bid_size="5",
        )
    )
    evidence.close(reason_code="QUALIFICATION_TEST")

    events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    notions = [
        item["minimum_notional"]
        for item in events
        if item["event"] == "TAKER_TOP_OF_BOOK_SECOND"
    ]
    assert notions == ["200", "404"]
    assert all("event_digest" in item for item in events)
    assert all(
        item["observation_id"] == evidence.spec.observation_id
        and item["parameter_digest"] == evidence.spec.parameter_digest
        and item["configuration_digest"] == evidence.spec.configuration_digest
        and item["source_sha256_digest"] == evidence.spec.source_sha256_digest
        for item in events
    )
    assert "qualification-key" not in path.read_text(encoding="utf-8")


def test_forward_observation_recovers_only_an_incomplete_tail(tmp_path) -> None:
    path = tmp_path / "observation.jsonl"
    first = {"event": "COMPLETE", "event_digest": "evidence-placeholder"}
    prefix = json.dumps(first).encode("utf-8") + b"\n"
    partial = b'{"event":"INCOMPLETE"'
    path.write_bytes(prefix + partial)

    evidence = ForwardObservationEvidence(_spec(), path)
    evidence.record_process_started()

    raw = path.read_bytes()
    assert raw.startswith(prefix)
    assert partial not in raw
    events = [json.loads(line) for line in raw.splitlines()]
    recovered = events[1]
    assert recovered["event"] == "OBSERVATION_PARTIAL_TAIL_RECOVERED"
    assert recovered["discarded_partial_tail_bytes"] == len(partial)
    assert events[2]["event"] == "OBSERVATION_PROCESS_STARTED"
    for item in events[1:]:
        digest = item.pop("event_digest")
        assert digest == content_digest(item)


def test_forward_observation_rejects_an_unbounded_partial_tail(tmp_path) -> None:
    path = tmp_path / "observation.jsonl"
    path.write_bytes(
        b"x" * (ForwardObservationEvidence.MAX_PARTIAL_TAIL_BYTES + 1)
    )

    with pytest.raises(
        ForwardObservationError,
        match="FORWARD_OBSERVATION_PARTIAL_TAIL_TOO_LARGE",
    ):
        evidence = ForwardObservationEvidence(_spec(), path)
        evidence.record_process_started()


def test_forward_observation_rejects_a_symlink_evidence_target(tmp_path) -> None:
    target = tmp_path / "target.jsonl"
    target.write_text("", encoding="utf-8")
    link = tmp_path / "observation.jsonl"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symlink creation is unavailable")

    with pytest.raises(
        ForwardObservationError,
        match="FORWARD_OBSERVATION_EVIDENCE_SYMLINK_FORBIDDEN",
    ):
        ForwardObservationEvidence(_spec(), link)


def test_forward_observation_does_not_write_before_runtime_build_succeeds(
    tmp_path,
) -> None:
    path = tmp_path / "observation.jsonl"
    evidence = ForwardObservationEvidence(_spec(), path)

    evidence.close(reason_code="BUILD_FAILED")

    assert not path.exists()


def test_forward_observation_rejects_callbacks_before_process_start(tmp_path) -> None:
    evidence = ForwardObservationEvidence(_spec(), tmp_path / "observation.jsonl")

    with pytest.raises(
        ForwardObservationError,
        match="FORWARD_OBSERVATION_PROCESS_START_REQUIRED",
    ):
        evidence.record_mark_price(SimpleNamespace(ts_event=1, value="1"))


def test_forward_observation_runtime_rejects_frozen_source_drift(
    tmp_path,
    monkeypatch,
) -> None:
    source = tmp_path / "src"
    source.mkdir()
    file = source / "runtime.py"
    file.write_text("VALUE = 1\n", encoding="utf-8")
    monkeypatch.setattr(
        forward_observation_module,
        "FORWARD_OBSERVATION_SOURCE_PATTERNS",
        ("src/*.py",),
    )
    source_sha256 = {
        "src/runtime.py": source_file_sha256(file)
    }
    spec = ForwardObservationSpec.model_validate(
        {
            **_spec().model_dump(mode="json"),
            "source_sha256": source_sha256,
            "source_sha256_digest": content_digest(source_sha256),
        }
    )

    assert (
        require_forward_observation_source_identity(tmp_path, spec)
        == source_sha256
    )
    file.write_text("VALUE = 2\n", encoding="utf-8")
    with pytest.raises(
        ForwardObservationError,
        match="FORWARD_OBSERVATION_SOURCE_IDENTITY_DRIFT",
    ):
        require_forward_observation_source_identity(tmp_path, spec)


def test_percentile_five_uses_conservative_nearest_rank() -> None:
    assert percentile_five([]) is None
    assert percentile_five([Decimal(value) for value in ("5", "1", "3", "2", "4")]) == Decimal("1")
