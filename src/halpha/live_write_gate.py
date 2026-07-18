"""Detached, fail-closed LIVE_WRITE deployment gate verification.

The binding is deliberately outside the repository and BuildManifest so it can
refer to the final manifest digest without creating a self-referential build.
It is non-secret, profile-specific deployment state; CAP records remain the
business authority and are rechecked before the effective gate can be OPEN.
"""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any, Callable, Literal

import pywintypes
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
import win32file
import win32security

from halpha.build_manifest import manifest_sha256, verify_manifest
from halpha.configuration import HalphaSettings
from halpha.windows_runtime import BUILTIN_ADMINISTRATORS_SID, SYSTEM_SID


class LiveWriteGateError(RuntimeError):
    """Sanitized fail-closed LIVE_WRITE gate failure."""


class _FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class LiveWriteGateBinding(_FrozenModel):
    schema_version: Literal[1]
    environment_id: str
    account_id: str
    profile: Literal["BINANCE_LIVE_WRITE"]
    live_write_build_capability: Literal["QUALIFIED"]
    b05_package_eligibility: Literal["AUTHORIZED"]
    runtime_real_write_gate: Literal["CLOSED", "OPEN"]
    build_manifest_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    user_authorization_ref: str = Field(min_length=3, max_length=200)
    account_capital_limit_version_ref: str | None = Field(default=None, min_length=3)
    machine_authorization_version_ref: str | None = Field(default=None, min_length=3)
    plan_allocation_ref: str | None = Field(default=None, min_length=3)
    effective_at: datetime
    expires_at: datetime

    @model_validator(mode="after")
    def validate_window_and_open_refs(self) -> "LiveWriteGateBinding":
        if self.effective_at.tzinfo is None or self.expires_at.tzinfo is None:
            raise ValueError("LIVE_WRITE_GATE_TIMEZONE_REQUIRED")
        if self.expires_at <= self.effective_at:
            raise ValueError("LIVE_WRITE_GATE_WINDOW_INVALID")
        references = (
            self.account_capital_limit_version_ref,
            self.machine_authorization_version_ref,
            self.plan_allocation_ref,
        )
        if self.runtime_real_write_gate == "OPEN" and any(ref is None for ref in references):
            raise ValueError("LIVE_WRITE_GATE_OPEN_REFS_REQUIRED")
        if self.runtime_real_write_gate == "CLOSED" and any(ref is not None for ref in references):
            raise ValueError("LIVE_WRITE_GATE_CLOSED_REFS_FORBIDDEN")
        return self


class LiveWriteGateStatus(_FrozenModel):
    live_write_build_capability: Literal["NOT_QUALIFIED", "QUALIFIED"]
    b05_package_eligibility: Literal["NOT_AUTHORIZED", "AUTHORIZED"]
    configured_runtime_real_write_gate: Literal["CLOSED", "OPEN"]
    runtime_real_write_gate: Literal["CLOSED", "OPEN"]
    build_manifest_digest: str | None = None
    user_authorization_ref: str | None = None
    account_capital_limit_version_ref: str | None = None
    machine_authorization_version_ref: str | None = None
    plan_allocation_ref: str | None = None
    authorized_activation_id: str | None = None
    binding_effective_at: datetime | None = None
    binding_expires_at: datetime | None = None
    violations: tuple[str, ...] = ()


def _file_grants(settings: HalphaSettings) -> dict[str, int]:
    return {
        SYSTEM_SID: win32file.FILE_ALL_ACCESS,
        BUILTIN_ADMINISTRATORS_SID: win32file.FILE_ALL_ACCESS,
        settings.windows.maintenance_sid: win32file.FILE_ALL_ACCESS,
        settings.windows.app_task_sid: win32file.FILE_GENERIC_READ,
        settings.windows.executor_task_sid: win32file.FILE_GENERIC_READ,
    }


def _assert_live_write_gate_security(
    path: Path,
    settings: HalphaSettings,
    *,
    expected_ace_flags: int,
    subject: str,
) -> None:

    try:
        descriptor = win32security.GetNamedSecurityInfo(
            str(path),
            win32security.SE_FILE_OBJECT,
            win32security.OWNER_SECURITY_INFORMATION
            | win32security.DACL_SECURITY_INFORMATION,
        )
        owner = str(
            win32security.ConvertSidToStringSid(
                descriptor.GetSecurityDescriptorOwner()
            )
        )
        dacl = descriptor.GetSecurityDescriptorDacl()
        control, _revision = descriptor.GetSecurityDescriptorControl()
    except pywintypes.error as exc:
        raise LiveWriteGateError(
            f"LIVE_WRITE_GATE_SECURITY_READ_FAILED code={exc.winerror}"
        ) from None
    except Exception as exc:
        raise LiveWriteGateError(
            f"LIVE_WRITE_GATE_SECURITY_READ_FAILED type={type(exc).__name__}"
        ) from None
    if owner != settings.windows.maintenance_sid:
        raise LiveWriteGateError(f"LIVE_WRITE_GATE_{subject}_OWNER_MISMATCH")
    if not control & win32security.SE_DACL_PROTECTED:
        raise LiveWriteGateError(f"LIVE_WRITE_GATE_{subject}_DACL_NOT_PROTECTED")
    expected = _file_grants(settings)
    if dacl is None or dacl.GetAceCount() != len(expected):
        raise LiveWriteGateError(f"LIVE_WRITE_GATE_{subject}_DACL_COUNT_MISMATCH")
    actual: dict[str, int] = {}
    for index in range(dacl.GetAceCount()):
        ace = dacl.GetAce(index)
        if ace[0][0] != win32security.ACCESS_ALLOWED_ACE_TYPE:
            raise LiveWriteGateError(
                f"LIVE_WRITE_GATE_{subject}_DACL_ACE_TYPE_MISMATCH"
            )
        if int(ace[0][1]) != expected_ace_flags:
            raise LiveWriteGateError(
                f"LIVE_WRITE_GATE_{subject}_DACL_ACE_FLAGS_MISMATCH"
            )
        sid = str(win32security.ConvertSidToStringSid(ace[2]))
        if sid in actual:
            raise LiveWriteGateError(
                f"LIVE_WRITE_GATE_{subject}_DACL_DUPLICATE_IDENTITY"
            )
        actual[sid] = int(ace[1])
    if actual != expected:
        raise LiveWriteGateError(f"LIVE_WRITE_GATE_{subject}_DACL_GRANTS_MISMATCH")


def assert_live_write_gate_security(path: Path, settings: HalphaSettings) -> None:
    """Require an owner-controlled, protected, exact read-only file DACL."""

    _assert_live_write_gate_security(
        path,
        settings,
        expected_ace_flags=0,
        subject="FILE",
    )


def assert_live_write_gate_directory_security(
    path: Path,
    settings: HalphaSettings,
) -> None:
    """Prevent a broader parent ACL from replacing an otherwise protected file."""

    _assert_live_write_gate_security(
        path,
        settings,
        expected_ace_flags=(
            win32security.OBJECT_INHERIT_ACE
            | win32security.CONTAINER_INHERIT_ACE
        ),
        subject="DIRECTORY",
    )


def _manifest_assessment(repo_root: Path, settings: HalphaSettings) -> tuple[str | None, bool, list[str]]:
    path = (repo_root / settings.release.build_manifest_path).resolve()
    if not path.is_relative_to(repo_root.resolve()):
        return None, False, ["BUILD_MANIFEST_PATH_OUTSIDE_REPOSITORY"]
    if not path.is_file() or path.is_symlink():
        return None, False, ["BUILD_MANIFEST_MISSING"]
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            raise TypeError("manifest root")
        digest = manifest_sha256(manifest)
        violations = verify_manifest(repo_root, manifest)
        capability = (
            not violations
            and manifest.get("build_eligible") is True
            and manifest.get("completeness") == {"status": "COMPLETE", "missing_required": []}
        )
        return digest, capability, list(violations)
    except Exception as exc:
        return None, False, [f"BUILD_MANIFEST_INVALID_{type(exc).__name__.upper()}"]


def require_live_write_gate_binding_provisionable(
    repo_root: Path,
    settings: HalphaSettings,
    binding: LiveWriteGateBinding,
    *,
    now: datetime | None = None,
) -> str:
    """Reject an invalid binding before the maintenance command changes disk."""

    if settings.release.profile != "BINANCE_LIVE_WRITE":
        raise LiveWriteGateError("LIVE_WRITE_GATE_PROFILE_REQUIRED")
    if (
        binding.environment_id != settings.release.environment_id
        or binding.account_id != settings.release.account_id
    ):
        raise LiveWriteGateError("LIVE_WRITE_GATE_BINDING_SCOPE_MISMATCH")
    observed_at = now or datetime.now(UTC)
    if not (binding.effective_at <= observed_at < binding.expires_at):
        raise LiveWriteGateError("LIVE_WRITE_GATE_BINDING_NOT_CURRENT")
    manifest_digest, capability, violations = _manifest_assessment(
        repo_root,
        settings,
    )
    if manifest_digest is None or not capability:
        raise LiveWriteGateError(
            "LIVE_WRITE_GATE_BUILD_NOT_QUALIFIED reasons="
            + ",".join(violations or ("BUILD_NOT_QUALIFIED",))
        )
    if binding.build_manifest_digest != manifest_digest:
        raise LiveWriteGateError("LIVE_WRITE_GATE_MANIFEST_MISMATCH")
    return manifest_digest


def _read_binding(
    settings: HalphaSettings,
    repo_root: Path,
) -> tuple[LiveWriteGateBinding | None, list[str]]:
    raw_path = settings.release.live_write_gate_path
    if raw_path is None:
        return None, ["LIVE_WRITE_GATE_PATH_MISSING"]
    path = Path(raw_path)
    try:
        if path.resolve().is_relative_to(repo_root.resolve()):
            return None, ["LIVE_WRITE_GATE_PATH_INSIDE_REPOSITORY"]
    except OSError:
        return None, ["LIVE_WRITE_GATE_PATH_INVALID"]
    if path.is_symlink():
        return None, ["LIVE_WRITE_GATE_SYMLINK_FORBIDDEN"]
    if not path.is_file():
        return None, ["LIVE_WRITE_GATE_BINDING_MISSING"]
    try:
        assert_live_write_gate_directory_security(path.parent, settings)
        assert_live_write_gate_security(path, settings)
    except LiveWriteGateError as exc:
        return None, [str(exc)]
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise TypeError("binding root")
        return LiveWriteGateBinding.model_validate(payload), []
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValidationError, TypeError) as exc:
        return None, [f"LIVE_WRITE_GATE_BINDING_INVALID_{type(exc).__name__.upper()}"]


def _database_assessment(
    connection: Any,
    settings: HalphaSettings,
    binding: LiveWriteGateBinding,
    now: datetime,
) -> tuple[list[str], str | None]:
    violations: list[str] = []
    limit_id = binding.account_capital_limit_version_ref
    authorization_id = binding.machine_authorization_version_ref
    allocation_id = binding.plan_allocation_ref
    if limit_id is None or authorization_id is None or allocation_id is None:
        return ["LIVE_WRITE_GATE_OPEN_REFS_REQUIRED"], None

    limit = connection.execute(
        """
        SELECT environment_kind, authority_class, account_ref, scope
        FROM halpha.account_capital_limit_version
        WHERE environment_id = %s AND capital_limit_version_id = %s
        """,
        (settings.release.environment_id, limit_id),
    ).fetchone()
    authorization = connection.execute(
        """
        SELECT activation_id, plan_version_ref, environment_kind, authority_class,
               account_ref, instrument_ref, valid_from, valid_until, terms
        FROM halpha.machine_authorization_version
        WHERE environment_id = %s AND authorization_version_id = %s
        """,
        (settings.release.environment_id, authorization_id),
    ).fetchone()
    allocation = connection.execute(
        """
        SELECT activation_id, capital_limit_version_ref, environment_kind,
               authority_class, status
        FROM halpha.plan_allocation
        WHERE environment_id = %s AND allocation_id = %s
        """,
        (settings.release.environment_id, allocation_id),
    ).fetchone()
    if limit is None:
        violations.append("LIVE_WRITE_CAPITAL_LIMIT_NOT_FOUND")
    if authorization is None:
        violations.append("LIVE_WRITE_MACHINE_AUTHORIZATION_NOT_FOUND")
    if allocation is None:
        violations.append("LIVE_WRITE_PLAN_ALLOCATION_NOT_FOUND")
    if violations:
        return violations, None

    activation_id = str(authorization[0])
    activation = connection.execute(
        """
        SELECT plan_version_ref, authorization_version_ref, allocation_ref,
               environment_kind, authority_class, account_ref, instrument_ref,
               lifecycle, run_state
        FROM halpha.plan_activation
        WHERE environment_id = %s AND activation_id = %s
        """,
        (settings.release.environment_id, activation_id),
    ).fetchone()
    if activation is None:
        return ["LIVE_WRITE_PLAN_ACTIVATION_NOT_FOUND"], None

    if (str(limit[0]), str(limit[1]), str(limit[2])) != (
        "LIVE",
        "LIVE_REAL_CAPITAL",
        settings.release.account_id,
    ):
        violations.append("LIVE_WRITE_CAPITAL_LIMIT_SCOPE_MISMATCH")
    if (str(authorization[2]), str(authorization[3]), str(authorization[4])) != (
        "LIVE",
        "LIVE_REAL_CAPITAL",
        settings.release.account_id,
    ):
        violations.append("LIVE_WRITE_MACHINE_AUTHORIZATION_SCOPE_MISMATCH")
    if (str(allocation[2]), str(allocation[3]), str(allocation[4])) != (
        "LIVE",
        "LIVE_REAL_CAPITAL",
        "HELD",
    ):
        violations.append("LIVE_WRITE_PLAN_ALLOCATION_SCOPE_MISMATCH")
    if str(allocation[0]) != activation_id or str(allocation[1]) != limit_id:
        violations.append("LIVE_WRITE_PLAN_ALLOCATION_REFERENCE_MISMATCH")
    if (
        str(activation[0]) != str(authorization[1])
        or str(activation[1]) != authorization_id
        or str(activation[2]) != allocation_id
        or str(activation[3]) != "LIVE"
        or str(activation[4]) != "LIVE_REAL_CAPITAL"
        or str(activation[5]) != settings.release.account_id
        or str(activation[6]) != str(authorization[5])
        or str(activation[7]) in {"COMPLETED", "USER_TAKEOVER"}
    ):
        violations.append("LIVE_WRITE_PLAN_ACTIVATION_SCOPE_MISMATCH")

    valid_from, valid_until = authorization[6], authorization[7]
    if not (valid_from <= now < valid_until):
        violations.append("LIVE_WRITE_MACHINE_AUTHORIZATION_EXPIRED")
    if binding.expires_at > valid_until:
        violations.append("LIVE_WRITE_GATE_EXCEEDS_MACHINE_AUTHORIZATION")
    terms = dict(authorization[8])
    required_acknowledgements = (
        "real_capital_acknowledged",
        "evidence_limitations_acknowledged",
        "online_monitoring_acknowledged",
    )
    if any(terms.get(name) is not True for name in required_acknowledgements):
        violations.append("LIVE_WRITE_OWNER_ACKNOWLEDGEMENTS_MISSING")
    return violations, activation_id


def closed_live_write_gate_status() -> LiveWriteGateStatus:
    """Return the profile-neutral closed state used by non-LIVE_WRITE callers."""

    return LiveWriteGateStatus(
        live_write_build_capability="NOT_QUALIFIED",
        b05_package_eligibility="NOT_AUTHORIZED",
        configured_runtime_real_write_gate="CLOSED",
        runtime_real_write_gate="CLOSED",
    )


def evaluate_live_write_gate(
    repo_root: Path,
    settings: HalphaSettings,
    *,
    connection: Any | None = None,
    now: datetime | None = None,
) -> LiveWriteGateStatus:
    """Return the effective gate; any missing or conflicting input closes it."""

    if settings.release.profile != "BINANCE_LIVE_WRITE":
        return closed_live_write_gate_status()

    observed_at = now or datetime.now(UTC)
    manifest_digest, capability, violations = _manifest_assessment(repo_root, settings)
    binding, binding_violations = _read_binding(settings, repo_root)
    violations.extend(binding_violations)
    if binding is None:
        return LiveWriteGateStatus(
            live_write_build_capability="QUALIFIED" if capability else "NOT_QUALIFIED",
            b05_package_eligibility="NOT_AUTHORIZED",
            configured_runtime_real_write_gate="CLOSED",
            runtime_real_write_gate="CLOSED",
            build_manifest_digest=manifest_digest,
            violations=tuple(sorted(set(violations))),
        )

    if binding.environment_id != settings.release.environment_id:
        violations.append("LIVE_WRITE_GATE_ENVIRONMENT_MISMATCH")
    if binding.account_id != settings.release.account_id:
        violations.append("LIVE_WRITE_GATE_ACCOUNT_MISMATCH")
    if manifest_digest is None or binding.build_manifest_digest != manifest_digest:
        violations.append("LIVE_WRITE_GATE_MANIFEST_MISMATCH")
    if not (binding.effective_at <= observed_at < binding.expires_at):
        violations.append("LIVE_WRITE_GATE_BINDING_EXPIRED_OR_NOT_EFFECTIVE")

    package_authorized = capability and not violations
    configured_gate = binding.runtime_real_write_gate if package_authorized else "CLOSED"
    authorized_activation_id: str | None = None
    if configured_gate == "OPEN":
        if connection is None:
            violations.append("LIVE_WRITE_DATABASE_BINDING_NOT_VERIFIED")
        else:
            try:
                database_violations, authorized_activation_id = _database_assessment(
                    connection,
                    settings,
                    binding,
                    observed_at,
                )
                violations.extend(database_violations)
            except Exception as exc:
                violations.append(f"LIVE_WRITE_DATABASE_BINDING_UNAVAILABLE_{type(exc).__name__.upper()}")
    effective_gate = "OPEN" if configured_gate == "OPEN" and not violations else "CLOSED"
    return LiveWriteGateStatus(
        live_write_build_capability="QUALIFIED" if capability else "NOT_QUALIFIED",
        b05_package_eligibility="AUTHORIZED" if package_authorized else "NOT_AUTHORIZED",
        configured_runtime_real_write_gate=configured_gate,
        runtime_real_write_gate=effective_gate,
        build_manifest_digest=manifest_digest,
        user_authorization_ref=binding.user_authorization_ref,
        account_capital_limit_version_ref=binding.account_capital_limit_version_ref,
        machine_authorization_version_ref=binding.machine_authorization_version_ref,
        plan_allocation_ref=binding.plan_allocation_ref,
        authorized_activation_id=(
            authorized_activation_id if effective_gate == "OPEN" else None
        ),
        binding_effective_at=binding.effective_at,
        binding_expires_at=binding.expires_at,
        violations=tuple(sorted(set(violations))),
    )


def require_live_write_gate_precheck(
    repo_root: Path,
    settings: HalphaSettings,
    *,
    now: datetime | None = None,
) -> LiveWriteGateStatus:
    status = evaluate_live_write_gate(repo_root, settings, now=now)
    expected_only = {"LIVE_WRITE_DATABASE_BINDING_NOT_VERIFIED"}
    if (
        status.configured_runtime_real_write_gate != "OPEN"
        or set(status.violations) != expected_only
    ):
        raise LiveWriteGateError(
            "LIVE_WRITE_GATE_PRECHECK_REJECTED reasons=" + ",".join(status.violations or ("GATE_CLOSED",))
        )
    return status


def require_live_write_gate_open(
    repo_root: Path,
    settings: HalphaSettings,
    connection: Any,
    *,
    now: datetime | None = None,
) -> LiveWriteGateStatus:
    status = evaluate_live_write_gate(repo_root, settings, connection=connection, now=now)
    if status.runtime_real_write_gate != "OPEN":
        raise LiveWriteGateError(
            "LIVE_WRITE_GATE_CLOSED reasons=" + ",".join(status.violations or ("GATE_CLOSED",))
        )
    return status


GateStatusProvider = Callable[[], LiveWriteGateStatus]
