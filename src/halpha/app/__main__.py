"""Entry point for the App process role."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from threading import Thread
from typing import Sequence

import keyring
import uvicorn

from halpha.app.secrets import resolve_app_secrets
from halpha.app.web import WebConfigurationError, create_app
from halpha.configuration import ConfigurationError, app_settings, load_settings
from halpha.operational_logging import configure_halpha_logging
from halpha.process_contract import ProcessRole, preflight
from halpha.product_build import calculate_product_build_id
from halpha.runtime_identity import RuntimeIdentityError, repository_root
from halpha.source_identity import SourceIdentityError
from halpha.winvault import SecretResolutionError
from halpha.windows_runtime import (
    WindowsRuntimeError,
    create_stop_event,
    require_process_identity,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog=ProcessRole.APP.value)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args(argv)

    try:
        settings = load_settings(args.config)
        report = preflight(ProcessRole.APP, settings)
        if args.preflight_only:
            print(json.dumps(report, sort_keys=True))
            return 0
        role_settings = app_settings(settings)
        product_build_id = calculate_product_build_id(repository_root(), settings)
        require_process_identity(role_settings.app_task_sid)
        secrets = resolve_app_secrets(role_settings, keyring.get_keyring())
        secret_values = [
            secrets.database_password.get_secret_value(),
            secrets.csrf_signing_secret.get_secret_value(),
        ]
        if secrets.smtp_password is not None:
            secret_values.append(secrets.smtp_password.get_secret_value())
        logger = configure_halpha_logging(
            repository_root() / settings.maintenance.log_root,
            role="app",
            secret_values=tuple(secret_values),
        )
        web_app = create_app(
            settings,
            secrets,
            repo_root=repository_root(),
            product_build_id=product_build_id,
        )
        gate_status = web_app.state.live_write_gate_status_provider()
        logger.info(
            "runtime_starting",
            profile=settings.release.profile,
            environment_id=settings.release.environment_id,
            configured_runtime_real_write_gate=(
                gate_status.configured_runtime_real_write_gate
            ),
            runtime_real_write_gate=gate_status.runtime_real_write_gate,
            product_build_id=product_build_id,
        )
    except (
        ConfigurationError,
        RuntimeIdentityError,
        SecretResolutionError,
        SourceIdentityError,
        WebConfigurationError,
        WindowsRuntimeError,
    ) as exc:
        print(json.dumps({"status": "STARTUP_REJECTED", "reason": str(exc)}, sort_keys=True))
        return 2

    try:
        with create_stop_event(
            name=role_settings.stop_event,
            task_sid=role_settings.app_task_sid,
            maintenance_sid=role_settings.maintenance_sid,
        ) as stop_event:
            config = uvicorn.Config(
                web_app,
                host=role_settings.app.bind,
                port=role_settings.app.port,
                workers=role_settings.app.workers,
                reload=role_settings.app.reload,
                proxy_headers=False,
                server_header=False,
                log_level="info",
            )
            server = uvicorn.Server(config)

            def wait_for_stop() -> None:
                stop_event.wait()
                server.should_exit = True

            waiter = Thread(target=wait_for_stop, name="halpha-app-stop-wait", daemon=True)
            waiter.start()
            try:
                server.run()
            finally:
                stop_event.signal()
                waiter.join(timeout=5)
                logger.info("runtime_stopped", reason_code="MAINTENANCE_STOP")
    except WindowsRuntimeError as exc:
        print(json.dumps({"status": "STARTUP_REJECTED", "reason": str(exc)}, sort_keys=True))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
