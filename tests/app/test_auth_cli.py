from __future__ import annotations

from pathlib import Path

from pwdlib import PasswordHash

from halpha.app.auth_cli import set_owner_password
from halpha.configuration import app_settings, load_settings


ROOT = Path(__file__).resolve().parents[2]


class _MemoryVault:
    def __init__(self) -> None:
        self.values: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self.values.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.values[(service, username)] = password


WinVaultKeyring = type(
    "WinVaultKeyring",
    (_MemoryVault,),
    {"__module__": "keyring.backends.Windows"},
)


def test_offline_password_command_writes_only_configured_winvault_refs() -> None:
    backend = WinVaultKeyring()
    config = ROOT / "config" / "halpha.example.toml"
    report = set_owner_password(config, backend=backend, password="a strong local value")
    settings = app_settings(load_settings(config)).app

    assert report["status"] == "OWNER_WEB_SECRETS_PROVISIONED"
    assert len(backend.values) == 3
    stored_hash = backend.get_password(
        settings.owner_password_hash_reference.service,
        settings.owner_password_hash_reference.account,
    )
    assert stored_hash is not None
    assert PasswordHash.recommended().verify("a strong local value", stored_hash)
    session_secret = backend.get_password(
        settings.session_signing_reference.service,
        settings.session_signing_reference.account,
    )
    csrf_secret = backend.get_password(
        settings.csrf_signing_reference.service,
        settings.csrf_signing_reference.account,
    )
    assert session_secret and csrf_secret and session_secret != csrf_secret
    assert "a strong local value" not in str(report)
