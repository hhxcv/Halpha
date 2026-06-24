from __future__ import annotations

from contextlib import suppress
import json
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

from halpha.runtime.pipeline_contracts import PipelineError, RunContext
from halpha.storage import write_json


OUTCOME_HISTORY_ARTIFACT = "data/research/outcomes/outcome_history.json"
OUTCOME_HISTORY_STATE_ARTIFACT = "data/research/metadata/outcome_history_state.json"
RESEARCH_DATA_CATALOG_ARTIFACT = "data/research/metadata/research_data_catalog.json"
PUBLICATION_ARTIFACTS = (
    OUTCOME_HISTORY_ARTIFACT,
    OUTCOME_HISTORY_STATE_ARTIFACT,
    RESEARCH_DATA_CATALOG_ARTIFACT,
)
STAGING_DIR_NAME = ".shared_state_publication"
STAGE_NAME = "validate_product_contracts"


def stage_shared_payloads(run: RunContext, *, group: str, payloads: dict[str, dict[str, Any]]) -> None:
    _validate_payload_map(payloads)
    path = _staging_dir(run) / f"{group}.json"
    write_json(
        path,
        {
            "schema_version": 1,
            "artifact_type": "shared_state_publication_candidate",
            "group": group,
            "payloads": payloads,
        },
    )


def read_staged_payload(run: RunContext, artifact_ref: str) -> dict[str, Any] | None:
    for payloads in _iter_staged_payload_maps(run):
        payload = payloads.get(artifact_ref)
        if isinstance(payload, dict):
            return payload
    return None


def has_staged_publication(run: RunContext) -> bool:
    path = _staging_dir(run)
    return path.is_dir() and any(path.glob("*.json"))


def prepared_shared_payloads(run: RunContext) -> dict[str, dict[str, Any]]:
    payloads: dict[str, dict[str, Any]] = {}
    for staged_payloads in _iter_staged_payload_maps(run):
        for ref, payload in staged_payloads.items():
            if ref in payloads:
                raise PipelineError(
                    f"shared publication candidate duplicates artifact {ref}.",
                    stage=STAGE_NAME,
                    exit_code=3,
                )
            payloads[ref] = payload
    _validate_complete_payloads(payloads)
    return payloads


def publish_prepared_shared_state(run: RunContext) -> dict[str, dict[str, Any]]:
    payloads = prepared_shared_payloads(run)
    targets = {ref: run.config_path.parent / ref for ref in PUBLICATION_ARTIFACTS}
    snapshots = {ref: _snapshot(path) for ref, path in targets.items()}
    written: list[str] = []
    try:
        for ref in PUBLICATION_ARTIFACTS:
            write_json(targets[ref], payloads[ref])
            written.append(ref)
    except Exception as exc:
        rollback_errors = _rollback_targets(targets, snapshots)
        if rollback_errors:
            mark_shared_publication_not_published(
                run,
                reason="shared publication failed and rollback was incomplete.",
                status="rollback_failed",
                rollback_errors=rollback_errors,
            )
            raise PipelineError(
                "shared state publication failed and rollback was incomplete.",
                stage=STAGE_NAME,
                exit_code=3,
                error_details={
                    "publication_refs": list(PUBLICATION_ARTIFACTS),
                    "written_refs": written,
                    "rollback_errors": rollback_errors,
                },
            ) from exc
        mark_shared_publication_not_published(
            run,
            reason="shared publication failed; official shared state was rolled back.",
            status="rolled_back",
        )
        raise PipelineError(
            "shared state publication failed; official shared state was rolled back.",
            stage=STAGE_NAME,
            exit_code=3,
            error_details={
                "publication_refs": list(PUBLICATION_ARTIFACTS),
                "written_refs": written,
                "rollback_errors": [],
            },
        ) from exc
    run.manifest["shared_state_publication"] = {
        "status": "published",
        "artifacts": list(PUBLICATION_ARTIFACTS),
        "rolled_back": False,
    }
    return payloads


def mark_shared_publication_not_published(
    run: RunContext,
    *,
    reason: str,
    status: str = "not_published",
    rollback_errors: list[dict[str, str]] | None = None,
) -> None:
    run.manifest["shared_state_publication"] = {
        "status": status,
        "reason": reason,
        "candidate_artifacts": list(PUBLICATION_ARTIFACTS),
        "rolled_back": status == "rolled_back",
        "rollback_errors": rollback_errors or [],
    }
    run.manifest["outcome_history"] = {
        "status": status,
        "reason": reason,
        "history_path": OUTCOME_HISTORY_ARTIFACT,
        "state_path": OUTCOME_HISTORY_STATE_ARTIFACT,
    }
    run.manifest["research_data_catalog"] = {
        "status": status,
        "reason": reason,
        "artifact": RESEARCH_DATA_CATALOG_ARTIFACT,
    }


def cleanup_staged_publication(run: RunContext) -> None:
    staging_dir = _staging_dir(run)
    if not staging_dir.exists():
        return
    for path in sorted(staging_dir.glob("*.json")):
        with suppress(OSError):
            path.unlink()
    with suppress(OSError):
        staging_dir.rmdir()


def _staging_dir(run: RunContext) -> Path:
    return run.run_dir / STAGING_DIR_NAME


def _iter_staged_payload_maps(run: RunContext) -> list[dict[str, dict[str, Any]]]:
    payload_maps = []
    staging_dir = _staging_dir(run)
    if not staging_dir.is_dir():
        return payload_maps
    for path in sorted(staging_dir.glob("*.json")):
        payload = _read_staged_file(path)
        payloads = payload.get("payloads")
        if not isinstance(payloads, dict):
            raise PipelineError(
                f"shared publication staging file {path.name} must contain payloads.",
                stage=STAGE_NAME,
                exit_code=3,
            )
        clean: dict[str, dict[str, Any]] = {}
        for ref, value in payloads.items():
            if not isinstance(ref, str) or not isinstance(value, dict):
                raise PipelineError(
                    f"shared publication staging file {path.name} contains malformed payloads.",
                    stage=STAGE_NAME,
                    exit_code=3,
                )
            clean[ref] = value
        payload_maps.append(clean)
    return payload_maps


def _read_staged_file(path: Path) -> dict[str, Any]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise PipelineError(
            f"shared publication staging file {path.name} is not valid JSON.",
            stage=STAGE_NAME,
            exit_code=3,
        ) from exc
    if not isinstance(loaded, dict):
        raise PipelineError(
            f"shared publication staging file {path.name} must be a JSON object.",
            stage=STAGE_NAME,
            exit_code=3,
        )
    return loaded


def _validate_payload_map(payloads: dict[str, dict[str, Any]]) -> None:
    for ref, payload in payloads.items():
        if not isinstance(ref, str) or not ref:
            raise PipelineError("shared publication artifact ref is missing.", stage=STAGE_NAME, exit_code=3)
        if ref not in PUBLICATION_ARTIFACTS:
            raise PipelineError(
                f"shared publication artifact {ref} is not part of the bounded publication set.",
                stage=STAGE_NAME,
                exit_code=3,
            )
        if not isinstance(payload, dict):
            raise PipelineError(
                f"shared publication payload for {ref} must be a JSON object.",
                stage=STAGE_NAME,
                exit_code=3,
            )


def _validate_complete_payloads(payloads: dict[str, dict[str, Any]]) -> None:
    missing = [ref for ref in PUBLICATION_ARTIFACTS if ref not in payloads]
    if missing:
        raise PipelineError(
            f"shared publication candidates are missing: {', '.join(missing)}.",
            stage=STAGE_NAME,
            exit_code=3,
        )
    _validate_payload_map(payloads)
    _validate_artifact_type(payloads[OUTCOME_HISTORY_ARTIFACT], OUTCOME_HISTORY_ARTIFACT, "outcome_history")
    if not isinstance(payloads[OUTCOME_HISTORY_ARTIFACT].get("records"), list):
        raise PipelineError(
            f"{OUTCOME_HISTORY_ARTIFACT} candidate must contain records.",
            stage=STAGE_NAME,
            exit_code=3,
        )
    _validate_artifact_type(
        payloads[OUTCOME_HISTORY_STATE_ARTIFACT],
        OUTCOME_HISTORY_STATE_ARTIFACT,
        "outcome_history_state",
    )
    if not isinstance(payloads[OUTCOME_HISTORY_STATE_ARTIFACT].get("totals"), dict):
        raise PipelineError(
            f"{OUTCOME_HISTORY_STATE_ARTIFACT} candidate must contain totals.",
            stage=STAGE_NAME,
            exit_code=3,
        )
    _validate_artifact_type(
        payloads[RESEARCH_DATA_CATALOG_ARTIFACT],
        RESEARCH_DATA_CATALOG_ARTIFACT,
        "research_data_catalog",
    )
    if not isinstance(payloads[RESEARCH_DATA_CATALOG_ARTIFACT].get("stores"), list):
        raise PipelineError(
            f"{RESEARCH_DATA_CATALOG_ARTIFACT} candidate must contain stores.",
            stage=STAGE_NAME,
            exit_code=3,
        )


def _validate_artifact_type(payload: dict[str, Any], ref: str, expected: str) -> None:
    if payload.get("artifact_type") != expected:
        raise PipelineError(
            f"{ref} candidate has unexpected artifact_type.",
            stage=STAGE_NAME,
            exit_code=3,
        )


def _snapshot(path: Path) -> tuple[bool, bytes]:
    try:
        return True, path.read_bytes()
    except FileNotFoundError:
        return False, b""


def _rollback_targets(
    targets: dict[str, Path],
    snapshots: dict[str, tuple[bool, bytes]],
) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    for ref, path in reversed(list(targets.items())):
        existed, previous = snapshots[ref]
        try:
            if existed:
                _atomic_write_bytes(path, previous)
            elif path.exists():
                path.unlink()
        except OSError as exc:
            errors.append({"artifact": ref, "message": str(exc)})
    return errors


def _atomic_write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temp_path.open("wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        with suppress(OSError):
            if temp_path.exists():
                temp_path.unlink()

