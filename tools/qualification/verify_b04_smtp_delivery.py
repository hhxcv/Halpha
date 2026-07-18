"""Qualify one actual SMTP acceptance without changing trading business state."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path
import sys
from typing import Any, Sequence

import keyring


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from halpha.app.notifications import (
    NotificationContent,
    NotificationDeliveryError,
    StdlibSMTPTransport,
)
from halpha.configuration import app_settings, load_settings, settings_digest
from halpha.winvault import SecretResolutionError, app_secret_resolver, require_win_vault_backend


DEFAULT_OUTPUT = ROOT / "build/qualification/b04-smtp-delivery.json"


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def classify_smtp_evidence(
    checks: dict[str, bool],
    *,
    send_requested: bool,
    delivery_attempted: bool,
) -> str:
    readiness_names = {
        "runtime_config_exists",
        "demo_profile_selected",
        "email_delivery_enabled",
        "route_configuration_complete",
        "smtp_secret_present",
        "starttls_required",
    }
    readiness = all(checks.get(name) is True for name in readiness_names)
    if not readiness or not send_requested:
        return "IN_PROGRESS"
    if delivery_attempted and all(checks.values()):
        return "QUALIFIED"
    return "REJECTED"


def verify(
    root: Path,
    *,
    config_path: Path,
    send: bool,
) -> dict[str, Any]:
    root = root.resolve()
    config_path = config_path.resolve()
    checks: dict[str, bool] = {
        "runtime_config_exists": config_path.is_file(),
        "demo_profile_selected": False,
        "email_delivery_enabled": False,
        "route_configuration_complete": False,
        "smtp_secret_present": False,
        "starttls_required": False,
        "explicit_send_requested": send,
        "smtp_transport_accepted_message": False,
        "business_state_unchanged": True,
        "no_venue_write_performed": True,
    }
    observations: dict[str, Any] = {
        "recipient_route_ref": "owner-primary-email",
        "delivery_attempted": False,
        "business_state_changed": False,
        "venue_write_performed": False,
    }
    errors: list[str] = []
    configuration_digest: str | None = None
    settings = None
    smtp_password = None

    if checks["runtime_config_exists"]:
        try:
            settings = load_settings(config_path)
            email = settings.email
            checks.update(
                {
                    "demo_profile_selected": settings.release.profile == "BINANCE_DEMO",
                    "email_delivery_enabled": email.delivery_enabled,
                    "route_configuration_complete": all(
                        (
                            email.smtp_host,
                            email.smtp_username,
                            email.sender,
                            email.owner_recipient,
                        )
                    ),
                    "starttls_required": email.require_starttls is True,
                }
            )
            configuration_digest = settings_digest(settings)
            if email.delivery_enabled:
                backend = keyring.get_keyring()
                require_win_vault_backend(backend)
                resolver = app_secret_resolver(backend, app_settings(settings))
                try:
                    smtp_password = resolver.resolve(
                        settings.app.smtp_credential_reference
                    )
                except SecretResolutionError:
                    smtp_password = None
                checks["smtp_secret_present"] = smtp_password is not None
        except Exception as exc:
            errors.append(f"SMTP_READINESS_FAILED:{type(exc).__name__}")

    ready = all(
        checks[name]
        for name in (
            "runtime_config_exists",
            "demo_profile_selected",
            "email_delivery_enabled",
            "route_configuration_complete",
            "smtp_secret_present",
            "starttls_required",
        )
    )
    if ready and send and settings is not None and smtp_password is not None:
        observations["delivery_attempted"] = True
        try:
            observed_at = datetime.now(UTC)
            StdlibSMTPTransport(settings.email, smtp_password).send(
                recipient=str(settings.email.owner_recipient),
                content=NotificationContent(
                    subject="Halpha B04 actual SMTP qualification",
                    body=(
                        "Halpha B04 actual SMTP qualification message.\n"
                        f"Environment: {settings.release.environment_id}\n"
                        f"Observed at: {observed_at.isoformat()}\n"
                        "No trading command, capital authorization, or venue write is included."
                    ),
                ),
            )
            checks["smtp_transport_accepted_message"] = True
            observations["accepted_at"] = observed_at.isoformat().replace("+00:00", "Z")
        except NotificationDeliveryError as exc:
            errors.append(f"SMTP_DELIVERY_FAILED:{str(exc)}")
        finally:
            smtp_password = None

    status = classify_smtp_evidence(
        checks,
        send_requested=send,
        delivery_attempted=bool(observations["delivery_attempted"]),
    )
    evidence: dict[str, Any] = {
        "schema_version": 1,
        "stage": "B04_ACTUAL_SMTP_DELIVERY",
        "observed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "status": status,
        "checks": checks,
        "observations": observations,
        "configuration_digest": configuration_digest,
        "source_sha256": {
            "src/halpha/app/notifications.py": _sha256_file(
                root / "src/halpha/app/notifications.py"
            ),
            "tools/qualification/verify_b04_smtp_delivery.py": _sha256_file(
                root / "tools/qualification/verify_b04_smtp_delivery.py"
            ),
        },
        "scope": "ACTUAL_SMTP_ACCEPTANCE_ONLY_NO_DATABASE_OR_VENUE_WRITE",
        "errors": errors,
        "superseded_by": None,
    }
    evidence["evidence_digest"] = sha256(_canonical(evidence)).hexdigest()
    return evidence


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, default=ROOT)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--send", action="store_true")
    args = parser.parse_args(argv)
    root = args.repository_root.resolve()
    output = args.output.resolve()
    if not output.is_relative_to(root):
        raise RuntimeError("B04_SMTP_OUTPUT_OUTSIDE_REPOSITORY")
    evidence = verify(root, config_path=args.config, send=args.send)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(f"{output.suffix}.tmp")
    temporary.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    temporary.replace(output)
    print(json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if evidence["status"] in {"IN_PROGRESS", "QUALIFIED"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
