"""Thin, research-only helpers for Git-external public data.

This module deliberately does not download data, load another study, implement
indicators, or expose product runtime state.  A study owns source-specific
retrieval and parsing; this module only gives verified bytes one stable identity
and resolves the current shared location before explicitly supplied legacy paths.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Literal, Mapping


DATA_ROOT_ENV = "HALPHA_RESEARCH_DATA_ROOT"
DEFAULT_DATA_ROOT = Path("D:/projects/Codex/CodexHome/research-data/halpha")
EXTERNAL_KINDS = frozenset({"derived", "replay", "latest", "tmp"})
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_SEGMENT_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+=-]{0,127}$")
_SUFFIX_PATTERN = re.compile(r"^(?:\.[A-Za-z0-9][A-Za-z0-9._-]{0,15})?$")
_UTC_SNAPSHOT_PERIOD_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{6}Z$",
    re.IGNORECASE,
)
_WINDOWS_RESERVED_NAMES = frozenset(
    {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{index}" for index in range(1, 10)),
        *(f"LPT{index}" for index in range(1, 10)),
    }
)
_LOWERCASE_IDENTITY_FIELDS = frozenset({"source", "venue", "family", "interval"})


class ResearchDataError(RuntimeError):
    """Base error for research data resolution and integrity failures."""


class ResearchDataIntegrityError(ResearchDataError):
    """A file exists but does not match its recorded byte identity."""


class ResearchDataUnavailableError(ResearchDataError):
    """No verified canonical or explicitly supplied legacy file is available."""


def _segment(value: str, field: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field} must be a string")
    if not _SEGMENT_PATTERN.fullmatch(value):
        raise ValueError(
            f"{field} must be one safe path segment containing only letters, "
            "digits, '.', '_', '+', '=' or '-'"
        )
    if value.endswith("."):
        raise ValueError(f"{field} must not end with '.'")
    if value.split(".", 1)[0].upper() in _WINDOWS_RESERVED_NAMES:
        raise ValueError(f"{field} must not use a Windows reserved device name")
    return value


def _canonical_identity_segment(value: str, field: str) -> str:
    checked = _segment(value, field)
    if field in _LOWERCASE_IDENTITY_FIELDS:
        return checked.lower()
    if field == "instrument":
        return checked.upper()
    if field == "period":
        if _UTC_SNAPSHOT_PERIOD_PATTERN.fullmatch(checked):
            return checked.upper()
        return checked.lower()
    raise ValueError(f"unsupported identity field: {field}")


def _canonical_suffix(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("suffix must be a string")
    if not _SUFFIX_PATTERN.fullmatch(value):
        raise ValueError(
            "suffix must be empty or a short safe extension beginning with '.'"
        )
    if value.casefold() == ".zip.checksum":
        return ".zip.CHECKSUM"
    return value.lower()


@dataclass(frozen=True)
class RawDataRef:
    """Stable identity for one immutable public raw or normalized input."""

    source: str
    venue: str
    instrument: str
    family: str
    interval: str
    period: str
    sha256: str
    suffix: str = ""
    bytes: int | None = None
    url: str | None = None
    checksum_url: str | None = None

    def __post_init__(self) -> None:
        for field in ("source", "venue", "instrument", "family", "interval", "period"):
            object.__setattr__(
                self,
                field,
                _canonical_identity_segment(getattr(self, field), field),
            )
        if not isinstance(self.sha256, str) or not _SHA256_PATTERN.fullmatch(
            self.sha256
        ):
            raise ValueError(
                "sha256 must contain exactly 64 lowercase hexadecimal characters"
            )
        object.__setattr__(self, "suffix", _canonical_suffix(self.suffix))
        if self.bytes is not None and (
            isinstance(self.bytes, bool)
            or not isinstance(self.bytes, int)
            or self.bytes < 0
        ):
            raise ValueError("bytes must be non-negative")
        for field in ("url", "checksum_url"):
            value = getattr(self, field)
            if value is not None and not isinstance(value, str):
                raise TypeError(f"{field} must be a string or None")

    @property
    def relative_path(self) -> Path:
        return (
            Path("raw")
            / self.source
            / self.venue
            / self.instrument
            / self.family
            / self.interval
            / self.period
            / f"{self.sha256}{self.suffix}"
        )

    def manifest_value(self) -> dict[str, str | int | None]:
        return {
            "source": self.source,
            "venue": self.venue,
            "instrument": self.instrument,
            "family": self.family,
            "interval": self.interval,
            "period": self.period,
            "sha256": self.sha256,
            "bytes": self.bytes,
            "suffix": self.suffix,
            "relative_path": self.relative_path.as_posix(),
            "url": self.url,
            "checksum_url": self.checksum_url,
        }

    @classmethod
    def from_manifest_value(cls, value: Mapping[str, object]) -> "RawDataRef":
        """Rebuild and strictly validate one value emitted by ``manifest_value``."""

        if not isinstance(value, Mapping):
            raise TypeError("manifest value must be a mapping")
        required = (
            "source",
            "venue",
            "instrument",
            "family",
            "interval",
            "period",
            "sha256",
            "relative_path",
        )
        missing = [field for field in required if field not in value]
        if missing:
            raise ValueError(f"manifest value is missing required fields: {missing}")

        identity_fields = (
            "source",
            "venue",
            "instrument",
            "family",
            "interval",
            "period",
        )
        for field in identity_fields + ("sha256", "relative_path"):
            if not isinstance(value[field], str):
                raise TypeError(f"manifest field {field} must be a string")

        raw_bytes = value.get("bytes")
        if raw_bytes is not None and (
            isinstance(raw_bytes, bool) or not isinstance(raw_bytes, int)
        ):
            raise TypeError("manifest field bytes must be an integer or None")
        suffix = value.get("suffix", "")
        url = value.get("url")
        checksum_url = value.get("checksum_url")
        for field, item in (
            ("suffix", suffix),
            ("url", url),
            ("checksum_url", checksum_url),
        ):
            if item is not None and not isinstance(item, str):
                raise TypeError(f"manifest field {field} must be a string or None")

        ref = cls(
            source=value["source"],
            venue=value["venue"],
            instrument=value["instrument"],
            family=value["family"],
            interval=value["interval"],
            period=value["period"],
            sha256=value["sha256"],
            suffix=suffix or "",
            bytes=raw_bytes,
            url=url,
            checksum_url=checksum_url,
        )
        for field in identity_fields:
            if value[field] != getattr(ref, field):
                raise ValueError(
                    f"manifest field {field} is not in canonical case: "
                    f"expected {getattr(ref, field)!r}"
                )
        if (suffix or "") != ref.suffix:
            raise ValueError(
                f"manifest field suffix is not canonical: expected {ref.suffix!r}"
            )
        expected_relative_path = ref.relative_path.as_posix()
        if value["relative_path"] != expected_relative_path:
            raise ResearchDataIntegrityError(
                "manifest relative_path does not match its identity fields: "
                f"expected {expected_relative_path!r}, got {value['relative_path']!r}"
            )
        return ref


@dataclass(frozen=True)
class ResolvedRawData:
    path: Path
    origin: Literal["canonical", "legacy"]


@dataclass(frozen=True)
class InstalledRawData:
    path: Path
    materialization: Literal["existing", "hardlink", "copy", "bytes"]


@dataclass(frozen=True)
class RelinkedLegacyData:
    canonical_path: Path
    legacy_path: Path
    materialization: Literal["already-linked", "hardlink"]


def data_root(override: str | Path | None = None) -> Path:
    """Resolve explicit path, environment override, then the compatible default."""

    selected = override
    if selected is None:
        selected = os.environ.get(DATA_ROOT_ENV) or DEFAULT_DATA_ROOT
    return Path(selected).expanduser().resolve()


def external_path(
    kind: str,
    study_slug: str,
    *parts: str,
    root: str | Path | None = None,
) -> Path:
    """Locate reconstructable external material without creating it."""

    if kind not in EXTERNAL_KINDS:
        raise ValueError(f"kind must be one of {sorted(EXTERNAL_KINDS)}")
    path = data_root(root) / kind / _segment(study_slug, "study_slug")
    for index, part in enumerate(parts):
        path /= _segment(part, f"parts[{index}]")
    return path


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_file(path: str | Path, ref: RawDataRef) -> Path:
    candidate = Path(path).resolve()
    if not candidate.is_file():
        raise FileNotFoundError(candidate)
    actual_bytes = candidate.stat().st_size
    if ref.bytes is not None and actual_bytes != ref.bytes:
        raise ResearchDataIntegrityError(
            f"byte length mismatch for {candidate}: expected {ref.bytes}, got {actual_bytes}"
        )
    actual_sha256 = sha256_file(candidate)
    if actual_sha256 != ref.sha256:
        raise ResearchDataIntegrityError(
            f"SHA-256 mismatch for {candidate}: expected {ref.sha256}, got {actual_sha256}"
        )
    return candidate


def resolve_raw(
    ref: RawDataRef,
    *,
    root: str | Path | None = None,
    legacy_paths: Iterable[str | Path] = (),
) -> ResolvedRawData:
    """Resolve canonical bytes, then only caller-declared legacy paths."""

    root_path = data_root(root)
    canonical = root_path / ref.relative_path
    if canonical.exists():
        return ResolvedRawData(verify_file(canonical, ref), "canonical")
    for legacy_path in legacy_paths:
        supplied = Path(legacy_path).expanduser()
        if supplied.is_absolute():
            candidate = supplied.resolve()
        else:
            candidate = (root_path / supplied).resolve()
            try:
                candidate.relative_to(root_path)
            except ValueError as exc:
                raise ValueError(
                    f"relative legacy path escapes the research data root: {supplied}"
                ) from exc
        if candidate.exists():
            return ResolvedRawData(verify_file(candidate, ref), "legacy")
    source_hint = f"; reacquire from {ref.url}" if ref.url else ""
    raise ResearchDataUnavailableError(
        f"verified research data is unavailable at {canonical} or declared legacy paths"
        f"{source_hint}"
    )


def _new_temporary_path(target: Path) -> Path:
    descriptor, name = tempfile.mkstemp(
        prefix=f".{target.name}.",
        suffix=".tmp",
        dir=target.parent,
    )
    os.close(descriptor)
    return Path(name)


def _publish_verified_temporary(
    temporary: Path,
    target: Path,
    ref: RawDataRef,
) -> Literal["published", "existing"]:
    """Publish a verified sibling without exposing partially written bytes."""

    verify_file(temporary, ref)
    if target.exists():
        verify_file(target, ref)
        return "existing"
    try:
        os.link(temporary, target)
    except FileExistsError:
        verify_file(target, ref)
        return "existing"
    except OSError as link_error:
        if os.name != "nt":
            raise ResearchDataError(
                f"cannot atomically publish {target} without hardlink support"
            ) from link_error
        try:
            os.rename(temporary, target)
        except FileExistsError:
            verify_file(target, ref)
            return "existing"
        except OSError as rename_error:
            raise ResearchDataError(
                f"cannot atomically publish {target}"
            ) from rename_error
    verify_file(target, ref)
    return "published"


def install_raw(
    ref: RawDataRef,
    source_path: str | Path,
    *,
    root: str | Path | None = None,
    prefer_hardlink: bool = True,
) -> InstalledRawData:
    """Install verified bytes once without overwriting an existing identity."""

    source = verify_file(source_path, ref)
    target = data_root(root) / ref.relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        return InstalledRawData(verify_file(target, ref), "existing")

    if prefer_hardlink:
        try:
            os.link(source, target)
            try:
                return InstalledRawData(verify_file(target, ref), "hardlink")
            except Exception:
                target.unlink(missing_ok=True)
                raise
        except FileExistsError:
            return InstalledRawData(verify_file(target, ref), "existing")
        except OSError:
            pass

    temporary = _new_temporary_path(target)
    try:
        with source.open("rb") as source_handle, temporary.open("wb") as target_handle:
            shutil.copyfileobj(source_handle, target_handle, length=1024 * 1024)
            target_handle.flush()
            os.fsync(target_handle.fileno())
        disposition = _publish_verified_temporary(temporary, target, ref)
        return InstalledRawData(
            verify_file(target, ref),
            "existing" if disposition == "existing" else "copy",
        )
    finally:
        temporary.unlink(missing_ok=True)


def relink_verified_legacy(
    ref: RawDataRef,
    legacy_path: str | Path,
    *,
    root: str | Path | None = None,
) -> RelinkedLegacyData:
    """Replace one verified duplicate with a hardlink to canonical bytes.

    The caller must use this only for immutable raw inputs.  A temporary hardlink
    is verified before the legacy path is atomically replaced, so a failure before
    replacement leaves the original file in place.
    """

    canonical = verify_file(data_root(root) / ref.relative_path, ref)
    legacy = verify_file(legacy_path, ref)
    if os.path.samefile(canonical, legacy):
        return RelinkedLegacyData(canonical, legacy, "already-linked")

    temporary = legacy.with_name(f".{legacy.name}.{os.getpid()}.halpha-link")
    if temporary.exists():
        raise FileExistsError(temporary)
    try:
        os.link(canonical, temporary)
        verify_file(temporary, ref)
        os.replace(temporary, legacy)
    finally:
        temporary.unlink(missing_ok=True)
    verify_file(legacy, ref)
    if not os.path.samefile(canonical, legacy):
        raise ResearchDataIntegrityError(
            f"legacy path was not linked to canonical bytes: {legacy}"
        )
    return RelinkedLegacyData(canonical, legacy, "hardlink")


def store_verified_bytes(
    ref: RawDataRef,
    value: bytes,
    *,
    root: str | Path | None = None,
) -> InstalledRawData:
    """Install already-fetched bytes after checking their declared identity."""

    if ref.bytes is not None and len(value) != ref.bytes:
        raise ResearchDataIntegrityError(
            f"byte length mismatch: expected {ref.bytes}, got {len(value)}"
        )
    actual_sha256 = hashlib.sha256(value).hexdigest()
    if actual_sha256 != ref.sha256:
        raise ResearchDataIntegrityError(
            f"SHA-256 mismatch: expected {ref.sha256}, got {actual_sha256}"
        )

    target = data_root(root) / ref.relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        return InstalledRawData(verify_file(target, ref), "existing")
    temporary = _new_temporary_path(target)
    try:
        with temporary.open("wb") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        disposition = _publish_verified_temporary(temporary, target, ref)
        return InstalledRawData(
            verify_file(target, ref),
            "existing" if disposition == "existing" else "bytes",
        )
    finally:
        temporary.unlink(missing_ok=True)
