"""Deterministic BuildManifest generation and drift verification.

This module deliberately uses only the standard library so build identity can be
checked before importing product or external-integration dependencies.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Iterable, Sequence


SCHEMA_VERSION = 2
ALLOWED_PROFILE_DIFFERENCES = (
    "account_id",
    "authority_class",
    "credential_reference",
    "database_connection_reference",
    "environment_id",
    "profile",
    "venue_endpoint",
    "venue_environment_configuration",
)


class BuildManifestError(RuntimeError):
    """Raised when build identity is missing, invalid, or has drifted."""


@dataclass(frozen=True)
class ArtifactSpec:
    name: str
    relative_path: str
    required: bool = True
    expected_json_status: str | None = None


DEFAULT_ARTIFACT_SPECS = (
    ArtifactSpec("python_runtime_lock", "requirements/runtime.txt"),
    ArtifactSpec("python_dev_lock", "requirements/dev.txt"),
    ArtifactSpec("npm_lock", "frontend/package-lock.json"),
    ArtifactSpec("halpha_wheel", "build/release/artifacts"),
    ArtifactSpec("database_migrations", "migrations"),
    ArtifactSpec("frontend_dist", "frontend/dist"),
    ArtifactSpec(
        "strategy_registry",
        "src/halpha/planning/strategy_registry.json",
        required=False,
    ),
    ArtifactSpec("nonsecret_runtime_config", "config/halpha.toml"),
    ArtifactSpec(
        "nonsecret_live_write_config",
        "config/halpha.live-write.toml",
    ),
    ArtifactSpec("evidence_storage_policy", "config/evidence-storage-policy.json"),
    ArtifactSpec(
        "dependency_lifecycle_ledger",
        "config/dependency-lifecycle-ledger.json",
    ),
    ArtifactSpec("windows_task_definitions", "build/runtime/tasks"),
    ArtifactSpec(
        "b00_qualification",
        "build/qualification/b00-qualification-latest.json",
        expected_json_status="QUALIFIED",
    ),
    ArtifactSpec(
        "b01_database_boundary",
        "build/qualification/b01-database-boundary.json",
        expected_json_status="QUALIFIED",
    ),
    ArtifactSpec(
        "b01_windows_runtime",
        "build/qualification/b01-windows-runtime.json",
        expected_json_status="QUALIFIED",
    ),
    ArtifactSpec(
        "b01_backup_boundary",
        "build/qualification/b01-backup-boundary.json",
        expected_json_status="QUALIFIED",
    ),
    ArtifactSpec(
        "b01_browser_qualification",
        "build/qualification/browser/playwright-report.json",
    ),
    ArtifactSpec(
        "b01_clean_venv",
        "build/qualification/b01-clean-venv.json",
        expected_json_status="QUALIFIED",
    ),
    ArtifactSpec(
        "b01_pytest_junit",
        "build/qualification/b01-pytest.xml",
    ),
    ArtifactSpec(
        "b01_frontend_unit_tests",
        "build/qualification/browser/vitest-report.json",
    ),
    ArtifactSpec(
        "b01_summary",
        "build/qualification/b01-summary.json",
        expected_json_status="QUALIFIED",
    ),
    ArtifactSpec(
        "b01_license_inventory",
        "build/qualification/b01-license-inventory.json",
        expected_json_status="QUALIFIED",
    ),
    ArtifactSpec(
        "third_party_notices",
        "build/qualification/THIRD_PARTY_NOTICES.txt",
    ),
    ArtifactSpec(
        "b02_database_boundary",
        "build/qualification/b02-database-boundary.json",
        expected_json_status="QUALIFIED",
    ),
    ArtifactSpec(
        "b02_strategy_adapter_parity",
        "build/qualification/b02-strategy-adapter-parity.json",
        expected_json_status="QUALIFIED",
    ),
    ArtifactSpec(
        "b02_critical_invariant_trace",
        "build/qualification/b02-critical-invariant-trace.json",
        expected_json_status="QUALIFIED",
    ),
    ArtifactSpec(
        "b02_license_inventory",
        "build/qualification/b02-license-inventory.json",
        expected_json_status="QUALIFIED",
    ),
    ArtifactSpec("b02_pytest_junit", "build/qualification/b02-pytest.xml"),
    ArtifactSpec(
        "b02_browser_qualification",
        "build/qualification/browser/b02-playwright-report.json",
    ),
    ArtifactSpec(
        "b02_summary",
        "build/qualification/b02-summary.json",
        expected_json_status="QUALIFIED",
    ),
    ArtifactSpec(
        "b03_execution_boundary",
        "build/qualification/b03-execution-boundary.json",
        expected_json_status="QUALIFIED",
    ),
    ArtifactSpec(
        "b03_product_demo_roundtrip",
        "build/qualification/b03-product-demo-roundtrip.json",
        expected_json_status="QUALIFIED",
    ),
    ArtifactSpec("b03_pytest_junit", "build/qualification/b03-pytest.xml"),
    ArtifactSpec(
        "b03_summary",
        "build/qualification/b03-summary.json",
        expected_json_status="QUALIFIED",
    ),
    ArtifactSpec(
        "b04_historical_data",
        "build/qualification/b04-historical-data.json",
        expected_json_status="QUALIFIED",
    ),
    ArtifactSpec(
        "b04_historical_catalog",
        "build/qualification/b04-historical-catalog.json",
        expected_json_status="QUALIFIED",
    ),
    ArtifactSpec(
        "b04_historical_backtest",
        "build/qualification/b04-historical-backtest.json",
        expected_json_status="QUALIFIED",
    ),
    ArtifactSpec(
        "b04_product_demo_cycle",
        "build/qualification/b04-product-demo-cycle.json",
        expected_json_status="QUALIFIED",
    ),
    ArtifactSpec(
        "b04_notification_boundary",
        "build/qualification/b04-notification-boundary.json",
        expected_json_status="QUALIFIED",
    ),
    ArtifactSpec(
        "b04_outcome_boundary",
        "build/qualification/b04-outcome-boundary.json",
        expected_json_status="QUALIFIED",
    ),
    ArtifactSpec(
        "b04_empty_database_restore",
        "build/qualification/b04-empty-restore.json",
        expected_json_status="QUALIFIED",
    ),
    ArtifactSpec(
        "b04_windows_fault_drills",
        "build/qualification/b04-windows-fault-drills.json",
        expected_json_status="QUALIFIED",
    ),
    ArtifactSpec(
        "b04_browser_workbench",
        "build/qualification/b04-browser.json",
        expected_json_status="QUALIFIED",
    ),
    ArtifactSpec(
        "b04_implemented_complexity_budget",
        "build/qualification/b04-complexity-budget.json",
        expected_json_status="QUALIFIED",
    ),
    ArtifactSpec(
        "b04_critical_invariant_trace",
        "build/qualification/b04-critical-invariant-trace.json",
        expected_json_status="QUALIFIED",
    ),
    ArtifactSpec("b04_pytest_junit", "build/qualification/b04-pytest.xml"),
    ArtifactSpec(
        "b04_playwright_report",
        "build/qualification/browser/b04-playwright-report-current.json",
    ),
    ArtifactSpec(
        "b04_actual_smtp_delivery",
        "build/qualification/b04-smtp-delivery.json",
        expected_json_status="QUALIFIED",
    ),
    ArtifactSpec(
        "b04_summary",
        "build/qualification/b04-summary.json",
        expected_json_status="QUALIFIED",
    ),
)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _directory_inventory(path: Path) -> list[dict[str, str]]:
    inventory: list[dict[str, str]] = []
    for child in sorted(path.rglob("*"), key=lambda item: item.as_posix()):
        if child.is_symlink():
            raise BuildManifestError(f"SYMLINK_NOT_ALLOWED path={child}")
        if child.is_file():
            inventory.append(
                {"path": child.relative_to(path).as_posix(), "sha256": _sha256_file(child)}
            )
    return inventory


def digest_path(path: Path) -> tuple[str, int]:
    if path.is_symlink():
        raise BuildManifestError(f"SYMLINK_NOT_ALLOWED path={path}")
    if path.is_file():
        return _sha256_file(path), 1
    if path.is_dir():
        inventory = _directory_inventory(path)
        payload = json.dumps(
            inventory, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest(), len(inventory)
    raise BuildManifestError(f"ARTIFACT_TYPE_UNSUPPORTED path={path}")


def _git(repo_root: Path, *args: str) -> str:
    process = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if process.returncode != 0:
        raise BuildManifestError(
            f"GIT_COMMAND_FAILED args={args!r} stderr={process.stderr.strip()!r}"
        )
    return process.stdout


def _source_identity(repo_root: Path) -> dict[str, object]:
    revision = _git(repo_root, "rev-parse", "HEAD").strip()
    raw_paths = _git(
        repo_root,
        "ls-files",
        "-z",
        "--cached",
        "--others",
        "--exclude-standard",
    )
    relative_paths = sorted(path for path in raw_paths.split("\0") if path)
    inventory: list[dict[str, str]] = []
    for relative in relative_paths:
        path = repo_root / relative
        if not path.is_file() or path.is_symlink():
            if path.is_symlink():
                raise BuildManifestError(f"SOURCE_SYMLINK_NOT_ALLOWED path={relative}")
            continue
        inventory.append({"path": Path(relative).as_posix(), "sha256": _sha256_file(path)})
    payload = json.dumps(
        inventory, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    status = _git(repo_root, "status", "--porcelain=v1", "--untracked-files=all")
    return {
        "revision": revision,
        "clean": not bool(status.strip()),
        "source_tree_sha256": hashlib.sha256(payload).hexdigest(),
        "source_file_count": len(inventory),
        "dirty_entry_count": len([line for line in status.splitlines() if line]),
    }


def _artifact_bindings(
    repo_root: Path, specs: Iterable[ArtifactSpec]
) -> list[dict[str, object]]:
    bindings: list[dict[str, object]] = []
    for spec in specs:
        path = (repo_root / spec.relative_path).resolve()
        if not path.is_relative_to(repo_root.resolve()):
            raise BuildManifestError(
                f"ARTIFACT_PATH_OUTSIDE_REPOSITORY name={spec.name} path={spec.relative_path}"
            )
        if not path.exists():
            bindings.append(
                {
                    "name": spec.name,
                    "path": spec.relative_path,
                    "required": spec.required,
                    "expected_json_status": spec.expected_json_status,
                    "qualification_status": None,
                    "status": "MISSING",
                    "sha256": None,
                    "file_count": 0,
                }
            )
            continue
        digest, count = digest_path(path)
        qualification_status: str | None = None
        binding_status = "BOUND"
        if spec.expected_json_status is not None:
            if path.suffix.lower() != ".json" or not path.is_file():
                qualification_status = "INVALID_ARTIFACT_TYPE"
            else:
                try:
                    parsed = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                    qualification_status = "INVALID_JSON"
                else:
                    qualification_status = (
                        str(parsed.get("status"))
                        if isinstance(parsed, dict) and parsed.get("status") is not None
                        else "STATUS_MISSING"
                    )
            if qualification_status != spec.expected_json_status:
                binding_status = "STATUS_MISMATCH"
        bindings.append(
            {
                "name": spec.name,
                "path": spec.relative_path,
                "required": spec.required,
                "expected_json_status": spec.expected_json_status,
                "qualification_status": qualification_status,
                "status": binding_status,
                "sha256": digest,
                "file_count": count,
            }
        )
    return bindings


def create_manifest(
    repo_root: Path,
    *,
    specs: Sequence[ArtifactSpec] = DEFAULT_ARTIFACT_SPECS,
    generated_at: datetime | None = None,
) -> dict[str, object]:
    root = repo_root.resolve()
    source = _source_identity(root)
    artifacts = _artifact_bindings(root, specs)
    missing_required = sorted(
        str(binding["name"])
        for binding in artifacts
        if binding["required"] and binding["status"] != "BOUND"
    )
    timestamp = generated_at or datetime.now(UTC)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": timestamp.isoformat().replace("+00:00", "Z"),
        "source": source,
        "artifacts": artifacts,
        "environment_equivalence": {
            "shared_implementation_required": True,
            "allowed_profile_differences": list(ALLOWED_PROFILE_DIFFERENCES),
        },
        "completeness": {
            "status": "COMPLETE" if not missing_required else "INCOMPLETE",
            "missing_required": missing_required,
        },
        "build_eligible": not missing_required and bool(source["clean"]),
        "capability_claim": "BUILD_IDENTITY_ONLY_NOT_REAL_WRITE_AUTHORIZATION",
    }


def manifest_sha256(manifest: dict[str, object]) -> str:
    payload = json.dumps(
        manifest, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def write_manifest(path: Path, manifest: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def verify_manifest(
    repo_root: Path,
    manifest: dict[str, object],
    *,
    specs: Sequence[ArtifactSpec] = DEFAULT_ARTIFACT_SPECS,
) -> list[str]:
    violations: list[str] = []
    if manifest.get("schema_version") != SCHEMA_VERSION:
        violations.append("SCHEMA_VERSION_MISMATCH")

    current_source = _source_identity(repo_root.resolve())
    recorded_source = manifest.get("source")
    if not isinstance(recorded_source, dict):
        violations.append("SOURCE_IDENTITY_MISSING")
    else:
        for key in (
            "revision",
            "clean",
            "source_tree_sha256",
            "source_file_count",
            "dirty_entry_count",
        ):
            if recorded_source.get(key) != current_source.get(key):
                violations.append(f"SOURCE_{key.upper()}_DRIFT")

    current_bindings = _artifact_bindings(repo_root, specs)
    expected = {binding["name"]: binding for binding in current_bindings}
    recorded_artifacts = manifest.get("artifacts")
    if not isinstance(recorded_artifacts, list):
        violations.append("ARTIFACT_BINDINGS_MISSING")
    else:
        recorded = {
            binding.get("name"): binding
            for binding in recorded_artifacts
            if isinstance(binding, dict) and isinstance(binding.get("name"), str)
        }
        recorded_names = [
            binding.get("name")
            for binding in recorded_artifacts
            if isinstance(binding, dict) and isinstance(binding.get("name"), str)
        ]
        if len(recorded_names) != len(set(recorded_names)):
            violations.append("ARTIFACT_BINDING_NAME_DUPLICATE")
        if set(recorded_names) != set(expected):
            violations.append("ARTIFACT_BINDING_SET_DRIFT")
        for name, current in expected.items():
            prior = recorded.get(name)
            if prior is None:
                violations.append(f"ARTIFACT_{name}_MISSING_FROM_MANIFEST")
                continue
            for key in (
                "path",
                "required",
                "expected_json_status",
                "qualification_status",
                "status",
                "sha256",
                "file_count",
            ):
                if prior.get(key) != current.get(key):
                    violations.append(f"ARTIFACT_{name}_{key.upper()}_DRIFT")

    equivalence = manifest.get("environment_equivalence")
    allowed = equivalence.get("allowed_profile_differences") if isinstance(equivalence, dict) else None
    if allowed != list(ALLOWED_PROFILE_DIFFERENCES):
        violations.append("PROFILE_DIFFERENCE_ALLOWLIST_DRIFT")

    missing_required = sorted(
        str(binding["name"])
        for binding in current_bindings
        if binding["required"] and binding["status"] != "BOUND"
    )
    expected_completeness = {
        "status": "COMPLETE" if not missing_required else "INCOMPLETE",
        "missing_required": missing_required,
    }
    if manifest.get("completeness") != expected_completeness:
        violations.append("COMPLETENESS_DRIFT")
    expected_eligibility = not missing_required and bool(current_source["clean"])
    if manifest.get("build_eligible") is not expected_eligibility:
        violations.append("BUILD_ELIGIBILITY_DRIFT")
    if manifest.get("capability_claim") != "BUILD_IDENTITY_ONLY_NOT_REAL_WRITE_AUTHORIZATION":
        violations.append("CAPABILITY_CLAIM_DRIFT")
    return sorted(set(violations))


def _load_manifest(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise BuildManifestError("MANIFEST_ROOT_MUST_BE_OBJECT")
    return data


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m halpha.build_manifest")
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate = subparsers.add_parser("generate")
    generate.add_argument("--output", type=Path, required=True)
    generate.add_argument("--allow-incomplete", action="store_true")
    generate.add_argument("--allow-dirty", action="store_true")

    verify = subparsers.add_parser("verify")
    verify.add_argument("--manifest", type=Path, required=True)
    verify.add_argument("--allow-ineligible", action="store_true")

    args = parser.parse_args(argv)
    repo_root = args.repo.resolve()
    if args.command == "generate":
        manifest = create_manifest(repo_root)
        write_manifest(args.output, manifest)
        print(
            json.dumps(
                {
                    "manifest": str(args.output),
                    "sha256": manifest_sha256(manifest),
                    "completeness": manifest["completeness"],
                    "source_clean": manifest["source"]["clean"],
                    "build_eligible": manifest["build_eligible"],
                },
                sort_keys=True,
            )
        )
        if manifest["completeness"]["status"] != "COMPLETE" and not args.allow_incomplete:
            return 2
        if not manifest["source"]["clean"] and not args.allow_dirty:
            return 2
        return 0

    manifest = _load_manifest(args.manifest)
    violations = verify_manifest(repo_root, manifest)
    if violations:
        print(json.dumps({"status": "DRIFT", "violations": violations}, sort_keys=True))
        return 2
    if not manifest.get("build_eligible") and not args.allow_ineligible:
        print(json.dumps({"status": "INELIGIBLE"}, sort_keys=True))
        return 2
    print(json.dumps({"status": "VERIFIED", "build_eligible": manifest.get("build_eligible")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
