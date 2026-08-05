"""Resolve the App process's role-scoped WinVault inputs."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import SecretStr

from halpha.configuration import AppSettingsView
from halpha.winvault import KeyringBackend, app_secret_resolver


@dataclass(frozen=True, repr=False)
class AppSecrets:
    database_password: SecretStr
    csrf_signing_secret: SecretStr
    smtp_password: SecretStr | None = None


def resolve_app_secrets(
    settings: AppSettingsView,
    backend: KeyringBackend,
) -> AppSecrets:
    resolver = app_secret_resolver(backend, settings)
    app = settings.app
    return AppSecrets(
        database_password=resolver.resolve(app.database_credential_reference),
        csrf_signing_secret=resolver.resolve(app.csrf_signing_reference),
        smtp_password=(
            resolver.resolve(app.smtp_credential_reference)
            if settings.email.delivery_enabled
            else None
        ),
    )
