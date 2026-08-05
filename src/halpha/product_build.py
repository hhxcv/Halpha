"""Deterministic identity for the inputs loaded by one Halpha product runtime."""

from __future__ import annotations

from pathlib import Path

from halpha.configuration import HalphaSettings
from halpha.domain_values import content_digest
from halpha.source_identity import capture_stable_source_sha256


PRODUCT_BUILD_INPUT_PATTERNS = (
    "pyproject.toml",
    "requirements/runtime.txt",
    "frontend/package-lock.json",
    "src/halpha/**/*.py",
    "src/halpha/**/*.json",
    "migrations/**/*.py",
    "frontend/dist/**/*",
)

EXECUTOR_STARTING_APPLICATION_NAME = "halpha-executor:starting"
EXECUTOR_READY_APPLICATION_NAME_PREFIX = "halpha-executor:ready:"


def executor_ready_application_name(product_build_id: str) -> str:
    """Return the bounded PostgreSQL session label for one ready Executor."""

    normalized = product_build_id.strip().lower()
    if len(normalized) != 64 or any(
        character not in "0123456789abcdef" for character in normalized
    ):
        raise ValueError("PRODUCT_BUILD_ID_INVALID")
    return f"{EXECUTOR_READY_APPLICATION_NAME_PREFIX}{normalized[:40]}"


def calculate_product_build_id(root: Path, settings: HalphaSettings) -> str:
    """Hash product files and effective non-secret configuration only."""

    files = capture_stable_source_sha256(root.resolve(), PRODUCT_BUILD_INPUT_PATTERNS)
    return content_digest(
        {
            "files": files,
            "configuration": settings.model_dump(mode="json"),
        }
    )
