from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "migrations" / "versions" / "20260717_0004_b03_execution_boundaries.py"
CLIENT_ID_MIGRATION = (
    ROOT / "migrations" / "versions" / "20260717_0005_b03_client_order_identity.py"
)


def _source() -> str:
    return MIGRATION.read_text(encoding="utf-8")


def test_b03_execution_action_identity_is_database_immutable() -> None:
    source = _source()
    assert 'down_revision = "20260717_0003"' in source
    assert "guard_execution_action_identity_immutable" in source
    assert "trg_execution_action_identity_immutable" in source
    for field in (
        "environment_id",
        "authority_class",
        "execution_profile_ref",
        "account_ref",
        "activation_id",
        "plan_event_ref",
        "source_identity",
        "action_terms_digest",
        "client_order_id",
    ):
        assert f"NEW.{field}" in source
        assert f"OLD.{field}" in source


def test_b03_unknown_closure_and_order_identity_have_database_checks() -> None:
    source = _source()
    assert "ck_execution_action_order_identity" in source
    assert "ck_execution_action_unknown_evidence" in source
    assert "ck_execution_action_closure_evidence" in source
    assert "ck_execution_action_time_order" in source


def test_venue_fact_is_append_only_for_executor_and_table_owner() -> None:
    source = _source()
    assert "guard_venue_fact_append_only" in source
    assert "BEFORE UPDATE OR DELETE ON halpha.venue_fact" in source
    assert "REVOKE UPDATE, DELETE ON TABLE halpha.venue_fact" in source
    assert "ck_venue_fact_source_identity" in source
    assert "ck_venue_fact_time_order" in source


def test_client_order_uuid_is_unique_inside_each_environment() -> None:
    source = CLIENT_ID_MIGRATION.read_text(encoding="utf-8")
    assert 'down_revision = "20260717_0004"' in source
    assert "uq_execution_action_client_order_identity" in source
    assert '("environment_id", "client_order_id")' in source
    assert 'postgresql_where=sa.text("client_order_id IS NOT NULL")' in source
