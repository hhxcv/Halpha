"""BuildManifest generation tests kept outside pytest's ignored ``build`` path."""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
import subprocess

import pytest

from halpha.build_manifest import (
    ALLOWED_PROFILE_DIFFERENCES,
    ArtifactSpec,
    BuildManifestError,
    create_manifest,
    digest_path,
    manifest_sha256,
    verify_manifest,
)


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def _fixture_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "--quiet")
    _git(repo, "config", "user.email", "halpha-test@example.invalid")
    _git(repo, "config", "user.name", "Halpha Test")
    (repo / "artifact.txt").write_text("locked\n", encoding="utf-8")
    (repo / "source.py").write_text("VALUE = 1\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "--quiet", "-m", "fixture")
    return repo


def test_file_and_directory_digests_are_deterministic(tmp_path: Path) -> None:
    directory = tmp_path / "tree"
    directory.mkdir()
    (directory / "b.txt").write_text("b\n", encoding="utf-8")
    (directory / "a.txt").write_text("a\n", encoding="utf-8")
    first = digest_path(directory)
    second = digest_path(directory)
    assert first == second
    assert first[1] == 2


def test_manifest_records_incomplete_without_inventing_artifacts(tmp_path: Path) -> None:
    repo = _fixture_repo(tmp_path)
    manifest = create_manifest(
        repo,
        specs=(
            ArtifactSpec("present", "artifact.txt"),
            ArtifactSpec("missing", "missing.txt"),
        ),
        generated_at=datetime(2026, 7, 17, tzinfo=UTC),
    )
    assert manifest["completeness"] == {
        "status": "INCOMPLETE",
        "missing_required": ["missing"],
    }
    assert manifest["build_eligible"] is False
    assert manifest["capability_claim"] == "BUILD_IDENTITY_ONLY_NOT_REAL_WRITE_AUTHORIZATION"


def test_manifest_detects_source_and_artifact_drift(tmp_path: Path) -> None:
    repo = _fixture_repo(tmp_path)
    specs = (ArtifactSpec("artifact", "artifact.txt"),)
    manifest = create_manifest(
        repo,
        specs=specs,
        generated_at=datetime(2026, 7, 17, tzinfo=UTC),
    )
    assert manifest["build_eligible"] is True
    assert verify_manifest(repo, manifest, specs=specs) == []

    (repo / "artifact.txt").write_text("changed\n", encoding="utf-8")
    violations = verify_manifest(repo, manifest, specs=specs)
    assert "ARTIFACT_artifact_SHA256_DRIFT" in violations
    assert "SOURCE_SOURCE_TREE_SHA256_DRIFT" in violations


def test_manifest_recomputes_completeness_and_eligibility(tmp_path: Path) -> None:
    repo = _fixture_repo(tmp_path)
    specs = (ArtifactSpec("missing", "missing.txt"),)
    manifest = create_manifest(
        repo,
        specs=specs,
        generated_at=datetime(2026, 7, 17, tzinfo=UTC),
    )
    manifest["completeness"] = {"status": "COMPLETE", "missing_required": []}
    manifest["build_eligible"] = True
    violations = verify_manifest(repo, manifest, specs=specs)
    assert "COMPLETENESS_DRIFT" in violations
    assert "BUILD_ELIGIBILITY_DRIFT" in violations


def test_manifest_rejects_duplicate_and_extra_bindings(tmp_path: Path) -> None:
    repo = _fixture_repo(tmp_path)
    specs = (ArtifactSpec("artifact", "artifact.txt"),)
    manifest = create_manifest(
        repo,
        specs=specs,
        generated_at=datetime(2026, 7, 17, tzinfo=UTC),
    )
    manifest["artifacts"].append(dict(manifest["artifacts"][0]))
    violations = verify_manifest(repo, manifest, specs=specs)
    assert "ARTIFACT_BINDING_NAME_DUPLICATE" in violations

    manifest["artifacts"].append(
        {
            "name": "unexpected",
            "path": "unexpected",
            "required": False,
            "status": "MISSING",
            "sha256": None,
            "file_count": 0,
        }
    )
    assert "ARTIFACT_BINDING_SET_DRIFT" in verify_manifest(repo, manifest, specs=specs)


def test_artifact_path_cannot_escape_repository(tmp_path: Path) -> None:
    repo = _fixture_repo(tmp_path)
    with pytest.raises(BuildManifestError, match="ARTIFACT_PATH_OUTSIDE_REPOSITORY"):
        create_manifest(
            repo,
            specs=(ArtifactSpec("outside", "../outside.txt"),),
            generated_at=datetime(2026, 7, 17, tzinfo=UTC),
        )


def test_manifest_digest_uses_canonical_json(tmp_path: Path) -> None:
    repo = _fixture_repo(tmp_path)
    manifest = create_manifest(
        repo,
        specs=(ArtifactSpec("artifact", "artifact.txt"),),
        generated_at=datetime(2026, 7, 17, tzinfo=UTC),
    )
    reordered = json.loads(json.dumps(manifest, sort_keys=False))
    assert manifest_sha256(manifest) == manifest_sha256(reordered)


def test_profile_difference_allowlist_is_exact_and_sorted() -> None:
    assert ALLOWED_PROFILE_DIFFERENCES == tuple(sorted(ALLOWED_PROFILE_DIFFERENCES))
    assert set(ALLOWED_PROFILE_DIFFERENCES) == {
        "account_id",
        "authority_class",
        "credential_reference",
        "database_connection_reference",
        "environment_id",
        "profile",
        "venue_endpoint",
        "venue_environment_configuration",
    }
