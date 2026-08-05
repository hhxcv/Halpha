from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = (
    ROOT
    / "migrations"
    / "versions"
    / "20260803_0012_venue_fact_hot_path_indexes.py"
)


def _revision_module():
    spec = importlib.util.spec_from_file_location(
        "halpha_venue_fact_hot_path_indexes",
        MIGRATION,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_upgrade_adds_bounded_hot_path_indexes(monkeypatch) -> None:
    revision = _revision_module()
    created: list[tuple[tuple[object, ...], dict[str, object]]] = []
    monkeypatch.setattr(
        revision.op,
        "create_index",
        lambda *args, **kwargs: created.append((args, kwargs)),
    )

    revision.upgrade()

    assert [item[0][0] for item in created] == [
        "ix_venue_fact_action_timeline",
        "ix_venue_fact_account_state_latest",
        "ix_venue_fact_trade_identity_timeline",
    ]
    assert created[0][0][2] == (
        "environment_id",
        "action_ref",
        "cutoff",
        "received_at",
        "venue_fact_id",
    )
    assert str(created[0][1]["postgresql_where"]) == "action_ref IS NOT NULL"
    assert created[1][0][2][:2] == ("environment_id", "account_ref")
    predicate = str(created[1][1]["postgresql_where"])
    assert "kind = 'ACCOUNT_STATE'" in predicate
    assert "source_class = 'VENUE_QUERY'" in predicate
    assert created[2][0][2] == (
        "environment_id",
        "kind",
        "source_object_id",
        "account_ref",
        "instrument_ref",
        "received_at",
        "venue_fact_id",
    )
    assert str(created[2][1]["postgresql_where"]) == (
        "kind IN ('FILL', 'COMMISSION')"
    )


def test_downgrade_removes_only_the_three_added_indexes(monkeypatch) -> None:
    revision = _revision_module()
    dropped: list[tuple[tuple[object, ...], dict[str, object]]] = []
    monkeypatch.setattr(
        revision.op,
        "drop_index",
        lambda *args, **kwargs: dropped.append((args, kwargs)),
    )

    revision.downgrade()

    assert [item[0][0] for item in dropped] == [
        "ix_venue_fact_trade_identity_timeline",
        "ix_venue_fact_account_state_latest",
        "ix_venue_fact_action_timeline",
    ]
    assert all(item[1] == {"table_name": "venue_fact", "schema": "halpha"} for item in dropped)
