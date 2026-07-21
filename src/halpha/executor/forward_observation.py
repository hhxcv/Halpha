"""Read-only forward-observation inputs and append-only evidence callbacks."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
import json
import os
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from halpha.domain_values import canonical_decimal, content_digest, decimal_from_string
from halpha.planning.registry import (
    ONE_SHOT_STRATEGY_ID,
    ONE_SHOT_STRATEGY_VERSION,
    OneShotParameters,
)
from halpha.planning.strategies.one_shot import StrategyProposal
from halpha.source_identity import (
    SourceIdentityError,
    capture_stable_source_sha256,
    source_sha256_digest,
)


FORWARD_OBSERVATION_SOURCE_PATTERNS = (
    "pyproject.toml",
    "requirements/runtime.txt",
    "config/halpha.live-read-only.toml",
    "src/halpha/**/*.py",
)


class ForwardObservationError(RuntimeError):
    """Sanitized failure in the qualification-only observation boundary."""


class ForwardObservationSpec(BaseModel):
    """Non-secret inputs for one explicitly started read-only observation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[4] = 4
    observation_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,95}$")
    profile: Literal["BINANCE_LIVE_READ_ONLY"] = "BINANCE_LIVE_READ_ONLY"
    activation_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,95}$")
    instrument_ref: Literal["BTCUSDT-PERP"] = "BTCUSDT-PERP"
    strategy_id: Literal["ONE_SHOT_DONCHIAN_ATR_BREAKOUT"] = ONE_SHOT_STRATEGY_ID
    strategy_version: Literal["1.0.1"] = ONE_SHOT_STRATEGY_VERSION
    strategy_evidence_ref: str = Field(min_length=1, max_length=512)
    strategy_evidence_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    configuration_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_sha256: dict[str, str] = Field(min_length=1)
    source_sha256_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    parameters: OneShotParameters
    parameter_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    starts_at: datetime
    max_allowed_loss: str
    max_notional: str
    max_margin: str
    effective_leverage: str
    capital_input_source: Literal["FROZEN_NON_AUTHORIZING_OBSERVATION_ENVELOPE"] = (
        "FROZEN_NON_AUTHORIZING_OBSERVATION_ENVELOPE"
    )

    @field_validator(
        "max_allowed_loss",
        "max_notional",
        "max_margin",
        "effective_leverage",
    )
    @classmethod
    def positive_decimal_strings(cls, value: str) -> str:
        return canonical_decimal(
            decimal_from_string(value, code="FORWARD_OBSERVATION_CAPITAL_INVALID", positive=True)
        )

    @model_validator(mode="after")
    def validate_inputs_and_digest(self) -> "ForwardObservationSpec":
        if self.starts_at.tzinfo is None:
            raise ValueError("FORWARD_OBSERVATION_TIMEZONE_REQUIRED")
        actual_digest = content_digest(self.parameters.model_dump(mode="json"))
        if actual_digest != self.parameter_digest:
            raise ValueError("FORWARD_OBSERVATION_PARAMETER_DIGEST_MISMATCH")
        try:
            actual_source_digest = source_sha256_digest(self.source_sha256)
        except SourceIdentityError as exc:
            raise ValueError(str(exc)) from None
        if actual_source_digest != self.source_sha256_digest:
            raise ValueError("FORWARD_OBSERVATION_SOURCE_DIGEST_MISMATCH")
        return self

    @property
    def entry_valid_until(self) -> datetime:
        return self.starts_at.astimezone(UTC) + timedelta(
            minutes=self.parameters.entry_valid_minutes
        )


def load_forward_observation_spec(path: Path) -> ForwardObservationSpec:
    """Load one explicit spec without allowing a symlink or unknown fields."""

    if path.is_symlink():
        raise ForwardObservationError("FORWARD_OBSERVATION_SPEC_SYMLINK_FORBIDDEN")
    resolved = path.resolve()
    if not resolved.is_file():
        raise ForwardObservationError("FORWARD_OBSERVATION_SPEC_MISSING")
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
        return ForwardObservationSpec.model_validate(payload)
    except ForwardObservationError:
        raise
    except Exception as exc:
        raise ForwardObservationError(
            f"FORWARD_OBSERVATION_SPEC_INVALID type={type(exc).__name__}"
        ) from None


def capture_forward_observation_source_identity(root: Path) -> dict[str, str]:
    """Capture the exact code and qualification-tool set for one observation."""

    try:
        return capture_stable_source_sha256(
            root,
            FORWARD_OBSERVATION_SOURCE_PATTERNS,
        )
    except SourceIdentityError as exc:
        raise ForwardObservationError(str(exc)) from None


def require_forward_observation_source_identity(
    root: Path,
    spec: ForwardObservationSpec,
) -> dict[str, str]:
    """Reject an observation process whose repository sources drifted."""

    current = capture_forward_observation_source_identity(root)
    if current != spec.source_sha256:
        raise ForwardObservationError(
            "FORWARD_OBSERVATION_SOURCE_IDENTITY_DRIFT"
        )
    return current


class ForwardObservationEvidence:
    """Append sanitized live facts; this is evidence, never product authority."""

    MAX_PARTIAL_TAIL_BYTES = 1024 * 1024

    def __init__(self, spec: ForwardObservationSpec, path: Path) -> None:
        self.spec = spec
        if path.is_symlink():
            raise ForwardObservationError(
                "FORWARD_OBSERVATION_EVIDENCE_SYMLINK_FORBIDDEN"
            )
        self.path = path.resolve()
        self._pending_second: int | None = None
        self._pending_taker_notional: Decimal | None = None
        self._last_mark_minute: int | None = None
        self._started = False
        self._closed = False
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record_process_started(self) -> None:
        if self._started:
            raise ForwardObservationError(
                "FORWARD_OBSERVATION_PROCESS_START_ALREADY_RECORDED"
            )
        recovered_tail = self._recover_partial_tail()
        if recovered_tail is not None:
            self._append(
                {
                    "event": "OBSERVATION_PARTIAL_TAIL_RECOVERED",
                    "observed_at": datetime.now(UTC),
                    **recovered_tail,
                }
            )
        self._append(
            {
                "event": "OBSERVATION_PROCESS_STARTED",
                "observed_at": datetime.now(UTC),
                "observation_id": self.spec.observation_id,
                "profile": self.spec.profile,
                "activation_id": self.spec.activation_id,
                "instrument_ref": self.spec.instrument_ref,
                "parameter_digest": self.spec.parameter_digest,
                "strategy_evidence_ref": self.spec.strategy_evidence_ref,
                "strategy_evidence_digest": self.spec.strategy_evidence_digest,
                "configuration_digest": self.spec.configuration_digest,
                "source_sha256_digest": self.spec.source_sha256_digest,
                "entry_valid_until": self.spec.entry_valid_until,
                "capital_input_source": self.spec.capital_input_source,
            }
        )
        self._started = True

    def _require_started(self) -> None:
        if not self._started:
            raise ForwardObservationError(
                "FORWARD_OBSERVATION_PROCESS_START_REQUIRED"
            )

    def _recover_partial_tail(self) -> dict[str, object] | None:
        """Discard only an incomplete final line before appending a new process."""

        if not self.path.is_file() or self.path.stat().st_size == 0:
            return None
        size = self.path.stat().st_size
        with self.path.open("rb") as stream:
            stream.seek(-1, os.SEEK_END)
            if stream.read(1) == b"\n":
                return None
            window_size = min(size, self.MAX_PARTIAL_TAIL_BYTES + 1)
            stream.seek(size - window_size)
            window = stream.read(window_size)
        newline_at = window.rfind(b"\n")
        tail = window[newline_at + 1 :] if newline_at >= 0 else window
        if len(tail) > self.MAX_PARTIAL_TAIL_BYTES or (
            newline_at < 0 and size > len(window)
        ):
            raise ForwardObservationError(
                "FORWARD_OBSERVATION_PARTIAL_TAIL_TOO_LARGE"
            )
        complete_size = size - len(tail)
        with self.path.open("r+b") as stream:
            stream.truncate(complete_size)
            stream.flush()
            os.fsync(stream.fileno())
        return {
            "discarded_partial_tail_bytes": len(tail),
            "discarded_partial_tail_sha256": sha256(tail).hexdigest(),
        }

    def _append(self, payload: dict[str, Any]) -> None:
        serialized = {
            key: (
                value.astimezone(UTC).isoformat().replace("+00:00", "Z")
                if isinstance(value, datetime)
                else value
            )
            for key, value in payload.items()
        }
        # Every line is independently attributable to the frozen observation.
        # This prevents a valid event from another process or configuration from
        # satisfying a later recovery/qualification check in the shared log.
        serialized["observation_id"] = self.spec.observation_id
        serialized["parameter_digest"] = self.spec.parameter_digest
        serialized["configuration_digest"] = self.spec.configuration_digest
        serialized["source_sha256_digest"] = self.spec.source_sha256_digest
        serialized["event_digest"] = content_digest(serialized)
        with self.path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(
                json.dumps(
                    serialized,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                )
                + "\n"
            )
            stream.flush()

    def record_runtime_ready(self, evidence: dict[str, object]) -> None:
        self._require_started()
        self._append(
            {
                "event": "READ_ONLY_RUNTIME_READY",
                "observed_at": datetime.now(UTC),
                **evidence,
            }
        )

    def record_bar(self, bar: object) -> None:
        self._require_started()
        self._append(
            {
                "event": "BAR_OBSERVED",
                "observed_at": datetime.now(UTC),
                "bar_type": str(getattr(bar, "bar_type")),
                "ts_event_ns": int(getattr(bar, "ts_event")),
            }
        )

    def record_mark_price(self, mark_price: object) -> None:
        self._require_started()
        ts_event = int(getattr(mark_price, "ts_event"))
        minute = ts_event // 60_000_000_000
        if minute == self._last_mark_minute:
            return
        self._last_mark_minute = minute
        self._append(
            {
                "event": "MARK_PRICE_OBSERVED",
                "observed_at": datetime.now(UTC),
                "ts_event_ns": ts_event,
                "price": str(getattr(mark_price, "value")),
            }
        )

    def record_quote_tick(self, tick: object) -> None:
        self._require_started()
        ts_event = int(getattr(tick, "ts_event"))
        second = ts_event // 1_000_000_000
        side_price = (
            getattr(tick, "ask_price")
            if self.spec.parameters.direction.value == "LONG"
            else getattr(tick, "bid_price")
        )
        side_size = (
            getattr(tick, "ask_size")
            if self.spec.parameters.direction.value == "LONG"
            else getattr(tick, "bid_size")
        )
        notional = Decimal(str(side_price)) * Decimal(str(side_size))
        if self._pending_second is None:
            self._pending_second = second
            self._pending_taker_notional = notional
            return
        if second == self._pending_second:
            self._pending_taker_notional = min(
                self._pending_taker_notional or notional,
                notional,
            )
            return
        self._flush_pending_quote()
        self._pending_second = second
        self._pending_taker_notional = notional

    def _flush_pending_quote(self) -> None:
        if self._pending_second is None or self._pending_taker_notional is None:
            return
        self._append(
            {
                "event": "TAKER_TOP_OF_BOOK_SECOND",
                "observed_at": datetime.now(UTC),
                "venue_second": self._pending_second,
                "direction": self.spec.parameters.direction.value,
                "minimum_notional": canonical_decimal(self._pending_taker_notional),
            }
        )
        self._pending_second = None
        self._pending_taker_notional = None

    def record_proposal(self, proposal: StrategyProposal) -> None:
        self._require_started()
        self._append(
            {
                "event": "UNSUBMITTABLE_STRATEGY_PROPOSAL_PREVIEW",
                "observed_at": datetime.now(UTC),
                "proposal": proposal.model_dump(mode="json"),
                "submission_capability": "ABSENT",
                "runtime_real_write_gate": "CLOSED",
            }
        )

    def close(self, *, reason_code: str) -> None:
        if self._closed:
            return
        if not self._started:
            self._closed = True
            return
        self._flush_pending_quote()
        self._append(
            {
                "event": "OBSERVATION_PROCESS_STOPPED",
                "observed_at": datetime.now(UTC),
                "reason_code": reason_code,
            }
        )
        self._closed = True
