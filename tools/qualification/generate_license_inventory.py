"""Generate a license inventory directly from the locked dependencies."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from hashlib import sha256
import importlib.metadata
import json
from pathlib import Path
import re
import tomllib
from typing import Any, Sequence

from halpha.runtime_identity import require_repository_runtime


REQUIREMENT = re.compile(r"^([A-Za-z0-9_.-]+)(?:\[[^]]+\])?==([^\s\\]+)")
STRONG_COPYLEFT = re.compile(r"(?<!L)(?:A?GPL)-", re.IGNORECASE)
CLASSIFIER_LICENSES = {
    "Apache Software License": "Apache-2.0",
    "BSD License": "BSD-3-Clause",
    "GNU Lesser General Public License v3 (LGPLv3)": "LGPL-3.0-only",
    "GNU Lesser General Public License v3 or later (LGPLv3+)": "LGPL-3.0-or-later",
    "MIT License": "MIT",
    "Mozilla Public License 2.0 (MPL 2.0)": "MPL-2.0",
    "Python Software Foundation License": "PSF-2.0",
}


class LicenseGateError(RuntimeError):
    """License inventory could not be proven complete and compatible."""


def _normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).casefold()


def _requirements(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        matched = REQUIREMENT.match(line)
        if matched:
            result[_normalize(matched.group(1))] = matched.group(2)
    return result


def _direct_python(root: Path) -> set[str]:
    direct: set[str] = set()
    for relative in ("requirements/runtime.in", "requirements/dev.in"):
        for line in (root / relative).read_text(encoding="utf-8").splitlines():
            matched = REQUIREMENT.match(line)
            if matched:
                direct.add(f"python:{_normalize(matched.group(1))}")
    pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    for requirement in pyproject["build-system"]["requires"]:
        matched = REQUIREMENT.match(requirement)
        if matched:
            direct.add(f"python:{_normalize(matched.group(1))}")
    return direct


def _direct_npm(package: dict[str, Any]) -> set[str]:
    return {
        f"npm:{name.casefold()}"
        for section in ("dependencies", "devDependencies")
        for name in package.get(section, {})
    }


def _classifier_license(metadata: importlib.metadata.PackageMetadata) -> str | None:
    licenses = []
    for classifier in metadata.get_all("Classifier") or []:
        prefix = "License :: OSI Approved :: "
        if classifier.startswith(prefix):
            mapped = CLASSIFIER_LICENSES.get(classifier[len(prefix) :])
            if mapped:
                licenses.append(mapped)
    if not licenses:
        return None
    return " OR ".join(sorted(set(licenses)))


def _python_license(distribution: importlib.metadata.Distribution) -> str:
    metadata = distribution.metadata
    expression = metadata.get("License-Expression")
    if expression:
        return expression.strip()
    classified = _classifier_license(metadata)
    if classified:
        return classified
    raw = (metadata.get("License") or "").strip()
    aliases = {
        "Apache 2.0": "Apache-2.0",
        "Apache-2.0": "Apache-2.0",
        "BSD": "BSD-3-Clause",
        "BSD-3-Clause": "BSD-3-Clause",
        "LGPL-3.0-or-later": "LGPL-3.0-or-later",
        "MIT": "MIT",
        "MPL-2.0 AND MIT": "MPL-2.0 AND MIT",
        "PSF": "PSF-2.0",
    }
    return aliases.get(raw, "UNKNOWN")


def _license_files(distribution: importlib.metadata.Distribution) -> list[dict[str, str]]:
    found: list[dict[str, str]] = []
    for relative in distribution.files or ():
        name = Path(str(relative)).name.casefold()
        if not any(token in name for token in ("license", "copying", "notice")):
            continue
        path = distribution.locate_file(relative)
        if path.is_file():
            found.append(
                {
                    "path": str(relative).replace("\\", "/"),
                    "sha256": sha256(path.read_bytes()).hexdigest(),
                }
            )
    return sorted(found, key=lambda item: item["path"])


def _python_inventory(locks: dict[str, str]) -> list[dict[str, Any]]:
    inventory: list[dict[str, Any]] = []
    installed = {
        _normalize(distribution.metadata["Name"]): distribution
        for distribution in importlib.metadata.distributions()
        if distribution.metadata.get("Name")
    }
    for name, version in sorted(locks.items()):
        distribution = installed.get(name)
        if distribution is None or distribution.version != version:
            inventory.append(
                {"name": name, "version": version, "license": "UNKNOWN", "status": "MISSING"}
            )
            continue
        metadata = distribution.metadata
        inventory.append(
            {
                "name": name,
                "version": version,
                "license": _python_license(distribution),
                "homepage": metadata.get("Home-page") or metadata.get("Project-URL") or "",
                "license_files": _license_files(distribution),
                "status": "INVENTORIED",
            }
        )
    return inventory


def _npm_inventory(lock: dict[str, Any]) -> list[dict[str, Any]]:
    inventory = []
    for path, package in sorted(lock["packages"].items()):
        if not path:
            continue
        inventory.append(
            {
                "path": path,
                "name": path.rsplit("node_modules/", 1)[-1],
                "version": package.get("version"),
                "license": package.get("license", "UNKNOWN"),
                "development_only": bool(package.get("dev", False)),
                "optional": bool(package.get("optional", False)),
                "resolved": package.get("resolved", ""),
                "status": "INVENTORIED" if package.get("license") else "MISSING",
            }
        )
    return inventory


def _license_violation(expression: str) -> bool:
    return expression == "UNKNOWN" or bool(STRONG_COPYLEFT.search(expression))


def _notices(python: list[dict[str, Any]], npm: list[dict[str, Any]]) -> str:
    lines = [
        "Halpha third-party attribution inventory",
        "Generated from the complete locked Python and npm dependency closures.",
        "This inventory does not replace the license files identified by their SHA-256 digests.",
        "",
        "Python packages",
    ]
    lines.extend(
        f"- {item['name']} {item['version']} | {item['license']} | {item.get('homepage', '')}"
        for item in python
    )
    lines.extend(("", "npm packages"))
    lines.extend(
        f"- {item['name']} {item['version']} | {item['license']}"
        for item in npm
    )
    return "\n".join(lines) + "\n"


def generate(root: Path) -> tuple[dict[str, Any], str]:
    runtime = require_repository_runtime(root)
    python_locks = _requirements(root / "requirements" / "dev.txt")
    runtime_locks = _requirements(root / "requirements" / "runtime.txt")
    if not set(runtime_locks).issubset(python_locks):
        raise LicenseGateError("RUNTIME_LOCK_NOT_SUBSET_OF_DEV_LOCK")
    package = json.loads((root / "frontend" / "package.json").read_text(encoding="utf-8"))
    npm_lock = json.loads((root / "frontend" / "package-lock.json").read_text(encoding="utf-8"))
    expected_direct = _direct_python(root) | _direct_npm(package)
    python_inventory = _python_inventory(python_locks)
    npm_inventory = _npm_inventory(npm_lock)
    unknown_or_incompatible = sorted(
        f"python:{item['name']}@{item['version']}:{item['license']}"
        for item in python_inventory
        if _license_violation(item["license"])
    ) + sorted(
        f"npm:{item['name']}@{item['version']}:{item['license']}"
        for item in npm_inventory
        if _license_violation(item["license"])
    )
    qualified = not unknown_or_incompatible
    report: dict[str, Any] = {
        "schema_version": 1,
        "observed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "status": "QUALIFIED" if qualified else "REJECTED",
        "runtime": {
            "python_version": runtime.python_version,
            "executable": runtime.executable,
        },
        "python": {
            "runtime_lock_count": len(runtime_locks),
            "full_dev_lock_count": len(python_locks),
            "inventory": python_inventory,
        },
        "npm": {"full_lock_count": len(npm_inventory), "inventory": npm_inventory},
        "direct_dependencies": {
            "count": len(expected_direct),
            "members": sorted(expected_direct),
        },
        "unknown_or_incompatible": unknown_or_incompatible,
        "gate_rule": "UNKNOWN_OR_STRONG_COPYLEFT_LICENSE_REJECTS",
    }
    canonical = json.dumps(report, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    report["evidence_digest"] = sha256(canonical.encode("utf-8")).hexdigest()
    return report, _notices(python_inventory, npm_inventory)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="generate-license-inventory")
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--notices", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report, notices = generate(args.repository_root.resolve())
    except Exception as exc:
        reason = str(exc) if isinstance(exc, LicenseGateError) else (
            f"LICENSE_INVENTORY_FAILED type={type(exc).__name__}"
        )
        print(json.dumps({"status": "REJECTED", "reason": reason}, sort_keys=True))
        return 2
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    args.notices.parent.mkdir(parents=True, exist_ok=True)
    args.notices.write_text(notices, encoding="utf-8")
    print(
        json.dumps(
            {
                "status": report["status"],
                "python_count": report["python"]["full_dev_lock_count"],
                "npm_count": report["npm"]["full_lock_count"],
                "direct_dependency_count": report["direct_dependencies"]["count"],
                "evidence_digest": report["evidence_digest"],
            },
            sort_keys=True,
        )
    )
    return 0 if report["status"] == "QUALIFIED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
