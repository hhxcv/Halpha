"""Two-process capability declarations used by composition roots and checks."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum

from halpha.configuration import (
    HalphaSettings,
    app_settings,
    executor_settings,
    settings_digest,
)
from halpha.runtime_identity import require_repository_runtime


class ProcessRole(StrEnum):
    APP = "halpha-app"
    EXECUTOR = "halpha-executor"


@dataclass(frozen=True)
class ProcessContract:
    role: ProcessRole
    allowed_capabilities: tuple[str, ...]
    forbidden_capabilities: tuple[str, ...]


PROCESS_CONTRACTS = {
    ProcessRole.APP: ProcessContract(
        role=ProcessRole.APP,
        allowed_capabilities=(
            "postgresql_app_boundary",
            "local_web_api",
            "local_origin_and_csrf",
        ),
        forbidden_capabilities=(
            "binance_credentials",
            "binance_connection",
            "nautilus_trading_node",
            "venue_write",
        ),
    ),
    ProcessRole.EXECUTOR: ProcessContract(
        role=ProcessRole.EXECUTOR,
        allowed_capabilities=(
            "postgresql_executor_boundary",
            "binance_credential_reference",
            "nautilus_trading_node",
            "halpha_coordinator",
        ),
        forbidden_capabilities=(
            "local_web_api",
            "csrf_signing_secret",
            "smtp_credentials",
            "web_server",
        ),
    ),
}


def preflight(
    role: ProcessRole,
    settings: HalphaSettings | None = None,
) -> dict[str, object]:
    runtime = require_repository_runtime()
    report: dict[str, object] = {
        "status": "PREFLIGHT_OK",
        "runtime": asdict(runtime),
        "process_contract": {
            "role": PROCESS_CONTRACTS[role].role.value,
            "allowed_capabilities": list(PROCESS_CONTRACTS[role].allowed_capabilities),
            "forbidden_capabilities": list(PROCESS_CONTRACTS[role].forbidden_capabilities),
        },
        "external_connections_started": False,
        "product_runtime_started": False,
        "runtime_real_write_gate": "CLOSED",
    }
    if settings is None:
        report["configuration"] = {"validated": False}
        return report

    role_view = app_settings(settings) if role is ProcessRole.APP else executor_settings(settings)
    report["configuration"] = {
        "validated": True,
        "schema_version": settings.schema_version,
        "environment_id": settings.release.environment_id,
        "account_id": settings.release.account_id,
        "profile": settings.release.profile,
        "authority_class": settings.release.authority_class,
        "database_name": settings.release.database_name,
        "settings_digest": settings_digest(settings),
        "role_view_digest": settings_digest_for_view(role_view.model_dump(mode="json")),
    }
    if role is ProcessRole.EXECUTOR:
        read_only = settings.release.profile == "BINANCE_LIVE_READ_ONLY"
        report["effective_composition"] = {
            "profile": settings.release.profile,
            "trading_authority": "NONE" if read_only else "PROFILE_GATED",
            "data_client_required": True,
            "trading_node_required": True,
            "binance_credentials_required": not read_only,
            "execution_client_required": not read_only,
            "product_database_required": not read_only,
            "halpha_coordinator_required": not read_only,
            "execution_action_repository_required": not read_only,
            "persisted_action_capability_required": not read_only,
            "venue_write_capability": "STRUCTURALLY_ABSENT" if read_only else "GATED",
        }
    return report


def settings_digest_for_view(values: dict[str, object]) -> str:
    """Hash a role projection without returning its credential references."""
    from hashlib import sha256
    import json

    payload = json.dumps(
        values,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return sha256(payload).hexdigest()
