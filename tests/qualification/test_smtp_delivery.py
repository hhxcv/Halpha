from __future__ import annotations

from tools.qualification.verify_smtp_delivery import classify_smtp_evidence


def _ready_checks() -> dict[str, bool]:
    return {
        "runtime_config_exists": True,
        "demo_profile_selected": True,
        "email_delivery_enabled": True,
        "route_configuration_complete": True,
        "smtp_secret_present": True,
        "starttls_required": True,
        "explicit_send_requested": True,
        "smtp_transport_accepted_message": True,
        "business_state_unchanged": True,
        "no_venue_write_performed": True,
    }


def test_smtp_evidence_requires_readiness_explicit_send_and_acceptance() -> None:
    checks = _ready_checks()
    assert (
        classify_smtp_evidence(checks, send_requested=True, delivery_attempted=True)
        == "QUALIFIED"
    )
    assert (
        classify_smtp_evidence(checks, send_requested=False, delivery_attempted=False)
        == "IN_PROGRESS"
    )
    checks["smtp_secret_present"] = False
    assert (
        classify_smtp_evidence(checks, send_requested=True, delivery_attempted=False)
        == "IN_PROGRESS"
    )
    checks["smtp_secret_present"] = True
    checks["smtp_transport_accepted_message"] = False
    assert (
        classify_smtp_evidence(checks, send_requested=True, delivery_attempted=True)
        == "REJECTED"
    )
