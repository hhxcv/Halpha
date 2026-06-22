from __future__ import annotations

import json
from datetime import datetime, timezone
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from halpha.runtime.pipeline_contracts import RunContext
from halpha.storage import write_json


PRODUCT_CONTRACT_VALIDATION_ARTIFACT = "analysis/product_contract_validation.json"
PRODUCT_CONTRACT_VALIDATION_TYPE = "product_contract_validation"
CURRENT_STAGE_NAME = "validate_product_contracts"
VALID_STATUSES = {"ok", "warning", "degraded", "failed", "skipped"}


def build_product_contract_validation(
    config: dict[str, Any],
    run: RunContext,
    *,
    now: datetime | None = None,
) -> list[str]:
    _ = config
    artifact = validate_product_contracts(run, mode="product_run", now=now)
    write_json(run.analysis_dir / "product_contract_validation.json", artifact)
    _record_manifest(run, artifact)
    return [PRODUCT_CONTRACT_VALIDATION_ARTIFACT]


def validate_product_contracts(
    run: RunContext,
    *,
    mode: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    manifest = run.manifest
    artifacts = _dict(manifest.get("artifacts")).copy()
    artifacts.pop("product_contract_validation", None)
    checks: list[dict[str, Any]] = []

    _check_manifest_shape(manifest, checks)
    _check_stage_health(manifest, checks)
    _check_artifacts(run.run_dir, _config_base(run.config_path), artifacts, checks)
    _check_codex_report_contract(run.run_dir, manifest, artifacts, checks)
    _check_codex_input_boundaries(manifest, checks)
    _check_workbench_boundaries(manifest, checks)

    counts = _counts(checks)
    status = _overall_status(counts)
    warnings = [
        check["message"]
        for check in checks
        if check.get("status") in {"warning", "degraded"} and isinstance(check.get("message"), str)
    ]
    errors = [
        check["message"]
        for check in checks
        if check.get("status") == "failed" and isinstance(check.get("message"), str)
    ]
    return {
        "schema_version": 1,
        "artifact_type": PRODUCT_CONTRACT_VALIDATION_TYPE,
        "run_id": manifest.get("run_id") or run.run_id,
        "created_at": _utc_timestamp(now),
        "status": status,
        "mode": mode,
        "counts": counts,
        "checks": checks,
        "source_artifacts": _source_artifacts(artifacts),
        "omitted": {
            "raw_artifact_contents_embedded": False,
            "full_run_manifest_embedded": False,
            "raw_local_user_state_embedded": False,
        },
        "privacy_boundary": {
            "local_config_values_embedded": False,
            "machine_local_paths_embedded": False,
            "credentials_embedded": False,
        },
        "codex_boundary": {
            "codex_generated_validation": False,
            "codex_input_by_default": False,
        },
        "warnings": _bounded_unique(warnings),
        "errors": _bounded_unique(errors),
    }


def _check_manifest_shape(manifest: dict[str, Any], checks: list[dict[str, Any]]) -> None:
    required = ("run_id", "status", "stage_order", "stages", "artifacts", "counts", "codex")
    missing = [key for key in required if key not in manifest]
    if missing:
        _add_check(
            checks,
            "manifest:required_fields",
            "manifest",
            "failed",
            f"run_manifest.json is missing required fields: {', '.join(missing)}.",
            expected="run_id, status, stage_order, stages, artifacts, counts, and codex fields",
            observed=f"missing={','.join(missing)}",
            recovery_hint="Inspect run_manifest.json and rerun the product pipeline or the missing producer stage.",
        )
        return
    _add_check(
        checks,
        "manifest:required_fields",
        "manifest",
        "ok",
        "run_manifest.json contains the required top-level fields.",
        expected="required manifest fields present",
        observed="present",
    )


def _check_stage_health(manifest: dict[str, Any], checks: list[dict[str, Any]]) -> None:
    stages = _list(manifest.get("stages"))
    failed = []
    running = []
    invalid = []
    for stage in stages:
        record = _dict(stage)
        name = _text(record.get("name")) or "unknown"
        status = _text(record.get("status")) or "unknown"
        if name == CURRENT_STAGE_NAME and status == "running":
            continue
        if status == "failed":
            failed.append(name)
        elif status == "running":
            running.append(name)
        elif status not in {"succeeded", "skipped", "not_run", "failed", "disabled"}:
            invalid.append(f"{name}:{status}")
    if failed:
        _add_check(
            checks,
            "manifest:stage_health",
            "stage",
            "failed",
            f"run_manifest.json records failed stages: {', '.join(sorted(failed))}.",
            expected="no failed stages before product validation",
            observed="failed=" + ",".join(sorted(failed)),
            recovery_hint="Inspect the failed stage error and rerun the relevant stage after fixing the cause.",
        )
    elif running or invalid:
        observed = [*(f"running={name}" for name in sorted(running)), *sorted(invalid)]
        _add_check(
            checks,
            "manifest:stage_health",
            "stage",
            "warning",
            "run_manifest.json records non-terminal or unknown stage states.",
            expected="terminal stage statuses",
            observed=", ".join(observed),
            recovery_hint="Inspect run_manifest.json and rerun the product pipeline if the run did not finish cleanly.",
        )
    else:
        _add_check(
            checks,
            "manifest:stage_health",
            "stage",
            "ok",
            "run_manifest.json stage records are terminal.",
            expected="terminal stage statuses",
            observed="terminal",
        )


def _check_artifacts(
    run_dir: Path,
    config_base: Path,
    artifacts: dict[str, Any],
    checks: list[dict[str, Any]],
) -> None:
    if not artifacts:
        _add_check(
            checks,
            "artifact_refs:present",
            "artifact",
            "warning",
            "run_manifest.json does not record produced artifacts.",
            expected="at least one artifact ref for product runs",
            observed="none",
            recovery_hint="Inspect stage records and rerun artifact-producing stages if needed.",
        )
        return
    for key, ref in sorted(artifacts.items()):
        if not isinstance(ref, str) or not ref:
            _add_check(
                checks,
                f"artifact_ref:{key}",
                "artifact",
                "failed",
                f"manifest artifact ref {key} is not a non-empty string.",
                expected="non-empty repo-relative artifact ref",
                observed=type(ref).__name__,
                recovery_hint="Inspect run_manifest.json artifact refs.",
            )
            continue
        path = _artifact_path(run_dir, config_base, ref)
        if not path.exists():
            _add_check(
                checks,
                f"artifact_ref:{ref}",
                "artifact",
                "failed",
                f"recorded artifact was not found: {ref}.",
                expected="recorded artifact file exists",
                observed="missing",
                source_artifacts=[ref],
                recovery_hint="Rerun the producer stage or inspect why the artifact was removed.",
            )
            continue
        if ref.endswith(".json"):
            _check_json_artifact(path, ref, checks)
        else:
            _add_check(
                checks,
                f"artifact_ref:{ref}",
                "artifact",
                "ok",
                f"recorded artifact exists: {ref}.",
                expected="recorded artifact file exists",
                observed="available",
                source_artifacts=[ref],
            )


def _check_json_artifact(path: Path, ref: str, checks: list[dict[str, Any]]) -> None:
    data, error = _read_json(path)
    if error:
        _add_check(
            checks,
            f"artifact_json:{ref}",
            "artifact",
            "failed",
            f"recorded JSON artifact is not readable: {ref}: {error}",
            expected="valid JSON object",
            observed=error,
            source_artifacts=[ref],
            recovery_hint="Rerun the producer stage or inspect the artifact contents.",
        )
        return
    expected_type = _expected_artifact_type(ref)
    if expected_type and data.get("artifact_type") != expected_type:
        _add_check(
            checks,
            f"artifact_type:{ref}",
            "artifact",
            "failed",
            f"{ref} has unexpected artifact_type.",
            expected=expected_type,
            observed=_text(data.get("artifact_type")) or "missing",
            source_artifacts=[ref],
            recovery_hint="Rerun the producer stage that owns this artifact.",
        )
        return
    status = data.get("status")
    if status is not None and not isinstance(status, str):
        _add_check(
            checks,
            f"artifact_status:{ref}",
            "artifact",
            "warning",
            f"{ref} records a non-string status field.",
            expected="status field is a string when present",
            observed=type(status).__name__,
            source_artifacts=[ref],
            recovery_hint="Inspect the artifact contract and producer.",
        )
        return
    _add_check(
        checks,
        f"artifact_json:{ref}",
        "artifact",
        "ok",
        f"recorded JSON artifact is readable: {ref}.",
        expected="valid JSON object",
        observed="valid",
        source_artifacts=[ref],
    )


def _check_codex_report_contract(
    run_dir: Path,
    manifest: dict[str, Any],
    artifacts: dict[str, Any],
    checks: list[dict[str, Any]],
) -> None:
    codex = _dict(manifest.get("codex"))
    status = _text(codex.get("status")) or "unknown"
    report_ref = artifacts.get("report")
    report_exists = isinstance(report_ref, str) and bool(report_ref) and (run_dir / report_ref).is_file()
    if status == "succeeded":
        if report_exists:
            _add_check(
                checks,
                "codex_report:completed_report",
                "report",
                "ok",
                "Codex completed and report artifact exists.",
                expected="report artifact exists when Codex succeeds",
                observed=str(report_ref),
                source_artifacts=[report_ref],
            )
        else:
            _add_check(
                checks,
                "codex_report:completed_report",
                "report",
                "failed",
                "Codex status is succeeded but report/report.md is not recorded and available.",
                expected="report artifact exists when Codex succeeds",
                observed="missing",
                recovery_hint="Inspect run_codex_report output and rerun the report stage.",
            )
        return
    if status in {"skipped", "not_run", "disabled", "not_started"} and not report_ref:
        _add_check(
            checks,
            "codex_report:skipped_report",
            "report",
            "ok",
            f"Codex status is {status} and no report artifact is claimed.",
            expected="no report artifact is required when Codex is skipped, disabled, not started, or not run",
            observed=status,
        )
        return
    if report_ref and not report_exists:
        _add_check(
            checks,
            "codex_report:report_ref",
            "report",
            "failed",
            "report artifact is recorded but the file is missing.",
            expected="recorded report file exists",
            observed=str(report_ref),
            source_artifacts=[str(report_ref)],
            recovery_hint="Rerun run_codex_report or inspect why report/report.md was removed.",
        )
        return
    _add_check(
        checks,
        "codex_report:status",
        "report",
        "warning",
        f"Codex report status is {status}; report contract could not be classified as completed or skipped.",
        expected="succeeded, skipped, disabled, not_started, or not_run",
        observed=status,
        recovery_hint="Inspect run_manifest.json codex status.",
    )


def _check_codex_input_boundaries(manifest: dict[str, Any], checks: list[dict[str, Any]]) -> None:
    codex_input = _dict(manifest.get("codex_input"))
    if not codex_input:
        _add_check(
            checks,
            "codex_input:metadata",
            "codex_input",
            "skipped",
            "Codex input metadata is not recorded.",
            expected="codex_input metadata when Codex context is built",
            observed="missing",
        )
        return
    over_budget = []
    materials = codex_input.get("materials")
    if isinstance(materials, dict):
        for ref, budget in sorted(materials.items()):
            record = _dict(budget)
            if record.get("over_budget"):
                over_budget.append(str(ref))
    elif isinstance(materials, list):
        for item in materials:
            record = _dict(item)
            if record.get("over_budget"):
                over_budget.append(_text(record.get("artifact")) or "unknown")
    if over_budget:
        _add_check(
            checks,
            "codex_input:budget",
            "codex_input",
            "warning",
            "Codex input metadata records over-budget material.",
            expected="no material over budget",
            observed="over_budget=" + ",".join(sorted(over_budget)),
            source_artifacts=sorted(over_budget),
            recovery_hint="Inspect codex_input material budget metadata and material compression.",
        )
        return
    _add_check(
        checks,
        "codex_input:budget",
        "codex_input",
        "ok",
        "Codex input metadata is present without over-budget material.",
        expected="codex input budget metadata present",
        observed="within_budget",
    )


def _check_workbench_boundaries(manifest: dict[str, Any], checks: list[dict[str, Any]]) -> None:
    codex_input = _dict(manifest.get("codex_input"))
    materials = codex_input.get("materials")
    refs: list[str] = []
    if isinstance(materials, dict):
        refs = [str(key) for key in materials]
    elif isinstance(materials, list):
        refs = [_text(_dict(item).get("artifact")) for item in materials]
    workbench_refs = [ref for ref in refs if ref.startswith("runs/workbench/")]
    if workbench_refs:
        _add_check(
            checks,
            "workbench:codex_boundary",
            "workbench",
            "failed",
            "Workbench artifacts are included in Codex input metadata.",
            expected="workbench outputs are not Codex input by default",
            observed=",".join(sorted(workbench_refs)),
            source_artifacts=sorted(workbench_refs),
            recovery_hint="Inspect Codex context material selection and remove workbench outputs from default context.",
        )
        return
    _add_check(
        checks,
        "workbench:codex_boundary",
        "workbench",
        "ok",
        "Workbench artifacts are not included in Codex input metadata.",
        expected="workbench outputs are not Codex input by default",
        observed="not_included",
    )


def _add_check(
    checks: list[dict[str, Any]],
    check_id: str,
    category: str,
    status: str,
    message: str,
    *,
    expected: str,
    observed: str,
    source_artifacts: list[str] | None = None,
    recovery_hint: str | None = None,
) -> None:
    check: dict[str, Any] = {
        "check_id": check_id,
        "category": category,
        "status": status if status in VALID_STATUSES else "failed",
        "severity": _severity(status),
        "message": message,
        "source_artifacts": _bounded_unique(source_artifacts or ["run_manifest.json"]),
        "expected": expected,
        "observed": observed,
    }
    if recovery_hint:
        check["recovery_hint"] = recovery_hint
    checks.append(check)


def _record_manifest(run: RunContext, artifact: dict[str, Any]) -> None:
    counts = _dict(artifact.get("counts"))
    run.manifest["artifacts"]["product_contract_validation"] = PRODUCT_CONTRACT_VALIDATION_ARTIFACT
    run.manifest["product_contract_validation"] = {
        "status": artifact.get("status"),
        "artifact": PRODUCT_CONTRACT_VALIDATION_ARTIFACT,
        "checks": counts.get("checks", 0),
        "warnings": counts.get("warnings", 0),
        "errors": counts.get("errors", 0),
        "failed": counts.get("failed", 0),
        "degraded": counts.get("degraded", 0),
    }
    run.manifest["counts"]["product_contract_validation_checks"] = _int(counts.get("checks"))
    run.manifest["counts"]["product_contract_validation_ok"] = _int(counts.get("ok"))
    run.manifest["counts"]["product_contract_validation_warning"] = _int(counts.get("warning"))
    run.manifest["counts"]["product_contract_validation_degraded"] = _int(counts.get("degraded"))
    run.manifest["counts"]["product_contract_validation_failed"] = _int(counts.get("failed"))
    run.manifest["counts"]["product_contract_validation_skipped"] = _int(counts.get("skipped"))
    run.manifest["counts"]["product_contract_validation_warnings"] = _int(counts.get("warnings"))
    run.manifest["counts"]["product_contract_validation_errors"] = _int(counts.get("errors"))


def _read_json(path: Path) -> tuple[dict[str, Any], str | None]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}, f"{path.name} was not found."
    except JSONDecodeError as exc:
        return {}, f"{path.name} is not valid JSON: {exc.msg}."
    if not isinstance(loaded, dict):
        return {}, f"{path.name} must be a JSON object."
    return loaded, None


def _expected_artifact_type(ref: str) -> str | None:
    path = Path(ref)
    if path.suffix != ".json":
        return None
    if path.parts and path.parts[0] == "analysis":
        return path.stem
    return None


def _artifact_path(run_dir: Path, config_base: Path, ref: str) -> Path:
    path = Path(ref)
    if path.is_absolute():
        return path
    if path.parts and path.parts[0] == "data":
        return config_base / path
    return run_dir / path


def _config_base(config_path: Path) -> Path:
    parent = config_path.parent
    if str(parent) in {"", "."}:
        return Path.cwd()
    return parent


def _counts(checks: list[dict[str, Any]]) -> dict[str, int]:
    counts = {
        "checks": len(checks),
        "ok": 0,
        "warning": 0,
        "degraded": 0,
        "failed": 0,
        "skipped": 0,
        "errors": 0,
        "warnings": 0,
    }
    for check in checks:
        status = _text(check.get("status"))
        if status in {"ok", "warning", "degraded", "failed", "skipped"}:
            counts[status] += 1
        severity = _text(check.get("severity"))
        if severity == "error":
            counts["errors"] += 1
        elif severity == "warning":
            counts["warnings"] += 1
    return counts


def _overall_status(counts: dict[str, int]) -> str:
    if counts["failed"]:
        return "failed"
    if counts["degraded"]:
        return "degraded"
    if counts["warning"]:
        return "warning"
    if counts["checks"] and counts["checks"] == counts["skipped"]:
        return "skipped"
    return "ok"


def _severity(status: str) -> str:
    if status == "failed":
        return "error"
    if status in {"warning", "degraded"}:
        return "warning"
    return "info"


def _source_artifacts(artifacts: dict[str, Any]) -> list[str]:
    refs = ["run_manifest.json"]
    refs.extend(str(ref) for ref in artifacts.values() if isinstance(ref, str) and ref)
    return _bounded_unique(refs)


def _bounded_unique(values: list[str], *, limit: int = 80) -> list[str]:
    unique = []
    seen = set()
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        unique.append(value)
        if len(unique) >= limit:
            break
    return unique


def _utc_timestamp(value: datetime | None = None) -> str:
    timestamp = value or datetime.now(timezone.utc)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    return value if isinstance(value, int) else 0
