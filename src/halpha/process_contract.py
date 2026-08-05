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
            "binance_public_read_only",
        ),
        forbidden_capabilities=(
            "binance_credentials",
            "binance_private_connection",
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

_LIVE_READ_ONLY_EXECUTOR_CONTRACT = ProcessContract(
    role=ProcessRole.EXECUTOR,
    allowed_capabilities=(
        "binance_public_read_only",
        "nautilus_trading_node",
        "strategy_observation_adapter",
        "forward_observation_evidence",
    ),
    forbidden_capabilities=(
        "postgresql_executor_boundary",
        "binance_credentials",
        "binance_private_connection",
        "binance_credential_reference",
        "halpha_coordinator",
        "execution_client",
        "persisted_action_capability",
        "venue_write",
        "local_web_api",
        "csrf_signing_secret",
        "smtp_credentials",
        "web_server",
    ),
)

_LIVE_PRIVATE_READ_ONLY_EXECUTOR_CONTRACT = ProcessContract(
    role=ProcessRole.EXECUTOR,
    allowed_capabilities=(
        "postgresql_executor_boundary",
        "binance_credential_reference",
        "binance_private_read_only",
        "binance_public_read_only",
        "nautilus_trading_node",
        "account_snapshot_observer",
        "venue_fact_append",
    ),
    forbidden_capabilities=(
        "halpha_coordinator",
        "execution_client",
        "execution_action_repository",
        "persisted_action_capability",
        "venue_write",
        "local_web_api",
        "csrf_signing_secret",
        "smtp_credentials",
        "web_server",
    ),
)


def _process_contract_for(
    role: ProcessRole,
    settings: HalphaSettings | None,
) -> ProcessContract:
    if (
        role is ProcessRole.EXECUTOR
        and settings is not None
        and settings.release.profile == "BINANCE_LIVE_READ_ONLY"
    ):
        if settings.executor.binance_api_key_reference is not None:
            return _LIVE_PRIVATE_READ_ONLY_EXECUTOR_CONTRACT
        return _LIVE_READ_ONLY_EXECUTOR_CONTRACT
    return PROCESS_CONTRACTS[role]


def preflight(
    role: ProcessRole,
    settings: HalphaSettings | None = None,
) -> dict[str, object]:
    runtime = require_repository_runtime()
    process_contract = _process_contract_for(role, settings)
    report: dict[str, object] = {
        "status": "PREFLIGHT_OK",
        "runtime": asdict(runtime),
        "process_contract": {
            "role": process_contract.role.value,
            "allowed_capabilities": list(process_contract.allowed_capabilities),
            "forbidden_capabilities": list(process_contract.forbidden_capabilities),
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
        private_account_observation = bool(
            read_only
            and settings.executor.binance_api_key_reference is not None
        )
        report["effective_composition"] = {
            "profile": settings.release.profile,
            "trading_authority": "NONE" if read_only else "PROFILE_GATED",
            "data_client_required": True,
            "trading_node_required": True,
            "read_only_mode": (
                "PRIVATE_ACCOUNT_OBSERVATION"
                if private_account_observation
                else "PUBLIC_FORWARD_OBSERVATION"
                if read_only
                else "NOT_APPLICABLE"
            ),
            "binance_credentials_required": (
                private_account_observation or not read_only
            ),
            "execution_client_required": not read_only,
            "product_database_required": (
                private_account_observation or not read_only
            ),
            "account_snapshot_observer_required": private_account_observation,
            "venue_fact_append_required": private_account_observation,
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
