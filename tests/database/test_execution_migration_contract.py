from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "migrations" / "versions" / "20260717_0004_execution_boundaries.py"
CLIENT_ID_MIGRATION = (
    ROOT / "migrations" / "versions" / "20260717_0005_client_order_identity.py"
)
NOT_SUBMITTED_REASON_MIGRATION = (
    ROOT / "migrations" / "versions" / "20260718_0006_execution_not_submitted_reason.py"
)


def _source() -> str:
    return MIGRATION.read_text(encoding="utf-8")


def test_execution_action_identity_is_database_immutable() -> None:
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


def test_unknown_closure_and_order_identity_have_database_checks() -> None:
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


def test_not_submitted_actions_persist_a_stable_reason() -> None:
    source = NOT_SUBMITTED_REASON_MIGRATION.read_text(encoding="utf-8")
    assert 'down_revision = "20260717_0005"' in source
    assert "not_submitted_reason" in source
    assert "ck_execution_action_not_submitted_reason" in source
    assert "LEGACY_DEFINITELY_NOT_SUBMITTED" in source
    assert 'values.pop("not_submitted_reason")' in source
    assert source.index('values.pop("not_submitted_reason")') < source.index(
        'op.drop_column("execution_action", "not_submitted_reason"'
    )


def test_not_submitted_reason_downgrade_restores_the_legacy_state_digest(
    monkeypatch,
) -> None:
    spec = importlib.util.spec_from_file_location(
        "execution_not_submitted_reason_migration",
        NOT_SUBMITTED_REASON_MIGRATION,
    )
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    row = {
        "execution_action_id": "action-legacy-not-submitted",
        "environment_id": "demo-main",
        "state": "NOT_SUBMITTED",
        "state_digest": "new-state-digest",
        "not_submitted_reason": "LEGACY_DEFINITELY_NOT_SUBMITTED",
    }

    class Rows:
        def mappings(self):
            return (row,)

    class Connection:
        def __init__(self) -> None:
            self.updates = []

        def execute(self, _statement, parameters=None):
            if parameters is None:
                return Rows()
            self.updates.append(parameters)
            return None

    connection = Connection()
    operations = []
    monkeypatch.setattr(migration.op, "get_bind", lambda: connection)
    monkeypatch.setattr(
        migration.op,
        "drop_constraint",
        lambda *args, **kwargs: operations.append(("constraint", args, kwargs)),
    )
    monkeypatch.setattr(
        migration.op,
        "drop_column",
        lambda *args, **kwargs: operations.append(("column", args, kwargs)),
    )

    migration.downgrade()

    legacy_values = dict(row)
    legacy_values.pop("state_digest")
    legacy_values.pop("not_submitted_reason")
    assert connection.updates == [
        {
            "state_digest": migration._digest(legacy_values),
            "execution_action_id": row["execution_action_id"],
            "environment_id": row["environment_id"],
        }
    ]
    assert [item[0] for item in operations] == ["constraint", "column"]
