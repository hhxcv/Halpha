from __future__ import annotations

import json

from halpha.external_services import read_external_service_registrations


def test_registry_reads_valid_records_and_reports_invalid_records(tmp_path) -> None:
    (tmp_path / "valid.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "service_id": "sample-monitor-8766",
                "pid": 123,
                "listeners": ["127.0.0.1:8766"],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "invalid.json").write_text("{}", encoding="utf-8")

    registrations, warnings = read_external_service_registrations(tmp_path)

    assert len(registrations) == 1
    assert registrations[0].service_id == "sample-monitor-8766"
    assert registrations[0].pid == 123
    assert registrations[0].listeners == ("127.0.0.1:8766",)
    assert len(warnings) == 1
    assert warnings[0].startswith("EXTERNAL_REGISTRATION_INVALID:invalid.json:")


def test_registry_rejects_duplicate_service_ids(tmp_path) -> None:
    registration = {
        "schema_version": 1,
        "service_id": "sample-monitor-8766",
        "pid": 123,
        "listeners": ["127.0.0.1:8766"],
    }
    (tmp_path / "a.json").write_text(json.dumps(registration), encoding="utf-8")
    (tmp_path / "b.json").write_text(json.dumps(registration), encoding="utf-8")

    registrations, warnings = read_external_service_registrations(tmp_path)

    assert len(registrations) == 1
    assert warnings == (
        "EXTERNAL_REGISTRATION_DUPLICATE:sample-monitor-8766",
    )
