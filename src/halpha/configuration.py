"""Explicit TOML-only non-secret runtime configuration."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict, TomlConfigSettingsSource


class ConfigurationError(RuntimeError):
    """A sanitized, fail-closed configuration error."""


_SID_PATTERN = re.compile(r"^S-1-(?:\d+-)+\d+$")
_IDENTITY_PATTERN = r"^[a-z0-9][a-z0-9._-]{2,95}$"
_FORBIDDEN_VALUE_KEYS = {
    "api_key",
    "api_secret",
    "authorization",
    "cookie",
    "credential_value",
    "database_url",
    "dsn",
    "password",
    "password_hash",
    "private_key",
    "secret",
    "session_secret",
    "token",
}


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class WinVaultReference(FrozenModel):
    service: str = Field(min_length=3, max_length=160)
    account: str = Field(min_length=2, max_length=96)


class ReleaseConfig(FrozenModel):
    environment_id: str = Field(pattern=_IDENTITY_PATTERN)
    account_id: str = Field(pattern=_IDENTITY_PATTERN)
    profile: Literal["BINANCE_DEMO", "BINANCE_LIVE_READ_ONLY", "BINANCE_LIVE_WRITE"]
    authority_class: Literal[
        "DEMO_VALIDATION",
        "LIVE_REAL_CAPITAL",
        "NO_TRADING_AUTHORITY",
    ]
    database_name: str = Field(pattern=r"^halpha_(?:demo|live)$")
    live_write_gate_path: str | None = None

    @model_validator(mode="after")
    def validate_live_write_gate_path(self) -> "ReleaseConfig":
        path_value = self.live_write_gate_path
        if self.profile == "BINANCE_LIVE_WRITE":
            if path_value is None:
                raise ValueError("LIVE_WRITE_GATE_PATH_REQUIRED")
            path = Path(path_value)
            if not path.is_absolute() or path.suffix.lower() != ".json" or ".." in path.parts:
                raise ValueError("LIVE_WRITE_GATE_PATH_INVALID")
        elif path_value is not None:
            raise ValueError("LIVE_WRITE_GATE_PATH_PROFILE_MISMATCH")
        return self


class AppConfig(FrozenModel):
    bind: Literal["127.0.0.1"] = "127.0.0.1"
    port: int = Field(default=8765, ge=1024, le=65535)
    workers: Literal[1] = 1
    reload: Literal[False] = False
    database_credential_reference: WinVaultReference
    csrf_signing_reference: WinVaultReference
    smtp_credential_reference: WinVaultReference


class ExecutorConfig(FrozenModel):
    database_credential_reference: WinVaultReference
    binance_api_key_reference: WinVaultReference | None = None
    binance_api_secret_reference: WinVaultReference | None = None
    runtime_proxy_reference: WinVaultReference | None = None
    mutex_name: Literal[r"Global\Halpha.Executor.WriteOwner"] = (
        r"Global\Halpha.Executor.WriteOwner"
    )


class DatabaseMaintenanceTarget(FrozenModel):
    environment_kind: Literal["DEMO", "LIVE"]
    database_name: str = Field(pattern=r"^halpha_(?:demo|live)$")
    backup_role_name: str = Field(pattern=r"^halpha_(?:demo|live)_backup$")
    migration_role_name: str = Field(pattern=r"^halpha_(?:demo|live)_migration$")
    backup_credential_reference: WinVaultReference
    migration_credential_reference: WinVaultReference


class MaintenanceConfig(FrozenModel):
    postgresql_bin_directory: str = Field(min_length=3, max_length=260)
    log_root: str = Field(min_length=3, max_length=200)
    backup_root: str = Field(min_length=3, max_length=200)
    temporary_root: str = Field(min_length=3, max_length=200)
    evidence_catalog_root: str = Field(min_length=3, max_length=200)
    evidence_raw_root: str = Field(min_length=3, max_length=200)
    evidence_report_root: str = Field(min_length=3, max_length=200)
    backup_retention_count: Literal[14] = 14
    backup_schedule_local: Literal["02:30"] = "02:30"
    demo: DatabaseMaintenanceTarget
    live: DatabaseMaintenanceTarget

    @model_validator(mode="after")
    def validate_targets_and_paths(self) -> "MaintenanceConfig":
        expected = {
            "demo": ("DEMO", "halpha_demo"),
            "live": ("LIVE", "halpha_live"),
        }
        for name, target in (("demo", self.demo), ("live", self.live)):
            kind, database = expected[name]
            if target.environment_kind != kind or target.database_name != database:
                raise ValueError("MAINTENANCE_DATABASE_TARGET_MISMATCH")
            if target.backup_role_name != f"{database}_backup":
                raise ValueError("MAINTENANCE_BACKUP_ROLE_MISMATCH")
            if target.migration_role_name != f"{database}_migration":
                raise ValueError("MAINTENANCE_MIGRATION_ROLE_MISMATCH")
            if target.backup_credential_reference == target.migration_credential_reference:
                raise ValueError("MAINTENANCE_CREDENTIAL_REFERENCE_OVERLAP")
        relative_paths = (
            self.log_root,
            self.backup_root,
            self.temporary_root,
            self.evidence_catalog_root,
            self.evidence_raw_root,
            self.evidence_report_root,
        )
        for value in relative_paths:
            path = Path(value)
            if path.is_absolute() or ".." in path.parts or "\\" in value:
                raise ValueError("MAINTENANCE_RELATIVE_PATH_INVALID")
        if len(set(relative_paths)) != len(relative_paths):
            raise ValueError("MAINTENANCE_RUNTIME_PATHS_MUST_BE_DISTINCT")
        return self


class EmailConfig(FrozenModel):
    delivery_enabled: bool = False
    smtp_host: str | None = Field(default=None, min_length=3, max_length=253)
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str | None = Field(default=None, min_length=1, max_length=320)
    sender: str | None = Field(default=None, min_length=3, max_length=320)
    owner_recipient: str | None = Field(default=None, min_length=3, max_length=320)
    require_starttls: Literal[True] = True
    timeout_seconds: int = Field(default=10, ge=1, le=60)

    @model_validator(mode="after")
    def validate_enabled_route(self) -> "EmailConfig":
        configured = (
            self.smtp_host,
            self.smtp_username,
            self.sender,
            self.owner_recipient,
        )
        if self.delivery_enabled and any(value is None for value in configured):
            raise ValueError("EMAIL_DELIVERY_CONFIGURATION_INCOMPLETE")
        for value in (self.sender, self.owner_recipient):
            if value is not None and ("\r" in value or "\n" in value or "@" not in value):
                raise ValueError("EMAIL_ADDRESS_INVALID")
        return self


class WindowsIdentityConfig(FrozenModel):
    app_task_sid: str
    executor_task_sid: str
    maintenance_sid: str
    app_stop_event: Literal[r"Global\Halpha.App.Stop"] = r"Global\Halpha.App.Stop"
    executor_stop_event: Literal[r"Global\Halpha.Executor.Stop"] = (
        r"Global\Halpha.Executor.Stop"
    )

    @model_validator(mode="after")
    def validate_distinct_sids(self) -> "WindowsIdentityConfig":
        sids = (self.app_task_sid, self.executor_task_sid, self.maintenance_sid)
        if any(_SID_PATTERN.fullmatch(sid) is None for sid in sids):
            raise ValueError("WINDOWS_SID_INVALID")
        if len(set(sids)) != len(sids):
            raise ValueError("WINDOWS_RUNTIME_SIDS_MUST_BE_DISTINCT")
        return self


class HalphaSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1]
    release: ReleaseConfig
    app: AppConfig
    executor: ExecutorConfig
    maintenance: MaintenanceConfig
    email: EmailConfig
    windows: WindowsIdentityConfig

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: Any,
        env_settings: Any,
        dotenv_settings: Any,
        file_secret_settings: Any,
    ) -> tuple[Any, ...]:
        # Direct tests may use explicit values only. The public loader below
        # adds exactly one explicit TomlConfigSettingsSource.
        return (init_settings,)

    @model_validator(mode="after")
    def validate_environment_and_secret_separation(self) -> "HalphaSettings":
        release = self.release
        if release.profile == "BINANCE_DEMO":
            if release.authority_class != "DEMO_VALIDATION":
                raise ValueError("DEMO_AUTHORITY_CLASS_MISMATCH")
            if release.database_name != "halpha_demo":
                raise ValueError("DEMO_DATABASE_MISMATCH")
            if (
                self.executor.binance_api_key_reference is None
                or self.executor.binance_api_key_reference.service
                != "Halpha/Binance/BINANCE_DEMO"
            ):
                raise ValueError("DEMO_BINANCE_REFERENCE_MISMATCH")
        elif release.profile == "BINANCE_LIVE_WRITE":
            if release.authority_class != "LIVE_REAL_CAPITAL":
                raise ValueError("LIVE_AUTHORITY_CLASS_MISMATCH")
            if release.database_name != "halpha_live":
                raise ValueError("LIVE_DATABASE_MISMATCH")
            if self.executor.binance_api_key_reference is None:
                raise ValueError("LIVE_WRITE_BINANCE_REFERENCE_REQUIRED")
            if "DEMO" in self.executor.binance_api_key_reference.service.upper():
                raise ValueError("LIVE_PROFILE_REFERENCES_DEMO_CREDENTIAL")
        else:
            if release.authority_class != "NO_TRADING_AUTHORITY":
                raise ValueError("LIVE_READ_ONLY_AUTHORITY_CLASS_MISMATCH")
            if release.database_name != "halpha_live":
                raise ValueError("LIVE_DATABASE_MISMATCH")
            if (
                self.executor.binance_api_key_reference is not None
                or self.executor.binance_api_secret_reference is not None
            ):
                raise ValueError("LIVE_READ_ONLY_BINANCE_CREDENTIAL_FORBIDDEN")

        key_ref = self.executor.binance_api_key_reference
        secret_ref = self.executor.binance_api_secret_reference
        if (key_ref is None) != (secret_ref is None):
            raise ValueError("BINANCE_REFERENCE_PAIR_INCOMPLETE")
        if key_ref is not None and secret_ref is not None:
            if key_ref.service != secret_ref.service or key_ref.account == secret_ref.account:
                raise ValueError("BINANCE_REFERENCE_PAIR_INVALID")

        app_references = {
            self.app.database_credential_reference,
            self.app.csrf_signing_reference,
            self.app.smtp_credential_reference,
            self.maintenance.demo.backup_credential_reference,
            self.maintenance.demo.migration_credential_reference,
            self.maintenance.live.backup_credential_reference,
            self.maintenance.live.migration_credential_reference,
        }
        executor_references = {self.executor.database_credential_reference}
        executor_references.update(
            reference for reference in (key_ref, secret_ref) if reference is not None
        )
        if self.executor.runtime_proxy_reference is not None:
            executor_references.add(self.executor.runtime_proxy_reference)
        if app_references & executor_references:
            raise ValueError("APP_EXECUTOR_CREDENTIAL_REFERENCE_OVERLAP")
        return self


class AppSettingsView(FrozenModel):
    release: ReleaseConfig
    app: AppConfig
    email: EmailConfig
    app_task_sid: str
    maintenance_sid: str
    stop_event: str


class ExecutorSettingsView(FrozenModel):
    release: ReleaseConfig
    executor: ExecutorConfig
    executor_task_sid: str
    maintenance_sid: str
    stop_event: str


class MaintenanceSettingsView(FrozenModel):
    maintenance: MaintenanceConfig
    app_task_sid: str


def _reject_secret_value_keys(value: Any, path: tuple[str, ...] = ()) -> None:
    if isinstance(value, Mapping):
        for raw_key, child in value.items():
            key = str(raw_key).lower()
            if key in _FORBIDDEN_VALUE_KEYS:
                location = ".".join((*path, str(raw_key)))
                raise ConfigurationError(f"SECRET_VALUE_KEY_FORBIDDEN field={location}")
            _reject_secret_value_keys(child, (*path, str(raw_key)))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_secret_value_keys(child, (*path, str(index)))


def _sanitized_validation_error(exc: ValidationError) -> ConfigurationError:
    summaries = []
    for issue in exc.errors(include_input=False, include_url=False):
        location = ".".join(str(part) for part in issue.get("loc", ())) or "root"
        summaries.append(f"{location}:{issue.get('type', 'validation_error')}")
    return ConfigurationError("CONFIGURATION_INVALID " + ",".join(sorted(summaries)))


def load_settings(
    config_path: Path,
    *,
    constructor_values: Mapping[str, Any] | None = None,
) -> HalphaSettings:
    if config_path.is_symlink():
        raise ConfigurationError("CONFIGURATION_SYMLINK_FORBIDDEN")
    path = config_path.resolve()
    if not path.is_file():
        raise ConfigurationError("CONFIGURATION_FILE_MISSING")

    try:
        values = TomlConfigSettingsSource(HalphaSettings, toml_file=path)()
    except Exception as exc:
        raise ConfigurationError(f"CONFIGURATION_TOML_READ_FAILED type={type(exc).__name__}") from None
    _reject_secret_value_keys(values)
    if constructor_values:
        _reject_secret_value_keys(constructor_values)
        values.update(dict(constructor_values))
    try:
        return HalphaSettings.model_validate(values)
    except ValidationError as exc:
        raise _sanitized_validation_error(exc) from None


def settings_digest(settings: HalphaSettings) -> str:
    payload = json.dumps(
        settings.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return sha256(payload).hexdigest()


def app_settings(settings: HalphaSettings) -> AppSettingsView:
    return AppSettingsView(
        release=settings.release,
        app=settings.app,
        email=settings.email,
        app_task_sid=settings.windows.app_task_sid,
        maintenance_sid=settings.windows.maintenance_sid,
        stop_event=settings.windows.app_stop_event,
    )


def executor_settings(settings: HalphaSettings) -> ExecutorSettingsView:
    return ExecutorSettingsView(
        release=settings.release,
        executor=settings.executor,
        executor_task_sid=settings.windows.executor_task_sid,
        maintenance_sid=settings.windows.maintenance_sid,
        stop_event=settings.windows.executor_stop_event,
    )


def maintenance_settings(settings: HalphaSettings) -> MaintenanceSettingsView:
    return MaintenanceSettingsView(
        maintenance=settings.maintenance,
        app_task_sid=settings.windows.app_task_sid,
    )
