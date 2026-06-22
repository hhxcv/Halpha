from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


class PipelineError(Exception):
    def __init__(
        self,
        message: str,
        *,
        stage: str | None = None,
        exit_code: int = 1,
        artifacts: list[str] | None = None,
        error_details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.stage = stage
        self.exit_code = exit_code
        self.artifacts = artifacts or []
        self.error_details = error_details or {}


class StageNotImplementedError(PipelineError):
    def __init__(self, stage: str) -> None:
        super().__init__(f"stage {stage} is not implemented", stage=stage, exit_code=3)


@dataclass(frozen=True)
class RunContext:
    run_id: str
    run_dir: Path
    raw_dir: Path
    analysis_dir: Path
    codex_context_dir: Path
    report_dir: Path
    manifest_path: Path
    config_path: Path
    manifest: dict[str, Any]


@dataclass(frozen=True)
class RunResult:
    succeeded: bool
    run: RunContext
    exit_code: int
    failed_stage: str | None
    reason: str | None


StageHandler = Callable[[dict[str, Any], RunContext], list[str] | None]
