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


def calculate_product_build_id(root: Path, settings: HalphaSettings) -> str:
    """Hash product files and effective non-secret configuration only."""

    files = capture_stable_source_sha256(root.resolve(), PRODUCT_BUILD_INPUT_PATTERNS)
    return content_digest(
        {
            "files": files,
            "configuration": settings.model_dump(mode="json"),
        }
    )
