from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from .config import SUPPORTED_TEXT_INTELLIGENCE_MODEL_PROVIDERS
from .storage import write_json


TEXT_MODEL_PREPARE_MANIFEST = "model_prepare_manifest.json"
TEXT_MODEL_ROLES = ("embedding", "classifier", "sentiment", "ner")
TEXT_MODEL_TASKS = {
    "classifier": "event_category_zero_shot",
    "embedding": "sentence_embedding",
    "ner": "open_entity_extraction",
    "sentiment": "financial_tone_classification",
}
TEXT_MODEL_ROLE_THRESHOLDS = {
    "classifier": ("classifier_accept_score", "classifier_top_margin"),
    "embedding": ("duplicate_similarity", "same_topic_similarity", "max_topic_window_hours"),
    "ner": ("entity_accept_score",),
    "sentiment": (),
}


@dataclass(frozen=True)
class TextModelPreparationResult:
    manifest_path: Path
    status: str
    exit_code: int
    manifest: dict[str, Any]

    @property
    def succeeded(self) -> bool:
        return self.exit_code == 0


def prepare_text_models(
    config: dict[str, Any],
    *,
    config_path: Path | str | None = None,
    output_dir: Path | str | None = None,
    now: datetime | str | None = None,
) -> TextModelPreparationResult:
    text = _mapping(config.get("text"))
    intelligence = _mapping(text.get("intelligence"))
    created_at = _format_utc(now)
    target_dir = _resolve_output_dir(intelligence, config_path=config_path, output_dir=output_dir)
    manifest_path = target_dir / TEXT_MODEL_PREPARE_MANIFEST

    model_states = _prepare_model_states(intelligence, text_enabled=bool(text.get("enabled")), target_dir=target_dir)
    status = _manifest_status(model_states)
    warnings = _combined_messages(model_states, key="warnings")
    errors = _combined_messages(model_states, key="errors")
    manifest = {
        "schema_version": 1,
        "artifact_type": "text_model_prepare_manifest",
        "created_at": created_at,
        "status": status,
        "text_enabled": bool(text.get("enabled")),
        "text_intelligence_enabled": bool(intelligence.get("enabled")),
        "download_policy": {
            "allow_model_download": bool(intelligence.get("allow_model_download")),
        },
        "coverage": _coverage(model_states),
        "model_states": model_states,
        "warnings": warnings,
        "errors": errors,
    }
    write_json(manifest_path, manifest)
    return TextModelPreparationResult(
        manifest_path=manifest_path,
        status=status,
        exit_code=0 if status in {"succeeded", "skipped"} else 1,
        manifest=manifest,
    )


def _prepare_model_states(
    intelligence: dict[str, Any],
    *,
    text_enabled: bool,
    target_dir: Path,
) -> list[dict[str, Any]]:
    models = _mapping(intelligence.get("models"))
    thresholds = _mapping(intelligence.get("thresholds"))
    roles = [role for role in TEXT_MODEL_ROLES if isinstance(models.get(role), dict)]

    if not roles:
        return []

    if not text_enabled:
        return [
            _model_state(
                role,
                model=models[role],
                thresholds=thresholds,
                status="skipped",
                warnings=["text_disabled"],
            )
            for role in roles
        ]

    if not bool(intelligence.get("enabled")):
        return [
            _model_state(
                role,
                model=models[role],
                thresholds=thresholds,
                status="skipped",
                warnings=["text_intelligence_disabled"],
            )
            for role in roles
        ]

    if not bool(intelligence.get("allow_model_download")):
        return [
            _model_state(
                role,
                model=models[role],
                thresholds=thresholds,
                status="skipped",
                warnings=["model_download_disabled"],
            )
            for role in roles
        ]

    snapshot_download = _snapshot_download()
    if snapshot_download is None:
        error = 'optional NLP preparation dependency is missing; install with python -m pip install -e ".[nlp]"'
        return [
            _model_state(
                role,
                model=models[role],
                thresholds=thresholds,
                status="unavailable",
                errors=[error],
            )
            for role in roles
        ]

    states = []
    for role in roles:
        model = models[role]
        revision = str(model.get("revision") or "").strip()
        if revision == "pinned":
            states.append(
                _model_state(
                    role,
                    model=model,
                    thresholds=thresholds,
                    status="failed",
                    errors=[
                        (
                            f"text.intelligence.models.{role}.revision must be an explicit "
                            "Hugging Face revision before downloads are allowed."
                        )
                    ],
                )
            )
            continue

        try:
            snapshot_download(
                repo_id=str(model["name"]),
                revision=revision,
                cache_dir=str(target_dir),
            )
        except Exception as exc:  # pragma: no cover - exercised only with optional runtime/network.
            states.append(
                _model_state(
                    role,
                    model=model,
                    thresholds=thresholds,
                    status="failed",
                    errors=[f"{role} model preparation failed: {exc.__class__.__name__}: {exc}"],
                )
            )
            continue

        states.append(
            _model_state(
                role,
                model=model,
                thresholds=thresholds,
                status="succeeded",
            )
        )

    return states


def _snapshot_download() -> Callable[..., str] | None:
    try:
        from huggingface_hub import snapshot_download
    except ModuleNotFoundError:
        return None
    return snapshot_download


def _model_state(
    role: str,
    *,
    model: dict[str, Any],
    thresholds: dict[str, Any],
    status: str,
    warnings: list[str] | None = None,
    errors: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "role": role,
        "provider": str(model.get("provider") or SUPPORTED_TEXT_INTELLIGENCE_MODEL_PROVIDERS.get(role) or ""),
        "name": str(model.get("name") or ""),
        "revision": str(model.get("revision") or ""),
        "status": status,
        "task": TEXT_MODEL_TASKS[role],
        "thresholds": _role_thresholds(role, thresholds),
        "warnings": warnings or [],
        "errors": errors or [],
    }


def _role_thresholds(role: str, thresholds: dict[str, Any]) -> dict[str, Any]:
    return {key: thresholds[key] for key in TEXT_MODEL_ROLE_THRESHOLDS[role] if key in thresholds}


def _manifest_status(model_states: list[dict[str, Any]]) -> str:
    if not model_states:
        return "skipped"
    statuses = {str(state.get("status")) for state in model_states}
    if statuses == {"succeeded"}:
        return "succeeded"
    if statuses <= {"skipped"}:
        return "skipped"
    if statuses & {"failed", "unavailable"}:
        return "failed"
    return "degraded"


def _coverage(model_states: list[dict[str, Any]]) -> dict[str, int]:
    coverage = {
        "models": len(model_states),
        "succeeded": 0,
        "skipped": 0,
        "degraded": 0,
        "failed": 0,
        "unavailable": 0,
    }
    for state in model_states:
        status = str(state.get("status") or "")
        if status in coverage:
            coverage[status] += 1
    return coverage


def _combined_messages(model_states: list[dict[str, Any]], *, key: str) -> list[str]:
    messages = []
    for state in model_states:
        for message in state.get(key) or []:
            if message not in messages:
                messages.append(str(message))
    return messages


def _resolve_output_dir(
    intelligence: dict[str, Any],
    *,
    config_path: Path | str | None,
    output_dir: Path | str | None,
) -> Path:
    if output_dir is not None:
        return Path(output_dir)

    configured = Path(str(intelligence.get("model_cache_dir") or "data/models/text"))
    if configured.is_absolute():
        return configured

    base = Path(config_path).parent if config_path is not None else Path.cwd()
    return base / configured


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _format_utc(value: datetime | str | None) -> str:
    if value is None:
        return datetime.now(UTC).isoformat().replace("+00:00", "Z")
    if isinstance(value, str):
        return value
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
