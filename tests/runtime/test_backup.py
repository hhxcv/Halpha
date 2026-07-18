from __future__ import annotations

from pathlib import Path

import pytest

from halpha.backup import (
    BackupError,
    _apply_retention,
    _escape_pgpass,
    _repository_path,
)


def test_pgpass_escaping_handles_separator_and_backslash() -> None:
    assert _escape_pgpass(r"a:b\c") == r"a\:b\\c"


def test_repository_paths_cannot_escape_root(tmp_path: Path) -> None:
    assert _repository_path(tmp_path, "backups/postgresql") == (
        tmp_path / "backups" / "postgresql"
    ).resolve()
    with pytest.raises(BackupError, match="OUTSIDE_REPOSITORY"):
        _repository_path(tmp_path, "../outside")


def test_retention_keeps_latest_fourteen_archives_and_manifests(tmp_path: Path) -> None:
    for day in range(16):
        archive = tmp_path / f"halpha_demo-202607{day + 1:02d}T000000Z.dump"
        archive.write_bytes(b"backup")
        archive.with_suffix(".json").write_text("{}", encoding="utf-8")
    removed = _apply_retention(tmp_path, 14)
    assert removed == [
        "halpha_demo-20260702T000000Z.dump",
        "halpha_demo-20260701T000000Z.dump",
    ]
    assert len(list(tmp_path.glob("*.dump"))) == 14
    assert len(list(tmp_path.glob("*.json"))) == 14


def test_backup_source_has_no_password_argument_or_environment_transport() -> None:
    source = (Path(__file__).resolve().parents[2] / "src" / "halpha" / "backup.py").read_text(
        encoding="utf-8"
    )
    assert "PGPASSWORD" not in source
    assert "--password" not in source
    assert "FILE_FLAG_DELETE_ON_CLOSE" in source
