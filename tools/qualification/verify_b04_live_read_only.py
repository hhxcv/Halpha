"""Qualify the single product Executor's 7-to-14-day read-only observation."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
import sys
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from halpha.configuration import load_settings, settings_digest
from halpha.domain_values import canonical_decimal, content_digest
from halpha.executor.forward_observation import (
    ForwardObservationSpec,
    load_forward_observation_spec,
)


DEFAULT_CONFIG = ROOT / "config/halpha.live-read-only.toml"
DEFAULT_SPEC = ROOT / "build/evidence/reports/b04-live-read-only-spec.json"
DEFAULT_EVENTS = ROOT / "build/evidence/reports/b04-live-read-only-events.jsonl"
DEFAULT_SMTP = ROOT / "build/qualification/b04-smtp-delivery.json"
DEFAULT_OUTPUT = ROOT / "build/qualification/b04-live-read-only.json"
SOURCE_1M_MINIMUM_COVERAGE = Decimal("0.999")
INTERNAL_15M_MINIMUM_COVERAGE = Decimal("0.995")
MARK_PRICE_MINIMUM_COVERAGE = Decimal("0.999")
TOP_OF_BOOK_MINIMUM_COVERAGE = Decimal("0.999")
MAXIMUM_SOURCE_GAP_SECONDS = 300
MAXIMUM_INTERNAL_GAP_SECONDS = 1800


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass
class EventLogScan:
    """Bounded-memory facts from one complete-line event-log snapshot."""

    errors: list[str] = field(default_factory=list)
    event_count: int = 0
    snapshot_bytes: int = 0
    ignored_trailing_bytes: int = 0
    snapshot_sha256: str | None = None
    process_start_count: int = 0
    ready_count: int = 0
    strategy_adapter_started: bool = False
    data_client_loaded: bool = False
    binance_credentials_absent: bool = True
    commission_query_disabled: bool = True
    execution_client_absent: bool = True
    database_connection_absent: bool = True
    execution_action_repository_absent: bool = True
    persisted_action_capability_absent: bool = True
    runtime_real_write_gate_closed: bool = True
    source_ns: list[int] = field(default_factory=list)
    target_ns: list[int] = field(default_factory=list)
    mark_price_count: int = 0
    mark_ns: list[int] = field(default_factory=list)
    top_by_second: dict[int, Decimal] = field(default_factory=dict)
    proposal_preview_count: int = 0
    live_execution_action_created: bool = False
    venue_write_event_observed: bool = False
    observation_identity_mismatch: bool = False
    parameter_digest_mismatch: bool = False
    configuration_digest_mismatch: bool = False
    last_stop_at: datetime | None = None
    latest_source_ns: int | None = None
    recovery_source_floor_ns: int | None = None
    maximum_process_gap_seconds: float = 0.0
    market_data_recovered_after_gap: bool = False


def _event_datetime(value: dict[str, Any]) -> datetime:
    return datetime.fromisoformat(
        str(value["observed_at"]).replace("Z", "+00:00")
    ).astimezone(UTC)


def _positive_decimal(value: object) -> Decimal:
    parsed = Decimal(str(value))
    if not parsed.is_finite() or parsed <= 0:
        raise ValueError("POSITIVE_FINITE_DECIMAL_REQUIRED")
    return parsed


def _record_event(
    scan: EventLogScan,
    value: dict[str, Any],
    *,
    line_number: int,
    spec: ForwardObservationSpec | None,
) -> None:
    event = value.get("event")
    if spec is not None:
        if value.get("observation_id") != spec.observation_id:
            scan.observation_identity_mismatch = True
        if value.get("parameter_digest") != spec.parameter_digest:
            scan.parameter_digest_mismatch = True
        if value.get("configuration_digest") != spec.configuration_digest:
            scan.configuration_digest_mismatch = True
    try:
        if event == "OBSERVATION_PROCESS_STARTED":
            started_at = _event_datetime(value)
            scan.process_start_count += 1
            if scan.last_stop_at is not None:
                gap_seconds = (started_at - scan.last_stop_at).total_seconds()
                if gap_seconds < 0:
                    raise ValueError("PROCESS_EVENT_TIME_REGRESSION")
                scan.maximum_process_gap_seconds = max(
                    scan.maximum_process_gap_seconds,
                    gap_seconds,
                )
                if gap_seconds > 90:
                    scan.recovery_source_floor_ns = scan.latest_source_ns or -1
                scan.last_stop_at = None
        elif event == "READ_ONLY_RUNTIME_READY":
            scan.ready_count += 1
            scan.strategy_adapter_started |= value.get("strategy_adapter_started") is True
            scan.data_client_loaded |= value.get("data_client_loaded") is True
            scan.binance_credentials_absent &= (
                value.get("binance_credentials_loaded") is False
            )
            scan.commission_query_disabled &= (
                value.get("instrument_commission_query_enabled") is False
            )
            scan.execution_client_absent &= value.get("execution_client_loaded") is False
            scan.database_connection_absent &= (
                value.get("database_connection_loaded") is False
            )
            scan.execution_action_repository_absent &= (
                value.get("execution_action_repository_loaded") is False
            )
            scan.persisted_action_capability_absent &= (
                value.get("persisted_action_capability_loaded") is False
            )
            scan.runtime_real_write_gate_closed &= (
                value.get("runtime_real_write_gate") == "CLOSED"
            )
        elif event == "BAR_OBSERVED":
            timestamp = int(value["ts_event_ns"])
            if timestamp <= 0:
                raise ValueError("POSITIVE_EVENT_TIMESTAMP_REQUIRED")
            bar_type = str(value.get("bar_type"))
            if "1-MINUTE-LAST-EXTERNAL" in bar_type:
                scan.source_ns.append(timestamp)
                if (
                    scan.recovery_source_floor_ns is not None
                    and timestamp > scan.recovery_source_floor_ns
                ):
                    scan.market_data_recovered_after_gap = True
                    scan.recovery_source_floor_ns = None
                scan.latest_source_ns = max(scan.latest_source_ns or 0, timestamp)
            if "15-MINUTE-LAST-INTERNAL" in bar_type:
                scan.target_ns.append(timestamp)
        elif event == "MARK_PRICE_OBSERVED":
            timestamp = int(value["ts_event_ns"])
            if timestamp <= 0:
                raise ValueError("POSITIVE_EVENT_TIMESTAMP_REQUIRED")
            _positive_decimal(value["price"])
            scan.mark_price_count += 1
            scan.mark_ns.append(timestamp)
        elif event == "TAKER_TOP_OF_BOOK_SECOND":
            venue_second = int(value["venue_second"])
            if venue_second <= 0:
                raise ValueError("POSITIVE_VENUE_SECOND_REQUIRED")
            if venue_second in scan.top_by_second:
                raise ValueError("DUPLICATE_TOP_OF_BOOK_SECOND")
            scan.top_by_second[venue_second] = _positive_decimal(
                value["minimum_notional"]
            )
        elif event == "UNSUBMITTABLE_STRATEGY_PROPOSAL_PREVIEW":
            scan.proposal_preview_count += 1
        elif event == "OBSERVATION_PROCESS_STOPPED":
            scan.last_stop_at = _event_datetime(value)
        if event == "EXECUTION_ACTION_CREATED":
            scan.live_execution_action_created = True
        if event in {
            "EXECUTION_ACTION_CREATED",
            "ORDER_SUBMIT_REQUESTED",
            "ORDER_CANCEL_REQUESTED",
            "VENUE_WRITE_REQUESTED",
        }:
            scan.venue_write_event_observed = True
    except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
        scan.errors.append(f"EVENT_PAYLOAD_INVALID:{line_number}:{type(exc).__name__}")


def scan_event_log(
    path: Path,
    *,
    spec: ForwardObservationSpec | None,
) -> EventLogScan:
    """Read only complete lines that existed at the start of this scan.

    The product Executor may append while a scheduled verification is running. A
    fixed-size binary snapshot prevents an unbounded read, and an incomplete final
    line is deferred to the next scan instead of being reported as corrupt.
    """

    scan = EventLogScan()
    if not path.is_file():
        return scan
    digest = sha256()
    consumed = 0
    try:
        snapshot_size = path.stat().st_size
        with path.open("rb") as handle:
            line_number = 0
            while consumed < snapshot_size:
                line = handle.readline(snapshot_size - consumed)
                if not line:
                    break
                consumed += len(line)
                line_number += 1
                if not line.endswith(b"\n"):
                    scan.ignored_trailing_bytes = len(line)
                    break
                digest.update(line)
                scan.snapshot_bytes += len(line)
                if not line.strip():
                    continue
                try:
                    value = json.loads(line.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    scan.errors.append(
                        f"EVENT_LOG_INVALID:{line_number}:{type(exc).__name__}"
                    )
                    continue
                if not isinstance(value, dict):
                    scan.errors.append(f"EVENT_ROOT_INVALID:{line_number}")
                    continue
                expected = value.get("event_digest")
                payload = {
                    key: item for key, item in value.items() if key != "event_digest"
                }
                if expected != content_digest(payload):
                    scan.errors.append(f"EVENT_DIGEST_MISMATCH:{line_number}")
                scan.event_count += 1
                _record_event(scan, value, line_number=line_number, spec=spec)
    except OSError as exc:
        scan.errors.append(f"EVENT_LOG_INVALID:{type(exc).__name__}")
    scan.snapshot_sha256 = digest.hexdigest()
    return scan


def _smtp_qualified(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        evidence = json.loads(path.read_text(encoding="utf-8"))
        return (
            evidence.get("stage") == "B04_ACTUAL_SMTP_DELIVERY"
            and evidence.get("status") == "QUALIFIED"
            and isinstance(evidence.get("checks"), dict)
            and bool(evidence["checks"])
            and all(value is True for value in evidence["checks"].values())
        )
    except Exception:
        return False


def classify_live_read_only(checks: dict[str, bool], *, integrity_errors: list[str]) -> str:
    if integrity_errors:
        return "REJECTED"
    return "QUALIFIED" if checks and all(checks.values()) else "IN_PROGRESS"


def _bar_sequence_coverage(
    timestamps_ns: list[int],
    *,
    interval_seconds: int,
    starts_at: datetime,
) -> tuple[Decimal, int, bool]:
    interval_ns = interval_seconds * 1_000_000_000
    first_expected_ns = (
        int(starts_at.timestamp()) // interval_seconds + 1
    ) * interval_ns
    ordered = sorted(set(value for value in timestamps_ns if value >= first_expected_ns))
    if not ordered:
        return Decimal("0"), 0, False
    expected = (ordered[-1] - first_expected_ns) // interval_ns + 1
    if expected <= 0:
        return Decimal("0"), 0, False
    coverage = Decimal(len(ordered)) / Decimal(expected)
    gaps = [
        (ordered[0] - first_expected_ns) // 1_000_000_000 + interval_seconds,
        *(
            (current - previous) // 1_000_000_000
            for previous, current in zip(ordered, ordered[1:])
        ),
    ]
    aligned = all(value % interval_ns == 0 for value in ordered)
    return coverage, int(max(gaps, default=0)), aligned


def _bucket_coverage(
    timestamps_ns: list[int],
    *,
    bucket_seconds: int,
    starts_at: datetime,
    ends_at: datetime,
) -> tuple[Decimal, int]:
    bucket_ns = bucket_seconds * 1_000_000_000
    first_bucket = int(starts_at.timestamp()) // bucket_seconds
    last_bucket = int(ends_at.timestamp()) // bucket_seconds
    expected = max(0, last_bucket - first_bucket + 1)
    if expected == 0:
        return Decimal("0"), 0
    buckets = sorted(
        set(
            timestamp // bucket_ns
            for timestamp in timestamps_ns
            if first_bucket <= timestamp // bucket_ns <= last_bucket
        )
    )
    if not buckets:
        return Decimal("0"), 0
    coverage = Decimal(len(buckets)) / Decimal(expected)
    gaps = [
        (buckets[0] - first_bucket + 1) * bucket_seconds,
        *((current - previous) * bucket_seconds for previous, current in zip(buckets, buckets[1:])),
    ]
    return coverage, int(max(gaps, default=0))


def _top_of_book_window(
    top_by_second: dict[int, Decimal],
    *,
    starts_at: datetime,
    ends_at: datetime,
) -> tuple[Decimal, Decimal | None, int, int]:
    first_second = int(starts_at.timestamp()) + 1
    last_second = int(ends_at.timestamp())
    expected = max(0, last_second - first_second + 1)
    if expected == 0:
        return Decimal("0"), None, 0, 0
    values = sorted(
        value
        for second, value in top_by_second.items()
        if first_second <= second <= last_second
    )
    observed = len(values)
    missing = expected - observed
    if missing < 0:
        return Decimal("0"), None, observed, 0
    coverage = Decimal(observed) / Decimal(expected)
    nearest_rank = max(1, (expected * 5 + 99) // 100)
    p05 = (
        Decimal("0")
        if nearest_rank <= missing
        else values[nearest_rank - missing - 1]
    )
    return coverage, p05, observed, missing


def verify(
    root: Path,
    *,
    config_path: Path,
    spec_path: Path,
    events_path: Path,
    smtp_path: Path,
) -> dict[str, Any]:
    root = root.resolve()
    config_path = config_path.resolve()
    spec_path = spec_path.resolve()
    events_path = events_path.resolve()
    smtp_path = smtp_path.resolve()
    checks: dict[str, bool] = {
        "live_read_only_config_present": config_path.is_file(),
        "read_only_profile_selected": False,
        "no_trading_authority_selected": False,
        "binance_credentials_structurally_absent": False,
        "account_commission_query_disabled": False,
        "frozen_observation_spec_valid": False,
        "configuration_matches_frozen_observation_spec": False,
        "observation_event_log_present": events_path.is_file(),
        "event_log_complete_line_boundary": False,
        "event_integrity_valid": False,
        "read_only_runtime_ready": False,
        "same_strategy_adapter_and_pure_logic_loaded": False,
        "data_client_loaded": False,
        "runtime_binance_credentials_absent": False,
        "execution_client_absent": False,
        "database_connection_absent": False,
        "execution_action_repository_absent": False,
        "persisted_action_capability_absent": False,
        "runtime_real_write_gate_closed": False,
        "source_1m_bars_observed": False,
        "internal_15m_bars_observed": False,
        "bar_sequences_monotonic": False,
        "source_1m_continuity_qualified": False,
        "internal_15m_continuity_qualified": False,
        "mark_price_observed": False,
        "mark_price_continuity_qualified": False,
        "top_of_book_each_second_observed": False,
        "minimum_seven_day_duration_elapsed": False,
        "trigger_or_explicit_expiry_observed": False,
        "market_data_gap_recovered": False,
        "controlled_restart_exactly_once": False,
        "actual_test_email_qualified": _smtp_qualified(smtp_path),
        "top_of_book_fifth_percentile_computed": False,
        "entry_notional_cap_derived_at_ten_percent": False,
        "exit_notional_cap_derived_at_ten_percent": False,
        "no_live_execution_action_created": True,
        "no_venue_write_event_observed": True,
    }
    errors: list[str] = []
    observations: dict[str, Any] = {
        "configuration_digest": None,
        "observation_id": None,
        "parameter_digest": None,
        "event_count": 0,
        "event_log_snapshot_bytes": 0,
        "event_log_ignored_trailing_bytes": 0,
        "source_1m_count": 0,
        "internal_15m_count": 0,
        "mark_price_count": 0,
        "mark_price_coverage": "0",
        "mark_price_maximum_gap_seconds": 0,
        "top_of_book_second_count": 0,
        "top_of_book_missing_second_count": 0,
        "top_of_book_coverage": "0",
        "proposal_preview_count": 0,
        "source_gap_count": 0,
        "source_1m_coverage": "0",
        "source_1m_maximum_gap_seconds": 0,
        "internal_15m_coverage": "0",
        "internal_15m_maximum_gap_seconds": 0,
        "maximum_controlled_process_gap_seconds": 0.0,
        "elapsed_days": 0.0,
        "taker_top_of_book_notional_p05": None,
        "first_live_entry_notional_cap": None,
        "first_live_exit_notional_cap": None,
        "capital_caps_are_qualification_evidence_not_authorization": True,
    }

    settings = None
    if config_path.is_file():
        try:
            settings = load_settings(config_path)
            observations["configuration_digest"] = settings_digest(settings)
            checks["read_only_profile_selected"] = (
                settings.release.profile == "BINANCE_LIVE_READ_ONLY"
            )
            checks["no_trading_authority_selected"] = (
                settings.release.authority_class == "NO_TRADING_AUTHORITY"
            )
            checks["binance_credentials_structurally_absent"] = (
                settings.executor.binance_api_key_reference is None
                and settings.executor.binance_api_secret_reference is None
            )
            checks["account_commission_query_disabled"] = True
        except Exception as exc:
            errors.append(f"LIVE_READ_ONLY_CONFIG_INVALID:{type(exc).__name__}")

    spec: ForwardObservationSpec | None = None
    if spec_path.is_file():
        try:
            spec = load_forward_observation_spec(spec_path)
            observations["observation_id"] = spec.observation_id
            observations["parameter_digest"] = spec.parameter_digest
            checks["frozen_observation_spec_valid"] = True
        except Exception as exc:
            errors.append(f"FORWARD_OBSERVATION_SPEC_INVALID:{type(exc).__name__}")

    if settings is not None and spec is not None:
        checks["configuration_matches_frozen_observation_spec"] = (
            settings_digest(settings) == spec.configuration_digest
        )
        if not checks["configuration_matches_frozen_observation_spec"]:
            errors.append("OBSERVATION_CONFIGURATION_DIGEST_MISMATCH")

    event_scan = scan_event_log(events_path, spec=spec)
    errors.extend(event_scan.errors)
    observations["event_count"] = event_scan.event_count
    observations["event_log_snapshot_bytes"] = event_scan.snapshot_bytes
    observations["event_log_ignored_trailing_bytes"] = event_scan.ignored_trailing_bytes
    checks["event_log_complete_line_boundary"] = (
        events_path.is_file() and event_scan.ignored_trailing_bytes == 0
    )
    checks["event_integrity_valid"] = (
        bool(event_scan.event_count)
        and not event_scan.errors
        and checks["event_log_complete_line_boundary"]
    )
    if spec is not None and event_scan.event_count:
        source_ns = event_scan.source_ns
        target_ns = event_scan.target_ns
        observations.update(
            {
                "source_1m_count": len(source_ns),
                "internal_15m_count": len(target_ns),
                "mark_price_count": event_scan.mark_price_count,
                "top_of_book_second_count": len(event_scan.top_by_second),
                "proposal_preview_count": event_scan.proposal_preview_count,
            }
        )
        checks["read_only_runtime_ready"] = bool(event_scan.ready_count)
        checks["same_strategy_adapter_and_pure_logic_loaded"] = (
            event_scan.strategy_adapter_started
        )
        checks["data_client_loaded"] = event_scan.data_client_loaded
        checks["runtime_binance_credentials_absent"] = (
            bool(event_scan.ready_count) and event_scan.binance_credentials_absent
        )
        checks["account_commission_query_disabled"] = (
            checks["account_commission_query_disabled"]
            and bool(event_scan.ready_count)
            and event_scan.commission_query_disabled
        )
        checks["execution_client_absent"] = (
            bool(event_scan.ready_count) and event_scan.execution_client_absent
        )
        checks["database_connection_absent"] = (
            bool(event_scan.ready_count) and event_scan.database_connection_absent
        )
        checks["execution_action_repository_absent"] = (
            bool(event_scan.ready_count)
            and event_scan.execution_action_repository_absent
        )
        checks["persisted_action_capability_absent"] = (
            bool(event_scan.ready_count)
            and event_scan.persisted_action_capability_absent
        )
        checks["runtime_real_write_gate_closed"] = (
            bool(event_scan.ready_count) and event_scan.runtime_real_write_gate_closed
        )
        checks["source_1m_bars_observed"] = bool(source_ns)
        checks["internal_15m_bars_observed"] = bool(target_ns)
        source_monotonic = source_ns == sorted(set(source_ns))
        target_monotonic = target_ns == sorted(set(target_ns))
        checks["bar_sequences_monotonic"] = source_monotonic and target_monotonic
        checks["mark_price_observed"] = bool(event_scan.mark_price_count)
        source_coverage, source_maximum_gap, source_aligned = _bar_sequence_coverage(
            source_ns,
            interval_seconds=60,
            starts_at=spec.starts_at.astimezone(UTC),
        )
        target_coverage, target_maximum_gap, target_aligned = _bar_sequence_coverage(
            target_ns,
            interval_seconds=900,
            starts_at=spec.starts_at.astimezone(UTC),
        )
        observations["source_1m_coverage"] = canonical_decimal(source_coverage)
        observations["source_1m_maximum_gap_seconds"] = source_maximum_gap
        observations["internal_15m_coverage"] = canonical_decimal(target_coverage)
        observations["internal_15m_maximum_gap_seconds"] = target_maximum_gap
        checks["source_1m_continuity_qualified"] = (
            source_coverage >= SOURCE_1M_MINIMUM_COVERAGE
            and source_maximum_gap <= MAXIMUM_SOURCE_GAP_SECONDS
            and source_aligned
        )
        checks["internal_15m_continuity_qualified"] = (
            target_coverage >= INTERNAL_15M_MINIMUM_COVERAGE
            and target_maximum_gap <= MAXIMUM_INTERNAL_GAP_SECONDS
            and target_aligned
        )
        source_gaps = [
            (current - previous) / 1_000_000_000
            for previous, current in zip(source_ns, source_ns[1:])
            if current - previous > 90_000_000_000
        ]
        observations["source_gap_count"] = len(source_gaps)
        observations["maximum_controlled_process_gap_seconds"] = (
            event_scan.maximum_process_gap_seconds
        )
        checks["market_data_gap_recovered"] = (
            event_scan.process_start_count >= 2
            and event_scan.maximum_process_gap_seconds > 90
            and event_scan.market_data_recovered_after_gap
        )
        checks["controlled_restart_exactly_once"] = (
            event_scan.process_start_count == 2
            and 90 < event_scan.maximum_process_gap_seconds <= 300
        )
        last_market_ns = max(source_ns + target_ns, default=0)
        last_market_at = datetime.fromtimestamp(last_market_ns / 1_000_000_000, tz=UTC)
        mark_coverage, mark_maximum_gap = _bucket_coverage(
            event_scan.mark_ns,
            bucket_seconds=60,
            starts_at=spec.starts_at.astimezone(UTC),
            ends_at=last_market_at,
        )
        observations["mark_price_coverage"] = canonical_decimal(mark_coverage)
        observations["mark_price_maximum_gap_seconds"] = mark_maximum_gap
        checks["mark_price_continuity_qualified"] = (
            mark_coverage >= MARK_PRICE_MINIMUM_COVERAGE
            and mark_maximum_gap <= MAXIMUM_SOURCE_GAP_SECONDS
        )
        elapsed = last_market_at - spec.starts_at.astimezone(UTC)
        observations["elapsed_days"] = max(0.0, elapsed.total_seconds() / 86400)
        checks["minimum_seven_day_duration_elapsed"] = (
            last_market_at >= spec.minimum_end_at.astimezone(UTC)
        )
        checks["trigger_or_explicit_expiry_observed"] = (
            bool(event_scan.proposal_preview_count)
            or last_market_at >= spec.entry_valid_until
        )
        top_coverage, p05, top_observed, top_missing = _top_of_book_window(
            event_scan.top_by_second,
            starts_at=spec.starts_at.astimezone(UTC),
            ends_at=last_market_at,
        )
        observations["top_of_book_second_count"] = top_observed
        observations["top_of_book_missing_second_count"] = top_missing
        observations["top_of_book_coverage"] = canonical_decimal(top_coverage)
        checks["top_of_book_each_second_observed"] = (
            top_coverage >= TOP_OF_BOOK_MINIMUM_COVERAGE
        )
        if p05 is not None and p05 > 0:
            cap = p05 * Decimal("0.10")
            observations["taker_top_of_book_notional_p05"] = canonical_decimal(p05)
            observations["first_live_entry_notional_cap"] = canonical_decimal(cap)
            observations["first_live_exit_notional_cap"] = canonical_decimal(cap)
            checks["top_of_book_fifth_percentile_computed"] = True
            checks["entry_notional_cap_derived_at_ten_percent"] = True
            checks["exit_notional_cap_derived_at_ten_percent"] = True
        checks["no_live_execution_action_created"] = (
            not event_scan.live_execution_action_created
        )
        checks["no_venue_write_event_observed"] = (
            not event_scan.venue_write_event_observed
        )
        if event_scan.observation_identity_mismatch:
            errors.append("OBSERVATION_IDENTITY_MISMATCH")
        if event_scan.parameter_digest_mismatch:
            errors.append("OBSERVATION_PARAMETER_DIGEST_MISMATCH")
        if event_scan.configuration_digest_mismatch:
            errors.append("OBSERVATION_EVENT_CONFIGURATION_DIGEST_MISMATCH")

    status = classify_live_read_only(checks, integrity_errors=errors)
    evidence: dict[str, Any] = {
        "schema_version": 1,
        "stage": "B04_BINANCE_LIVE_READ_ONLY_OBSERVATION",
        "observed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "status": status,
        "checks": checks,
        "observations": observations,
        "source_sha256": {
            "src/halpha/executor/runtime.py": _sha256_file(
                root / "src/halpha/executor/runtime.py"
            ),
            "src/halpha/executor/forward_observation.py": _sha256_file(
                root / "src/halpha/executor/forward_observation.py"
            ),
            "src/halpha/planning/adapter.py": _sha256_file(
                root / "src/halpha/planning/adapter.py"
            ),
            "tools/qualification/verify_b04_live_read_only.py": _sha256_file(
                root / "tools/qualification/verify_b04_live_read_only.py"
            ),
        },
        "input_sha256": {
            "config": _sha256_file(config_path) if config_path.is_file() else None,
            "spec": _sha256_file(spec_path) if spec_path.is_file() else None,
            "events": event_scan.snapshot_sha256,
            "smtp_evidence": _sha256_file(smtp_path) if smtp_path.is_file() else None,
        },
        "scope": (
            "ONE_PRODUCT_EXECUTOR_PUBLIC_DATA_ONLY_SAME_ADAPTER_NO_BINANCE_"
            "CREDENTIAL_NO_EXECUTION_CLIENT_NO_DATABASE_NO_EXECUTION_ACTION_"
            "NO_VENUE_WRITE"
        ),
        "errors": errors,
        "superseded_by": None,
    }
    evidence["evidence_digest"] = sha256(_canonical(evidence)).hexdigest()
    return evidence


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, default=ROOT)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--spec", type=Path, default=DEFAULT_SPEC)
    parser.add_argument("--events", type=Path, default=DEFAULT_EVENTS)
    parser.add_argument("--smtp-evidence", type=Path, default=DEFAULT_SMTP)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    root = args.repository_root.resolve()
    output = args.output.resolve()
    if not output.is_relative_to(root):
        raise RuntimeError("B04_LIVE_READ_ONLY_OUTPUT_OUTSIDE_REPOSITORY")
    evidence = verify(
        root,
        config_path=args.config,
        spec_path=args.spec,
        events_path=args.events,
        smtp_path=args.smtp_evidence,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(f"{output.suffix}.tmp")
    temporary.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    temporary.replace(output)
    print(json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if evidence["status"] in {"IN_PROGRESS", "QUALIFIED"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
