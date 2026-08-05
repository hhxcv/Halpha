from __future__ import annotations

from pathlib import Path

import pytest

from halpha.source_identity import (
    SourceIdentityError,
    require_source_sha256,
    source_file_sha256,
    source_sha256_digest,
    validate_source_sha256,
)
from tools.qualification.source_binding import (
    SourceBindingError,
    capture_source_sha256,
)


def test_source_binding_detects_content_and_file_set_changes(tmp_path: Path) -> None:
    source = tmp_path / "src"
    source.mkdir()
    first = source / "first.py"
    first.write_text("VALUE = 1\n", encoding="utf-8")
    before = capture_source_sha256(tmp_path, ("src/*.py",))

    first.write_text("VALUE = 2\n", encoding="utf-8")
    after_content_change = capture_source_sha256(tmp_path, ("src/*.py",))
    assert after_content_change != before

    (source / "second.py").write_text("VALUE = 3\n", encoding="utf-8")
    after_file_set_change = capture_source_sha256(tmp_path, ("src/*.py",))
    assert set(after_file_set_change) == {"src/first.py", "src/second.py"}


def test_source_identity_normalizes_text_line_endings_but_not_binary(
    tmp_path: Path,
) -> None:
    text_path = tmp_path / "source.py"
    text_path.write_bytes(b"VALUE = 1\nNEXT = 2\n")
    lf_digest = source_file_sha256(text_path)
    text_path.write_bytes(b"VALUE = 1\r\nNEXT = 2\r\n")
    assert source_file_sha256(text_path) == lf_digest

    text_path.write_bytes(b"VALUE = 3\r\nNEXT = 2\r\n")
    assert source_file_sha256(text_path) != lf_digest

    binary_path = tmp_path / "artifact.bin"
    binary_path.write_bytes(b"\x00\r\n\xff")
    binary_crlf_digest = source_file_sha256(binary_path)
    binary_path.write_bytes(b"\x00\n\xff")
    assert source_file_sha256(binary_path) != binary_crlf_digest


@pytest.mark.parametrize(
    "pattern",
    ("", "../outside.py", r"src\\*.py"),
)
def test_source_binding_rejects_unsafe_patterns(
    tmp_path: Path,
    pattern: str,
) -> None:
    with pytest.raises(SourceBindingError, match="SOURCE_BINDING_PATTERN_UNSAFE"):
        capture_source_sha256(tmp_path, (pattern,))


@pytest.mark.parametrize("pattern", ("missing/*.py", "empty-directory"))
def test_source_binding_rejects_a_pattern_without_files(
    tmp_path: Path,
    pattern: str,
) -> None:
    (tmp_path / "empty-directory").mkdir()
    with pytest.raises(SourceBindingError, match="SOURCE_BINDING_PATTERN_EMPTY"):
        capture_source_sha256(tmp_path, (pattern,))


def test_frozen_source_identity_rejects_content_and_file_set_drift(
    tmp_path: Path,
) -> None:
    source = tmp_path / "src"
    source.mkdir()
    first = source / "first.py"
    first.write_text("VALUE = 1\n", encoding="utf-8")
    patterns = ("src/*.py",)
    frozen = capture_source_sha256(tmp_path, patterns)

    assert require_source_sha256(
        tmp_path,
        patterns=patterns,
        expected=frozen,
    ) == frozen
    assert source_sha256_digest(frozen) == source_sha256_digest(
        dict(reversed(tuple(frozen.items())))
    )

    first.write_text("VALUE = 2\n", encoding="utf-8")
    with pytest.raises(SourceIdentityError, match="SOURCE_IDENTITY_DRIFT"):
        require_source_sha256(tmp_path, patterns=patterns, expected=frozen)

    first.write_text("VALUE = 1\n", encoding="utf-8")
    (source / "second.py").write_text("VALUE = 3\n", encoding="utf-8")
    with pytest.raises(SourceIdentityError, match="SOURCE_IDENTITY_DRIFT"):
        require_source_sha256(tmp_path, patterns=patterns, expected=frozen)


def test_source_identity_manifest_rejects_unsafe_path_and_digest() -> None:
    with pytest.raises(SourceIdentityError, match="SOURCE_IDENTITY_PATH_UNSAFE"):
        validate_source_sha256({"../outside.py": "1" * 64})
    with pytest.raises(SourceIdentityError, match="SOURCE_IDENTITY_PATH_UNSAFE"):
        validate_source_sha256({"src/*.py": "1" * 64})
    with pytest.raises(SourceIdentityError, match="SOURCE_IDENTITY_DIGEST_INVALID"):
        validate_source_sha256({"src/example.py": "not-a-digest"})
