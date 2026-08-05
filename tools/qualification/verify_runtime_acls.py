"""Read-only qualification for the Windows runtime filesystem boundary."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from halpha.configuration import load_settings
from halpha.runtime_identity import require_repository_runtime
from halpha.windows_filesystem import WindowsFilesystemError
from tools.provisioning.provision_runtime_acls import (
    RuntimeAclProvisioningError,
    qualify_runtime_acls,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="verify-runtime-acls")
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--demo-config", type=Path, required=True)
    parser.add_argument("--live-copy-config", type=Path, required=True)
    parser.add_argument("--live-personal-config", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        root = args.repository_root.resolve()
        require_repository_runtime(root)
        report = qualify_runtime_acls(
            root,
            load_settings(args.demo_config),
            load_settings(args.live_copy_config),
            load_settings(args.live_personal_config),
        )
    except Exception as exc:
        if isinstance(
            exc,
            (
                RuntimeAclProvisioningError,
                WindowsFilesystemError,
            ),
        ):
            reason = str(exc)
        else:
            reason = (
                "WINDOWS_RUNTIME_ACL_QUALIFICATION_FAILED "
                f"type={type(exc).__name__}"
            )
        print(json.dumps({"status": "REJECTED", "reason": reason}, sort_keys=True))
        return 2
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
