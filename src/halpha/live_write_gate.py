"""Detached, fail-closed LIVE_WRITE deployment switch verification.

The switch binds a build to one environment and account.  The user's fixed
plan and explicit activation are the only trading authority; the switch does
not reproduce capital limits, allocations, acknowledgements, or authorization
records.  Before it becomes effective, the database must contain exactly one
current Halpha-owned real-account activation.
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

from halpha.configuration import HalphaSettings
from halpha.product_build import calculate_product_build_id
from halpha.source_identity import SourceIdentityError
from halpha.windows_runtime import BUILTIN_ADMINISTRATORS_SID, SYSTEM_SID


class LiveWriteGateError(RuntimeError):
    """Sanitized fail-closed LIVE_WRITE gate failure."""


class _FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class LiveWriteGateBinding(_FrozenModel):
    schema_version: Literal[3]
    environment_id: str
    account_id: str
    profile: Literal["BINANCE_LIVE_WRITE"]
    runtime_real_write_gate: Literal["CLOSED", "OPEN"]
    product_build_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    effective_at: datetime
    expires_at: datetime

    @model_validator(mode="after")
    def validate_window(self) -> "LiveWriteGateBinding":
        if self.effective_at.tzinfo is None or self.expires_at.tzinfo is None:
            raise ValueError("LIVE_WRITE_GATE_TIMEZONE_REQUIRED")
        if self.expires_at <= self.effective_at:
            raise ValueError("LIVE_WRITE_GATE_WINDOW_INVALID")
        return self


class LiveWriteGateStatus(_FrozenModel):
    configured_runtime_real_write_gate: Literal["CLOSED", "OPEN"]
    runtime_real_write_gate: Literal["CLOSED", "OPEN"]
    product_build_id: str | None = None
    product_build_consistent: bool | None = None
    authorized_activation_id: str | None = None
    binding_effective_at: datetime | None = None
    binding_expires_at: datetime | None = None
    violations: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_effective_state(self) -> "LiveWriteGateStatus":
        if (
            self.runtime_real_write_gate == "OPEN"
            and self.configured_runtime_real_write_gate != "OPEN"
        ):
            raise ValueError("LIVE_WRITE_EFFECTIVE_GATE_CONFIGURATION_MISMATCH")
        if self.runtime_real_write_gate == "OPEN" and self.authorized_activation_id is None:
            raise ValueError("LIVE_WRITE_EFFECTIVE_ACTIVATION_REQUIRED")
        return self


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
    try:
        current_product_build_id = calculate_product_build_id(repo_root, settings)
    except SourceIdentityError as exc:
        raise LiveWriteGateError(
            f"LIVE_WRITE_GATE_PRODUCT_BUILD_UNAVAILABLE reason={exc}"
        ) from None
    if binding.product_build_id != current_product_build_id:
        raise LiveWriteGateError("LIVE_WRITE_GATE_PRODUCT_BUILD_MISMATCH")
    return current_product_build_id


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
    product_build_id: str,
) -> tuple[list[str], str | None]:
    rows = connection.execute(
        """
        SELECT activation.activation_id, plan.product_build_id
        FROM halpha.plan_activation AS activation
        JOIN halpha.trade_plan_version AS plan
          ON plan.environment_id = activation.environment_id
         AND plan.plan_version_id = activation.plan_version_ref
        WHERE activation.environment_id = %s
          AND activation.environment_kind = 'LIVE'
          AND activation.authority_class = 'LIVE_REAL_CAPITAL'
          AND activation.account_ref = %s
          AND activation.lifecycle IN ('RUNNING', 'EXITING')
          AND activation.responsibility_owner = 'HALPHA'
        ORDER BY activation.created_at, activation.activation_id
        """,
        (settings.release.environment_id, settings.release.account_id),
    ).fetchall()
    if not rows:
        return ["LIVE_WRITE_CURRENT_ACTIVATION_MISSING"], None
    if len(rows) != 1:
        return ["LIVE_WRITE_CURRENT_ACTIVATION_AMBIGUOUS"], None
    if str(rows[0][1]) != product_build_id:
        return ["LIVE_WRITE_PLAN_PRODUCT_BUILD_MISMATCH"], None
    return [], str(rows[0][0])


def closed_live_write_gate_status(
    product_build_id: str | None = None,
) -> LiveWriteGateStatus:
    """Return the profile-neutral closed state used by non-LIVE_WRITE callers."""

    return LiveWriteGateStatus(
        configured_runtime_real_write_gate="CLOSED",
        runtime_real_write_gate="CLOSED",
        product_build_id=product_build_id,
    )


def evaluate_live_write_gate(
    repo_root: Path,
    settings: HalphaSettings,
    *,
    current_product_build_id: str | None = None,
    connection: Any | None = None,
    now: datetime | None = None,
) -> LiveWriteGateStatus:
    """Return the effective gate; any missing or conflicting input closes it."""

    if current_product_build_id is not None:
        product_build_id = current_product_build_id
        product_build_violations: list[str] = []
    else:
        try:
            product_build_id = calculate_product_build_id(repo_root, settings)
            product_build_violations = []
        except SourceIdentityError as exc:
            product_build_id = None
            product_build_violations = [
                f"LIVE_WRITE_PRODUCT_BUILD_UNAVAILABLE_{type(exc).__name__.upper()}"
            ]

    if settings.release.profile != "BINANCE_LIVE_WRITE":
        return LiveWriteGateStatus(
            configured_runtime_real_write_gate="CLOSED",
            runtime_real_write_gate="CLOSED",
            product_build_id=product_build_id,
            violations=tuple(product_build_violations),
        )

    observed_at = now or datetime.now(UTC)
    violations = list(product_build_violations)
    binding, binding_violations = _read_binding(settings, repo_root)
    violations.extend(binding_violations)
    if binding is None:
        return LiveWriteGateStatus(
            configured_runtime_real_write_gate="CLOSED",
            runtime_real_write_gate="CLOSED",
            product_build_id=product_build_id,
            violations=tuple(sorted(set(violations))),
        )

    if binding.environment_id != settings.release.environment_id:
        violations.append("LIVE_WRITE_GATE_ENVIRONMENT_MISMATCH")
    if binding.account_id != settings.release.account_id:
        violations.append("LIVE_WRITE_GATE_ACCOUNT_MISMATCH")
    product_build_consistent = (
        product_build_id is not None and binding.product_build_id == product_build_id
    )
    if not product_build_consistent:
        violations.append("LIVE_WRITE_GATE_PRODUCT_BUILD_MISMATCH")
    if not (binding.effective_at <= observed_at < binding.expires_at):
        violations.append("LIVE_WRITE_GATE_BINDING_EXPIRED_OR_NOT_EFFECTIVE")

    configured_gate = binding.runtime_real_write_gate if not violations else "CLOSED"
    authorized_activation_id: str | None = None
    if configured_gate == "OPEN":
        if connection is None:
            violations.append("LIVE_WRITE_DATABASE_BINDING_NOT_VERIFIED")
        else:
            try:
                database_violations, authorized_activation_id = _database_assessment(
                    connection,
                    settings,
                    product_build_id,
                )
                violations.extend(database_violations)
            except Exception as exc:
                violations.append(f"LIVE_WRITE_DATABASE_BINDING_UNAVAILABLE_{type(exc).__name__.upper()}")
    effective_gate = "OPEN" if configured_gate == "OPEN" and not violations else "CLOSED"
    return LiveWriteGateStatus(
        configured_runtime_real_write_gate=configured_gate,
        runtime_real_write_gate=effective_gate,
        product_build_id=product_build_id,
        product_build_consistent=product_build_consistent,
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
    current_product_build_id: str | None = None,
    now: datetime | None = None,
) -> LiveWriteGateStatus:
    status = evaluate_live_write_gate(
        repo_root,
        settings,
        current_product_build_id=current_product_build_id,
        now=now,
    )
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
    current_product_build_id: str | None = None,
    now: datetime | None = None,
) -> LiveWriteGateStatus:
    status = evaluate_live_write_gate(
        repo_root,
        settings,
        current_product_build_id=current_product_build_id,
        connection=connection,
        now=now,
    )
    if status.runtime_real_write_gate != "OPEN":
        raise LiveWriteGateError(
            "LIVE_WRITE_GATE_CLOSED reasons=" + ",".join(status.violations or ("GATE_CLOSED",))
        )
    return status


GateStatusProvider = Callable[[], LiveWriteGateStatus]
