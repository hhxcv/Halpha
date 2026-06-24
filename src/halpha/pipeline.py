from __future__ import annotations

from copy import deepcopy
import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from halpha.runtime.exception_diagnostics import bounded_exception_diagnostic
from halpha.runtime.logging_utils import redact_private_text
from halpha.runtime.pipeline_contracts import (
    PipelineError,
    RunContext,
    RunResult,
    StageHandler,
)
from halpha.pipeline_stage_handlers import default_stage_handlers
from halpha.pipeline_stages import (
    DECISION_INTELLIGENCE_STAGES,
    OPERATION_ORDER,
    STAGE_OPERATION_MAP,
    STAGE_ORDER,
    TASK_STAGE_MAP,
    downstream_closure as _downstream_closure,
    stages_after as _stages_after,
    stages_before as _stages_before,
    tasks_for_stage as _tasks_for_stage,
    validate_optional_stage as _validate_optional_stage,
    validate_stage as _validate_stage,
    validate_stage_graph as _validate_stage_graph,
)
from halpha.storage import artifact_base, config_base, display_path, ensure_directory, write_json


LOGGER = logging.getLogger(__name__)
RUN_LOCAL_ARTIFACT_PREFIXES = ("raw/", "analysis/", "codex_context/", "report/")


def run_pipeline(
    config: dict[str, Any],
    *,
    config_path: Path,
    stage_handlers: dict[str, StageHandler] | None = None,
    now: datetime | None = None,
    until_stage: str | None = None,
    skip_codex: bool = False,
) -> RunResult:
    _validate_optional_stage(until_stage, option_name="--until")
    _validate_stage_graph()
    clock = _clock(now)
    run = _create_run_context(config, config_path=config_path, now=clock())
    _record_validation_mode(run, until_stage=until_stage, skip_codex=skip_codex)
    _write_manifest(run)
    LOGGER.info(
        "Pipeline run started.",
        extra={
            "event": "pipeline.run.start",
            "run_id": run.run_id,
            "until_stage": until_stage,
            "skip_codex": skip_codex,
        },
    )

    handlers = default_stage_handlers(stage_handlers)

    for stage in STAGE_ORDER:
        stage_record: dict[str, Any] = {
            "name": stage,
            "status": "running",
            "started_at": _utc_timestamp(clock()),
            "finished_at": None,
            "artifacts": [],
            "tasks": [],
        }
        run.manifest["stages"].append(stage_record)
        _write_manifest(run)

        failure = _run_stage_tasks(
            config,
            run,
            stage,
            stage_record,
            handlers=handlers,
            clock=clock,
            mode=None,
            skip_codex=skip_codex,
        )
        if failure:
            return failure
        _write_manifest(run)
        if stage == until_stage:
            _record_not_run_stages(
                run,
                _stages_after(stage),
                reason=f"--until {stage} requested",
            )
            break

    run.manifest["status"] = "succeeded"
    run.manifest["finished_at"] = _utc_timestamp(clock())
    _write_manifest(run)
    _commit_terminal_run_projection(config, run, clock=clock)
    LOGGER.info(
        "Pipeline run succeeded.",
        extra={"event": "pipeline.run.succeeded", "run_id": run.run_id},
    )
    return RunResult(True, run, 0, None, None)


def run_pipeline_stage(
    config: dict[str, Any],
    *,
    config_path: Path,
    run_dir: Path,
    stage: str,
    stage_handlers: dict[str, StageHandler] | None = None,
    now: datetime | None = None,
) -> RunResult:
    _validate_stage(stage, option_name="stage")
    _validate_stage_graph()
    clock = _clock(now)
    source_run = _load_run_context(config, config_path=config_path, run_dir=run_dir)
    LOGGER.info(
        "Pipeline stage rerun started.",
        extra={"event": "pipeline.stage_rerun.start", "run_id": source_run.run_id, "stage": stage},
    )
    handlers = default_stage_handlers(stage_handlers)
    if source_run.manifest.get("status") == "succeeded":
        return _run_derived_stage_rerun(
            config,
            source_run,
            config_path=config_path,
            stage=stage,
            handlers=handlers,
            clock=clock,
        )
    return _resume_pipeline_stage(
        config,
        source_run,
        stage=stage,
        handlers=handlers,
        clock=clock,
    )


def _run_derived_stage_rerun(
    config: dict[str, Any],
    parent: RunContext,
    *,
    config_path: Path,
    stage: str,
    handlers: dict[str, StageHandler],
    clock: Callable[[], datetime],
) -> RunResult:
    terminal_stage = _rerun_terminal_stage(parent, stage=stage)
    closure = _downstream_closure(stage, through_stage=terminal_stage)
    reusable_stages = _stages_before(stage)
    reusable_records = _validated_reusable_stage_records(parent, reusable_stages)
    reusable_refs = _stage_artifact_refs(reusable_records)
    _validate_reusable_artifacts(parent, reusable_records)

    run = _create_run_context(config, config_path=config_path, now=clock())
    skip_codex = _inherits_no_codex(parent)
    _prepare_derived_manifest(
        run,
        parent,
        stage=stage,
        terminal_stage=terminal_stage,
        closure=closure,
        reusable_records=reusable_records,
        reusable_refs=reusable_refs,
        skip_codex=skip_codex,
        requested_at=_utc_timestamp(clock()),
    )
    _copy_reusable_artifacts(parent, run, reusable_refs)
    _write_manifest(run)

    failure = _run_stage_sequence(
        config,
        run,
        closure,
        handlers=handlers,
        clock=clock,
        mode="recomputed",
        skip_codex=skip_codex,
    )
    if failure:
        return failure

    if terminal_stage != STAGE_ORDER[-1]:
        _record_not_run_stages(
            run,
            _stages_after(terminal_stage),
            reason=f"stage rerun validation ended at {terminal_stage}",
        )

    run.manifest["status"] = "succeeded"
    run.manifest["finished_at"] = _utc_timestamp(clock())
    _write_manifest(run)
    _commit_terminal_run_projection(config, run, clock=clock)
    LOGGER.info(
        "Pipeline stage rerun succeeded.",
        extra={
            "event": "pipeline.stage_rerun.succeeded",
            "run_id": run.run_id,
            "parent_run_id": parent.run_id,
            "stage": stage,
        },
    )
    return RunResult(True, run, 0, None, None)


def _resume_pipeline_stage(
    config: dict[str, Any],
    run: RunContext,
    *,
    stage: str,
    handlers: dict[str, StageHandler],
    clock: Callable[[], datetime],
) -> RunResult:
    terminal_stage = _resume_terminal_stage(run, stage=stage)
    closure = _downstream_closure(stage, through_stage=terminal_stage)
    _validate_resume_request(run, stage=stage)
    _validate_reusable_artifacts(run, _validated_reusable_stage_records(run, _stages_before(stage)))
    skip_codex = _inherits_no_codex(run)

    run.manifest["status"] = "running"
    run.manifest["finished_at"] = None
    run.manifest["stage_rerun"] = {
        "mode": "resume_in_place",
        "requested_stage": stage,
        "terminal_stage": terminal_stage,
        "downstream_closure": list(closure),
        "requested_at": _utc_timestamp(clock()),
    }
    _truncate_manifest_for_resume(run, stage=stage)
    _write_manifest(run)

    failure = _run_stage_sequence(
        config,
        run,
        closure,
        handlers=handlers,
        clock=clock,
        mode="resume",
        skip_codex=skip_codex,
    )
    if failure:
        return failure

    if terminal_stage != STAGE_ORDER[-1]:
        _record_not_run_stages(
            run,
            _stages_after(terminal_stage),
            reason=f"stage resume validation ended at {terminal_stage}",
        )

    run.manifest["status"] = "succeeded"
    run.manifest["finished_at"] = _utc_timestamp(clock())
    _write_manifest(run)
    _commit_terminal_run_projection(config, run, clock=clock)
    LOGGER.info(
        "Pipeline stage resume succeeded.",
        extra={"event": "pipeline.stage_resume.succeeded", "run_id": run.run_id, "stage": stage},
    )
    return RunResult(True, run, 0, None, None)


def _create_run_context(config: dict[str, Any], *, config_path: Path, now: datetime | None) -> RunContext:
    output_dir = Path(config["run"]["output_dir"])
    if not output_dir.is_absolute():
        output_dir = artifact_base(config_path) / output_dir

    run_id = _run_id(now)
    run_dir = _unique_run_dir(output_dir, run_id)
    run_id = run_dir.name

    raw_dir = run_dir / "raw"
    analysis_dir = run_dir / "analysis"
    codex_context_dir = run_dir / "codex_context"
    report_dir = run_dir / "report"

    for directory in (raw_dir, analysis_dir, codex_context_dir, report_dir):
        ensure_directory(directory)

    manifest = {
        "schema_version": 1,
        "run_id": run_id,
        "status": "running",
        "started_at": _utc_timestamp(now),
        "finished_at": None,
        "config_path": _path_for_manifest(config_path),
        "sources": _source_summary(config),
        "artifacts": {},
        "counts": {},
        "stage_order": list(STAGE_ORDER),
        "task_order": list(OPERATION_ORDER),
        "stages": [],
        "codex": _codex_summary(config),
        "errors": [],
    }

    return RunContext(
        run_id=run_id,
        run_dir=run_dir,
        raw_dir=raw_dir,
        analysis_dir=analysis_dir,
        codex_context_dir=codex_context_dir,
        report_dir=report_dir,
        manifest_path=run_dir / "run_manifest.json",
        config_path=config_path,
        manifest=manifest,
    )


def _load_run_context(config: dict[str, Any], *, config_path: Path, run_dir: Path) -> RunContext:
    manifest_path = run_dir / "run_manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PipelineError(
            "run_manifest.json was not found in the requested run directory.",
            stage="stage",
            exit_code=3,
        ) from exc
    except json.JSONDecodeError as exc:
        raise PipelineError(
            f"run_manifest.json is not valid JSON: {exc.msg}.",
            stage="stage",
            exit_code=3,
        ) from exc
    if not isinstance(manifest, dict):
        raise PipelineError(
            "run_manifest.json must be a JSON object.",
            stage="stage",
            exit_code=3,
        )

    raw_dir = run_dir / "raw"
    analysis_dir = run_dir / "analysis"
    codex_context_dir = run_dir / "codex_context"
    report_dir = run_dir / "report"
    for directory in (raw_dir, analysis_dir, codex_context_dir, report_dir):
        ensure_directory(directory)
    manifest.setdefault("schema_version", 1)
    manifest.setdefault("run_id", run_dir.name)
    manifest.setdefault("config_path", _path_for_manifest(config_path))
    manifest.setdefault("sources", _source_summary(config))
    manifest.setdefault("artifacts", {})
    manifest.setdefault("counts", {})
    manifest.setdefault("stage_order", list(STAGE_ORDER))
    manifest.setdefault("task_order", list(OPERATION_ORDER))
    manifest.setdefault("stages", [])
    manifest.setdefault("codex", _codex_summary(config))
    manifest.setdefault("errors", [])

    return RunContext(
        run_id=str(manifest.get("run_id") or run_dir.name),
        run_dir=run_dir,
        raw_dir=raw_dir,
        analysis_dir=analysis_dir,
        codex_context_dir=codex_context_dir,
        report_dir=report_dir,
        manifest_path=manifest_path,
        config_path=config_path,
        manifest=manifest,
    )


def _run_stage_sequence(
    config: dict[str, Any],
    run: RunContext,
    stages: list[str],
    *,
    handlers: dict[str, StageHandler],
    clock: Callable[[], datetime],
    mode: str,
    skip_codex: bool,
) -> RunResult | None:
    for stage in stages:
        stage_record: dict[str, Any] = {
            "name": stage,
            "status": "running",
            "started_at": _utc_timestamp(clock()),
            "finished_at": None,
            "artifacts": [],
            "tasks": [],
        }
        if mode:
            stage_record["mode"] = mode
        run.manifest["stages"].append(stage_record)
        _write_manifest(run)
        failure = _run_stage_tasks(
            config,
            run,
            stage,
            stage_record,
            handlers=handlers,
            clock=clock,
            mode=mode,
            skip_codex=skip_codex,
        )
        if failure:
            return failure
        _write_manifest(run)
    return None


def _run_stage_tasks(
    config: dict[str, Any],
    run: RunContext,
    stage: str,
    stage_record: dict[str, Any],
    *,
    handlers: dict[str, StageHandler],
    clock: Callable[[], datetime],
    mode: str | None,
    skip_codex: bool,
) -> RunResult | None:
    for task in _tasks_for_stage(stage):
        task_record: dict[str, Any] = {
            "name": task,
            "status": "running",
            "started_at": _utc_timestamp(clock()),
            "finished_at": None,
            "artifacts": [],
            "warnings": [],
            "errors": [],
            "dependencies": _task_dependencies(task),
        }
        if mode:
            task_record["mode"] = mode
        stage_record.setdefault("tasks", []).append(task_record)
        _set_codex_status(run, stage=task, status="running")
        _refresh_stage_record(stage_record)
        _write_manifest(run)

        if skip_codex and task == "run_codex_report":
            _skip_stage(
                run,
                task_record,
                stage=task,
                reason="--no-codex requested",
                finished_at=_utc_timestamp(clock()),
            )
        else:
            failure = _run_stage_handler(
                config,
                run,
                handlers[task],
                stage=task,
                stage_record=task_record,
                clock=clock,
                parent_stage_record=stage_record,
            )
            if failure:
                return failure
        _refresh_stage_record(stage_record)
        _write_manifest(run)
    _finish_stage_record(stage_record, finished_at=_utc_timestamp(clock()))
    return None


def _refresh_stage_record(stage_record: dict[str, Any]) -> None:
    tasks = [task for task in stage_record.get("tasks", []) if isinstance(task, dict)]
    stage_record["artifacts"] = _unique_artifact_refs(task.get("artifacts") for task in tasks)
    if not tasks:
        return
    statuses = [str(task.get("status") or "unknown") for task in tasks]
    if any(status == "failed" for status in statuses):
        stage_record["status"] = "failed"
    elif any(status == "running" for status in statuses):
        stage_record["status"] = "running"
    elif any(status == "succeeded" for status in statuses):
        stage_record["status"] = "succeeded"
    elif all(status == "not_run" for status in statuses):
        stage_record["status"] = "not_run"
    elif all(status in {"skipped", "disabled"} for status in statuses):
        stage_record["status"] = "skipped"
    else:
        stage_record["status"] = "succeeded"


def _finish_stage_record(stage_record: dict[str, Any], *, finished_at: str) -> None:
    _refresh_stage_record(stage_record)
    stage_record["finished_at"] = finished_at


def _unique_artifact_refs(values: Any) -> list[str]:
    refs: list[str] = []
    seen: set[str] = set()
    for value in values:
        for ref in _artifact_ref_strings(value):
            if ref not in seen:
                refs.append(ref)
                seen.add(ref)
    return refs


def _prepare_derived_manifest(
    run: RunContext,
    parent: RunContext,
    *,
    stage: str,
    terminal_stage: str,
    closure: list[str],
    reusable_records: list[dict[str, Any]],
    reusable_refs: list[str],
    skip_codex: bool,
    requested_at: str,
) -> None:
    run.manifest["artifacts"] = _reused_manifest_artifacts(parent.manifest, reusable_refs)
    run.manifest["counts"] = deepcopy(parent.manifest.get("counts")) if isinstance(parent.manifest.get("counts"), dict) else {}
    run.manifest["stages"] = [_reused_stage_record(parent.run_id, record) for record in reusable_records]
    run.manifest["parent_run_id"] = parent.run_id
    run.manifest["lineage"] = {
        "parent_run_id": parent.run_id,
        "parent_run_dir": display_path(parent.run_dir, base=artifact_base(parent.config_path)),
        "parent_manifest": display_path(parent.manifest_path, base=artifact_base(parent.config_path)),
    }
    run.manifest["stage_rerun"] = {
        "mode": "derived_run",
        "parent_run_id": parent.run_id,
        "requested_stage": stage,
        "terminal_stage": terminal_stage,
        "downstream_closure": list(closure),
        "reused_stages": [str(record.get("name")) for record in reusable_records],
        "reused_artifacts": list(reusable_refs),
        "requested_at": requested_at,
    }
    run.manifest["validation"] = {
        "mode": "stage_rerun",
        "until_stage": None if terminal_stage == STAGE_ORDER[-1] else terminal_stage,
        "skip_codex": skip_codex,
    }
    if any(_stage_record_has_task(record, "run_codex_report") for record in reusable_records) and isinstance(
        parent.manifest.get("codex"), dict
    ):
        run.manifest["codex"] = deepcopy(parent.manifest["codex"])


def _rerun_terminal_stage(parent: RunContext, *, stage: str) -> str:
    until_stage = _manifest_until_stage(parent)
    if until_stage is None:
        return STAGE_ORDER[-1]

    requested_index = STAGE_ORDER.index(stage)
    until_index = STAGE_ORDER.index(until_stage)
    if requested_index <= until_index:
        return until_stage
    if requested_index == until_index + 1:
        return stage
    missing = STAGE_ORDER[until_index + 1]
    raise PipelineError(
        f"requested stage {stage} depends on parent operation {missing}, which was not run.",
        stage="stage",
        exit_code=3,
    )


def _resume_terminal_stage(run: RunContext, *, stage: str) -> str:
    return _rerun_terminal_stage(run, stage=stage)


def _manifest_until_stage(run: RunContext) -> str | None:
    validation = run.manifest.get("validation")
    if not isinstance(validation, dict):
        return None
    until_stage = validation.get("until_stage")
    if until_stage is None:
        return None
    if not isinstance(until_stage, str) or until_stage not in STAGE_ORDER:
        raise PipelineError(
            "parent run validation metadata references an unknown until_stage.",
            stage="stage",
            exit_code=3,
        )
    return until_stage


def _validated_reusable_stage_records(run: RunContext, stages: list[str]) -> list[dict[str, Any]]:
    records_by_stage = _latest_stage_records(run.manifest)
    records: list[dict[str, Any]] = []
    for stage in stages:
        record = records_by_stage.get(stage)
        if record is None:
            raise PipelineError(
                f"parent run is missing upstream operation {stage}.",
                stage="stage",
                exit_code=3,
            )
        status = str(record.get("status") or "")
        if status not in {"succeeded", "skipped", "disabled"}:
            raise PipelineError(
                f"upstream operation {stage} cannot be reused because its status is {status or 'unknown'}.",
                stage="stage",
                exit_code=3,
            )
        records.append(record)
    return records


def _latest_stage_records(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    stages = manifest.get("stages")
    if not isinstance(stages, list):
        return records
    for record in stages:
        if not isinstance(record, dict):
            continue
        stage = record.get("name")
        if isinstance(stage, str) and stage in STAGE_ORDER:
            records[stage] = record
    return records


def _stage_artifact_refs(records: list[dict[str, Any]]) -> list[str]:
    refs: list[str] = []
    seen: set[str] = set()
    for record in records:
        for ref in _artifact_ref_strings(record.get("artifacts")):
            if ref not in seen:
                refs.append(ref)
                seen.add(ref)
    return refs


def _artifact_ref_strings(value: Any) -> list[str]:
    if isinstance(value, str) and value:
        return [value]
    if isinstance(value, list):
        refs: list[str] = []
        for item in value:
            refs.extend(_artifact_ref_strings(item))
        return refs
    if isinstance(value, dict):
        refs: list[str] = []
        for item in value.values():
            refs.extend(_artifact_ref_strings(item))
        return refs
    return []


def _validate_reusable_artifacts(run: RunContext, records: list[dict[str, Any]]) -> None:
    for record in records:
        stage = str(record.get("name") or "stage")
        for ref in _artifact_ref_strings(record.get("artifacts")):
            path = _run_artifact_path(run, ref, stage=stage)
            if not path.exists():
                raise PipelineError(
                    f"reusable upstream artifact {ref} from operation {stage} was not found.",
                    stage="stage",
                    exit_code=3,
                )


def _copy_reusable_artifacts(parent: RunContext, run: RunContext, refs: list[str]) -> None:
    for ref in refs:
        if not _is_run_local_artifact_ref(ref):
            continue
        source = _run_artifact_path(parent, ref, stage="stage")
        target = _run_artifact_path(run, ref, stage="stage")
        ensure_directory(target.parent)
        if source.is_dir():
            shutil.copytree(source, target, dirs_exist_ok=True)
        else:
            shutil.copy2(source, target)


def _run_artifact_path(run: RunContext, ref: str, *, stage: str) -> Path:
    artifact_ref = Path(ref)
    if artifact_ref.is_absolute() or any(part == ".." for part in artifact_ref.parts):
        raise PipelineError(
            f"artifact ref {ref} from operation {stage} must stay inside the run directory.",
            stage="stage",
            exit_code=3,
        )
    base = run.run_dir if _is_run_local_artifact_ref(ref) else artifact_base(run.config_path)
    return base / artifact_ref


def _is_run_local_artifact_ref(ref: str) -> bool:
    normalized = ref.replace("\\", "/")
    return normalized.startswith(RUN_LOCAL_ARTIFACT_PREFIXES)


def _reused_manifest_artifacts(manifest: dict[str, Any], reusable_refs: list[str]) -> dict[str, Any]:
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict):
        return {}
    reusable = set(reusable_refs)
    reused: dict[str, Any] = {}
    for key, value in artifacts.items():
        filtered = _filter_artifact_value(value, reusable)
        if filtered is not None:
            reused[str(key)] = filtered
    return reused


def _filter_artifact_value(value: Any, reusable_refs: set[str]) -> Any:
    if isinstance(value, str):
        return value if value in reusable_refs else None
    if isinstance(value, list):
        filtered = [_filter_artifact_value(item, reusable_refs) for item in value]
        return [item for item in filtered if item is not None] or None
    if isinstance(value, dict):
        filtered = {str(key): _filter_artifact_value(item, reusable_refs) for key, item in value.items()}
        filtered = {key: item for key, item in filtered.items() if item is not None}
        return filtered or None
    return None


def _reused_stage_record(parent_run_id: str, record: dict[str, Any]) -> dict[str, Any]:
    reused = deepcopy(record)
    reused["mode"] = "reused"
    reused["source_run_id"] = parent_run_id
    for task in reused.get("tasks", []):
        if isinstance(task, dict):
            task["mode"] = "reused"
            task["source_run_id"] = parent_run_id
    return reused


def _stage_record_has_task(record: dict[str, Any], task_name: str) -> bool:
    tasks = record.get("tasks")
    if not isinstance(tasks, list):
        return False
    return any(isinstance(task, dict) and task.get("name") == task_name for task in tasks)


def _inherits_no_codex(run: RunContext) -> bool:
    validation = run.manifest.get("validation")
    if isinstance(validation, dict) and validation.get("skip_codex") is True:
        return True
    codex = run.manifest.get("codex")
    if not isinstance(codex, dict):
        return False
    return codex.get("status") == "skipped" and codex.get("skip_reason") == "--no-codex requested"


def _validate_resume_request(run: RunContext, *, stage: str) -> None:
    status = str(run.manifest.get("status") or "")
    if status == "succeeded":
        raise PipelineError(
            "completed successful runs are immutable; rerun created a derived run instead of resuming in place.",
            stage="stage",
            exit_code=3,
        )
    if status == "failed":
        failed_stage = _first_failed_stage(run.manifest)
        if failed_stage is None:
            raise PipelineError(
                "failed run cannot be resumed because no failed operation is recorded.",
                stage="stage",
                exit_code=3,
            )
        if failed_stage != stage:
            raise PipelineError(
                f"failed run can only resume from failed operation {failed_stage}.",
                stage="stage",
                exit_code=3,
            )
        return
    if status != "running":
        raise PipelineError(
            f"run status {status or 'unknown'} cannot be resumed in place.",
            stage="stage",
            exit_code=3,
        )


def _first_failed_stage(manifest: dict[str, Any]) -> str | None:
    stages = manifest.get("stages")
    if not isinstance(stages, list):
        return None
    for record in stages:
        if not isinstance(record, dict):
            continue
        stage = record.get("name")
        if record.get("status") == "failed" and isinstance(stage, str):
            return stage
    return None


def _truncate_manifest_for_resume(run: RunContext, *, stage: str) -> None:
    start_index = STAGE_ORDER.index(stage)
    stages = run.manifest.get("stages")
    if not isinstance(stages, list):
        run.manifest["stages"] = []
        return

    kept: list[dict[str, Any]] = []
    removed_refs: list[str] = []
    removed_stages: list[str] = []
    for record in stages:
        if not isinstance(record, dict):
            continue
        name = record.get("name")
        if not isinstance(name, str) or name not in STAGE_ORDER:
            continue
        if STAGE_ORDER.index(name) < start_index:
            kept.append(record)
        else:
            removed_stages.append(name)
            removed_refs.extend(_artifact_ref_strings(record.get("artifacts")))
    removed_refs.extend(_operation_output_refs(removed_stages))
    run.manifest["stages"] = kept
    _drop_manifest_artifacts(run, removed_refs)
    _delete_artifact_refs(run, removed_refs)
    _drop_stage_errors(run, start_index=start_index)


def _operation_output_refs(stages: list[str]) -> list[str]:
    refs: list[str] = []
    seen: set[str] = set()
    for stage in stages:
        for task in _tasks_for_stage(stage):
            operation = STAGE_OPERATION_MAP.get(task)
            if operation is None:
                continue
            for ref in operation.outputs:
                if ref not in seen:
                    refs.append(ref)
                    seen.add(ref)
    return refs


def _drop_manifest_artifacts(run: RunContext, refs: list[str]) -> None:
    artifacts = run.manifest.get("artifacts")
    if not isinstance(artifacts, dict) or not refs:
        return
    stale_refs = set(refs)
    filtered: dict[str, Any] = {}
    for key, value in artifacts.items():
        kept = _filter_artifact_value(value, set(_artifact_ref_strings(value)) - stale_refs)
        if kept is not None:
            filtered[str(key)] = kept
    run.manifest["artifacts"] = filtered


def _delete_artifact_refs(run: RunContext, refs: list[str]) -> None:
    for ref in sorted(set(refs)):
        if not _is_run_local_artifact_ref(ref):
            continue
        path = _run_artifact_path(run, ref, stage="stage")
        if path.is_dir():
            shutil.rmtree(path)
        elif path.exists():
            path.unlink()


def _drop_stage_errors(run: RunContext, *, start_index: int) -> None:
    errors = run.manifest.get("errors")
    if not isinstance(errors, list):
        run.manifest["errors"] = []
        return
    kept: list[Any] = []
    for error in errors:
        if not isinstance(error, dict):
            continue
        stage = error.get("stage")
        if isinstance(stage, str):
            product_stage = stage if stage in STAGE_ORDER else TASK_STAGE_MAP.get(stage)
            if product_stage is not None and STAGE_ORDER.index(product_stage) >= start_index:
                continue
        kept.append(error)
    run.manifest["errors"] = kept


def _run_stage_handler(
    config: dict[str, Any],
    run: RunContext,
    handler: StageHandler,
    *,
    stage: str,
    stage_record: dict[str, Any],
    clock: Callable[[], datetime],
    parent_stage_record: dict[str, Any] | None = None,
) -> RunResult | None:
    LOGGER.debug(
        "Pipeline stage started.",
        extra={"event": "pipeline.stage.start", "run_id": run.run_id, "stage": stage},
    )
    try:
        artifacts = handler(config, run)
    except PipelineError as exc:
        finished_at = _utc_timestamp(clock())
        failed_stage = exc.stage or stage
        reason = redact_private_text(str(exc), config_path=run.config_path, config=config)
        error = _error_summary(
            failed_stage,
            reason,
            details=exc.error_details,
            diagnostic=(
                bounded_exception_diagnostic(exc, context={"pipeline_exit_code": exc.exit_code})
                if exc.error_details
                else None
            ),
        )
        stage_record["status"] = "failed"
        stage_record["finished_at"] = finished_at
        stage_record["artifacts"] = exc.artifacts
        stage_record["error"] = error
        stage_record["errors"] = [error]
        if parent_stage_record is not None:
            parent_stage_record["status"] = "failed"
            parent_stage_record["finished_at"] = finished_at
            parent_stage_record["error"] = error
            parent_stage_record["errors"] = [error]
            _refresh_stage_record(parent_stage_record)
        _set_codex_status(run, stage=stage, status="failed")
        _record_stage_failure_context(config, run, stage=stage, error=error)
        _finish_manifest(config, run, status="failed", error=error, finished_at=finished_at, clock=clock)
        LOGGER.error(
            "Pipeline stage failed.",
            extra={
                "event": "pipeline.stage.failed",
                "run_id": run.run_id,
                "stage": failed_stage,
                "exit_code": exc.exit_code,
                "reason": reason,
            },
        )
        return RunResult(False, run, exc.exit_code, failed_stage, reason)
    except Exception as exc:
        finished_at = _utc_timestamp(clock())
        exception_message = redact_private_text(str(exc), config_path=run.config_path, config=config)
        reason = f"stage {stage} failed: {exception_message}"
        error = _error_summary(stage, reason, diagnostic=bounded_exception_diagnostic(exc))
        stage_record["status"] = "failed"
        stage_record["finished_at"] = finished_at
        stage_record["error"] = error
        stage_record["errors"] = [error]
        if parent_stage_record is not None:
            parent_stage_record["status"] = "failed"
            parent_stage_record["finished_at"] = finished_at
            parent_stage_record["error"] = error
            parent_stage_record["errors"] = [error]
            _refresh_stage_record(parent_stage_record)
        _set_codex_status(run, stage=stage, status="failed")
        _record_stage_failure_context(config, run, stage=stage, error=error)
        _finish_manifest(config, run, status="failed", error=error, finished_at=finished_at, clock=clock)
        LOGGER.error(
            "Pipeline stage failed.",
            extra={
                "event": "pipeline.stage.failed",
                "run_id": run.run_id,
                "stage": stage,
                "exit_code": 1,
                "reason": reason,
            },
        )
        return RunResult(False, run, 1, stage, reason)

    finished_at = _utc_timestamp(clock())
    stage_record["status"] = "succeeded"
    stage_record["finished_at"] = finished_at
    stage_record["artifacts"] = artifacts or []
    _set_codex_status(run, stage=stage, status="succeeded")
    LOGGER.debug(
        "Pipeline stage succeeded.",
        extra={
            "event": "pipeline.stage.succeeded",
            "run_id": run.run_id,
            "stage": stage,
            "artifact_count": len(stage_record["artifacts"]),
        },
    )
    return None


def _skip_stage(
    run: RunContext,
    stage_record: dict[str, Any],
    *,
    stage: str,
    reason: str,
    finished_at: str,
) -> None:
    stage_record["status"] = "skipped"
    stage_record["finished_at"] = finished_at
    stage_record["artifacts"] = []
    stage_record["reason"] = reason
    if stage == "run_codex_report":
        run.manifest["codex"]["status"] = "skipped"
        run.manifest["codex"]["exit_code"] = None
        run.manifest["codex"]["skip_reason"] = reason
    LOGGER.info(
        "Pipeline stage skipped.",
        extra={"event": "pipeline.stage.skipped", "run_id": run.run_id, "stage": stage, "reason": reason},
    )


def _task_dependencies(task: str) -> list[str]:
    operation = STAGE_OPERATION_MAP.get(task)
    if operation is None:
        return []
    return list(operation.dependencies)


def _record_stage_failure_context(
    config: dict[str, Any],
    run: RunContext,
    *,
    stage: str,
    error: dict[str, Any],
) -> None:
    failed_stage = str(error.get("stage") or stage)
    if stage not in DECISION_INTELLIGENCE_STAGES and failed_stage not in DECISION_INTELLIGENCE_STAGES:
        return
    from halpha.decision.decision_intelligence import record_decision_intelligence_failure

    message = str(error.get("message") or f"stage {failed_stage} failed")
    record_decision_intelligence_failure(config, run, stage=failed_stage, message=message)


def _record_not_run_stages(run: RunContext, stages: list[str], *, reason: str) -> None:
    for stage in stages:
        record: dict[str, Any] = {
            "name": stage,
            "status": "not_run",
            "started_at": None,
            "finished_at": None,
            "artifacts": [],
            "reason": reason,
            "tasks": [
                {
                    "name": task,
                    "status": "not_run",
                    "started_at": None,
                    "finished_at": None,
                    "artifacts": [],
                    "warnings": [],
                    "errors": [],
                    "dependencies": _task_dependencies(task),
                    "reason": reason,
                }
                for task in _tasks_for_stage(stage)
            ],
        }
        run.manifest["stages"].append(record)
        if "run_codex_report" in _tasks_for_stage(stage):
            run.manifest["codex"]["status"] = "not_run"
            run.manifest["codex"]["exit_code"] = None
            run.manifest["codex"]["skip_reason"] = reason
    if stages:
        LOGGER.info(
            "Pipeline stages marked not run.",
            extra={
                "event": "pipeline.stages.not_run",
                "run_id": run.run_id,
                "stage_count": len(stages),
                "first_stage": stages[0],
                "last_stage": stages[-1],
                "reason": reason,
            },
        )


def _record_validation_mode(run: RunContext, *, until_stage: str | None, skip_codex: bool) -> None:
    if until_stage is None and not skip_codex:
        return
    run.manifest["validation"] = {
        "mode": "run",
        "until_stage": until_stage,
        "skip_codex": skip_codex,
    }


def _finish_manifest(
    config: dict[str, Any],
    run: RunContext,
    *,
    status: str,
    error: dict[str, Any],
    finished_at: str,
    clock: Callable[[], datetime],
) -> None:
    run.manifest["status"] = status
    run.manifest["finished_at"] = finished_at
    run.manifest["errors"].append(error)
    _write_manifest(run)
    _commit_terminal_run_projection(config, run, clock=clock)


def _commit_terminal_run_projection(
    config: dict[str, Any],
    run: RunContext,
    *,
    clock: Callable[[], datetime],
) -> None:
    from halpha.data.run_index import RUN_INDEX_ARTIFACT, write_run_index

    try:
        summary = write_run_index(run, now=clock())
    except Exception as exc:
        reason = redact_private_text(str(exc), config_path=run.config_path, config=config)
        LOGGER.error(
            "Terminal run state projection failed.",
            extra={
                "event": "pipeline.terminal_projection.failed",
                "run_id": run.run_id,
                "artifact": RUN_INDEX_ARTIFACT,
                "reason": reason,
                "diagnostic": bounded_exception_diagnostic(exc),
            },
        )
        return
    LOGGER.info(
        "Terminal run state projection committed.",
        extra={
            "event": "pipeline.terminal_projection.committed",
            "run_id": run.run_id,
            "artifact": summary.get("artifact"),
            "status": summary.get("status"),
        },
    )


def _error_summary(
    stage: str,
    reason: str,
    *,
    details: dict[str, Any] | None = None,
    diagnostic: dict[str, Any] | None = None,
) -> dict[str, Any]:
    error: dict[str, Any] = {"stage": stage, "message": reason}
    if details:
        error.update(details)
    if diagnostic:
        error["diagnostic"] = diagnostic
    return error


def _set_codex_status(run: RunContext, *, stage: str, status: str) -> None:
    if stage == "run_codex_report":
        if run.manifest["codex"].get("status") == "disabled" and status == "succeeded":
            return
        run.manifest["codex"]["status"] = status


def _write_manifest(run: RunContext) -> None:
    write_json(run.manifest_path, run.manifest)


def _clock(now: datetime | None) -> Callable[[], datetime]:
    if now is not None:
        return lambda: now
    return lambda: datetime.now(timezone.utc)


def _run_id(now: datetime | None) -> str:
    value = now or datetime.now(timezone.utc)
    return value.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _utc_timestamp(now: datetime | None = None) -> str:
    value = now or datetime.now(timezone.utc)
    value = value.astimezone(timezone.utc).replace(microsecond=0)
    return value.isoformat().replace("+00:00", "Z")


def _unique_run_dir(output_dir: Path, run_id: str) -> Path:
    ensure_directory(output_dir)
    candidate = output_dir / run_id
    if not candidate.exists():
        candidate.mkdir()
        return candidate

    for index in range(1, 100):
        candidate = output_dir / f"{run_id}-{index:02d}"
        if not candidate.exists():
            candidate.mkdir()
            return candidate

    raise PipelineError(f"could not create a unique run directory for run_id {run_id}")


def _source_summary(config: dict[str, Any]) -> dict[str, Any]:
    market = config.get("market", {})
    text = config.get("text", {})
    derivatives = market.get("derivatives") if isinstance(market, dict) else {}
    macro_calendar = config.get("macro_calendar", {})
    onchain_flow = config.get("onchain_flow", {})
    derivatives_summary = {}
    if isinstance(derivatives, dict):
        derivatives_summary = {
            "enabled": derivatives.get("enabled"),
            "source": derivatives.get("source"),
            "symbols": list(derivatives.get("symbols", [])),
            "data_classes": list(derivatives.get("data_classes", [])),
            "periods": list(derivatives.get("periods", [])),
        }
    macro_calendar_summary = {}
    if isinstance(macro_calendar, dict):
        macro_calendar_summary = {
            "enabled": macro_calendar.get("enabled"),
            "source": macro_calendar.get("source"),
            "data_classes": list(macro_calendar.get("data_classes", [])),
            "regions": list(macro_calendar.get("regions", [])),
        }
    onchain_flow_summary = {}
    if isinstance(onchain_flow, dict):
        onchain_flow_summary = {
            "enabled": onchain_flow.get("enabled"),
            "source": onchain_flow.get("source"),
            "data_classes": list(onchain_flow.get("data_classes", [])),
            "assets": list(onchain_flow.get("assets", [])),
            "chains": list(onchain_flow.get("chains", [])),
        }

    return {
        "market": {
            "enabled": market.get("enabled"),
            "source": market.get("source"),
            "symbols": list(market.get("symbols", [])),
            "derivatives": derivatives_summary,
        },
        "macro_calendar": macro_calendar_summary,
        "onchain_flow": onchain_flow_summary,
        "text": [
            {
                "name": source.get("name"),
                "type": source.get("type"),
                "url": source.get("url"),
            }
            for source in text.get("sources", [])
        ],
    }


def _codex_summary(config: dict[str, Any]) -> dict[str, Any]:
    codex = config.get("codex", {})
    return {
        "enabled": codex.get("enabled"),
        "command": codex.get("command"),
        "status": "not_started",
        "exit_code": None,
    }


def _path_for_manifest(path: Path) -> str:
    return display_path(path, base=config_base(path))

