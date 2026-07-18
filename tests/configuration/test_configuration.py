from __future__ import annotations

from pathlib import Path

import pytest

from halpha.configuration import (
    ConfigurationError,
    app_settings,
    executor_settings,
    load_settings,
    settings_digest,
)


ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "config" / "halpha.example.toml"


def test_explicit_toml_loads_with_stable_digest() -> None:
    first = load_settings(EXAMPLE)
    second = load_settings(EXAMPLE)
    assert first.release.profile == "BINANCE_DEMO"
    assert first.release.authority_class == "DEMO_VALIDATION"
    assert settings_digest(first) == settings_digest(second)


def test_environment_variables_are_not_a_settings_source(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HALPHA_RELEASE__PROFILE", "BINANCE_LIVE_WRITE")
    settings = load_settings(EXAMPLE)
    assert settings.release.profile == "BINANCE_DEMO"


def test_process_views_do_not_cross_secret_reference_boundaries() -> None:
    settings = load_settings(EXAMPLE)
    app_view = app_settings(settings).model_dump(mode="json")
    executor_view = executor_settings(settings).model_dump(mode="json")
    assert "binance_api_key_reference" not in app_view["app"]
    assert "binance_api_secret_reference" not in app_view["app"]
    assert "owner_password_hash_reference" not in executor_view["executor"]
    assert "session_signing_reference" not in executor_view["executor"]
    assert "csrf_signing_reference" not in executor_view["executor"]
    assert "smtp_credential_reference" not in executor_view["executor"]


def test_runtime_proxy_is_an_optional_executor_only_reference() -> None:
    settings = load_settings(EXAMPLE)
    assert settings.executor.runtime_proxy_reference is None
    executor = settings.executor.model_dump(mode="json")
    executor["runtime_proxy_reference"] = {
        "service": "Halpha/Network/BINANCE_DEMO",
        "account": "runtime_proxy",
    }
    configured = load_settings(EXAMPLE, constructor_values={"executor": executor})
    assert configured.executor.runtime_proxy_reference is not None
    assert configured.executor.runtime_proxy_reference.account == "runtime_proxy"


def test_maintenance_targets_are_fixed_and_paths_are_repository_relative() -> None:
    settings = load_settings(EXAMPLE)
    assert settings.maintenance.demo.database_name == "halpha_demo"
    assert settings.maintenance.live.database_name == "halpha_live"
    assert settings.maintenance.backup_retention_count == 14
    maintenance = settings.maintenance.model_dump(mode="json")
    maintenance["backup_root"] = "../outside"
    with pytest.raises(ConfigurationError, match="CONFIGURATION_INVALID"):
        load_settings(EXAMPLE, constructor_values={"maintenance": maintenance})


def test_email_delivery_is_disabled_until_complete_nonsecret_route_exists() -> None:
    settings = load_settings(EXAMPLE)
    assert settings.email.delivery_enabled is False
    email = settings.email.model_dump(mode="json")
    email["delivery_enabled"] = True
    with pytest.raises(ConfigurationError, match="CONFIGURATION_INVALID"):
        load_settings(EXAMPLE, constructor_values={"email": email})


def test_live_profile_cannot_reuse_demo_credential_reference() -> None:
    settings = load_settings(EXAMPLE)
    release = settings.release.model_dump(mode="json")
    release.update(
        profile="BINANCE_LIVE_WRITE",
        authority_class="LIVE_REAL_CAPITAL",
        database_name="halpha_live",
    )
    with pytest.raises(ConfigurationError, match="CONFIGURATION_INVALID"):
        load_settings(EXAMPLE, constructor_values={"release": release})


def test_live_read_only_requires_binance_credentials_to_be_absent() -> None:
    settings = load_settings(EXAMPLE)
    release = settings.release.model_dump(mode="json")
    release.update(
        profile="BINANCE_LIVE_READ_ONLY",
        authority_class="NO_TRADING_AUTHORITY",
        database_name="halpha_live",
    )
    with pytest.raises(ConfigurationError, match="CONFIGURATION_INVALID"):
        load_settings(EXAMPLE, constructor_values={"release": release})

    read_only = load_settings(ROOT / "config" / "halpha.live-read-only.example.toml")
    assert read_only.executor.binance_api_key_reference is None
    assert read_only.executor.binance_api_secret_reference is None
    assert read_only.release.authority_class == "NO_TRADING_AUTHORITY"


def test_app_and_executor_credential_references_must_not_overlap() -> None:
    settings = load_settings(EXAMPLE)
    executor = settings.executor.model_dump(mode="json")
    executor["database_credential_reference"] = settings.app.database_credential_reference.model_dump(
        mode="json"
    )
    with pytest.raises(ConfigurationError, match="CONFIGURATION_INVALID"):
        load_settings(EXAMPLE, constructor_values={"executor": executor})


def test_secret_value_key_is_rejected_without_echoing_value(tmp_path: Path) -> None:
    secret = "must-never-appear-in-error"
    path = tmp_path / "bad.toml"
    path.write_text(EXAMPLE.read_text(encoding="utf-8") + f'\napi_secret = "{secret}"\n', encoding="utf-8")
    with pytest.raises(ConfigurationError) as captured:
        load_settings(path)
    assert "SECRET_VALUE_KEY_FORBIDDEN" in str(captured.value)
    assert secret not in str(captured.value)


def test_same_windows_sid_for_multiple_roles_is_rejected() -> None:
    settings = load_settings(EXAMPLE)
    windows = settings.windows.model_dump(mode="json")
    windows["executor_task_sid"] = windows["app_task_sid"]
    with pytest.raises(ConfigurationError, match="CONFIGURATION_INVALID"):
        load_settings(EXAMPLE, constructor_values={"windows": windows})
