"""Maintenance-only provisioning for the detached LIVE_WRITE gate binding."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import secrets
from typing import Sequence

import pywintypes
from pydantic import ValidationError
import win32security

from halpha.configuration import ConfigurationError, HalphaSettings, load_settings
from halpha.live_write_gate import (
    LiveWriteGateBinding,
    LiveWriteGateError,
    _file_grants,
    assert_live_write_gate_directory_security,
    assert_live_write_gate_security,
    evaluate_live_write_gate,
    require_live_write_gate_binding_provisionable,
)
from halpha.runtime_identity import RuntimeIdentityError, repository_root
from halpha.windows_runtime import WindowsRuntimeError, require_process_identity


def _apply_security(path: Path, settings: HalphaSettings, *, directory: bool) -> None:
    flags = (
        win32security.OBJECT_INHERIT_ACE | win32security.CONTAINER_INHERIT_ACE
        if directory
        else 0
    )
    dacl = win32security.ACL()
    for sid_text, mask in _file_grants(settings).items():
        dacl.AddAccessAllowedAceEx(
            win32security.ACL_REVISION,
            flags,
            mask,
            win32security.ConvertStringSidToSid(sid_text),
        )
    try:
        win32security.SetNamedSecurityInfo(
            str(path),
            win32security.SE_FILE_OBJECT,
            win32security.OWNER_SECURITY_INFORMATION
            | win32security.DACL_SECURITY_INFORMATION
            | win32security.PROTECTED_DACL_SECURITY_INFORMATION,
            win32security.ConvertStringSidToSid(settings.windows.maintenance_sid),
            None,
            dacl,
            None,
        )
    except pywintypes.error as exc:
        raise LiveWriteGateError(
            f"LIVE_WRITE_GATE_SECURITY_WRITE_FAILED code={exc.winerror}"
        ) from None


def provision_live_write_gate_binding(
    repo_root: Path,
    settings: HalphaSettings,
    binding: LiveWriteGateBinding,
) -> dict[str, object]:
    """Atomically write one validated non-secret binding under an exact DACL."""

    if settings.release.profile != "BINANCE_LIVE_WRITE":
        raise LiveWriteGateError("LIVE_WRITE_GATE_PROFILE_REQUIRED")
    require_process_identity(settings.windows.maintenance_sid)
    require_live_write_gate_binding_provisionable(repo_root, settings, binding)
    raw_target = settings.release.live_write_gate_path
    if raw_target is None:
        raise LiveWriteGateError("LIVE_WRITE_GATE_PATH_MISSING")
    target = Path(raw_target)
    root = repo_root.resolve()
    if target.resolve().is_relative_to(root):
        raise LiveWriteGateError("LIVE_WRITE_GATE_PATH_INSIDE_REPOSITORY")
    if target.is_symlink() or target.parent.is_symlink():
        raise LiveWriteGateError("LIVE_WRITE_GATE_SYMLINK_FORBIDDEN")

    target.parent.mkdir(parents=True, exist_ok=True)
    _apply_security(target.parent, settings, directory=True)
    assert_live_write_gate_directory_security(target.parent, settings)
    temporary = target.parent / f".{target.name}.{secrets.token_hex(16)}.tmp"
    try:
        temporary.write_text(
            json.dumps(
                binding.model_dump(mode="json"),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        _apply_security(temporary, settings, directory=False)
        if target.exists():
            if target.is_symlink() or not target.is_file():
                raise LiveWriteGateError("LIVE_WRITE_GATE_TARGET_INVALID")
            assert_live_write_gate_security(target, settings)
        temporary.replace(target)
        _apply_security(target, settings, directory=False)
        assert_live_write_gate_security(target, settings)
    finally:
        if temporary.exists():
            temporary.unlink()

    status = evaluate_live_write_gate(root, settings)
    common_postconditions = (
        status.product_build_consistent is True
        and status.product_build_id == binding.product_build_id
    )
    if binding.runtime_real_write_gate == "OPEN":
        postcondition_valid = (
            common_postconditions
            and status.configured_runtime_real_write_gate == "OPEN"
            and status.runtime_real_write_gate == "CLOSED"
            and set(status.violations)
            == {"LIVE_WRITE_DATABASE_BINDING_NOT_VERIFIED"}
        )
    else:
        postcondition_valid = (
            common_postconditions
            and status.configured_runtime_real_write_gate == "CLOSED"
            and status.runtime_real_write_gate == "CLOSED"
            and not status.violations
        )
    if not postcondition_valid:
        raise LiveWriteGateError("LIVE_WRITE_GATE_POSTCONDITION_FAILED")
    return {
        "status": "PROVISIONED",
        "configured_runtime_real_write_gate": (
            status.configured_runtime_real_write_gate
        ),
        "runtime_real_write_gate": status.runtime_real_write_gate,
        "product_build_id": status.product_build_id,
        "product_build_consistent": status.product_build_consistent,
        "violations": list(status.violations),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="halpha-live-gate")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--binding", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        settings = load_settings(args.config)
        if args.binding.is_symlink() or not args.binding.is_file():
            raise LiveWriteGateError("LIVE_WRITE_GATE_INPUT_INVALID")
        raw = json.loads(args.binding.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise LiveWriteGateError("LIVE_WRITE_GATE_INPUT_INVALID")
        binding = LiveWriteGateBinding.model_validate(raw)
        report = provision_live_write_gate_binding(
            repository_root(),
            settings,
            binding,
        )
        print(json.dumps(report, sort_keys=True))
        return 0
    except (
        ConfigurationError,
        json.JSONDecodeError,
        LiveWriteGateError,
        OSError,
        RuntimeIdentityError,
        ValidationError,
        WindowsRuntimeError,
    ) as exc:
        print(
            json.dumps(
                {
                    "status": "PROVISIONING_REJECTED",
                    "reason": type(exc).__name__,
                },
                sort_keys=True,
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
