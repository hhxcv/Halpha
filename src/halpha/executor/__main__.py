"""Entry point for the Executor process role."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
import os
from pathlib import Path
from typing import Sequence

import keyring
import psycopg

from halpha.configuration import (
    ConfigurationError,
    executor_settings,
    load_settings,
    settings_digest,
)
from halpha.executor.continuity import (
    ExecutorContinuityUnavailable,
    PostgreSQLExecutorContinuityGuard,
)
from halpha.executor.forward_observation import (
    ForwardObservationError,
    ForwardObservationEvidence,
    load_forward_observation_spec,
    require_forward_observation_source_identity,
)
from halpha.executor.runtime import (
    ExecutorRuntimeError,
    ProductExecutorRuntime,
    _connect_product_database,
)
from halpha.live_write_gate import (
    LiveWriteGateError,
    evaluate_live_write_gate,
    require_live_write_gate_open,
    require_live_write_gate_precheck,
)
from halpha.operational_logging import configure_halpha_logging
from halpha.process_contract import ProcessRole, preflight
from halpha.runtime_identity import RuntimeIdentityError, repository_root
from halpha.source_identity import (
    SourceIdentityError,
    capture_product_runtime_source_identity,
    source_sha256_digest,
)
from halpha.winvault import SecretResolutionError, executor_secret_resolver
from halpha.windows_runtime import (
    WindowsRuntimeError,
    acquire_executor_mutex,
    create_stop_event,
    require_process_identity,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog=ProcessRole.EXECUTOR.value)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--forward-observation-spec", type=Path)
    parser.add_argument("--forward-observation-evidence", type=Path)
    args = parser.parse_args(argv)
    try:
        settings = load_settings(args.config)
        repo_root = repository_root()
        report = preflight(ProcessRole.EXECUTOR, settings)
        if args.preflight_only:
            gate_status = evaluate_live_write_gate(repo_root, settings)
            report.update(
                {
                    "live_write_build_capability": gate_status.live_write_build_capability,
                    "b05_package_eligibility": gate_status.b05_package_eligibility,
                    "configured_runtime_real_write_gate": (
                        gate_status.configured_runtime_real_write_gate
                    ),
                    "runtime_real_write_gate": gate_status.runtime_real_write_gate,
                    "live_write_gate_violations": list(gate_status.violations),
                }
            )
            print(json.dumps(report, sort_keys=True))
            return 0
        role_settings = executor_settings(settings)
        runtime_source_sha256 = capture_product_runtime_source_identity(
            repo_root,
            config_path=args.config,
        )
        runtime_source_digest = source_sha256_digest(runtime_source_sha256)
        read_only = settings.release.profile == "BINANCE_LIVE_READ_ONLY"
        observation = None
        observation_spec = None
        if read_only:
            if (
                args.forward_observation_spec is None
                or args.forward_observation_evidence is None
            ):
                raise ExecutorRuntimeError("READ_ONLY_OBSERVATION_ARGUMENTS_REQUIRED")
            evidence_root = (
                repo_root / "build" / "evidence" / "reports"
            ).resolve()
            spec_path = args.forward_observation_spec.resolve()
            evidence_path = args.forward_observation_evidence.resolve()
            try:
                spec_path.relative_to(evidence_root)
                evidence_path.relative_to(evidence_root)
            except ValueError:
                raise ExecutorRuntimeError(
                    "READ_ONLY_OBSERVATION_PATH_OUTSIDE_EVIDENCE_ROOT"
                ) from None
            if evidence_path.suffix.lower() != ".jsonl":
                raise ExecutorRuntimeError("READ_ONLY_OBSERVATION_EVIDENCE_FORMAT_INVALID")
            observation_spec = load_forward_observation_spec(spec_path)
            if observation_spec.configuration_digest != settings_digest(settings):
                raise ExecutorRuntimeError("READ_ONLY_OBSERVATION_CONFIGURATION_DRIFT")
            require_forward_observation_source_identity(
                repo_root,
                observation_spec,
            )
            observation = ForwardObservationEvidence(observation_spec, evidence_path)
        elif (
            args.forward_observation_spec is not None
            or args.forward_observation_evidence is not None
        ):
            raise ExecutorRuntimeError("FORWARD_OBSERVATION_ARGUMENTS_PROFILE_MISMATCH")
        require_process_identity(role_settings.executor_task_sid)
        live_write = settings.release.profile == "BINANCE_LIVE_WRITE"
        gate_status = (
            require_live_write_gate_precheck(repo_root, settings)
            if live_write
            else evaluate_live_write_gate(repo_root, settings)
        )
        with acquire_executor_mutex(
            name=role_settings.executor.mutex_name,
            task_sid=role_settings.executor_task_sid,
        ), create_stop_event(
            name=role_settings.stop_event,
            task_sid=role_settings.executor_task_sid,
            maintenance_sid=role_settings.maintenance_sid,
        ) as stop_event:
            resolver = executor_secret_resolver(keyring.get_keyring(), role_settings)
            database_password = (
                None
                if read_only
                else resolver.resolve(
                    role_settings.executor.database_credential_reference
                )
            )
            live_write_submission_guard = None
            if live_write:
                if database_password is None:
                    raise ExecutorRuntimeError("PRODUCT_DATABASE_CREDENTIAL_REQUIRED")
                gate_connection = _connect_product_database(
                    psycopg.connect,
                    database_name=settings.release.database_name,
                    password=database_password.get_secret_value(),
                )
                try:
                    gate_status = require_live_write_gate_open(
                        repo_root,
                        settings,
                        gate_connection,
                    )
                finally:
                    gate_connection.close()

                def live_write_submission_guard(activation_id: str) -> None:
                    current_connection = _connect_product_database(
                        psycopg.connect,
                        database_name=settings.release.database_name,
                        password=database_password.get_secret_value(),
                    )
                    try:
                        current_status = require_live_write_gate_open(
                            repo_root,
                            settings,
                            current_connection,
                        )
                    finally:
                        current_connection.close()
                    if current_status.authorized_activation_id != activation_id:
                        raise LiveWriteGateError(
                            "LIVE_WRITE_ACTIVATION_SCOPE_MISMATCH"
                        )
            if read_only:
                api_key = None
                api_secret = None
            else:
                key_reference = role_settings.executor.binance_api_key_reference
                secret_reference = role_settings.executor.binance_api_secret_reference
                if key_reference is None or secret_reference is None:
                    raise ExecutorRuntimeError("BINANCE_CREDENTIAL_REFERENCE_REQUIRED")
                api_key = resolver.resolve(key_reference)
                api_secret = resolver.resolve(secret_reference)
            proxy_reference = role_settings.executor.runtime_proxy_reference
            vault_proxy = (
                resolver.resolve(proxy_reference) if proxy_reference is not None else None
            )
            environment_proxy = os.environ.get("HALPHA_RUNTIME_PROXY_URL")
            if (
                vault_proxy is not None
                and environment_proxy is not None
                and vault_proxy.get_secret_value() != environment_proxy
            ):
                raise ExecutorRuntimeError("RUNTIME_PROXY_SOURCES_CONFLICT")
            proxy_url = (
                environment_proxy
                if environment_proxy is not None
                else (
                    vault_proxy.get_secret_value() if vault_proxy is not None else None
                )
            )
            secret_values: list[str] = []
            if api_key is not None and api_secret is not None:
                secret_values.extend(
                    (api_key.get_secret_value(), api_secret.get_secret_value())
                )
            if database_password is not None:
                secret_values.append(database_password.get_secret_value())
            if proxy_url is not None:
                secret_values.append(proxy_url)
            logger = configure_halpha_logging(
                repo_root / settings.maintenance.log_root,
                role="executor",
                secret_values=tuple(secret_values),
            )
            paused_activations = 0
            if not read_only:
                if database_password is None:
                    raise ExecutorRuntimeError("PRODUCT_DATABASE_CREDENTIAL_REQUIRED")
                paused_activations = PostgreSQLExecutorContinuityGuard(
                    database_name=settings.release.database_name,
                    password=database_password,
                    environment_id=settings.release.environment_id,
                ).pause_open_activations(datetime.now(UTC))
            runtime = ProductExecutorRuntime(
                settings=role_settings,
                database_password=database_password,
                api_key=api_key,
                api_secret=api_secret,
                log_directory=repo_root / settings.maintenance.log_root,
                proxy_url=proxy_url,
                runtime_real_write_gate=gate_status.runtime_real_write_gate,
                live_write_activation_id=gate_status.authorized_activation_id,
                live_write_submission_guard=live_write_submission_guard,
                forward_observation_spec=observation_spec,
                observation_proposal_sink=(
                    observation.record_proposal if observation is not None else None
                ),
                observation_bar_sink=(
                    observation.record_bar if observation is not None else None
                ),
                observation_quote_sink=(
                    observation.record_quote_tick if observation is not None else None
                ),
                observation_mark_price_sink=(
                    observation.record_mark_price if observation is not None else None
                ),
            )
            try:
                runtime.build()
                if observation is not None:
                    observation.record_process_started()

                def report_ready(runtime_evidence: dict[str, object]) -> None:
                    report = {
                        "status": (
                            "B04_READ_ONLY_RUNTIME_READY"
                            if read_only
                            else "B03_RUNTIME_READY"
                        ),
                        "role": ProcessRole.EXECUTOR.value,
                        "paused_open_activations": paused_activations,
                        "source_sha256_digest": runtime_source_digest,
                        "source_file_count": len(runtime_source_sha256),
                        **runtime_evidence,
                    }
                    if observation is not None:
                        observation.record_runtime_ready(runtime_evidence)
                    print(json.dumps(report, sort_keys=True))
                    logger.info(
                        "runtime_ready",
                        profile=settings.release.profile,
                        environment_id=settings.release.environment_id,
                        paused_open_activations=paused_activations,
                        proxy_supplied=proxy_url is not None,
                        source_sha256_digest=runtime_source_digest,
                        source_file_count=len(runtime_source_sha256),
                        **runtime_evidence,
                    )

                runtime.run_until_stop(stop_event.wait, on_ready=report_ready)
                logger.info("runtime_stopped", reason_code="MAINTENANCE_STOP")
                if observation is not None:
                    observation.close(reason_code="MAINTENANCE_STOP")
            finally:
                runtime.close()
                if observation is not None:
                    observation.close(reason_code="RUNTIME_EXIT")
            return 0
    except (
        ConfigurationError,
        ExecutorContinuityUnavailable,
        ExecutorRuntimeError,
        ForwardObservationError,
        LiveWriteGateError,
        RuntimeIdentityError,
        SecretResolutionError,
        SourceIdentityError,
        WindowsRuntimeError,
    ) as exc:
        print(json.dumps({"status": "STARTUP_REJECTED", "reason": str(exc)}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
