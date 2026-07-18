from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace

from halpha.domain_values import content_digest
from tools.qualification.verify_b04_live_read_only import (
    _bar_sequence_coverage,
    _bucket_coverage,
    _top_of_book_window,
    classify_live_read_only,
    scan_event_log,
    verify,
)


ROOT = Path(__file__).resolve().parents[2]


def test_live_read_only_missing_external_inputs_remains_in_progress(tmp_path) -> None:
    evidence = verify(
        ROOT,
        config_path=tmp_path / "missing.toml",
        spec_path=tmp_path / "missing-spec.json",
        events_path=tmp_path / "missing-events.jsonl",
        smtp_path=tmp_path / "missing-smtp.json",
    )

    assert evidence["status"] == "IN_PROGRESS"
    assert evidence["stage"] == "B04_BINANCE_LIVE_READ_ONLY_OBSERVATION"
    assert evidence["checks"]["execution_client_absent"] is False
    assert evidence["checks"]["event_log_complete_line_boundary"] is False
    assert evidence["checks"]["no_live_execution_action_created"] is True


def test_live_read_only_classifier_rejects_integrity_errors() -> None:
    assert classify_live_read_only({"only": True}, integrity_errors=[]) == "QUALIFIED"
    assert classify_live_read_only({"only": False}, integrity_errors=[]) == "IN_PROGRESS"
    assert (
        classify_live_read_only({"only": True}, integrity_errors=["DIGEST_MISMATCH"])
        == "REJECTED"
    )


def _event_line(**values: object) -> bytes:
    payload = dict(values)
    payload["event_digest"] = content_digest(payload)
    return (
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        + "\n"
    ).encode("utf-8")


def test_event_scan_streams_a_complete_line_snapshot_and_defers_partial_tail(
    tmp_path,
) -> None:
    ready = _event_line(
        event="READ_ONLY_RUNTIME_READY",
        strategy_adapter_started=True,
        data_client_loaded=True,
        binance_credentials_loaded=False,
        instrument_commission_query_enabled=False,
        execution_client_loaded=False,
        database_connection_loaded=False,
        execution_action_repository_loaded=False,
        persisted_action_capability_loaded=False,
        runtime_real_write_gate="CLOSED",
    )
    top = _event_line(
        event="TAKER_TOP_OF_BOOK_SECOND",
        venue_second=1,
        minimum_notional="123.45",
    )
    partial = b'{"event":"BAR_OBSERVED"'
    events_path = tmp_path / "events.jsonl"
    events_path.write_bytes(ready + top + partial)

    scan = scan_event_log(events_path, spec=None)

    assert scan.event_count == 2
    assert scan.ready_count == 1
    assert next(iter(scan.top_by_second.values())).as_tuple().exponent == -2
    assert scan.snapshot_bytes == len(ready + top)
    assert scan.ignored_trailing_bytes == len(partial)
    assert scan.snapshot_sha256 == sha256(ready + top).hexdigest()
    assert scan.errors == []


def test_event_scan_rejects_a_digest_valid_malformed_payload_without_crashing(
    tmp_path,
) -> None:
    events_path = tmp_path / "events.jsonl"
    events_path.write_bytes(_event_line(event="BAR_OBSERVED", bar_type="1-MINUTE-LAST-EXTERNAL"))

    scan = scan_event_log(events_path, spec=None)

    assert scan.event_count == 1
    assert scan.source_ns == []
    assert scan.errors == ["EVENT_PAYLOAD_INVALID:1:KeyError"]


def test_event_scan_rejects_process_start_configuration_drift(tmp_path) -> None:
    spec = SimpleNamespace(
        observation_id="observation-1",
        parameter_digest="1" * 64,
        configuration_digest="2" * 64,
        source_sha256_digest="4" * 64,
    )
    events_path = tmp_path / "events.jsonl"
    events_path.write_bytes(
        _event_line(
            event="OBSERVATION_PROCESS_STARTED",
            observed_at="2026-07-18T00:00:00Z",
            observation_id=spec.observation_id,
            parameter_digest=spec.parameter_digest,
            configuration_digest="3" * 64,
            source_sha256_digest=spec.source_sha256_digest,
        )
    )

    scan = scan_event_log(events_path, spec=spec)

    assert scan.process_start_count == 1
    assert scan.configuration_digest_mismatch is True


def test_event_scan_rejects_source_identity_drift(tmp_path) -> None:
    spec = SimpleNamespace(
        observation_id="observation-1",
        parameter_digest="1" * 64,
        configuration_digest="2" * 64,
        source_sha256_digest="4" * 64,
    )
    events_path = tmp_path / "events.jsonl"
    events_path.write_bytes(
        _event_line(
            event="OBSERVATION_PROCESS_STARTED",
            observed_at="2026-07-18T00:00:00Z",
            observation_id=spec.observation_id,
            parameter_digest=spec.parameter_digest,
            configuration_digest=spec.configuration_digest,
            source_sha256_digest="5" * 64,
        )
    )

    scan = scan_event_log(events_path, spec=spec)

    assert scan.process_start_count == 1
    assert scan.source_sha256_digest_mismatch is True


def test_event_scan_proves_controlled_process_gap_even_when_bars_are_contiguous(
    tmp_path,
) -> None:
    spec = SimpleNamespace(
        observation_id="observation-1",
        parameter_digest="1" * 64,
        configuration_digest="2" * 64,
        source_sha256_digest="4" * 64,
    )
    stopped_at = "2026-07-18T00:00:00Z"
    started_at = "2026-07-18T00:01:40Z"
    minute = 60_000_000_000
    events_path = tmp_path / "events.jsonl"
    events_path.write_bytes(
        b"".join(
            (
                _event_line(
                    event="BAR_OBSERVED",
                    bar_type="BTCUSDT-PERP-1-MINUTE-LAST-EXTERNAL",
                    ts_event_ns=minute,
                    observation_id=spec.observation_id,
                    parameter_digest=spec.parameter_digest,
                    configuration_digest=spec.configuration_digest,
                    source_sha256_digest=spec.source_sha256_digest,
                ),
                _event_line(
                    event="OBSERVATION_PROCESS_STOPPED",
                    observed_at=stopped_at,
                    observation_id=spec.observation_id,
                    parameter_digest=spec.parameter_digest,
                    configuration_digest=spec.configuration_digest,
                    source_sha256_digest=spec.source_sha256_digest,
                ),
                _event_line(
                    event="OBSERVATION_PROCESS_STARTED",
                    observed_at=started_at,
                    observation_id=spec.observation_id,
                    parameter_digest=spec.parameter_digest,
                    configuration_digest=spec.configuration_digest,
                    source_sha256_digest=spec.source_sha256_digest,
                ),
                _event_line(
                    event="BAR_OBSERVED",
                    bar_type="BTCUSDT-PERP-1-MINUTE-LAST-EXTERNAL",
                    ts_event_ns=minute * 2,
                    observation_id=spec.observation_id,
                    parameter_digest=spec.parameter_digest,
                    configuration_digest=spec.configuration_digest,
                    source_sha256_digest=spec.source_sha256_digest,
                ),
            )
        )
    )

    scan = scan_event_log(events_path, spec=spec)

    assert scan.maximum_process_gap_seconds == 100
    assert scan.market_data_recovered_after_gap is True
    assert scan.source_ns == [minute, minute * 2]


def test_bar_and_mark_coverage_include_the_frozen_start_window() -> None:
    starts_at = datetime(2026, 7, 18, 0, 0, 30, tzinfo=UTC)
    minute = 60_000_000_000
    source = [
        int(datetime(2026, 7, 18, 0, 3, tzinfo=UTC).timestamp() * 1_000_000_000),
        int(datetime(2026, 7, 18, 0, 4, tzinfo=UTC).timestamp() * 1_000_000_000),
    ]

    coverage, maximum_gap, aligned = _bar_sequence_coverage(
        source,
        interval_seconds=60,
        starts_at=starts_at,
    )
    mark_coverage, mark_gap = _bucket_coverage(
        [source[0] + minute // 2, source[1] + minute // 2],
        bucket_seconds=60,
        starts_at=starts_at,
        ends_at=datetime(2026, 7, 18, 0, 4, 59, tzinfo=UTC),
    )

    assert coverage == Decimal("0.5")
    assert maximum_gap == 180
    assert aligned is True
    assert mark_coverage == Decimal("0.4")
    assert mark_gap == 240


def test_top_of_book_percentile_counts_missing_seconds_as_zero() -> None:
    starts_at = datetime(2026, 7, 18, 0, 0, 0, tzinfo=UTC)
    ends_at = starts_at + timedelta(seconds=100)
    first = int(starts_at.timestamp()) + 1
    values = {second: Decimal("100") for second in range(first + 5, first + 100)}

    coverage, p05, observed, missing = _top_of_book_window(
        values,
        starts_at=starts_at,
        ends_at=ends_at,
    )

    assert coverage == Decimal("0.95")
    assert p05 == Decimal("0")
    assert observed == 95
    assert missing == 5


def test_event_scan_rejects_duplicate_top_of_book_seconds(tmp_path) -> None:
    top = _event_line(
        event="TAKER_TOP_OF_BOOK_SECOND",
        venue_second=1,
        minimum_notional="123.45",
    )
    events_path = tmp_path / "events.jsonl"
    events_path.write_bytes(top + top)

    scan = scan_event_log(events_path, spec=None)

    assert scan.errors == ["EVENT_PAYLOAD_INVALID:2:ValueError"]
