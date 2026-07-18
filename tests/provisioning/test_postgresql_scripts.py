from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
INSTALL = ROOT / "tools" / "provisioning" / "install_postgresql_17.ps1"
CONFIGURE = ROOT / "tools" / "provisioning" / "configure_postgresql_17.ps1"


def test_install_secret_never_enters_process_arguments() -> None:
    source = INSTALL.read_text(encoding="utf-8").lower()
    assert "--pwfile" in source
    assert "--superpassword" not in source
    assert "--servicepassword" not in source


def test_psql_uses_only_a_temporary_pgpass_reference() -> None:
    source = CONFIGURE.read_text(encoding="utf-8")
    assert "$env:PGPASSFILE = $passFile" in source
    assert "--no-password" in source
    assert "Remove-Item Env:PGPASSFILE" in source
    assert "Remove-Item -LiteralPath $passFile -Force" in source
    assert "PGPASSWORD" not in source
