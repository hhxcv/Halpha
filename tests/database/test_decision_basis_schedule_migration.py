from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = (
    ROOT
    / "migrations"
    / "versions"
    / "20260723_0011_decision_basis_and_order_schedule.py"
)


def test_decision_basis_schedule_migration_is_linear_and_adds_no_record_family() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    assert 'revision = "20260723_0011"' in source
    assert 'down_revision = "20260721_0010"' in source
    assert "op.create_table(" not in source
    assert "RENAME COLUMN strategy_definition_ref TO decision_basis_ref" in source
    assert "RENAME COLUMN fixed_strategy_basis TO fixed_decision_basis" in source
    assert "RENAME COLUMN strategy_id TO decision_basis_ref" in source


def test_decision_basis_schedule_migration_persists_paired_json_snapshots() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    for column in (
        "order_schedule_spec",
        "order_schedule_spec_digest",
        "order_schedule_snapshot",
        "order_schedule_snapshot_digest",
    ):
        assert f'Column("{column}"' in source
    assert "ck_trade_plan_version_schedule_pair" in source
    assert "ck_trade_plan_version_schedule_digest" in source
    assert "ck_plan_activation_schedule_pair" in source
    assert "ck_plan_activation_schedule_digest" in source
    assert "ck_trade_plan_version_decision_basis_consistency" in source
    assert "ck_trade_plan_version_direct_schedule" in source
    assert "ck_plan_activation_direct_schedule" in source
    assert "= (order_schedule_spec IS NOT NULL)" in source
    assert "= (order_schedule_snapshot IS NOT NULL)" in source


def test_decision_basis_schedule_downgrade_refuses_direct_execution_facts() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    assert "fixed_decision_basis->>'kind' = 'DIRECT_EXECUTION'" in source
    assert "cannot downgrade decision basis or order schedule facts" in source
    assert "content ? 'decision_basis' OR content ? 'order_schedule_spec'" in source
    assert "fixed_decision_basis - 'kind' - 'decision_basis_ref'" in source
