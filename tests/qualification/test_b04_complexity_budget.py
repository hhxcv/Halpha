from __future__ import annotations

from pathlib import Path

from tools.qualification.verify_b04_complexity_budget import build_evidence


ROOT = Path(__file__).resolve().parents[2]


def test_current_p0_implementation_stays_within_the_accepted_complexity_budget() -> None:
    evidence = build_evidence(ROOT)
    assert evidence["status"] == "QUALIFIED", evidence["errors"]
    observations = evidence["observations"]
    assert observations["physical_record_family_count"] == 16
    assert observations["business_modules"] == [
        "capital",
        "outcomes",
        "planning",
        "user_workbench",
        "venue_integration",
    ]
    assert observations["authoritative_database_products"] == ["PostgreSQL 17.10"]
    assert observations["real_venue_write_pipelines"] == [
        "venue_integration/nautilus_client.py:NautilusVenueExecutionClient"
    ]
    assert observations["live_read_only_topology"] == {
        "product_process": "halpha-executor",
        "data_client_count": 1,
        "binance_credential_count": 0,
        "instrument_commission_query_enabled": False,
        "execution_client_count": 0,
        "execution_reconciliation_enabled": False,
        "new_persistent_worker_count": 0,
        "new_record_family_count": 0,
        "new_write_pipeline_count": 0,
    }
