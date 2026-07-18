from __future__ import annotations

import importlib
import importlib.metadata
import json

from verify_venv import collect_environment


EXPECTED_DISTRIBUTIONS = {
    "hypothesis": "6.156.6",
    "keyring": "25.7.0",
    "nautilus-trader": "1.230.0",
    "pandas": "2.3.3",
    "pip": "26.1.2",
    "pip-tools": "7.5.3",
    "pytest": "9.1.1",
    "pywin32": "312",
    "PyYAML": "6.0.3",
}
EXPECTED_KEYRING_BACKEND = "keyring.backends.Windows.WinVaultKeyring"


def main() -> int:
    environment, errors = collect_environment()
    versions: dict[str, str] = {}
    for distribution, expected in EXPECTED_DISTRIBUTIONS.items():
        try:
            actual = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            errors.append(f"DISTRIBUTION_MISSING:{distribution}")
            continue
        versions[distribution] = actual
        if actual != expected:
            errors.append(f"DISTRIBUTION_VERSION_MISMATCH:{distribution}")

    imported_modules: list[str] = []
    for module_name in ("nautilus_trader", "win32event", "yaml"):
        try:
            importlib.import_module(module_name)
        except Exception as exc:  # pragma: no cover - evidence contains type only
            errors.append(f"MODULE_IMPORT_FAILED:{module_name}:{type(exc).__name__}")
        else:
            imported_modules.append(module_name)

    backend_name = "UNAVAILABLE"
    try:
        keyring = importlib.import_module("keyring")
        backend = keyring.get_keyring()
        backend_name = f"{type(backend).__module__}.{type(backend).__qualname__}"
    except Exception as exc:  # pragma: no cover - evidence contains type only
        errors.append(f"KEYRING_BACKEND_FAILED:{type(exc).__name__}")
    else:
        if backend_name != EXPECTED_KEYRING_BACKEND:
            errors.append("KEYRING_BACKEND_MISMATCH")

    evidence = {
        "environment": environment,
        "versions": versions,
        "imported_modules": imported_modules,
        "keyring_backend": backend_name,
        "errors": errors,
        "status": "QUALIFIED" if not errors else "REJECTED",
    }
    print(json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
